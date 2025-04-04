import unittest
from unittest.mock import MagicMock, patch
import sys
import tempfile
import json
from pathlib import Path
import shutil

# Add the parent directory to sys.path to import the module
sys.path.append(str(Path(__file__).parent.parent))

from todord import StorageManager, Task


class TestStorageManager(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Create a temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.session_id = "test_session_id"

        # Create the storage manager
        self.storage = StorageManager(self.temp_dir, self.session_id)

        # Create a mock context
        self.mock_ctx = MagicMock()
        self.mock_ctx.author.name = "test_user"

    def tearDown(self):
        # Clean up the temporary directory
        shutil.rmtree(self.temp_dir)

    @patch("todord.datetime")
    async def test_save_and_load(self, mock_datetime):
        # Mock datetime to return a fixed time for testing
        mock_time = MagicMock()
        mock_time.strftime.return_value = "2023-01-01_12-00-00"
        mock_datetime.now.return_value = mock_time

        # Create a test task and add it to a channel's todo list
        channel_id = 123456789
        test_task = Task(self.mock_ctx, 0, "Test Task", "pending")
        self.storage.todo_lists[channel_id] = [test_task]

        # Save the state
        filename = await self.storage.save(self.mock_ctx)

        # Verify the expected filename
        expected_filename = f"todo_lists_{self.session_id}_2023-01-01_12-00-00.json"
        self.assertEqual(filename, expected_filename)

        # Verify the file exists
        file_path = Path(self.temp_dir) / expected_filename
        self.assertTrue(file_path.exists())

        # Verify file contents
        with open(file_path, "r") as f:
            data = json.load(f)

        self.assertIn(
            str(channel_id), data
        )  # Channel ID is converted to string in JSON
        self.assertEqual(len(data[str(channel_id)]), 1)  # One task in the channel
        self.assertEqual(data[str(channel_id)][0]["title"], "Test Task")

        # Clear the todo lists and load
        self.storage.todo_lists = {}
        success = await self.storage.load(self.mock_ctx, expected_filename)

        # Verify load was successful
        self.assertTrue(success)
        self.assertIn(channel_id, self.storage.todo_lists)
        self.assertEqual(len(self.storage.todo_lists[channel_id]), 1)
        self.assertEqual(self.storage.todo_lists[channel_id][0].title, "Test Task")

    async def test_list_saved_files(self):
        # Create some test files
        test_files = [
            f"todo_lists_{self.session_id}_2023-01-01_12-00-00.json",
            f"todo_lists_{self.session_id}_2023-01-02_12-00-00.json",
        ]

        for filename in test_files:
            file_path = Path(self.temp_dir) / filename
            with open(file_path, "w") as f:
                f.write("{}")  # Empty JSON object

        # Add some non-matching files that should be ignored
        with open(Path(self.temp_dir) / "other_file.txt", "w") as f:
            f.write("not a todo list")

        # Get the list of files
        files = self.storage.list_saved_files()

        # Verify the correct files are returned
        self.assertEqual(len(files), 2)
        for filename in test_files:
            self.assertIn(filename, files)


if __name__ == "__main__":
    unittest.main()

