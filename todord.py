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
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, cast

import discord
from discord.ext import commands
from discord import errors as discord_errors
from aiohttp import client_exceptions


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("todord")


class TaskEvent:
    """Constants for task events."""

    CREATED = "task_created"
    STATUS_UPDATED = "task_status_updated"
    LOG_ADDED = "task_log_added"
    TITLE_EDITED = "task_title_edited"


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
        """Initialize a new task.

        Args:
            ctx: The command context
            id: The task ID
            title: The task title
            status: The task status
            logs: Optional list of logs
            creator: Optional creator name (defaults to ctx.author.name)
        """
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
        """Add an internal log entry.

        Args:
            ctx: The command context
            log: The log message
            extra_info: Optional additional information about the action
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user = ctx.author.name
        action = log if not extra_info else f"{log}: {extra_info}"
        self.internal_logs.append((timestamp, user, action))

    def add_log(self, ctx: commands.Context, log: str) -> None:
        """Add a user log entry.

        Args:
            ctx: The command context
            log: The log message
        """
        self.logs.append(log)
        self.add_internal_log(
            ctx, TaskEvent.LOG_ADDED, f"'{log[:30]}{'...' if len(log) > 30 else ''}'"
        )

    def set_status(self, ctx: commands.Context, status: str) -> None:
        """Set the task status.

        Args:
            ctx: The command context
            status: The new status
        """
        old_status = self.status
        self.status = status
        self.add_internal_log(
            ctx, TaskEvent.STATUS_UPDATED, f"from '{old_status}' to '{status}'"
        )

    def set_title(self, ctx: commands.Context, title: str) -> None:
        """Set the task title.

        Args:
            ctx: The command context
            title: The new title
        """
        old_title = self.title
        self.title = title
        self.add_internal_log(
            ctx,
            TaskEvent.TITLE_EDITED,
            f"from '{old_title[:30]}{'...' if len(old_title) > 30 else ''}' to '{title[:30]}{'...' if len(title) > 30 else ''}'",
        )

    def show_details(self) -> str:
        """Get a detailed representation of the task.

        Returns:
            A formatted string with task details including history
        """
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
        """Get a string representation of the task.

        Returns:
            A formatted string with basic task info
        """
        return f"**[{self.status}] {self.title}**"


# Utility functions
def create_embed(
    ctx: commands.Context, title: str, description: str, color: discord.Color
) -> discord.Embed:
    """Create a standardized Discord embed."""
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=f"Requested by {ctx.author.name}")
    return embed


def get_tasks(
    ctx: commands.Context, storage
) -> Tuple[List[Task], Optional[discord.Embed]]:
    """Get tasks for the current channel. Returns (task_list, error_embed)."""
    # ctx is accessed for channel_id and embed creation, pylint: disable=unused-argument
    channel_id = ctx.channel.id
    tasks = storage.todo_lists.get(channel_id, [])

    if not tasks:
        embed = create_embed(
            ctx,
            "ℹ️ Info",
            "There are no tasks in this channel's to-do list.",
            discord.Color.blue(),
        )
        return tasks, embed

    return tasks, None


def validate_task_number(
    ctx: commands.Context, task_number: int, tasks: List[Task]
) -> Tuple[Optional[Task], Optional[discord.Embed]]:
    """Validate task number and return (task, error_embed)."""
    if 0 < task_number <= len(tasks):
        return tasks[task_number - 1], None

    embed = create_embed(
        ctx,
        "❌ Error",
        f"Invalid task number: {task_number}. Use `!list` to see valid numbers.",
        discord.Color.red(),
    )
    return None, embed


class StorageManager:
    """Manages task persistence."""

    def __init__(self, data_dir: Union[str, Path], session_id: str) -> None:
        """Initialize the storage manager.

        Args:
            data_dir: Directory to store data files
            session_id: Current session ID
        """
        self.data_dir = Path(data_dir)
        self.session_id = session_id
        self.todo_lists: Dict[int, List[Task]] = {}  # channel_id -> [Task, Task, ...]

        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True)
            logger.info(f"Created data directory: {self.data_dir}")

    async def save(self, ctx: Optional[commands.Context] = None) -> str:
        """Save the current state of todo lists.

        Args:
            ctx: The command context, can be None for auto-saves during shutdown

        Returns:
            The filename of the saved file
        """
        _ = ctx
        current_time = datetime.now()
        filename = f"todo_lists_{self.session_id}_{current_time.strftime('%Y-%m-%d_%H-%M-%S')}.json"
        filepath = self.data_dir / filename

        with open(filepath, "w") as f:
            json.dump(self.todo_lists, f, default=lambda o: o.__dict__, indent=2)

        return filename

    async def load(self, ctx: commands.Context, filename: str) -> bool:
        """Load todo lists from a file.

        Args:
            ctx: The command context
            filename: The file to load from

        Returns:
            True if successful, False otherwise
        """
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
        """List all saved todo list files.

        Returns:
            A list of filenames
        """
        files = [
            f
            for f in os.listdir(self.data_dir)
            if f.startswith("todo_lists_") and f.endswith(".json")
        ]
        files.sort(key=lambda x: os.path.getctime(str(self.data_dir / x)))
        return files


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
        """Send the bot help page."""
        embed = discord.Embed(
            title="Todord Help",
            color=discord.Color.blue(),
        )

        for cog, cmds in mapping.items():
            filtered = await self.filter_commands(cmds, sort=True)
            if filtered:
                name = getattr(cog, "qualified_name", "Other Commands")
                commands_text = "\n".join(
                    [f"`!{cmd.name}` - {cmd.short_doc}" for cmd in filtered]
                )
                embed.add_field(name=name, value=commands_text, inline=False)

        embed.set_footer(text="Type !help <command> for detailed info on a command.")
        await self.get_destination().send(embed=embed)

    async def send_command_help(self, command):
        """Send help for a specific command."""
        embed = discord.Embed(
            title=f"Command: !{command.name}",
            description=command.help or "No description provided",
            color=discord.Color.green(),
        )

        if command.aliases:
            aliases = ", ".join(f"`!{alias}`" for alias in command.aliases)
            embed.add_field(name="Aliases", value=aliases, inline=False)

        usage = f"`!{command.name}"
        if command.signature:
            usage += f" {command.signature}"
        usage += "`"
        embed.add_field(name="Usage", value=usage, inline=False)

        await self.get_destination().send(embed=embed)

    async def send_cog_help(self, cog):
        """Send help for a specific category/cog."""
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
        """Send an error message."""
        embed = discord.Embed(
            title="Error", description=error, color=discord.Color.red()
        )
        await self.get_destination().send(embed=embed)


class TodoList(commands.Cog):
    """Task management commands."""

    def __init__(self, bot: commands.Bot, storage: StorageManager) -> None:
        """Initialize the TodoList cog.

        Args:
            bot: The Discord bot
            storage: The storage manager
        """
        self.bot = bot
        self.storage = storage

    @commands.command(
        name="add",
        aliases=["a"],
        help="Add new task to the channel's to-do list.",
    )
    async def add_task(self, ctx: commands.Context, *, task: str) -> None:
        """Add a task to the channel's to-do list.

        Args:
            ctx: The command context
            task: The task description
        """
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
        """List all tasks in the channel's to-do list.

        Args:
            ctx: The command context
        """
        tasks, error_embed = get_tasks(ctx, self.storage)
        if error_embed:
            await ctx.reply(embed=error_embed)
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
        """Mark a task as done.

        Args:
            ctx: The command context
            task_number: The task number to mark as done
        """
        tasks, error_embed = get_tasks(ctx, self.storage)
        if error_embed:
            await ctx.reply(embed=error_embed)
            return

        task, error_embed = validate_task_number(ctx, task_number, tasks)
        if error_embed or task is None:
            if error_embed:
                await ctx.reply(embed=error_embed)
            return

        # Remove task from list
        tasks.pop(task_number - 1)
        task.set_status(ctx, "done")

        embed = create_embed(
            ctx, "✔️ Task Marked as Done", f"**{task}**", discord.Color.green()
        )
        await ctx.reply(embed=embed)
        await self.storage.save(ctx)

    @commands.command(
        name="close",
        aliases=["c"],
        help="Close a task without completing and remove from list.",
    )
    async def close_task(self, ctx: commands.Context, task_number: int) -> None:
        """Close a task.

        Args:
            ctx: The command context
            task_number: The task number to close
        """
        tasks, error_embed = get_tasks(ctx, self.storage)
        if error_embed:
            await ctx.reply(embed=error_embed)
            return

        task, error_embed = validate_task_number(ctx, task_number, tasks)
        if error_embed or task is None:
            if error_embed:
                await ctx.reply(embed=error_embed)
            return

        # Remove task from list
        tasks.pop(task_number - 1)
        task.set_status(ctx, "closed")

        embed = create_embed(
            ctx,
            "✖️ Task Closed",
            f"**{task}**",
            discord.Color.orange(),
        )
        await ctx.reply(embed=embed)
        await self.storage.save(ctx)

    @commands.command(
        name="log",
        aliases=["lg"],
        help="Add a progress note or comment to an existing task.",
    )
    async def log_task(
        self, ctx: commands.Context, task_number: int, *, log: str
    ) -> None:
        """Add a log to a task.

        Args:
            ctx: The command context
            task_number: The task number to add a log to
            log: The log message
        """
        tasks, error_embed = get_tasks(ctx, self.storage)
        if error_embed:
            await ctx.reply(embed=error_embed)
            return

        task, error_embed = validate_task_number(ctx, task_number, tasks)
        if error_embed or task is None:
            if error_embed:
                await ctx.reply(embed=error_embed)
            return

        task.add_log(ctx, log)

        embed = create_embed(
            ctx,
            f"📝 Log Added to Task #{task_number}",
            f"Log: '{log}'\n\n**Current Task Details:**\n{task.show_details()}",
            discord.Color.green(),
        )
        await ctx.reply(embed=embed)
        await self.storage.save(ctx)

    @commands.command(
        name="details",
        aliases=["det"],
        help="Show details of a task.",
    )
    async def details_task(self, ctx: commands.Context, task_number: int) -> None:
        """Show details of a task.

        Args:
            ctx: The command context
            task_number: The task number to show details for
        """
        tasks, error_embed = get_tasks(ctx, self.storage)
        if error_embed:
            await ctx.reply(embed=error_embed)
            return

        task, error_embed = validate_task_number(ctx, task_number, tasks)
        if error_embed or task is None:
            if error_embed:
                await ctx.reply(embed=error_embed)
            return

        details = task.show_details()

        embed = create_embed(
            ctx, f"🔍 Task #{task_number} Details", details, discord.Color.blue()
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
        """Edit a task's title.

        Args:
            ctx: The command context
            task_number: The task number to edit
            new_title: The new task title
        """
        tasks, error_embed = get_tasks(ctx, self.storage)
        if error_embed:
            await ctx.reply(embed=error_embed)
            return

        task, error_embed = validate_task_number(ctx, task_number, tasks)
        if error_embed or task is None:
            if error_embed:
                await ctx.reply(embed=error_embed)
            return

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


class BotManagement(commands.Cog):
    """Administrative Bot commands."""

    def __init__(self, bot: commands.Bot, storage: StorageManager) -> None:
        """Initialize the BotManagement cog.

        Args:
            bot: The Discord bot
            storage: The storage manager
        """
        self.bot = bot
        self.storage = storage

    @commands.command(
        name="clear",
        aliases=["clr"],
        help="Remove current channel's state.",
    )
    async def clear_tasks(self, ctx: commands.Context) -> None:
        """Clear the channel's to-do list.

        Args:
            ctx: The command context
        """
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
        """Save the current to-do lists.

        Args:
            ctx: The command context
        """
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
        """Load to-do lists from a file.

        Args:
            ctx: The command context
            filename: The file to load from
        """
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
        """Load the most recent to-do list file.

        Args:
            ctx: The command context
        """
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
        """List all saved to-do list files.

        Args:
            ctx: The command context
        """
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
        """Initialize connection monitor.

        Args:
            max_retries: Maximum number of consecutive failures before exit
        """
        self.max_retries = max_retries
        self.consecutive_failures = 0
        self.total_failures = 0
        self.failure_types = {}
        self.last_failure_time = None
        self.first_failure_time = None

    def connection_successful(self) -> None:
        """Reset the failure counter on successful connection."""
        if self.consecutive_failures > 0:
            logger.info(
                f"Connection restored after {self.consecutive_failures} consecutive failures"
            )
        self.consecutive_failures = 0

    def connection_failed(self, error_type: str) -> bool:
        """Increment failure counter and check if max retries reached.

        Args:
            error_type: Type of connection error that occurred

        Returns:
            True if max retries reached, False otherwise
        """
        now = datetime.now()
        if self.consecutive_failures == 0:
            self.first_failure_time = now

        self.consecutive_failures += 1
        self.total_failures += 1
        self.last_failure_time = now

        # Track types of failures
        self.failure_types[error_type] = self.failure_types.get(error_type, 0) + 1

        logger.warning(f"Connection failure #{self.consecutive_failures}: {error_type}")

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
        """Get a detailed status report of connection health.

        Returns:
            A string with connection status information
        """
        if self.total_failures == 0:
            return "No connection failures detected"

        status = [
            f"Connection Status Report: {''}",
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

        status.append("- Failure types:")
        for error_type, count in self.failure_types.items():
            status.append(f"  - {error_type}: {count}")

        return "\n".join(status)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        The parsed arguments
    """
    parser = argparse.ArgumentParser(description="Todord - A Discord To-Do List Bot")
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
        "--debug",
        action="store_true",
        help="Enable debug mode with verbose logging",
    )
    parser.add_argument(
        "--max_retries",
        type=int,
        default=3,
        help="Maximum number of consecutive connection failures before exiting (default: 3)",
    )

    return parser.parse_args()


def get_token(args: argparse.Namespace) -> Optional[str]:
    """Get the Discord token from args or environment.

    Args:
        args: The parsed command line arguments

    Returns:
        The Discord token or None if not found
    """
    # First try from args
    if args.token:
        return args.token

    # Then try from environment
    token = os.getenv("DISCORD_TOKEN")
    return token


async def main() -> None:
    """Main entry point for the application."""
    # Parse arguments
    args = parse_args()

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
    logger.info(f"Starting new session: {session_id}")

    # Initialize bot with intents
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(
        command_prefix="!", intents=intents, help_command=CustomHelpCommand()
    )

    # Initialize connection monitor
    connection_monitor = ConnectionMonitor(max_retries=args.max_retries)
    logger.info(f"Connection monitor initialized with max_retries={args.max_retries}")

    # Initialize storage
    storage = StorageManager(Path(args.data_dir), session_id)

    @bot.event
    async def on_ready() -> None:
        """Called when the bot is ready."""
        connection_monitor.connection_successful()
        if bot.user:
            logger.info(f"Logged in as {bot.user.name} (ID: {bot.user.id})")

            # Add cogs
            await bot.add_cog(TodoList(bot, storage))
            await bot.add_cog(BotManagement(bot, storage))

            # Load last state if available
            files = storage.list_saved_files()
            if files:
                try:
                    # Find a channel to use for context
                    for guild in bot.guilds:
                        for channel in guild.text_channels:
                            try:
                                # Create a mock message for context
                                class MockMessage:
                                    """A minimal mock of discord.Message for context creation."""

                                    def __init__(self, channel):
                                        self.content = "!loadlast"
                                        # Use proper type for author to match what discord.py expects
                                        self.author = cast(discord.User, bot.user)
                                        self.channel = channel
                                        self.id = 0
                                        self.attachments = []
                                        self.embeds = []
                                        self.mentions = []
                                        self.role_mentions = []
                                        self.guild = channel.guild

                                # Create context for command
                                mock_msg = MockMessage(channel)
                                ctx = await bot.get_context(mock_msg)  # type: ignore

                                # Execute loadlast command
                                bot_management = bot.get_cog("BotManagement")
                                if bot_management and isinstance(
                                    bot_management, BotManagement
                                ):
                                    await bot_management.loadlast_command(ctx)
                                    logger.info(
                                        f"Auto-loaded last state from {files[-1]}"
                                    )
                                    return
                            except Exception:
                                continue
                except Exception as e:
                    logger.error(f"Error auto-loading last state: {e}")

    @bot.event  # Used by discord.py
    async def on_error(event_method: str, *_args, **_kwargs) -> None:
        """Handle errors that occur in the bot."""
        _, _ = _args, _kwargs
        exc_type, exc_value, _ = sys.exc_info()
        logger.error(f"Error in {event_method}: {exc_value}")

        # Check if connection-related error
        connection_errors = (
            TimeoutError,
            discord_errors.ConnectionClosed,
            discord_errors.GatewayNotFound,
            discord_errors.LoginFailure,
            client_exceptions.ClientConnectorError,
            client_exceptions.ClientConnectorDNSError,
        )

        if isinstance(exc_value, connection_errors):
            error_type = exc_type.__name__ if exc_type else "Unknown"
            if connection_monitor.connection_failed(error_type):
                logger.critical("Connection failure threshold reached. Exiting...")
                logger.critical(connection_monitor.get_status_report())
                sys.exit(1)

    # Run the bot with error handling
    try:
        logger.info("Starting bot...")
        await bot.start(token)
    except Exception as e:
        logger.exception(f"Error starting bot: {e}")

        # Check if connection-related error
        connection_errors = (
            TimeoutError,
            discord_errors.ConnectionClosed,
            discord_errors.GatewayNotFound,
            discord_errors.LoginFailure,
            client_exceptions.ClientConnectorError,
            client_exceptions.ClientConnectorDNSError,
        )

        if isinstance(e, connection_errors):
            error_type = type(e).__name__
            if connection_monitor.connection_failed(error_type):
                logger.critical("Connection failure threshold reached. Exiting...")
                logger.critical(connection_monitor.get_status_report())
        sys.exit(1)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
