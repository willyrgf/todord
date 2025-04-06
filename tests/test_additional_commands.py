import unittest
from unittest.mock import MagicMock, AsyncMock
import sys
from pathlib import Path

# Add the parent directory to sys.path to import the module
sys.path.append(str(Path(__file__).parent.parent))

from todord import TodoList, StorageManager


class TestAdditionalTodoListCommands(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Mock the bot
        self.mock_bot = MagicMock()

        # Mock the storage manager
        self.mock_storage = MagicMock(spec=StorageManager)
        self.mock_storage.todo_lists = {}
        self.mock_storage.save = AsyncMock(return_value="test_save.json")

        # Create the TodoList cog
        self.todo_list = TodoList(self.mock_bot, self.mock_storage)

        # Create a mock context
        self.mock_ctx = MagicMock()
        self.mock_ctx.author.name = "test_user"
        self.mock_ctx.channel.id = 123456789
        self.mock_ctx.reply = AsyncMock()

    async def test_close_task(self):
        # Add a mock task
        channel_id = self.mock_ctx.channel.id
        mock_task = MagicMock()
        mock_task.set_status = MagicMock()
        mock_task.__str__.return_value = "[closed] Test Task"
        
        self.mock_storage.todo_lists[channel_id] = [mock_task]

        # Call the close_task method
        await self.todo_list.close_task.callback(
            self.todo_list,
            self.mock_ctx,
            task_number=1,
        )

        # Assert that the task was marked as closed
        mock_task.set_status.assert_called_once_with(self.mock_ctx, "closed")

        # Assert that the task was removed from the list
        self.assertEqual(len(self.mock_storage.todo_lists[channel_id]), 0)

        # Assert that the reply was called
        self.mock_ctx.reply.assert_called_once()

        # Assert that save was called
        self.mock_storage.save.assert_called_once_with(self.mock_ctx)

    async def test_log_task(self):
        # Add a mock task
        channel_id = self.mock_ctx.channel.id
        mock_task = MagicMock()
        mock_task.add_log = MagicMock()
        mock_task.__str__.return_value = "[pending] Test Task"
        
        self.mock_storage.todo_lists[channel_id] = [mock_task]

        # Call the log_task method
        await self.todo_list.log_task.callback(
            self.todo_list,
            self.mock_ctx,
            task_number=1,
            log="Test log entry"
        )

        # Assert that the log was added to the task
        mock_task.add_log.assert_called_once_with(self.mock_ctx, "Test log entry")

        # Assert that the reply was called
        self.mock_ctx.reply.assert_called_once()

        # Assert that save was called
        self.mock_storage.save.assert_called_once_with(self.mock_ctx)

    async def test_details_task(self):
        # Add a mock task
        channel_id = self.mock_ctx.channel.id
        mock_task = MagicMock()
        mock_task.show_details.return_value = "Detailed task info"
        
        self.mock_storage.todo_lists[channel_id] = [mock_task]

        # Call the details_task method
        await self.todo_list.details_task.callback(
            self.todo_list,
            self.mock_ctx,
            task_number=1,
        )

        # Assert that show_details was called
        mock_task.show_details.assert_called_once()

        # Assert that the reply was called
        self.mock_ctx.reply.assert_called_once()

    async def test_edit_task(self):
        # Add a mock task
        channel_id = self.mock_ctx.channel.id
        mock_task = MagicMock()
        mock_task.set_title = MagicMock()
        mock_task.__str__.return_value = "[pending] Updated Task Title"
        
        self.mock_storage.todo_lists[channel_id] = [mock_task]

        # Call the edit_task method
        await self.todo_list.edit_task.callback(
            self.todo_list,
            self.mock_ctx,
            task_number=1,
            new_title="Updated Task Title"
        )

        # Assert that the title was updated
        mock_task.set_title.assert_called_once_with(self.mock_ctx, "Updated Task Title")

        # Assert that the reply was called
        self.mock_ctx.reply.assert_called_once()

        # Assert that save was called
        self.mock_storage.save.assert_called_once_with(self.mock_ctx)


if __name__ == "__main__":
    unittest.main() 