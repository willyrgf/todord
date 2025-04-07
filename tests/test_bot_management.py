import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import sys
from pathlib import Path

# Add the parent directory to sys.path to import the module
sys.path.append(str(Path(__file__).parent.parent))

from todord import BotManagement, StorageManager


class TestBotManagementCommands(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Mock the bot
        self.mock_bot = MagicMock()

        # Mock the storage manager
        self.mock_storage = MagicMock(spec=StorageManager)
        self.mock_storage.todo_lists = {}
        self.mock_storage.save = AsyncMock(return_value="test_save.json")
        self.mock_storage.load = AsyncMock(return_value=True)  # Default to successful load
        self.mock_storage.list_saved_files = MagicMock(return_value=["file1.json", "file2.json"])

        # Create the BotManagement cog
        self.bot_management = BotManagement(self.mock_bot, self.mock_storage)

        # Create a mock context
        self.mock_ctx = MagicMock()
        self.mock_ctx.author.name = "test_user"
        self.mock_ctx.channel.id = 123456789
        self.mock_ctx.reply = AsyncMock()
        self.mock_ctx.send = AsyncMock()

    async def test_clear_tasks_with_tasks(self):
        # Setup a channel with tasks
        channel_id = self.mock_ctx.channel.id
        self.mock_storage.todo_lists[channel_id] = [MagicMock(), MagicMock()]  # Two mock tasks

        # Call the clear_tasks method directly via callback
        await self.bot_management.clear_tasks.callback(
            self.bot_management,
            self.mock_ctx,  # type: ignore
        )

        # Assert the channel's tasks were cleared
        self.assertEqual(self.mock_storage.todo_lists[channel_id], [])

        # Assert that the reply method was called
        self.mock_ctx.reply.assert_called_once()

        # Extract the embed from the call
        _, kwargs = self.mock_ctx.reply.call_args
        embed = kwargs["embed"]
        self.assertIn("cleared", embed.description.lower())

        # Assert that save was called
        self.mock_storage.save.assert_called_once_with(self.mock_ctx)

    async def test_clear_tasks_empty(self):
        # Setup an empty channel
        channel_id = self.mock_ctx.channel.id
        self.mock_storage.todo_lists[channel_id] = []

        # Call the clear_tasks method directly via callback
        await self.bot_management.clear_tasks.callback(
            self.bot_management,
            self.mock_ctx,  # type: ignore
        )

        # Assert that the reply informs about no tasks
        self.mock_ctx.reply.assert_called_once()
        _, kwargs = self.mock_ctx.reply.call_args
        embed = kwargs["embed"]
        self.assertIn("no tasks", embed.description.lower())

        # Assert that save was not called
        self.mock_storage.save.assert_not_called()

    async def test_save_command_success(self):
        # Call the save_command method directly via callback
        await self.bot_management.save_command.callback(
            self.bot_management,
            self.mock_ctx,  # type: ignore
        )

        # Assert that storage.save was called
        self.mock_storage.save.assert_called_once_with(self.mock_ctx)

        # Assert that reply was called with success message
        self.mock_ctx.reply.assert_called_once()
        _, kwargs = self.mock_ctx.reply.call_args
        embed = kwargs["embed"]
        self.assertIn("test_save.json", embed.description)

    @patch("todord.logger.error")
    async def test_save_command_failure(self, mock_logger_error):
        # Make storage.save raise an exception
        self.mock_storage.save.side_effect = Exception("Test error")

        # Call the save_command method directly via callback
        await self.bot_management.save_command.callback(
            self.bot_management,
            self.mock_ctx,  # type: ignore
        )

        # Assert that logger.error was called
        mock_logger_error.assert_called()

        # Assert that reply was called with error message
        self.mock_ctx.reply.assert_called_once()
        _, kwargs = self.mock_ctx.reply.call_args
        embed = kwargs["embed"]
        self.assertIn("error", embed.title.lower())
        self.assertIn("Test error", embed.description)

    async def test_load_command_success(self):
        # Set up the storage manager to return success
        self.mock_storage.load.return_value = True

        # Call the load_command method directly via callback
        await self.bot_management.load_command.callback(
            self.bot_management,
            self.mock_ctx,  # type: ignore
            filename="valid_file.json",
        )

        # Assert that storage.load was called with the right filename
        self.mock_storage.load.assert_called_once_with(self.mock_ctx, "valid_file.json")

        # Assert that reply was called with success message
        self.mock_ctx.reply.assert_called_once()
        _, kwargs = self.mock_ctx.reply.call_args
        embed = kwargs["embed"]
        self.assertIn("successfully", embed.description.lower())

    async def test_load_command_invalid_filename(self):
        # Call the load_command method with an invalid filename
        await self.bot_management.load_command.callback(
            self.bot_management,
            self.mock_ctx,  # type: ignore
            filename="../invalid/path.json",
        )

        # Assert that storage.load was not called
        self.mock_storage.load.assert_not_called()

        # Assert that reply was called with error message
        self.mock_ctx.reply.assert_called_once()
        _, kwargs = self.mock_ctx.reply.call_args
        embed = kwargs["embed"]
        self.assertIn("invalid", embed.title.lower())

    async def test_load_command_failure(self):
        # Set up the storage manager to return failure
        self.mock_storage.load.return_value = False

        # Call the load_command method directly via callback
        await self.bot_management.load_command.callback(
            self.bot_management,
            self.mock_ctx,  # type: ignore
            filename="invalid_file.json",
        )

        # Assert that storage.load was called
        self.mock_storage.load.assert_called_once()

        # Assert that reply was called with error message
        self.mock_ctx.reply.assert_called_once()
        _, kwargs = self.mock_ctx.reply.call_args
        embed = kwargs["embed"]
        self.assertIn("failed", embed.description.lower())

    async def test_loadlast_command_with_files(self):
        # Set up mock files
        mock_files = ["file1.json", "file2.json", "most_recent.json"]
        self.mock_storage.list_saved_files.return_value = mock_files

        # Call the loadlast_command method directly via callback
        await self.bot_management.loadlast_command.callback(
            self.bot_management,
            self.mock_ctx,  # type: ignore
        )

        # Assert that list_saved_files was called
        self.mock_storage.list_saved_files.assert_called_once()

        # Assert that load was called with the most recent file
        self.mock_storage.load.assert_called_once_with(self.mock_ctx, "most_recent.json")

        # Assert that send was called with success message
        self.mock_ctx.send.assert_called_once()
        _, kwargs = self.mock_ctx.send.call_args
        embed = kwargs["embed"]
        self.assertIn("most_recent.json", embed.description)

    async def test_loadlast_command_no_files(self):
        # Set up mock to return no files
        self.mock_storage.list_saved_files.return_value = []

        # Call the loadlast_command method directly via callback
        await self.bot_management.loadlast_command.callback(
            self.bot_management,
            self.mock_ctx,  # type: ignore
        )

        # Assert that send was called with "no files" message
        self.mock_ctx.send.assert_called_once()
        _, kwargs = self.mock_ctx.send.call_args
        embed = kwargs["embed"]
        self.assertIn("no", embed.description.lower())
        self.assertIn("found", embed.description.lower())

        # Assert that load was not called
        self.mock_storage.load.assert_not_called()

    async def test_loadlast_command_load_failure(self):
        # Set up mock files
        mock_files = ["file1.json", "file2.json"]
        self.mock_storage.list_saved_files.return_value = mock_files
        # Make load return failure
        self.mock_storage.load.return_value = False

        # Call the loadlast_command method directly via callback
        await self.bot_management.loadlast_command.callback(
            self.bot_management,
            self.mock_ctx,  # type: ignore
        )

        # Assert that send was called with error message
        self.mock_ctx.send.assert_called_once()
        _, kwargs = self.mock_ctx.send.call_args
        embed = kwargs["embed"]
        self.assertIn("failed", embed.description.lower())

    async def test_list_files_command_with_files(self):
        # Set up mock files
        mock_files = ["file1.json", "file2.json"]
        self.mock_storage.list_saved_files.return_value = mock_files

        # Call the list_files_command method directly via callback
        await self.bot_management.list_files_command.callback(
            self.bot_management,
            self.mock_ctx,  # type: ignore
        )

        # Assert that list_saved_files was called
        self.mock_storage.list_saved_files.assert_called_once()

        # Assert that send was called with the file list
        self.mock_ctx.send.assert_called_once()
        _, kwargs = self.mock_ctx.send.call_args
        embed = kwargs["embed"]
        self.assertIn("file1.json", embed.description)
        self.assertIn("file2.json", embed.description)

    async def test_list_files_command_no_files(self):
        # Set up mock to return no files
        self.mock_storage.list_saved_files.return_value = []

        # Call the list_files_command method directly via callback
        await self.bot_management.list_files_command.callback(
            self.bot_management,
            self.mock_ctx,  # type: ignore
        )

        # Assert that send was called with "no files" message
        self.mock_ctx.send.assert_called_once()
        _, kwargs = self.mock_ctx.send.call_args
        embed = kwargs["embed"]
        self.assertIn("no", embed.description.lower())
        self.assertIn("found", embed.description.lower())

    @patch("todord.logger.error")
    async def test_list_files_command_error(self, mock_logger_error):
        # Make list_saved_files raise an exception
        self.mock_storage.list_saved_files.side_effect = Exception("Test error")

        # Call the list_files_command method directly via callback
        await self.bot_management.list_files_command.callback(
            self.bot_management,
            self.mock_ctx,  # type: ignore
        )

        # Assert that logger.error was called
        mock_logger_error.assert_called()

        # Assert that send was called with error message
        self.mock_ctx.send.assert_called_once()
        _, kwargs = self.mock_ctx.send.call_args
        embed = kwargs["embed"]
        self.assertIn("error", embed.title.lower())
        self.assertIn("Test error", embed.description)


if __name__ == "__main__":
    unittest.main() 