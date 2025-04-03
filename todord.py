import discord
import os
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("No DISCORD_TOKEN env configured.")
    exit(1)

# set up the bot with a command prefix.
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# In-memory dictionary to store to-do lists for each user.
todo_lists = {}


@bot.event
async def on_ready():
    if bot.user:
        print(f"Logged in as {bot.user.name}")
    else:
        print("Failed to log in")


@bot.listen("on_message")
async def print_message(message):
    print(
        f"Received message from {message.author} in {message.channel}: {message.content}"
    )


@bot.command(name="add", help="Add a task to your to-do list. Usage: !add <task>")
async def add_task(ctx, *, task: str):
    user_id = ctx.author.id
    # Create a new list if user does not have one.
    if user_id not in todo_lists:
        todo_lists[user_id] = []
    todo_lists[user_id].append(task)
    await ctx.send(f"Task added: **{task}**")


@bot.command(name="list", help="List all tasks in your to-do list. Usage: !list")
async def list_tasks(ctx):
    user_id = ctx.author.id
    tasks = todo_lists.get(user_id, [])
    if not tasks:
        await ctx.send("You have no tasks in your to-do list.")
        return

    response = "**Your To-Do List:**\n"
    for idx, task in enumerate(tasks, start=1):
        response += f"{idx}. {task}\n"
    await ctx.send(response)


@bot.command(
    name="remove", help="Remove a task by its number. Usage: !remove <task number>"
)
async def remove_task(ctx, task_number: int):
    user_id = ctx.author.id
    tasks = todo_lists.get(user_id, [])
    if 0 < task_number <= len(tasks):
        removed = tasks.pop(task_number - 1)
        await ctx.send(f"Removed task: **{removed}**")
    else:
        await ctx.send("Invalid task number. Please check your list using !list.")


@bot.command(name="clear", help="Clear your to-do list. Usage: !clear")
async def clear_tasks(ctx):
    user_id = ctx.author.id
    todo_lists[user_id] = []
    await ctx.send("Your to-do list has been cleared.")


bot.run(TOKEN)
