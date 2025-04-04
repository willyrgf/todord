# Todord - A Discord To-Do List Bot

Todord is a Discord bot that helps you manage to-do lists in your Discord channels.

## Features

- Create and manage to-do lists in Discord channels
- Mark tasks as done or closed
- Add logs to tasks
- View task details with complete history tracking
- Track who created tasks and made changes
- Edit task titles
- Save and load task lists

## Usage

### Using Nix (recommended)

```sh
DISCORD_TOKEN="your_discord_token" nix run 'github:willyrgf/todord'
```

### Running directly

```sh
# Set your Discord token as an environment variable
export DISCORD_TOKEN="your_discord_token"

# Run the bot
python todord.py
```

Or specify the token and other options via command-line arguments:

```sh
python todord.py --token "your_discord_token" --data_dir "./my_data" --debug
```

## Bot Commands

- `!add <task>` - Add a task to the channel's to-do list
- `!list` - List all tasks in the channel
- `!done <task number>` - Mark a task as done
- `!close <task number>` - Close a task
- `!log <task number> <log>` - Add a log to a task
- `!details <task number>` - Show details of a task including full history and who made changes
- `!edit <task number> <new title>` - Edit a task's title
- `!clear` - Clear the channel's to-do list
- `!save` - Manually save your to-do lists
- `!load <filename>` - Load to-do lists from a JSON file
- `!list_files` - List all saved to-do list files

