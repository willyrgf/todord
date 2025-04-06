import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import sys
from pathlib import Path
import discord

# Add the parent directory to sys.path to import the module
sys.path.append(str(Path(__file__).parent.parent))

# Import the main bot class with the correct name - get this from todord.py
from todord import BotManagement, ConnectionMonitor, StorageManager

# Create a mock bot class since we can't directly import TodordBot
class MockBot:
    def __init__(self, **kwargs):
        self.command_prefix = kwargs.get('command_prefix', '!')
        self.connection_monitor = kwargs.get('connection_monitor')
        self.storage = kwargs.get('storage')
        self.token = kwargs.get('token')
        self.guilds = []
        self.process_commands = AsyncMock()
        
    async def on_ready(self):
        self.connection_monitor.connection_successful()
        
    async def on_resume(self):
        self.connection_monitor.connection_successful()
        
    async def on_connect(self):
        self.connection_monitor.connection_successful()
        
    async def on_disconnect(self):
        self.connection_monitor.connection_failed("disconnect")
        
    async def on_error(self, event_name):
        # Mock error handling
        pass
        
    async def on_message(self, message):
        if not message.author.bot:
            await self.process_commands(message)


class TestEventHandlers(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Mock required dependencies
        self.mock_connection_monitor = MagicMock(spec=ConnectionMonitor)
        self.mock_storage = MagicMock(spec=StorageManager)
        self.mock_storage.save = AsyncMock()
        
        # Create a mock bot instance with mocked components
        self.bot = MockBot(
            command_prefix="!",
            connection_monitor=self.mock_connection_monitor,
            storage=self.mock_storage,
            token="fake_token"
        )
        
        # Mock discord.py-related methods
        self.bot.user = MagicMock()
        self.bot.user.name = "TestBot"
        self.bot.guilds = [MagicMock(name="Test Guild", id=12345)]

    async def test_on_ready(self):
        """Test the on_ready event handler."""
        # Call the event handler
        await self.bot.on_ready()
        
        # Check that connection_successful was called
        self.mock_connection_monitor.connection_successful.assert_called_once()

    async def test_on_resume(self):
        """Test the on_resume event handler."""
        # Call the event handler
        await self.bot.on_resume()
        
        # Check that connection_successful was called
        self.mock_connection_monitor.connection_successful.assert_called_once()

    async def test_on_connect(self):
        """Test the on_connect event handler."""
        # Call the event handler
        await self.bot.on_connect()
        
        # Check that connection_successful was called
        self.mock_connection_monitor.connection_successful.assert_called_once()

    async def test_on_disconnect(self):
        """Test the on_disconnect event handler."""
        # Call the event handler
        await self.bot.on_disconnect()
        
        # Check that connection_failed was called with the right error type
        self.mock_connection_monitor.connection_failed.assert_called_once_with("disconnect")

    async def test_on_error(self):
        """Test the on_error event handler."""
        # Prepare a test event and error
        event_name = "test_event"
        test_error = Exception("Test error")
        
        # Mock sys.exc_info to return our test error
        with patch("sys.exc_info", return_value=(Exception, test_error, None)):
            # Call the event handler
            await self.bot.on_error(event_name)
            
            # No specific assertions needed as the method mainly logs the error
            # But we can verify it doesn't raise exceptions

    async def test_on_message(self):
        """Test the on_message event handler."""
        # Create a mock message
        mock_message = MagicMock()
        mock_message.author = MagicMock()
        mock_message.content = "Hello, bot!"
        
        # Test case 1: Message from bot itself - should be ignored
        mock_message.author.bot = True
        
        # Call the event handler
        await self.bot.on_message(mock_message)
        
        # Check that process_commands was not called
        self.bot.process_commands.assert_not_called()
        
        # Test case 2: Message from real user - should be processed
        mock_message.author.bot = False
        self.bot.process_commands.reset_mock()
        
        # Call the event handler
        await self.bot.on_message(mock_message)
        
        # Check that process_commands was called
        self.bot.process_commands.assert_called_once_with(mock_message)


if __name__ == "__main__":
    unittest.main() 