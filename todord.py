from datetime import datetime
import json
import discord
import os
import uuid
import argparse
from pathlib import Path
from discord.ext import commands

# Parse command line arguments
parser = argparse.ArgumentParser(description="Todord - A Discord To-Do List Bot")
parser.add_argument(
    "--data_dir",
    default="./data",
    help="Directory to store data files (default: ./data)",
)
args = parser.parse_args()

# Ensure data directory exists
data_dir = Path(args.data_dir)
if not data_dir.exists():
    data_dir.mkdir(parents=True)
    print(f"Created data directory: {data_dir}")

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("No DISCORD_TOKEN env configured.")
    exit(1)

# set up the bot with a command prefix.
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# In-memory dictionary to store to-do lists for each channel.
todo_lists = {}  # channel->task

# Global session ID for this bot run
SessionID = str(uuid.uuid4())


# async func to save the todo_lists as an json file based on session_id and datetime
async def save_todo_lists(session_id: str):
    current_time = datetime.now()
    filename = (
        f"todo_lists_{session_id}_{current_time.strftime('%Y-%m-%d_%H-%M-%S')}.json"
    )
    filepath = data_dir / filename
    with open(filepath, "w") as f:
        json.dump(todo_lists, f, default=lambda o: o.__dict__, indent=2)
    return filename


# Helper function to save after changes
async def save_changes(ctx):
    filename = await save_todo_lists(SessionID)
    return filename


# Load todo lists from a JSON file
async def load_todo_lists_from_file(ctx, filename):
    global todo_lists
    try:
        filepath = data_dir / filename
        with open(filepath, "r") as f:
            data = json.load(f)

        # Convert raw data back to Task objects
        reconstructed_todo_lists = {}
        for channel_id, tasks in data.items():
            channel_id = int(channel_id)  # JSON keys are strings, convert back to int
            reconstructed_todo_lists[channel_id] = []

            for task_data in tasks:
                # Create a Task object with the data
                task = Task(
                    ctx,
                    task_data["id"],
                    task_data["title"],
                    task_data["status"],
                    task_data["logs"],
                    task_data.get("creator", "Unknown")
                )

                # Restore internal logs if they exist
                if "internal_logs" in task_data:
                    task.internal_logs = task_data["internal_logs"]

                reconstructed_todo_lists[channel_id].append(task)

        todo_lists = reconstructed_todo_lists
        return True
    except Exception as e:
        print(f"Error loading todo lists: {e}")
        return False


## ---
## Task
TaskCreated = "task_created"
TaskStatusUpdated = "task_status_updated"
TaskLogAdded = "task_log_added"


class Task:
    id: int
    title: str
    status: str
    logs: list[str]
    internal_logs: list[tuple[str, str, str]]  # (timestamp, user, log)
    creator: str

    def __init__(
        self, ctx: commands.Context, id: int, title: str, status: str, logs: list[str], creator: str = None
    ):
        self.id = id
        self.title = title
        self.status = status
        self.logs = logs
        self.internal_logs = []
        self.creator = creator or ctx.author.name
        self.add_internal_log(ctx, TaskCreated)

    def add_internal_log(self, ctx: commands.Context, log: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user = ctx.author.name
        self.internal_logs.append((timestamp, user, log))

    def add_log(self, ctx: commands.Context, log: str):
        self.logs.append(log)
        self.add_internal_log(ctx, TaskLogAdded)

    def set_status(self, ctx: commands.Context, status: str):
        self.status = status
        self.add_internal_log(ctx, TaskStatusUpdated)

    def show_details(self):
        return f"[{self.status}] {self.title}\n{'\n'.join(self.logs)}"

    def __str__(self):
        return f"[{self.status}] {self.title}"


## ---
## Cogs


class ToDoList(commands.Cog):
    """Commands for managing your to-do list."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name="add", help="Add a task to the channel's to-do list. Usage: !add <task>"
    )
    async def add_task(self, ctx, *, task: str):
        channel_id = ctx.channel.id
        # Create a new list if channel does not have one
        if channel_id not in todo_lists:
            todo_lists[channel_id] = []

        t = Task(ctx, len(todo_lists[channel_id]), task, "pending", [])
        todo_lists[channel_id].append(t)

        await ctx.reply(f"Task added by {ctx.author.name}:\n**{task}**")
        await save_changes(ctx)

    @commands.command(
        name="list", help="List all tasks in the channel's to-do list. Usage: !list"
    )
    async def list_tasks(self, ctx):
        channel_id = ctx.channel.id
        tasks = todo_lists.get(channel_id, [])
        if not tasks:
            await ctx.reply("There are no tasks in this channel's to-do list.")
            return

        response = "**Channel To-Do List:**\n"
        for idx, task in enumerate(tasks, start=1):
            response += f"{idx}. {task}\n"
        await ctx.reply(response)

    @commands.command(
        name="done", help="Mark a task as done. Usage: !done <task number>"
    )
    async def done_task(self, ctx, task_number: int):
        channel_id = ctx.channel.id
        tasks = todo_lists.get(channel_id, [])
        if 0 < task_number <= len(tasks):
            removed = tasks.pop(task_number - 1)
            removed.set_status(ctx, "done")
            await ctx.reply(f"Task marked as done by {ctx.author.name}:\n**{removed}**")
            await save_changes(ctx)
        else:
            await ctx.reply("Invalid task number. Please check the list using !list.")

    @commands.command(name="close", help="Close a task. Usage: !close <task number>")
    async def close_task(self, ctx, task_number: int):
        channel_id = ctx.channel.id
        tasks = todo_lists.get(channel_id, [])
        if 0 < task_number <= len(tasks):
            removed = tasks.pop(task_number - 1)
            removed.set_status(ctx, "closed")
            await ctx.reply(f"Task closed by {ctx.author.name}:\n**{removed}**")
            await save_changes(ctx)
        else:
            await ctx.reply("Invalid task number. Please check the list using !list.")

    @commands.command(
        name="log", help="Add a log to a task. Usage: !log <task number> <log>"
    )
    async def log_task(self, ctx, task_number: int, *, log: str):
        channel_id = ctx.channel.id
        tasks = todo_lists.get(channel_id, [])
        if 0 < task_number <= len(tasks):
            t = tasks[task_number - 1]
            t.add_log(ctx, log)
            await ctx.reply(f"Log added to task by {ctx.author.name}:\n{t.show_details()}")
            await save_changes(ctx)
        else:
            await ctx.reply("Invalid task number. Please check the list using !list.")

    @commands.command(
        name="details", help="Show details of a task. Usage: !details <task number>"
    )
    async def details_task(self, ctx, task_number: int):
        channel_id = ctx.channel.id
        tasks = todo_lists.get(channel_id, [])
        if 0 < task_number <= len(tasks):
            t = tasks[task_number - 1]
            await ctx.reply(f"Details of task:\n{t.show_details()}")
        else:
            await ctx.reply("Invalid task number. Please check the list using !list.")


class Bot(commands.Cog):
    """Maintenance commands for the to-do list system."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="save", help="Manually save your to-do lists. Usage: !save")
    async def save_command(self, ctx):
        filename = await save_changes(ctx)
        await ctx.reply(f"The to-do lists have been saved to '{filename}'.")

    @commands.command(
        name="load", help="Load to-do lists from a JSON file. Usage: !load <filename>"
    )
    async def load_command(self, ctx, filename: str):
        success = await load_todo_lists_from_file(ctx, filename)
        if success:
            await ctx.reply(f"Successfully loaded to-do lists from '{filename}'.")
        else:
            await ctx.reply(
                f"Failed to load to-do lists from '{filename}'. Make sure the file exists and is in the correct format."
            )

    @commands.command(
        name="list_files", help="List all saved to-do list files. Usage: !list_files"
    )
    async def list_files_command(self, ctx):
        files = [
            f
            for f in os.listdir(data_dir)
            if f.startswith("todo_lists_") and f.endswith(".json")
        ]
        files.sort(key=lambda x: os.path.getctime(str(data_dir / x)))
        if files:
            files_list = "\n".join(files)
            await ctx.reply(f"**Available to-do list files:**\n{files_list}")
        else:
            await ctx.reply("No saved to-do list files found.")

    @commands.command(name="clear", help="Clear the channel's to-do list. Usage: !clear")
    async def clear_tasks(self, ctx):
        channel_id = ctx.channel.id
        todo_lists[channel_id] = []
        await ctx.reply(f"The channel's to-do list has been cleared by {ctx.author.name}.")
        await save_changes(ctx)


@bot.event
async def on_ready():
    if bot.user:
        print(f"Logged in as {bot.user.name}")
        print(f"SessionID: {SessionID}")
    else:
        print("Failed to log in")

    # Load cogs
    await bot.add_cog(ToDoList(bot))
    await bot.add_cog(Bot(bot))


@bot.listen("on_message")
async def print_message(message):
    print(
        f"Received message from {message.author} in {message.channel}: {message.content}"
    )


bot.run(TOKEN)
