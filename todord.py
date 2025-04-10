#!/usr/bin/env python3
"""Todord - A Discord To-Do List Bot.

This script implements a Discord bot that helps manage to-do lists in Discord channels.
"""

import argparse
import json
import logging
import os
import sys
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import re

import discord
from discord.ext import commands
from discord import errors as discord_errors
from aiohttp import client_exceptions

# Application information from environment variables
APP_NAME = os.getenv("TODORD_APP_NAME", "todord")
APP_VERSION = os.getenv("TODORD_APP_VERSION", "dev")

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("todord")


# Constants
class TaskEvent:
    """Constants for task events."""

    CREATED = "task_created"
    STATUS_UPDATED = "task_status_updated"
    LOG_ADDED = "task_log_added"
    TITLE_EDITED = "task_title_edited"


# Exceptions
class TodordError(Exception):
    """Base exception for Todord errors."""

    pass


# Utility Functions
def create_embed(ctx, title, description, color):
    """Create a standardized Discord embed."""
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=f"Requested by {ctx.author.name}")
    return embed


class Task:
    """Represents a task in a to-do list."""

    def __init__(
        self,
        ctx: commands.Context,
        id: int,
        title: str,
        status: str,
        logs: Optional[List[str]] = None,
        creator: Optional[str] = None,
    ) -> None:
        self.id: int = id
        self.title: str = title
        self.status: str = status
        self.logs: List[str] = logs or []
        self.internal_logs: List[Tuple[str, str, str]] = []  # (timestamp, user, log)
        self.creator: str = creator or ctx.author.name
        self.add_internal_log(ctx, TaskEvent.CREATED)

    def add_internal_log(
        self, ctx: commands.Context, log: str, extra_info: str = ""
    ) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user = ctx.author.name
        action = log if not extra_info else f"{log}: {extra_info}"
        self.internal_logs.append((timestamp, user, action))

    def add_log(self, ctx: commands.Context, log: str) -> None:
        self.logs.append(log)
        self.add_internal_log(
            ctx, TaskEvent.LOG_ADDED, f"'{log[:30]}{'...' if len(log) > 30 else ''}'"
        )

    def set_status(self, ctx: commands.Context, status: str) -> None:
        old_status = self.status
        self.status = status
        self.add_internal_log(
            ctx, TaskEvent.STATUS_UPDATED, f"from '{old_status}' to '{status}'"
        )

    def set_title(self, ctx: commands.Context, title: str) -> None:
        old_title = self.title
        self.title = title
        self.add_internal_log(
            ctx,
            TaskEvent.TITLE_EDITED,
            f"from '{old_title[:30]}{'...' if len(old_title) > 30 else ''}' to '{title[:30]}{'...' if len(title) > 30 else ''}'",
        )

    def show_details(self) -> str:
        details = [f"**[{self.status}] {self.title}**"]
        details.append(f"Created by: {self.creator}")

        # Add task logs if any
        if self.logs:
            details.append("\n**Logs:**")
            for i, log in enumerate(self.logs, 1):
                details.append(f"{i}. {log}")

        # Add history from internal logs
        if self.internal_logs:
            details.append("\n**History:**")
            for timestamp, user, action in self.internal_logs:
                # Extract the basic action type
                action_type = action.split(":", 1)[0] if ":" in action else action
                action_details = (
                    action.split(":", 1)[1].strip() if ":" in action else ""
                )

                # Convert action code to readable text
                readable_action = action_type
                if action_type == TaskEvent.CREATED:
                    readable_action = "Created task"
                elif action_type == TaskEvent.STATUS_UPDATED:
                    readable_action = f"Updated status {action_details}"
                elif action_type == TaskEvent.LOG_ADDED:
                    readable_action = f"Added log {action_details}"
                elif action_type == TaskEvent.TITLE_EDITED:
                    readable_action = f"Edited title {action_details}"

                details.append(f"• {timestamp} - {user}: {readable_action}")

        return "\n".join(details)

    def __str__(self) -> str:
        return f"**[{self.status}] {self.title}**"


class StorageManager:
    """Manages task persistence."""

    def __init__(self, data_dir: Union[str, Path], session_id: str) -> None:
        self.data_dir = Path(data_dir)
        self.session_id = session_id
        self.todo_lists: Dict[int, List[Task]] = {}  # channel_id -> [Task, Task, ...]
        # Regex to validate save file names: APP_NAME_SESSIONID_YYYY-MM-DD_HH-MM-SS.json
        self.filename_pattern = re.compile(
            rf"^{re.escape(APP_NAME)}_.+_[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}_[0-9]{{2}}-[0-9]{{2}}-[0-9]{{2}}\.json$"
        )

        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True)
            logger.info(f"Created data directory: {self.data_dir}")

    async def save(self, ctx: Optional[commands.Context] = None) -> str:
        current_time = datetime.now()
        filename = f"{APP_NAME}_{self.session_id}_{current_time.strftime('%Y-%m-%d_%H-%M-%S')}.json"
        filepath = self.data_dir / filename

        with open(filepath, "w") as f:
            json.dump(self.todo_lists, f, default=lambda o: o.__dict__, indent=2)

        return filename

    async def load(self, ctx: commands.Context, filename: str) -> bool:
        # Validate filename format
        if not self.filename_pattern.match(filename):
            logger.error(
                f"Attempted to load file with invalid format: {filename}. "
                f"Expected format: {APP_NAME}_<session_id>_<YYYY-MM-DD_HH-MM-SS>.json"
            )
            return False

        try:
            filepath = self.data_dir / filename
            with open(filepath, "r") as f:
                data = json.load(f)

            reconstructed_todo_lists: Dict[int, List[Task]] = {}

            for channel_id, tasks in data.items():
                channel_id_int = int(
                    channel_id
                )  # JSON keys are strings, convert back to int
                reconstructed_todo_lists[channel_id_int] = []

                for task_data in tasks:
                    task = Task(
                        ctx,
                        task_data["id"],
                        task_data["title"],
                        task_data["status"],
                        task_data.get("logs", []),
                        task_data.get("creator", "Unknown"),
                    )

                    if "internal_logs" in task_data:
                        task.internal_logs = task_data["internal_logs"]

                    reconstructed_todo_lists[channel_id_int].append(task)

            self.todo_lists = reconstructed_todo_lists
            return True

        except Exception as e:
            logger.error(f"Error loading todo lists: {e}")
            return False

    def list_saved_files(self) -> List[str]:
        valid_files = []
        for f in os.listdir(self.data_dir):
            if self.filename_pattern.match(f):
                valid_files.append(f)

        # Sort files based on the timestamp in the filename (YYYY-MM-DD_HH-MM-SS)
        # which is the 19 characters before ".json"
        valid_files.sort(key=lambda x: x[-24:-5])
        return valid_files


class CustomHelpCommand(commands.HelpCommand):
    """Custom help command implementation for better readability."""

    def __init__(self):
        super().__init__(
            command_attrs={
                "help": "Shows the bot's commands and their descriptions",
                "cooldown": commands.CooldownMapping.from_cooldown(
                    1, 3.0, commands.BucketType.member
                ),
            }
        )

    async def send_bot_help(self, mapping):
        embed = discord.Embed(
            title="!help command:",
            color=discord.Color.blue(),
        )

        for cog, cmds in mapping.items():
            # Filter commands that can be run
            filtered = await self.filter_commands(cmds, sort=True)
            if filtered:
                name = getattr(cog, "qualified_name", "Other Commands")

                cog_description = ""
                if cog and cog.description:
                    cog_description = f"{cog.description}\n"

                # Create command list for this category
                command_list = []
                for command in filtered:
                    name_with_aliases = f"`!{command.name}`"
                    if command.aliases:
                        aliases = ", ".join(f"`!{alias}`" for alias in command.aliases)
                        name_with_aliases = f"{name_with_aliases}\t{aliases}"

                    usage = f"`!{command.name}"
                    if command.signature:
                        usage += f" {command.signature}"
                    usage += "`"

                    # Add usage above command description
                    command_list.append(
                        f"**{name_with_aliases}**\u00a0\u00a0\u00a0{command.short_doc}\n> Usage: {usage}\n"
                    )

                if command_list:
                    # add an embed field to give space for the cog title and desc
                    embed.add_field(
                        name="\n",
                        value="\n",
                        inline=False,
                    )
                    embed.add_field(
                        name=f"📋 **{name}** - {cog_description}",
                        value=f"{'---' * 25}\n" + "\n".join(command_list),
                        inline=False,
                    )

        embed.set_footer(text="Type !help <command> for detailed info on a command.")

        await self.get_destination().send(embed=embed)

    async def send_command_help(self, command):
        embed = discord.Embed(
            title=f"Command: !{command.name}", color=discord.Color.green()
        )

        # Add aliases if any
        if command.aliases:
            aliases = ", ".join(f"`!{alias}`" for alias in command.aliases)
            embed.add_field(name="Aliases", value=aliases, inline=False)

        if command.help:
            embed.add_field(name="Description", value=command.help, inline=False)

        usage = f"`!{command.name}"
        if command.signature:
            usage += f" {command.signature}"
        usage += "`"

        embed.add_field(name="Usage", value=usage, inline=False)

        await self.get_destination().send(embed=embed)

    async def send_cog_help(self, cog):
        embed = discord.Embed(
            title=f"Category: {cog.qualified_name}",
            description=cog.description or "No description provided.",
            color=discord.Color.gold(),
        )

        filtered = await self.filter_commands(cog.get_commands(), sort=True)

        for command in filtered:
            name_with_aliases = f"`!{command.name}`"
            if command.aliases:
                aliases = ", ".join(f"`!{alias}`" for alias in command.aliases)
                name_with_aliases = f"{name_with_aliases} (aliases: {aliases})"

            embed.add_field(
                name=name_with_aliases,
                value=command.short_doc or "No description provided.",
                inline=False,
            )

        await self.get_destination().send(embed=embed)

    async def send_error_message(self, error):
        embed = discord.Embed(
            title="Error", description=error, color=discord.Color.red()
        )
        await self.get_destination().send(embed=embed)


# Command Cogs
class TodoList(commands.Cog):
    """Task management commands."""

    def __init__(self, bot: commands.Bot, storage: StorageManager) -> None:
        self.bot = bot
        self.storage = storage

    @commands.command(
        name="add",
        aliases=["a"],
        help="Add new task to the channel's to-do list.",
    )
    async def add_task(self, ctx: commands.Context, *, task: str) -> None:
        channel_id = ctx.channel.id

        if channel_id not in self.storage.todo_lists:
            self.storage.todo_lists[channel_id] = []

        task_id = len(self.storage.todo_lists[channel_id])
        new_task = Task(ctx, task_id, task, "pending", [])
        self.storage.todo_lists[channel_id].append(new_task)

        embed = create_embed(
            ctx, "✅ Task Added", f"**{new_task.title}**", discord.Color.green()
        )
        await ctx.reply(embed=embed)
        await self.storage.save(ctx)

    @commands.command(
        name="list",
        aliases=["ls", "l"],
        help="List all tasks for this channel.",
    )
    async def list_tasks(self, ctx: commands.Context) -> None:
        channel_id = ctx.channel.id
        tasks = self.storage.todo_lists.get(channel_id, [])

        if not tasks:
            embed = create_embed(
                ctx,
                "ℹ️ Info",
                "There are no tasks in this channel's to-do list.",
                discord.Color.blue(),
            )
            await ctx.reply(embed=embed)
            return

        response = ""
        for idx, task in enumerate(tasks, start=1):
            response += f"{idx}. {task}\n"

        embed = create_embed(
            ctx, "📋 Channel To-Do List", response, discord.Color.blue()
        )
        await ctx.reply(embed=embed)

    @commands.command(
        name="done",
        aliases=["d"],
        help="Mark task as done and remove it from list.",
    )
    async def done_task(self, ctx: commands.Context, task_number: int) -> None:
        channel_id = ctx.channel.id
        tasks = self.storage.todo_lists.get(channel_id, [])

        if not tasks:
            embed = create_embed(
                ctx,
                "ℹ️ Info",
                "There are no tasks in this channel's to-do list.",
                discord.Color.blue(),
            )
            await ctx.reply(embed=embed)
            return

        if 0 < task_number <= len(tasks):
            removed = tasks.pop(task_number - 1)
            removed.set_status(ctx, "done")

            embed = create_embed(
                ctx, "✔️ Task Marked as Done", f"**{removed}**", discord.Color.green()
            )
            await ctx.reply(embed=embed)
            await self.storage.save(ctx)
        else:
            embed = create_embed(
                ctx,
                "❌ Error",
                f"Invalid task number: {task_number}. Use `!list` to see valid numbers.",
                discord.Color.red(),
            )
            await ctx.reply(embed=embed)

    @commands.command(
        name="close",
        aliases=["c"],
        help="Close a task without completing and remove from list.",
    )
    async def close_task(self, ctx: commands.Context, task_number: int) -> None:
        channel_id = ctx.channel.id
        tasks = self.storage.todo_lists.get(channel_id, [])

        if not tasks:
            embed = create_embed(
                ctx,
                "ℹ️ Info",
                "There are no tasks in this channel's to-do list.",
                discord.Color.blue(),
            )
            await ctx.reply(embed=embed)
            return

        if 0 < task_number <= len(tasks):
            removed = tasks.pop(task_number - 1)
            removed.set_status(ctx, "closed")

            embed = create_embed(
                ctx,
                "✖️ Task Closed",
                f"**{removed}**",
                discord.Color.orange(),
            )
            await ctx.reply(embed=embed)
            await self.storage.save(ctx)
        else:
            embed = create_embed(
                ctx,
                "❌ Error",
                f"Invalid task number: {task_number}. Use `!list` to see valid numbers.",
                discord.Color.red(),
            )
            await ctx.reply(embed=embed)

    @commands.command(
        name="log",
        aliases=["lg"],
        help="Add a progress note or comment to an existing task.",
    )
    async def log_task(
        self, ctx: commands.Context, task_number: int, *, log: str
    ) -> None:
        channel_id = ctx.channel.id
        tasks = self.storage.todo_lists.get(channel_id, [])

        if not tasks:
            embed = create_embed(
                ctx,
                "ℹ️ Info",
                "There are no tasks in this channel's to-do list.",
                discord.Color.blue(),
            )
            await ctx.reply(embed=embed)
            return

        if 0 < task_number <= len(tasks):
            task = tasks[task_number - 1]
            task.add_log(ctx, log)

            embed = create_embed(
                ctx,
                f"📝 Log Added to Task #{task_number}",
                f"Log: '{log}'\n\n**Current Task Details:**\n{task.show_details()}",
                discord.Color.green(),
            )
            await ctx.reply(embed=embed)
            await self.storage.save(ctx)
        else:
            embed = create_embed(
                ctx,
                "❌ Error",
                f"Invalid task number: {task_number}. Use `!list` to see valid numbers.",
                discord.Color.red(),
            )
            await ctx.reply(embed=embed)

    @commands.command(
        name="details",
        aliases=["det"],
        help="Show details of a task.",
    )
    async def details_task(self, ctx: commands.Context, task_number: int) -> None:
        channel_id = ctx.channel.id
        tasks = self.storage.todo_lists.get(channel_id, [])

        if not tasks:
            embed = create_embed(
                ctx,
                "ℹ️ Info",
                "There are no tasks in this channel's to-do list.",
                discord.Color.blue(),
            )
            await ctx.reply(embed=embed)
            return

        if 0 < task_number <= len(tasks):
            task = tasks[task_number - 1]
            details = task.show_details()

            embed = create_embed(
                ctx, f"🔍 Task #{task_number} Details", details, discord.Color.blue()
            )
            await ctx.reply(embed=embed)
        else:
            embed = create_embed(
                ctx,
                "❌ Error",
                f"Invalid task number: {task_number}. Use `!list` to see valid numbers.",
                discord.Color.red(),
            )
            await ctx.reply(embed=embed)

    @commands.command(
        name="edit",
        aliases=["e"],
        help="Change the title of an existing task.",
    )
    async def edit_task(
        self, ctx: commands.Context, task_number: int, *, new_title: str
    ) -> None:
        channel_id = ctx.channel.id
        tasks = self.storage.todo_lists.get(channel_id, [])

        if not tasks:
            embed = create_embed(
                ctx,
                "ℹ️ Info",
                "There are no tasks in this channel's to-do list.",
                discord.Color.blue(),
            )
            await ctx.reply(embed=embed)
            return

        if 0 < task_number <= len(tasks):
            task = tasks[task_number - 1]
            old_title = task.title
            task.set_title(ctx, new_title)

            embed = create_embed(
                ctx,
                "✏️ Task Edited",
                f"Task #{task_number} title changed:\n**From:** {old_title}\n**To:** {new_title}",
                discord.Color.green(),
            )
            await ctx.reply(embed=embed)
            await self.storage.save(ctx)
        else:
            embed = create_embed(
                ctx,
                "❌ Error",
                f"Invalid task number: {task_number}. Use `!list` to see valid numbers.",
                discord.Color.red(),
            )
            await ctx.reply(embed=embed)


class BotManagement(commands.Cog):
    """Administrative Bot commands."""

    def __init__(self, bot: commands.Bot, storage: StorageManager) -> None:
        self.bot = bot
        self.storage = storage

    @commands.command(
        name="clear",
        aliases=["clr"],
        help="Remove current channel's state.",
    )
    async def clear_tasks(self, ctx: commands.Context) -> None:
        channel_id = ctx.channel.id

        if (
            channel_id in self.storage.todo_lists
            and self.storage.todo_lists[channel_id]
        ):
            self.storage.todo_lists[channel_id] = []
            embed = create_embed(
                ctx,
                "🗑️ List Cleared",
                "The channel's to-do list has been cleared.",
                discord.Color.orange(),  # Using orange for potentially destructive actions
            )
            await ctx.reply(embed=embed)
            await self.storage.save(ctx)
        else:
            embed = create_embed(
                ctx,
                "ℹ️ Info",
                "There are no tasks in this channel's to-do list to clear.",
                discord.Color.blue(),
            )
            await ctx.reply(embed=embed)

    @commands.command(
        name="save",
        aliases=["s"],
        help="Manually save the current state to a file.",
    )
    async def save_command(self, ctx: commands.Context) -> None:
        try:
            filename = await self.storage.save(ctx)
            embed = create_embed(
                ctx,
                "💾 Lists Saved",
                f"The to-do lists have been saved to `{filename}`.",
                discord.Color.green(),
            )
            await ctx.reply(embed=embed)
        except Exception as e:
            logger.error(f"Error during save command: {e}", exc_info=True)
            embed = create_embed(
                ctx,
                "❌ Error Saving",
                f"An error occurred while saving the lists: {e}",
                discord.Color.red(),
            )
            await ctx.reply(embed=embed)

    @commands.command(
        name="load",
        aliases=["ld"],
        help="Load state from a previously saved file.",
    )
    async def load_command(self, ctx: commands.Context, filename: str) -> None:
        # Basic validation to prevent path traversal
        if ".." in filename or "/" in filename:
            embed = create_embed(
                ctx,
                "❌ Invalid Filename",
                "Invalid characters detected in filename.",
                discord.Color.red(),
            )
            await ctx.reply(embed=embed)
            return

        # Validate filename format using the regex from StorageManager
        if not self.storage.filename_pattern.match(filename):
            embed = create_embed(
                ctx,
                "❌ Invalid Filename Format",
                f"Filename '{filename}' does not match the expected format: "
                f"`{APP_NAME}_<session_id>_<YYYY-MM-DD_HH-MM-SS>.json`",
                discord.Color.red(),
            )
            await ctx.reply(embed=embed)
            return

        success = await self.storage.load(ctx, filename)
        if success:
            embed = create_embed(
                ctx,
                "📂 Lists Loaded",
                f"Successfully loaded to-do lists from `{filename}`.",
                discord.Color.green(),
            )
            await ctx.reply(embed=embed)
        else:
            embed = create_embed(
                ctx,
                "❌ Error Loading",
                f"Failed to load lists from `{filename}`. Check the filename and ensure it's a valid save file.",
                discord.Color.red(),
            )
            await ctx.reply(embed=embed)

    @commands.command(
        name="loadlast",
        aliases=["ll"],
        help="Load the most recently state saved in file.",
    )
    async def loadlast_command(self, ctx: commands.Context) -> None:
        files = self.storage.list_saved_files()

        if not files:
            embed = create_embed(
                ctx,
                "ℹ️ No Files Found",
                "No saved to-do list files found.",
                discord.Color.blue(),
            )
            await ctx.send(embed=embed)
            return

        # Files are already sorted by creation time, so the last one is the most recent
        most_recent_file = files[-1]

        success = await self.storage.load(ctx, most_recent_file)
        if success:
            embed = create_embed(
                ctx,
                "📂 Last List Loaded",
                f"Successfully loaded the most recent lists from `{most_recent_file}`.",
                discord.Color.green(),
            )
            await ctx.send(embed=embed)
        else:
            embed = create_embed(
                ctx,
                "❌ Error Loading",
                f"Failed to load the most recent lists from `{most_recent_file}`. The file might be corrupted.",
                discord.Color.red(),
            )
            await ctx.send(embed=embed)

    @commands.command(
        name="list_files",
        aliases=["lf"],
        help="Show all states in files that can be loaded.",
    )
    async def list_files_command(self, ctx: commands.Context) -> None:
        try:
            files = self.storage.list_saved_files()
            if files:
                # Format files nicely, potentially with numbering
                files_list = "\n".join([f"{i + 1}. `{f}`" for i, f in enumerate(files)])
                embed = create_embed(
                    ctx, "📄 Available Save Files", files_list, discord.Color.blue()
                )
                await ctx.send(embed=embed)
            else:
                embed = create_embed(
                    ctx,
                    "ℹ️ No Files Found",
                    "No saved to-do list files found.",
                    discord.Color.blue(),
                )
                await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"Error listing files: {e}", exc_info=True)
            embed = create_embed(
                ctx,
                "❌ Error Listing Files",
                f"An error occurred while listing saved files: {e}",
                discord.Color.red(),
            )
            await ctx.send(embed=embed)


class ConnectionMonitor:
    """Monitors connection health and failures."""

    def __init__(self, max_retries: int = 3) -> None:
        self.max_retries = max_retries
        self.consecutive_failures = 0
        self.total_failures = 0
        self.failure_types = {}
        self.last_failure_time = None
        self.first_failure_time = None

    def connection_successful(self) -> None:
        if self.consecutive_failures > 0:
            logger.info(
                f"Connection restored after {self.consecutive_failures} consecutive failures"
            )
        self.consecutive_failures = 0

    def connection_failed(self, error_type: str) -> bool:
        now = datetime.now()
        if self.consecutive_failures == 0:
            self.first_failure_time = now

        self.consecutive_failures += 1
        self.total_failures += 1
        self.last_failure_time = now

        # Track types of failures
        if error_type in self.failure_types:
            self.failure_types[error_type] += 1
        else:
            self.failure_types[error_type] = 1

        # Log detailed failure info
        elapsed = None
        if self.first_failure_time:
            elapsed_seconds = (now - self.first_failure_time).total_seconds()
            elapsed = f"{elapsed_seconds:.1f} seconds"

        logger.warning(
            f"Connection failure #{self.consecutive_failures}: {error_type}. "
            f"Total failures: {self.total_failures}"
            + (f" in {elapsed}" if elapsed else "")
        )

        # Critical errors that should cause immediate exit
        critical_errors = [
            "ConnectionClosed",
            "GatewayNotFound",
            "LoginFailure",
            "Disconnection",
            "ClientConnectorDNSError",
        ]
        if error_type in critical_errors and self.consecutive_failures >= 2:
            logger.critical(
                f"Critical connection error: {error_type}. Exiting immediately."
            )
            return True

        # Check if max retries reached
        if self.consecutive_failures >= self.max_retries:
            logger.critical(
                f"Maximum connection retries ({self.max_retries}) reached. "
                f"Failure types: {self.failure_types}"
            )
            return True

        return False

    def get_status_report(self) -> str:
        if self.total_failures == 0:
            return "No connection failures detected"

        status = [
            f"Connection Status Report:",
            f"- Total failures: {self.total_failures}",
            f"- Consecutive failures: {self.consecutive_failures}",
        ]

        if self.first_failure_time:
            status.append(
                f"- First failure: {self.first_failure_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )

        if self.last_failure_time:
            status.append(
                f"- Latest failure: {self.last_failure_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )

        if self.first_failure_time and self.last_failure_time:
            elapsed_seconds = (
                self.last_failure_time - self.first_failure_time
            ).total_seconds()
            status.append(f"- Problem duration: {elapsed_seconds:.1f} seconds")

        status.append("- Failure types:")

        if not self.failure_types:
            status.append("  - None recorded")
        else:
            for error_type, count in sorted(
                self.failure_types.items(), key=lambda x: x[1], reverse=True
            ):
                percentage = (count / self.total_failures) * 100
                status.append(f"  - {error_type}: {count} ({percentage:.1f}%)")

        return "\n".join(status)


# Bot management functions
async def send_announcement_to_all_channels(
    bot,
    title: str,
    description: str,
    color: discord.Color,
    skip_channel_id: Optional[int] = None,
) -> None:
    """Send an announcement to all text channels."""
    for guild in bot.guilds:
        for channel in guild.text_channels:
            if skip_channel_id and channel.id == skip_channel_id:
                continue
            try:
                embed = discord.Embed(title=title, description=description, color=color)
                await channel.send(embed=embed)
            except Exception as e:
                logger.warning(
                    f"Failed to send announcement to {channel.name} in {guild.name}: {e}"
                )


async def find_first_available_channel(bot):
    """Find the first available text channel for sending messages."""
    for guild in bot.guilds:
        for channel in guild.text_channels:
            try:
                # Try sending a test message
                test_msg = await channel.send("Testing channel availability...")
                await test_msg.delete()  # Clean up test message
                return channel
            except Exception:
                continue
    return None


# Command line argument parsing
def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} - A Discord To-Do List Bot"
    )
    parser.add_argument(
        "--data_dir",
        default="./data",
        help="Directory to store data files (default: ./data)",
    )
    parser.add_argument(
        "--token",
        help="Discord bot token (can also be set via DISCORD_TOKEN env variable)",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug mode with verbose logging"
    )
    parser.add_argument(
        "--max_retries",
        type=int,
        default=3,
        help="Maximum number of consecutive connection failures before exiting (default: 3)",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help=f"Show {APP_NAME} version information and exit",
    )

    return parser.parse_args()


def get_token(args: argparse.Namespace) -> Optional[str]:
    """Get the Discord token from args or environment."""
    # First try from args
    if args.token:
        return args.token

    # Then try from environment
    return os.getenv("DISCORD_TOKEN")


# Setup and start the bot
async def setup_bot(args, token, session_id, connection_monitor):
    """Set up the Discord bot with all event handlers and cogs."""
    # Initialize bot with intents
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(
        command_prefix="!", intents=intents, help_command=CustomHelpCommand()
    )

    # Initialize storage
    data_dir = Path(args.data_dir)
    storage = StorageManager(data_dir, session_id)

    # Define event handlers
    @bot.event
    async def on_ready() -> None:
        # Reset connection failures on successful connection
        connection_monitor.connection_successful()

        if bot.user:
            logger.info(f"Logged in as {bot.user.name}")
            logger.info(f"Bot ID: {bot.user.id}")
            logger.info("Session ID: " + session_id)

            # Add cogs
            await bot.add_cog(TodoList(bot, storage))
            await bot.add_cog(BotManagement(bot, storage))

            logger.info("Cogs loaded successfully")

            # Announce bot is online in all text channels
            await send_announcement_to_all_channels(
                bot,
                f"🟢 {APP_NAME} v{APP_VERSION}: Bot Online",
                "Ready to help!",
                discord.Color.green(),
            )

            # Auto-execute loadlast command if there are saved files
            bot_management_cog = bot.get_cog("BotManagement")
            if bot_management_cog:
                files = storage.list_saved_files()
                if files:
                    # Find a channel where we can run the command
                    channel = await find_first_available_channel(bot)
                    if channel:
                        try:
                            # Send loading message and create context for command
                            loading_msg = await channel.send(
                                "Auto-loading last saved state..."
                            )
                            ctx = await bot.get_context(loading_msg)

                            # Execute loadlast command using getattr to fix attribute access error
                            loadlast_cmd = getattr(
                                bot_management_cog, "loadlast_command"
                            )
                            await loadlast_cmd(ctx)

                            # Announce successful loading to all channels
                            most_recent_file = files[-1]
                            await send_announcement_to_all_channels(
                                bot,
                                "📂 State Auto-Loaded",
                                f"Successfully loaded the most recent todo list from `{most_recent_file}`",
                                discord.Color.green(),
                                channel.id,  # Skip the channel we already announced in
                            )
                        except Exception as e:
                            logger.error(f"Error during auto-load: {e}", exc_info=True)
                    else:
                        logger.warning("Could not find any channel to auto-load state")
            else:
                logger.error("BotManagement cog not found for auto-loading")
        else:
            logger.error("Failed to log in - bot.user is None")

    @bot.event
    async def on_resume() -> None:
        connection_monitor.connection_successful()
        logger.info("Bot resumed connection to Discord")

    @bot.event
    async def on_disconnect() -> None:
        logger.warning("Bot disconnected from Discord")

        # Track disconnects as connection failures
        error_type = "Disconnection"
        if connection_monitor.connection_failed(error_type):
            logger.critical(
                "Connection failure threshold reached after multiple disconnections. Exiting..."
            )
            logger.critical(connection_monitor.get_status_report())
            sys.exit(1)

    @bot.event
    async def on_connect() -> None:
        connection_monitor.connection_successful()
        logger.info("Bot connected to Discord")

    @bot.event
    async def on_error(event_method: str, *_args, **_kwargs) -> None:
        logger.error(f"Error in {event_method}: {sys.exc_info()[1]}")

        # Check if this is a connection-related error
        exc_type, exc_value, _ = sys.exc_info()

        # Check for client connector errors (network issues)
        if isinstance(
            exc_value,
            (
                TimeoutError,
                discord_errors.ConnectionClosed,
                discord_errors.GatewayNotFound,
                asyncio.exceptions.CancelledError,
                discord_errors.HTTPException,
                discord_errors.LoginFailure,
                client_exceptions.ClientConnectorError,
                client_exceptions.ClientConnectorDNSError,
            ),
        ):
            error_type = exc_type.__name__  # type: ignore
            logger.warning(f"Connection error detected: {error_type}: {exc_value}")

            if connection_monitor.connection_failed(error_type):
                logger.critical("Connection failure threshold reached. Exiting...")
                logger.critical(connection_monitor.get_status_report())
                sys.exit(1)

    # Message logging (optional)
    @bot.listen("on_message")
    async def on_message(message: discord.Message) -> None:
        if message.author != bot.user:  # Don't log the bot's own messages
            logger.debug(
                f"Message from {message.author} in {message.channel}: {message.content}"
            )

    return bot, storage


async def main() -> None:
    """Main entry point for the application."""
    # Parse arguments
    args = parse_args()

    # Check if version flag was set
    if args.version:
        print(f"{APP_NAME} v{APP_VERSION}")
        sys.exit(0)

    # Configure logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")

    # Get token
    token = get_token(args)
    if not token:
        logger.error(
            "No Discord token provided. Use --token or set DISCORD_TOKEN environment variable."
        )
        sys.exit(1)

    # Generate session ID
    session_id = str(uuid.uuid4())
    logger.info("Starting new session: " + session_id)

    # Log application details
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")

    # Initialize connection monitor
    connection_monitor = ConnectionMonitor(max_retries=args.max_retries)
    logger.info(
        "Connection monitor initialized with max_retries=" + str(args.max_retries)
    )

    # Set up the bot with all its handlers and cogs
    bot, _storage = await setup_bot(args, token, session_id, connection_monitor)

    # Run the bot
    try:
        logger.info("Starting bot...")
        await bot.start(token)
    except Exception as e:
        logger.exception(f"Error starting bot: {e}")

        # Check if this is a connection-related error
        if isinstance(
            e,
            (
                TimeoutError,
                discord_errors.ConnectionClosed,
                discord_errors.GatewayNotFound,
                asyncio.exceptions.CancelledError,
                discord_errors.HTTPException,
                discord_errors.LoginFailure,
                client_exceptions.ClientConnectorError,
                client_exceptions.ClientConnectorDNSError,
            ),
        ):
            error_type = type(e).__name__
            logger.warning(f"Connection error detected: {error_type}: {e}")

            if connection_monitor.connection_failed(error_type):
                logger.critical("Connection failure threshold reached. Exiting...")
                logger.critical(connection_monitor.get_status_report())
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
