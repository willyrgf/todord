import unittest
from unittest.mock import MagicMock
import sys
from pathlib import Path

# Add the parent directory to sys.path to import the module
sys.path.append(str(Path(__file__).parent.parent))

from todord import Task, TaskEvent


class TestTask(unittest.TestCase):
    def setUp(self):
        # Create a mock Context object
        self.mock_ctx = MagicMock()
        self.mock_ctx.author.name = "test_user"

        # Create a test task
        self.task = Task(ctx=self.mock_ctx, id=1, title="Test Task", status="pending")

    def test_task_initialization(self):
        """Test that a task is properly initialized with correct values."""
        self.assertEqual(self.task.id, 1)
        self.assertEqual(self.task.title, "Test Task")
        self.assertEqual(self.task.status, "pending")
        self.assertEqual(self.task.creator, "test_user")
        self.assertEqual(len(self.task.logs), 0)

        # Check that an internal log was created for task creation
        self.assertEqual(len(self.task.internal_logs), 1)
        _, user, action = self.task.internal_logs[0]
        self.assertEqual(user, "test_user")
        self.assertEqual(action, TaskEvent.CREATED)

    def test_add_log(self):
        """Test adding a log to a task."""
        self.task.add_log(self.mock_ctx, "Test log message")

        # Check the user log was added
        self.assertEqual(len(self.task.logs), 1)
        self.assertEqual(self.task.logs[0], "Test log message")

        # Check that an internal log was created for the log addition
        self.assertEqual(len(self.task.internal_logs), 2)
        _, user, action = self.task.internal_logs[1]
        self.assertEqual(user, "test_user")
        self.assertTrue(action.startswith(TaskEvent.LOG_ADDED))
        self.assertTrue("Test log message" in action)

    def test_set_status(self):
        """Test changing a task's status."""
        self.task.set_status(self.mock_ctx, "done")

        # Check status was updated
        self.assertEqual(self.task.status, "done")

        # Check internal log was added
        self.assertEqual(len(self.task.internal_logs), 2)
        _, user, action = self.task.internal_logs[1]
        self.assertEqual(user, "test_user")
        self.assertTrue(action.startswith(TaskEvent.STATUS_UPDATED))
        self.assertTrue("from 'pending' to 'done'" in action)

    def test_set_title(self):
        """Test changing a task's title."""
        self.task.set_title(self.mock_ctx, "Updated Task Title")

        # Check title was updated
        self.assertEqual(self.task.title, "Updated Task Title")

        # Check internal log was added
        self.assertEqual(len(self.task.internal_logs), 2)
        _, user, action = self.task.internal_logs[1]
        self.assertEqual(user, "test_user")
        self.assertTrue(action.startswith(TaskEvent.TITLE_EDITED))

    def test_show_details(self):
        """Test the formatted details output."""
        # Add a log and change status to create more details
        self.task.add_log(self.mock_ctx, "Progress update")
        self.task.set_status(self.mock_ctx, "in_progress")

        # Get details
        details = self.task.show_details()

        # Basic assertions on the content
        self.assertTrue("[in_progress] Test Task" in details)
        self.assertTrue("Created by: test_user" in details)
        self.assertTrue("Progress update" in details)
        self.assertTrue("History:" in details)


if __name__ == "__main__":
    unittest.main()

