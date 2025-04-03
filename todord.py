from datetime import datetime
import json
import discord
import os
import uuid
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("No DISCORD_TOKEN env configured.")
    exit(1)

# set up the bot with a command prefix.
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# In-memory dictionary to store to-do lists for each user.
todo_lists = {}  # channel->user->task

# Global session ID for this bot run
SessionID = str(uuid.uuid4())


# async func to save the todo_lists as an json file based on session_id and datetime
async def save_todo_lists(session_id: str):
    current_time = datetime.now()
    filename = (
        f"todo_lists_{session_id}_{current_time.strftime('%Y-%m-%d_%H-%M-%S')}.json"
    )
    with open(filename, "w") as f:
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
        with open(filename, "r") as f:
            data = json.load(f)

        # Convert raw data back to Task objects
        reconstructed_todo_lists = {}
        for channel_id, users in data.items():
            channel_id = int(channel_id)  # JSON keys are strings, convert back to int
            reconstructed_todo_lists[channel_id] = {}

            for user_id, tasks in users.items():
                user_id = int(user_id)  # JSON keys are strings, convert back to int
                reconstructed_todo_lists[channel_id][user_id] = []

                for task_data in tasks:
                    # Create a Task object with the data
                    task = Task(
                        ctx,
                        task_data["id"],
                        task_data["title"],
                        task_data["status"],
                        task_data["logs"],
                    )

                    # Restore internal logs if they exist
                    if "internal_logs" in task_data:
                        task.internal_logs = task_data["internal_logs"]

                    reconstructed_todo_lists[channel_id][user_id].append(task)

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

    def __init__(
        self, ctx: commands.Context, id: int, title: str, status: str, logs: list[str]
    ):
        self.id = id
        self.title = title
        self.status = status
        self.logs = logs
        self.internal_logs = []
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
        return f"[{self.status}] {self.title} \n{'\n'.join(self.logs)}"

    def __str__(self):
        return f"[{self.status}] {self.title}"


## ---
## Cogs


class TodoCog(commands.Cog):
    """Commands for managing your to-do list."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name="add", help="Add a task to your to-do list. Usage: !add <task>"
    )
    async def add_task(self, ctx, *, task: str):
        user_id = ctx.author.id
        channel_id = ctx.channel.id
        # Create a new list if user does not have one.
        if channel_id not in todo_lists:
            todo_lists[channel_id] = {}
        if user_id not in todo_lists[channel_id]:
            todo_lists[channel_id][user_id] = []

        t = Task(ctx, len(todo_lists[channel_id][user_id]), task, "pending", [])
        todo_lists[channel_id][user_id].append(t)

        await ctx.send(f"Task added: **{task}**")
        await save_changes(ctx)

    @commands.command(
        name="list", help="List all tasks in your to-do list. Usage: !list"
    )
    async def list_tasks(self, ctx):
        channel_id = ctx.channel.id
        user_id = ctx.author.id
        tasks = todo_lists.get(channel_id, {}).get(user_id, [])
        if not tasks:
            await ctx.send("You have no tasks in your to-do list.")
            return

        response = "**Your To-Do List:**\n"
        for idx, task in enumerate(tasks, start=1):
            response += f"{idx}. {task}\n"
        await ctx.send(response)

    @commands.command(
        name="done", help="Mark a task as done. Usage: !done <task number>"
    )
    async def done_task(self, ctx, task_number: int):
        channel_id = ctx.channel.id
        user_id = ctx.author.id
        tasks = todo_lists.get(channel_id, {}).get(user_id, [])
        if 0 < task_number <= len(tasks):
            removed = tasks.pop(task_number - 1)
            await ctx.send(f"Marked task as done: **{removed}**")
            await save_changes(ctx)
        else:
            await ctx.send("Invalid task number. Please check your list using !list.")

    @commands.command(name="close", help="Close a task. Usage: !close <task number>")
    async def close_task(self, ctx, task_number: int):
        channel_id = ctx.channel.id
        user_id = ctx.author.id
        tasks = todo_lists.get(channel_id, {}).get(user_id, [])
        if 0 < task_number <= len(tasks):
            t = tasks[task_number - 1]
            t.set_status(ctx, "closed")
            await ctx.send(f"Closed task: **{t}**")
            await save_changes(ctx)
        else:
            await ctx.send("Invalid task number. Please check your list using !list.")

    @commands.command(
        name="log", help="Add a log to a task. Usage: !log <task number> <log>"
    )
    async def log_task(self, ctx, task_number: int, *, log: str):
        channel_id = ctx.channel.id
        user_id = ctx.author.id
        tasks = todo_lists.get(channel_id, {}).get(user_id, [])
        if 0 < task_number <= len(tasks):
            t = tasks[task_number - 1]
            t.add_log(ctx, log)
            await ctx.send(f"Added log to task: {t.show_details()}")
            await save_changes(ctx)
        else:
            await ctx.send("Invalid task number. Please check your list using !list.")

    @commands.command(
        name="details", help="Show details of a task. Usage: !details <task number>"
    )
    async def details_task(self, ctx, task_number: int):
        channel_id = ctx.channel.id
        user_id = ctx.author.id
        tasks = todo_lists.get(channel_id, {}).get(user_id, [])
        if 0 < task_number <= len(tasks):
            t = tasks[task_number - 1]
            await ctx.send(f"Details of task: {t.show_details()}")
        else:
            await ctx.send("Invalid task number. Please check your list using !list.")

    @commands.command(name="clear", help="Clear your to-do list. Usage: !clear")
    async def clear_tasks(self, ctx):
        channel_id = ctx.channel.id
        user_id = ctx.author.id
        todo_lists[channel_id][user_id] = []
        await ctx.send("Your to-do list has been cleared.")
        await save_changes(ctx)


class MaintenanceCog(commands.Cog):
    """Maintenance commands for the to-do list system."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="save", help="Manually save your to-do lists. Usage: !save")
    async def save_command(self, ctx):
        filename = await save_changes(ctx)
        await ctx.send(f"Your to-do lists have been saved to '{filename}'.")

    @commands.command(
        name="load", help="Load to-do lists from a JSON file. Usage: !load <filename>"
    )
    async def load_command(self, ctx, filename: str):
        success = await load_todo_lists_from_file(ctx, filename)
        if success:
            await ctx.send(f"Successfully loaded to-do lists from '{filename}'.")
        else:
            await ctx.send(
                f"Failed to load to-do lists from '{filename}'. Make sure the file exists and is in the correct format."
            )

    @commands.command(
        name="list_files", help="List all saved to-do list files. Usage: !list_files"
    )
    async def list_files_command(self, ctx):
        files = [
            f
            for f in os.listdir(".")
            if f.startswith("todo_lists_") and f.endswith(".json")
        ]
        files.sort(key=lambda x: os.path.getctime(x))
        if files:
            files_list = "\n".join(files)
            await ctx.send(f"**Available to-do list files:**\n{files_list}")
        else:
            await ctx.send("No saved to-do list files found.")


@bot.event
async def on_ready():
    if bot.user:
        print(f"Logged in as {bot.user.name}")
        print(f"SessionID: {SessionID}")
    else:
        print("Failed to log in")

    # Load cogs
    await bot.add_cog(TodoCog(bot))
    await bot.add_cog(MaintenanceCog(bot))


@bot.listen("on_message")
async def print_message(message):
    print(
        f"Received message from {message.author} in {message.channel}: {message.content}"
    )


bot.run(TOKEN)
