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
from typing import Dict, List, Optional, Tuple, Union, Any, TypeVar, cast

import discord
from discord.ext import commands


# Configure logging
logging.basicConfig(
    level=logging.INFO,
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
        creator: Optional[str] = None
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

    def add_internal_log(self, ctx: commands.Context, log: str, extra_info: str = "") -> None:
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
        self.add_internal_log(ctx, TaskEvent.LOG_ADDED, f"'{log[:30]}{'...' if len(log) > 30 else ''}'")

    def set_status(self, ctx: commands.Context, status: str) -> None:
        """Set the task status.
        
        Args:
            ctx: The command context
            status: The new status
        """
        old_status = self.status
        self.status = status
        self.add_internal_log(ctx, TaskEvent.STATUS_UPDATED, f"from '{old_status}' to '{status}'")
        
    def set_title(self, ctx: commands.Context, title: str) -> None:
        """Set the task title.
        
        Args:
            ctx: The command context
            title: The new title
        """
        old_title = self.title
        self.title = title
        self.add_internal_log(ctx, TaskEvent.TITLE_EDITED, f"from '{old_title[:30]}{'...' if len(old_title) > 30 else ''}' to '{title[:30]}{'...' if len(title) > 30 else ''}'")

    def show_details(self) -> str:
        """Get a detailed representation of the task.
        
        Returns:
            A formatted string with task details including history
        """
        # Start with the basic task info
        details = [f"[{self.status}] {self.title}"]
        
        # Add creator info
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
                action_details = action.split(":", 1)[1].strip() if ":" in action else ""
                
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
        return f"[{self.status}] {self.title}"


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

        # Ensure data directory exists
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True)
            logger.info(f"Created data directory: {self.data_dir}")

    async def save(self, ctx: commands.Context) -> str:
        """Save the current state of todo lists.
        
        Args:
            ctx: The command context
            
        Returns:
            The filename of the saved file
        """
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

            # Convert raw data back to Task objects
            reconstructed_todo_lists: Dict[int, List[Task]] = {}
            
            for channel_id, tasks in data.items():
                channel_id_int = int(channel_id)  # JSON keys are strings, convert back to int
                reconstructed_todo_lists[channel_id_int] = []

                for task_data in tasks:
                    # Create a Task object with the data
                    task = Task(
                        ctx,
                        task_data["id"],
                        task_data["title"],
                        task_data["status"],
                        task_data.get("logs", []),
                        task_data.get("creator", "Unknown")
                    )

                    # Restore internal logs if they exist
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
            f for f in os.listdir(self.data_dir)
            if f.startswith("todo_lists_") and f.endswith(".json")
        ]
        files.sort(key=lambda x: os.path.getctime(str(self.data_dir / x)))
        return files


class TodoList(commands.Cog):
    """Commands for managing your to-do list."""

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
        help="Add a task to the channel's to-do list. Usage: !add <task>"
    )
    async def add_task(self, ctx: commands.Context, *, task: str) -> None:
        """Add a task to the channel's to-do list.
        
        Args:
            ctx: The command context
            task: The task description
        """
        channel_id = ctx.channel.id
        
        # Create a new list if channel does not have one
        if channel_id not in self.storage.todo_lists:
            self.storage.todo_lists[channel_id] = []

        task_id = len(self.storage.todo_lists[channel_id])
        new_task = Task(ctx, task_id, task, "pending", [])
        self.storage.todo_lists[channel_id].append(new_task)

        await ctx.reply(f"Task added by {ctx.author.name}:\n**{task}**")
        await self.storage.save(ctx)

    @commands.command(
        name="list", 
        help="List all tasks in the channel's to-do list. Usage: !list"
    )
    async def list_tasks(self, ctx: commands.Context) -> None:
        """List all tasks in the channel's to-do list.
        
        Args:
            ctx: The command context
        """
        channel_id = ctx.channel.id
        tasks = self.storage.todo_lists.get(channel_id, [])
        
        if not tasks:
            await ctx.reply("There are no tasks in this channel's to-do list.")
            return

        response = "**Channel To-Do List:**\n"
        for idx, task in enumerate(tasks, start=1):
            response += f"{idx}. {task}\n"
            
        await ctx.reply(response)

    @commands.command(
        name="done", 
        help="Mark a task as done. Usage: !done <task number>"
    )
    async def done_task(self, ctx: commands.Context, task_number: int) -> None:
        """Mark a task as done.
        
        Args:
            ctx: The command context
            task_number: The task number to mark as done
        """
        channel_id = ctx.channel.id
        tasks = self.storage.todo_lists.get(channel_id, [])
        
        if not tasks:
            await ctx.reply("There are no tasks in this channel's to-do list.")
            return
            
        if 0 < task_number <= len(tasks):
            removed = tasks.pop(task_number - 1)
            removed.set_status(ctx, "done")
            await ctx.reply(f"Task marked as done by {ctx.author.name}:\n**{removed}**")
            await self.storage.save(ctx)
        else:
            await ctx.reply("Invalid task number. Please check the list using !list.")

    @commands.command(
        name="close", 
        help="Close a task. Usage: !close <task number>"
    )
    async def close_task(self, ctx: commands.Context, task_number: int) -> None:
        """Close a task.
        
        Args:
            ctx: The command context
            task_number: The task number to close
        """
        channel_id = ctx.channel.id
        tasks = self.storage.todo_lists.get(channel_id, [])
        
        if not tasks:
            await ctx.reply("There are no tasks in this channel's to-do list.")
            return
            
        if 0 < task_number <= len(tasks):
            removed = tasks.pop(task_number - 1)
            removed.set_status(ctx, "closed")
            await ctx.reply(f"Task closed by {ctx.author.name}:\n**{removed}**")
            await self.storage.save(ctx)
        else:
            await ctx.reply("Invalid task number. Please check the list using !list.")

    @commands.command(
        name="log", 
        help="Add a log to a task. Usage: !log <task number> <log>"
    )
    async def log_task(self, ctx: commands.Context, task_number: int, *, log: str) -> None:
        """Add a log to a task.
        
        Args:
            ctx: The command context
            task_number: The task number to add a log to
            log: The log message
        """
        channel_id = ctx.channel.id
        tasks = self.storage.todo_lists.get(channel_id, [])
        
        if not tasks:
            await ctx.reply("There are no tasks in this channel's to-do list.")
            return
            
        if 0 < task_number <= len(tasks):
            task = tasks[task_number - 1]
            task.add_log(ctx, log)
            await ctx.reply(f"Log added to task by {ctx.author.name}:\n{task.show_details()}")
            await self.storage.save(ctx)
        else:
            await ctx.reply("Invalid task number. Please check the list using !list.")

    @commands.command(
        name="details", 
        help="Show details of a task. Usage: !details <task number>"
    )
    async def details_task(self, ctx: commands.Context, task_number: int) -> None:
        """Show details of a task.
        
        Args:
            ctx: The command context
            task_number: The task number to show details for
        """
        channel_id = ctx.channel.id
        tasks = self.storage.todo_lists.get(channel_id, [])
        
        if not tasks:
            await ctx.reply("There are no tasks in this channel's to-do list.")
            return
            
        if 0 < task_number <= len(tasks):
            task = tasks[task_number - 1]
            details = task.show_details()
            
            # Send the task details in a nicely formatted message
            await ctx.reply(f"**Task #{task_number} Details:**\n{details}")
        else:
            await ctx.reply("Invalid task number. Please check the list using !list.")

    @commands.command(
        name="edit", 
        help="Edit a task's title. Usage: !edit <task number> <new title>"
    )
    async def edit_task(self, ctx: commands.Context, task_number: int, *, new_title: str) -> None:
        """Edit a task's title.
        
        Args:
            ctx: The command context
            task_number: The task number to edit
            new_title: The new task title
        """
        channel_id = ctx.channel.id
        tasks = self.storage.todo_lists.get(channel_id, [])
        
        if not tasks:
            await ctx.reply("There are no tasks in this channel's to-do list.")
            return
            
        if 0 < task_number <= len(tasks):
            task = tasks[task_number - 1]
            old_title = task.title
            task.set_title(ctx, new_title)
            await ctx.reply(f"Task title edited by {ctx.author.name}:\nFrom: **{old_title}**\nTo: **{new_title}**")
            await self.storage.save(ctx)
        else:
            await ctx.reply("Invalid task number. Please check the list using !list.")

    @commands.command(
        name="clear", 
        help="Clear the channel's to-do list. Usage: !clear"
    )
    async def clear_tasks(self, ctx: commands.Context) -> None:
        """Clear the channel's to-do list.
        
        Args:
            ctx: The command context
        """
        channel_id = ctx.channel.id
        
        if channel_id in self.storage.todo_lists:
            self.storage.todo_lists[channel_id] = []
            await ctx.reply(f"The channel's to-do list has been cleared by {ctx.author.name}.")
            await self.storage.save(ctx)
        else:
            await ctx.reply("There are no tasks in this channel's to-do list.")


class BotManagement(commands.Cog):
    """Maintenance commands for the to-do list system."""

    def __init__(self, bot: commands.Bot, storage: StorageManager) -> None:
        """Initialize the BotManagement cog.
        
        Args:
            bot: The Discord bot
            storage: The storage manager
        """
        self.bot = bot
        self.storage = storage

    @commands.command(
        name="save", 
        help="Manually save your to-do lists. Usage: !save"
    )
    async def save_command(self, ctx: commands.Context) -> None:
        """Save the current to-do lists.
        
        Args:
            ctx: The command context
        """
        filename = await self.storage.save(ctx)
        await ctx.reply(f"The to-do lists have been saved to '{filename}'.")

    @commands.command(
        name="load", 
        help="Load to-do lists from a JSON file. Usage: !load <filename>"
    )
    async def load_command(self, ctx: commands.Context, filename: str) -> None:
        """Load to-do lists from a file.
        
        Args:
            ctx: The command context
            filename: The file to load from
        """
        success = await self.storage.load(ctx, filename)
        if success:
            await ctx.reply(f"Successfully loaded to-do lists from '{filename}'.")
        else:
            await ctx.reply(
                f"Failed to load to-do lists from '{filename}'. "
                "Make sure the file exists and is in the correct format."
            )

    @commands.command(
        name="loadlast",
        help="Load the most recent to-do list file. Usage: !loadlast"
    )
    async def loadlast_command(self, ctx: commands.Context) -> None:
        """Load the most recent to-do list file.
        
        Args:
            ctx: The command context
        """
        files = self.storage.list_saved_files()
        
        if not files:
            await ctx.reply("No saved to-do list files found.")
            return
            
        # Files are already sorted by creation time, so the last one is the most recent
        most_recent_file = files[-1]
        
        success = await self.storage.load(ctx, most_recent_file)
        if success:
            await ctx.reply(f"Successfully loaded the most recent to-do lists from '{most_recent_file}'.")
        else:
            await ctx.reply(
                f"Failed to load to-do lists from '{most_recent_file}'. "
                "The file may be corrupted or in an incorrect format."
            )

    @commands.command(
        name="list_files", 
        help="List all saved to-do list files. Usage: !list_files"
    )
    async def list_files_command(self, ctx: commands.Context) -> None:
        """List all saved to-do list files.
        
        Args:
            ctx: The command context
        """
        files = self.storage.list_saved_files()
        if files:
            files_list = "\n".join(files)
            await ctx.reply(f"**Available to-do list files:**\n{files_list}")
        else:
            await ctx.reply("No saved to-do list files found.")


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
        logger.error("No Discord token provided. Use --token or set DISCORD_TOKEN environment variable.")
        sys.exit(1)
    
    # Ensure data directory exists
    data_dir = Path(args.data_dir)
    
    # Generate session ID
    session_id = str(uuid.uuid4())
    logger.info(f"Starting new session: {session_id}")
    
    # Initialize bot with intents
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    
    # Initialize storage
    storage = StorageManager(data_dir, session_id)
    
    # Define on_ready event
    @bot.event
    async def on_ready() -> None:
        """Called when the bot is ready."""
        if bot.user:
            logger.info(f"Logged in as {bot.user.name}")
            logger.info(f"Bot ID: {bot.user.id}")
            logger.info(f"Session ID: {session_id}")
            
            # Add cogs
            await bot.add_cog(TodoList(bot, storage))
            await bot.add_cog(BotManagement(bot, storage))
            
            logger.info("Cogs loaded successfully")
        else:
            logger.error("Failed to log in - bot.user is None")
    
    # Message logging (optional)
    @bot.listen("on_message")
    async def on_message(message: discord.Message) -> None:
        """Log messages received by the bot.
        
        Args:
            message: The Discord message
        """
        if message.author != bot.user:  # Don't log the bot's own messages
            logger.debug(
                f"Message from {message.author} in {message.channel}: {message.content}"
            )
    
    # Run the bot
    try:
        logger.info("Starting bot...")
        await bot.start(token)
    except Exception as e:
        logger.exception(f"Error starting bot: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
