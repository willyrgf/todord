import discord
from discord.ext import commands

# Set up the bot with a command prefix.
bot = commands.Bot(command_prefix='!')

# In-memory dictionary to store to-do lists for each user.
todo_lists = {}

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.command(name='add', help='Add a task to your to-do list. Usage: !add <task>')
async def add_task(ctx, *, task: str):
    user_id = ctx.author.id
    # Create a new list if user does not have one.
    if user_id not in todo_lists:
        todo_lists[user_id] = []
    todo_lists[user_id].append(task)
    await ctx.send(f"Task added: **{task}**")

@bot.command(name='list', help='List all tasks in your to-do list. Usage: !list')
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

@bot.command(name='remove', help='Remove a task by its number. Usage: !remove <task number>')
async def remove_task(ctx, task_number: int):
    user_id = ctx.author.id
    tasks = todo_lists.get(user_id, [])
    if 0 < task_number <= len(tasks):
        removed = tasks.pop(task_number - 1)
        await ctx.send(f"Removed task: **{removed}**")
    else:
        await ctx.send("Invalid task number. Please check your list using !list.")

@bot.command(name='clear', help='Clear your to-do list. Usage: !clear')
async def clear_tasks(ctx):
    user_id = ctx.author.id
    todo_lists[user_id] = []
    await ctx.send("Your to-do list has been cleared.")

# Replace 'YOUR_BOT_TOKEN' with your bot's token.
bot.run('YOUR_BOT_TOKEN')

