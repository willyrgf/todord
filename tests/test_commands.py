import unittest
from unittest.mock import MagicMock, AsyncMock
import sys
from pathlib import Path

# Add the parent directory to sys.path to import the module
sys.path.append(str(Path(__file__).parent.parent))

from todord import TodoList, StorageManager


class TestTodoListCommands(unittest.IsolatedAsyncioTestCase):
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

    async def test_add_task(self):
        # Access the callback directly instead of calling the decorated command
        # This way we avoid Discord's command handling logic
        # Type ignoring since we know it works at runtime even if type checker is confused
        # about the parameter structure
        await self.todo_list.add_task.callback(
            self.todo_list,
            self.mock_ctx,  # type: ignore
            task="Test Task",
        )

        # Assert that the task was added to the storage
        self.assertIn(self.mock_ctx.channel.id, self.mock_storage.todo_lists)
        tasks = self.mock_storage.todo_lists[self.mock_ctx.channel.id]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].title, "Test Task")
        self.assertEqual(tasks[0].status, "pending")

        # Assert that the reply method was called
        self.mock_ctx.reply.assert_called_once()

        # Assert that save was called
        self.mock_storage.save.assert_called_once_with(self.mock_ctx)

    async def test_list_tasks_empty(self):
        # Ensure the list is empty
        self.mock_storage.todo_lists = {}

        # Call the list_tasks method directly via callback
        await self.todo_list.list_tasks.callback(
            self.todo_list,
            self.mock_ctx,  # type: ignore
        )

        # Assert that the reply was called with a message indicating no tasks
        self.mock_ctx.reply.assert_called_once()
        # Extract the embed from the call
        _, kwargs = self.mock_ctx.reply.call_args
        embed = kwargs["embed"]
        self.assertIn("no tasks", embed.description.lower())

    async def test_list_tasks_with_items(self):
        # Add a couple of mock tasks
        channel_id = self.mock_ctx.channel.id

        # Create mocks with proper string representation
        mock_task1 = MagicMock()
        mock_task1.status = "pending"
        mock_task1.title = "Task 1"
        # Use the __str__ override that works at runtime
        mock_task1.__str__.return_value = "[pending] Task 1"  # type: ignore

        mock_task2 = MagicMock()
        mock_task2.status = "in_progress"
        mock_task2.title = "Task 2"
        mock_task2.__str__.return_value = "[in_progress] Task 2"  # type: ignore

        self.mock_storage.todo_lists[channel_id] = [mock_task1, mock_task2]

        # Call the list_tasks method directly via callback
        await self.todo_list.list_tasks.callback(
            self.todo_list,
            self.mock_ctx,  # type: ignore
        )

        # Assert that the reply was called
        self.mock_ctx.reply.assert_called_once()

        # Extract the embed from the call
        _, kwargs = self.mock_ctx.reply.call_args
        embed = kwargs["embed"]

        # Check that both tasks are in the description
        self.assertIn("Task 1", embed.description)
        self.assertIn("Task 2", embed.description)

    async def test_done_task(self):
        # Add a mock task
        channel_id = self.mock_ctx.channel.id
        mock_task = MagicMock()
        mock_task.set_status = MagicMock()
        # Use the return_value approach instead of lambda
        mock_task.__str__.return_value = "[done] Test Task"  # type: ignore

        self.mock_storage.todo_lists[channel_id] = [mock_task]

        # Call the done_task method directly via callback
        await self.todo_list.done_task.callback(  # type: ignore
            self.todo_list,
            self.mock_ctx,
            task_number=1,  # type: ignore
        )

        # Assert that the task was marked as done
        mock_task.set_status.assert_called_once_with(self.mock_ctx, "done")

        # Assert that the task was removed from the list
        self.assertEqual(len(self.mock_storage.todo_lists[channel_id]), 0)

        # Assert that the reply was called
        self.mock_ctx.reply.assert_called_once()

        # Assert that save was called
        self.mock_storage.save.assert_called_once_with(self.mock_ctx)

    async def test_close_task(self):
        # Add a mock task
        channel_id = self.mock_ctx.channel.id
        mock_task = MagicMock()
        mock_task.set_status = MagicMock()
        mock_task.__str__.return_value = "[closed] Test Task"  # type: ignore

        self.mock_storage.todo_lists[channel_id] = [mock_task]

        # Call the close_task method directly via callback
        await self.todo_list.close_task.callback(
            self.todo_list,
            self.mock_ctx,
            task_number=1,  # type: ignore
        )

        # Assert that the task was marked as closed
        mock_task.set_status.assert_called_once_with(self.mock_ctx, "closed")

        # Assert that the task was removed from the list
        self.assertEqual(len(self.mock_storage.todo_lists[channel_id]), 0)

        # Assert that the reply method was called
        self.mock_ctx.reply.assert_called_once()

        # Assert that save was called
        self.mock_storage.save.assert_called_once_with(self.mock_ctx)

    async def test_log_task(self):
        # Add a mock task
        channel_id = self.mock_ctx.channel.id
        mock_task = MagicMock()
        mock_task.add_log = MagicMock()
        mock_task.show_details = MagicMock(return_value="Task details")

        self.mock_storage.todo_lists[channel_id] = [mock_task]

        # Call the log_task method directly via callback
        await self.todo_list.log_task.callback(
            self.todo_list, 
            self.mock_ctx,
            task_number=1,  # type: ignore
            log="Test log entry",
        )

        # Assert that the log was added to the task
        mock_task.add_log.assert_called_once_with(self.mock_ctx, "Test log entry")

        # Assert that the reply method was called
        self.mock_ctx.reply.assert_called_once()

        # Assert that save was called
        self.mock_storage.save.assert_called_once_with(self.mock_ctx)

    async def test_details_task(self):
        # Add a mock task
        channel_id = self.mock_ctx.channel.id
        mock_task = MagicMock()
        mock_task.show_details = MagicMock(return_value="Task details with logs and history")

        self.mock_storage.todo_lists[channel_id] = [mock_task]

        # Call the details_task method directly via callback
        await self.todo_list.details_task.callback(
            self.todo_list,
            self.mock_ctx,
            task_number=1,  # type: ignore
        )

        # Assert that show_details was called
        mock_task.show_details.assert_called_once()

        # Assert that the reply method was called
        self.mock_ctx.reply.assert_called_once()

        # Check the embed content
        _, kwargs = self.mock_ctx.reply.call_args
        embed = kwargs["embed"]
        self.assertIn("Task details with logs and history", embed.description)

    async def test_edit_task(self):
        # Add a mock task
        channel_id = self.mock_ctx.channel.id
        mock_task = MagicMock()
        mock_task.title = "Original Title"
        mock_task.set_title = MagicMock()

        self.mock_storage.todo_lists[channel_id] = [mock_task]

        # Call the edit_task method directly via callback
        await self.todo_list.edit_task.callback(
            self.todo_list,
            self.mock_ctx,
            task_number=1,  # type: ignore
            new_title="Updated Title",
        )

        # Assert that set_title was called with the new title
        mock_task.set_title.assert_called_once_with(self.mock_ctx, "Updated Title")

        # Assert that the reply method was called
        self.mock_ctx.reply.assert_called_once()

        # Assert that save was called
        self.mock_storage.save.assert_called_once_with(self.mock_ctx)

    async def test_invalid_task_number(self):
        # Add a mock task
        channel_id = self.mock_ctx.channel.id
        mock_task = MagicMock()
        self.mock_storage.todo_lists[channel_id] = [mock_task]

        # Call methods with invalid task numbers via callback
        await self.todo_list.done_task.callback(
            self.todo_list,
            self.mock_ctx,
            task_number=999,  # type: ignore
        )

        # Assert error replies were sent
        self.mock_ctx.reply.assert_called_once()

        # Extract the embed from the call
        _, kwargs = self.mock_ctx.reply.call_args
        embed = kwargs["embed"]
        self.assertIn("invalid task number", embed.description.lower())


if __name__ == "__main__":
    unittest.main()
