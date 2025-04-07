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
- **Optional:** Automatically sync task data with a Git repository using `syng`

## Usage

### Running the Bot (Standard)

#### Using Nix (recommended)

```sh
# Required: Set your Discord token
# Run the bot (data stored in ./data by default)
DISCORD_TOKEN="your_discord_token" nix run 'github:willyrgf/todord' -- --data_dir ./my_task_data
```

#### Running directly

```sh
# Required: Set your Discord token as an environment variable
# Run the bot (data stored in ./data by default)
export DISCORD_TOKEN="your_discord_token" python todord.py --data_dir ./my_task_data
```

### Running the Bot with Git Synchronization (`todord-syng`)

This mode runs the Todord bot and simultaneously uses `syng` to automatically synchronize the data directory with a Git repository.

#### Using Nix

```sh
# Run the bot, syncing data to a local git repository path
# The data_dir MUST be a path inside a git repository.
DISCORD_TOKEN="<TOKEN>" nix run 'github:willyrgf/todord#todord-syng' -- --data_dir /path/to/your/git/repo/data
```

**Explanation:**

*   `DISCORD_TOKEN`: Your Discord bot token (required).
*   `--data_dir`: The directory **within a Git repository** where Todord will store its data files (`.json` files). `syng` will monitor this directory, commit changes, and push/pull from the remote associated with the repository.
*   **SSH Authentication:** For `syng` to push/pull using SSH keys (e.g., with GitHub), ensure your SSH agent is running and configured in the terminal where you run the `nix run` command. The `todord-syng` script will automatically forward your `SSH_AUTH_SOCK` environment variable to enable `git` access.

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
- `!loadlast` - Load the most recent saved to-do list file
- `!list_files` - List all saved to-do list files

