import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import discord
from pathlib import Path

# Add the parent directory to sys.path to import the module
sys.path.append(str(Path(__file__).parent.parent))

from todord import CustomHelpCommand


class TestCustomHelpCommand(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Create the CustomHelpCommand instance
        self.help_command = CustomHelpCommand()
        
        # Set up mock destination
        self.mock_destination = AsyncMock()
        self.help_command.get_destination = MagicMock(return_value=self.mock_destination)
        
        # Set up mock context
        self.mock_context = MagicMock()
        self.help_command.context = self.mock_context

    async def test_send_bot_help(self):
        """Test sending the main help page."""
        # Create a mock cog with commands
        mock_cog = MagicMock()
        mock_cog.qualified_name = "TestCog"
        mock_cog.description = "Test cog description"
        
        # Create mock commands for the cog
        mock_command1 = MagicMock()
        mock_command1.name = "test"
        mock_command1.short_doc = "Test command description"
        mock_command1.aliases = ["t"]
        mock_command1.signature = "<arg>"
        
        mock_command2 = MagicMock()
        mock_command2.name = "other"
        mock_command2.short_doc = "Other command description"
        mock_command2.aliases = []
        mock_command2.signature = ""
        
        # Mock the filter_commands method to return our commands
        self.help_command.filter_commands = AsyncMock(return_value=[mock_command1, mock_command2])
        
        # Create the mapping for the help command
        mapping = {mock_cog: [mock_command1, mock_command2]}
        
        # Call the method
        await self.help_command.send_bot_help(mapping)
        
        # Verify destination was called with an embed
        self.mock_destination.send.assert_called_once()
        _, kwargs = self.mock_destination.send.call_args
        embed = kwargs["embed"]
        
        # Verify embed content
        self.assertEqual(embed.title, "!help command:")
        self.assertIsInstance(embed.color, discord.Color)
        
        # Verify fields contain our commands
        found_cog_field = False
        for field in embed.fields:
            if "TestCog" in field.name:
                found_cog_field = True
                self.assertIn("Test cog description", field.name)
                self.assertIn("!test", field.value)
                self.assertIn("!t", field.value)
                self.assertIn("!other", field.value)
        
        self.assertTrue(found_cog_field, "Cog field not found in embed")
        
        # Verify footer has hint about command help
        self.assertIn("Type !help <command>", embed.footer.text)

    async def test_send_command_help(self):
        """Test sending help for a specific command."""
        # Create a mock command
        mock_command = MagicMock()
        mock_command.name = "test"
        mock_command.help = "Detailed help for test command"
        mock_command.aliases = ["t", "tst"]
        mock_command.signature = "<required> [optional]"
        
        # Call the method
        await self.help_command.send_command_help(mock_command)
        
        # Verify destination was called with an embed
        self.mock_destination.send.assert_called_once()
        _, kwargs = self.mock_destination.send.call_args
        embed = kwargs["embed"]
        
        # Verify embed content
        self.assertEqual(embed.title, "Command: !test")
        self.assertIsInstance(embed.color, discord.Color)
        
        # Verify fields
        field_names = [field.name for field in embed.fields]
        field_values = [field.value for field in embed.fields]
        
        self.assertIn("Aliases", field_names)
        self.assertIn("Description", field_names)
        self.assertIn("Usage", field_names)
        
        # Check aliases field
        aliases_index = field_names.index("Aliases")
        self.assertIn("!t", field_values[aliases_index])
        self.assertIn("!tst", field_values[aliases_index])
        
        # Check description field
        description_index = field_names.index("Description")
        self.assertEqual(field_values[description_index], "Detailed help for test command")
        
        # Check usage field
        usage_index = field_names.index("Usage")
        self.assertEqual(field_values[usage_index], "`!test <required> [optional]`")

    async def test_send_cog_help(self):
        """Test sending help for a cog."""
        # Create a mock cog
        mock_cog = MagicMock()
        mock_cog.qualified_name = "TestCog"
        mock_cog.description = "This is a test cog"
        
        # Create mock commands for the cog
        mock_command1 = MagicMock()
        mock_command1.name = "test1"
        mock_command1.short_doc = "First test command"
        mock_command1.aliases = ["t1"]
        
        mock_command2 = MagicMock()
        mock_command2.name = "test2"
        mock_command2.short_doc = "Second test command"
        mock_command2.aliases = []
        
        # Set up the mock get_commands method
        mock_cog.get_commands.return_value = [mock_command1, mock_command2]
        
        # Mock the filter_commands method to return all commands
        self.help_command.filter_commands = AsyncMock(return_value=[mock_command1, mock_command2])
        
        # Call the method
        await self.help_command.send_cog_help(mock_cog)
        
        # Verify destination was called with an embed
        self.mock_destination.send.assert_called_once()
        _, kwargs = self.mock_destination.send.call_args
        embed = kwargs["embed"]
        
        # Verify embed content
        self.assertEqual(embed.title, "Category: TestCog")
        self.assertEqual(embed.description, "This is a test cog")
        self.assertIsInstance(embed.color, discord.Color)
        
        # Verify fields contain our commands
        field_names = [field.name for field in embed.fields]
        field_values = [field.value for field in embed.fields]
        
        # First command should be in the embed
        self.assertTrue(any("!test1" in name for name in field_names))
        self.assertTrue(any("First test command" in value for value in field_values))
        
        # Second command should be in the embed
        self.assertTrue(any("!test2" in name for name in field_names))
        self.assertTrue(any("Second test command" in value for value in field_values))

    async def test_send_error_message(self):
        """Test sending an error message."""
        # Call the method with an error
        await self.help_command.send_error_message("This is a test error")
        
        # Verify destination was called with an embed
        self.mock_destination.send.assert_called_once()
        _, kwargs = self.mock_destination.send.call_args
        embed = kwargs["embed"]
        
        # Verify embed content
        self.assertEqual(embed.title, "Error")
        self.assertEqual(embed.description, "This is a test error")
        self.assertIsInstance(embed.color, discord.Color)
        self.assertEqual(embed.color, discord.Color.red())


if __name__ == "__main__":
    unittest.main() 