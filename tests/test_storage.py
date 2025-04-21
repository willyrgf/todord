import unittest
from unittest.mock import MagicMock, patch
import sys
import tempfile
import json
from pathlib import Path
import shutil

import todord

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
        # Update format to include 'Z'
        mock_time.strftime.return_value = "2023-01-01_12-00-00Z"
        mock_datetime.now.return_value = mock_time

        # Create a test task and add it to a channel's todo list
        channel_id = 123456789
        test_task = Task(self.mock_ctx, 0, "Test Task", "pending")
        self.storage.todo_lists[channel_id] = [test_task]

        # Save the state
        filename = await self.storage.save(self.mock_ctx)

        # Verify the expected filename - update to include 'Z'
        expected_filename = f"{todord.APP_NAME}_{self.session_id}_2023-01-01_12-00-00Z.json"
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
        # Create some test files with timestamps out of order - update to include 'Z'
        valid_files_unsorted = [
            f"{todord.APP_NAME}_{self.session_id}_2023-01-02_10-00-00Z.json",
            f"{todord.APP_NAME}_{self.session_id}_2023-01-01_12-00-00Z.json",
            f"{todord.APP_NAME}_{self.session_id}_2023-01-02_09-30-00Z.json",
        ]
        # Update expected sorted list to include 'Z'
        expected_sorted_files = [
            f"{todord.APP_NAME}_{self.session_id}_2023-01-01_12-00-00Z.json",
            f"{todord.APP_NAME}_{self.session_id}_2023-01-02_09-30-00Z.json",
            f"{todord.APP_NAME}_{self.session_id}_2023-01-02_10-00-00Z.json",
        ]

        # These should still be invalid with the new 'Z' requirement
        invalid_files = [
            f"malformed_{todord.APP_NAME}_{self.session_id}_2023-01-03_12-00-00Z.json", # Malformed prefix
            f"{todord.APP_NAME}_{self.session_id}_nodateZ.json", # Missing date part
            "other_file.txt", # Wrong name structure and extension
            f"{todord.APP_NAME}_{self.session_id}_2023-01-04_12-00-00Z.txt", # Wrong extension
            f"{todord.APP_NAME}_{self.session_id}_2023-01-05_12-00-00.json", # Missing Z
        ]

        all_files_to_create = valid_files_unsorted + invalid_files

        for filename in all_files_to_create:
            file_path = Path(self.temp_dir) / filename
            with open(file_path, "w") as f:
                f.write("{}")  # Empty JSON object

        # Get the list of files
        listed_files = self.storage.list_saved_files()

        # Verify only valid files are returned and they are sorted correctly
        self.assertEqual(len(listed_files), len(expected_sorted_files))
        self.assertEqual(listed_files, expected_sorted_files)

    async def test_load_invalid_filename(self):
        """Test that loading fails for filenames with invalid formats."""
        # Update invalid files list relative to the new 'Z' requirement
        invalid_files = [
            f"malformed_{todord.APP_NAME}_{self.session_id}_2023-01-03_12-00-00Z.json", # Malformed prefix
            f"{todord.APP_NAME}_{self.session_id}_nodateZ.json", # Missing date part
            "other_file.txt", # Wrong name structure and extension
            f"{todord.APP_NAME}_{self.session_id}_2023-01-04_12-00-00Z.txt", # Wrong extension
            f"{todord.APP_NAME}_{self.session_id}_2023-01-05_12-00-00.json", # Missing Z
            f"../{todord.APP_NAME}_{self.session_id}_2023-01-01_12-00-00Z.json", # Path traversal attempt
        ]

        # Create dummy files for invalid names (optional, load should fail based on name alone)
        for filename in invalid_files:
            # Avoid creating files outside the temp dir for the path traversal case
            if "../" not in filename:
                file_path = Path(self.temp_dir) / filename
                try:
                    with open(file_path, "w") as f:
                        f.write("{}")
                except OSError as e:
                    # Handle cases where filename might be invalid for the OS
                    print(f"Skipping file creation for {filename}: {e}")

        # Ensure todo_lists is empty before testing load failures
        self.storage.todo_lists = {}

        for filename in invalid_files:
            with self.subTest(filename=filename):
                success = await self.storage.load(self.mock_ctx, filename)
                self.assertFalse(
                    success, f"Load should have failed for invalid filename: {filename}"
                )
                # Ensure the invalid load attempt didn't modify the internal state
                self.assertEqual(self.storage.todo_lists, {})


if __name__ == "__main__":
    unittest.main()
