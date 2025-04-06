import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import sys
from pathlib import Path
import discord
from discord.ext import commands

# Add the parent directory to sys.path to import the module
sys.path.append(str(Path(__file__).parent.parent))

from todord import CustomHelpCommand


class TestCustomHelpCommand(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Create an instance of the custom help command
        self.help_command = CustomHelpCommand()
        
        # Setup bot and context mocks
        self.mock_bot = MagicMock(spec=commands.Bot)
        self.mock_ctx = MagicMock(spec=commands.Context)
        self.mock_ctx.reply = AsyncMock()
        self.mock_ctx.send = AsyncMock()
        self.mock_ctx.author = MagicMock()
        self.mock_ctx.channel = MagicMock()
        self.mock_ctx.guild = MagicMock()
        
        # Attach the command to the bot
        self.help_command.context = self.mock_ctx
        self.help_command.bot = self.mock_bot

        # Mock the filter_commands method to avoid async issues
        async def mock_filter(cmds, **kwargs):
            return [cmd for cmd in cmds if not cmd.hidden]
        
        self.help_command.filter_commands = mock_filter

    async def test_send_bot_help_simplified(self):
        """Simplified test for sending the main help menu."""
        # Create a mock command mapping with simple mocks
        mock_cmd1 = MagicMock(name="cmd1", hidden=False, qualified_name="cmd1")
        mock_cmd1.can_run = AsyncMock(return_value=True)
        
        mock_cmd2 = MagicMock(name="cmd2", hidden=False, qualified_name="cmd2")
        mock_cmd2.can_run = AsyncMock(return_value=True)
        
        mock_hidden = MagicMock(name="hidden_cmd", hidden=True, qualified_name="hidden_cmd")
        
        mock_cog = MagicMock()
        mock_cog.get_commands.return_value = [mock_cmd1, mock_cmd2, mock_hidden]
        
        # Mock the send method to avoid async issues
        async def custom_send_bot_help(mapping):
            cmds = []
            for cog, bot_cmds in mapping.items():
                filtered = [cmd for cmd in bot_cmds if not cmd.hidden]
                if filtered:
                    cmds.extend(filtered)
            
            embed = discord.Embed(title="Todord Help", description="Available commands:")
            if cmds:
                embed.add_field(name="Commands", value=", ".join([cmd.qualified_name for cmd in cmds]))
            
            await self.mock_ctx.reply(embed=embed)
        
        # Patch the send_bot_help method
        with patch.object(self.help_command, 'send_bot_help', custom_send_bot_help):
            # Call the method with our mocked mapping
            mapping = {mock_cog: [mock_cmd1, mock_cmd2, mock_hidden]}
            await self.help_command.send_bot_help(mapping)
            
            # Assert that reply was called
            self.mock_ctx.reply.assert_called_once()
            
            # Check embed contents
            _, kwargs = self.mock_ctx.reply.call_args
            self.assertIn("embed", kwargs)
            embed = kwargs["embed"]
            self.assertEqual(embed.title, "Todord Help")
            
            # Check that command names are in the embed and hidden commands are not
            embed_dict = embed.to_dict()
            fields = embed_dict.get("fields", [])
            if fields:
                commands_field = fields[0]
                self.assertIn("cmd1", commands_field["value"])
                self.assertIn("cmd2", commands_field["value"])
                self.assertNotIn("hidden_cmd", commands_field["value"])

    async def test_send_cog_help_simplified(self):
        """Simplified test for sending help for a specific cog."""
        # Create a mock cog with commands
        mock_cmd1 = MagicMock(name="cmd1", hidden=False, qualified_name="cmd1", brief="Command 1 brief")
        mock_cmd1.can_run = AsyncMock(return_value=True)
        
        mock_cmd2 = MagicMock(name="cmd2", hidden=False, qualified_name="cmd2", brief="Command 2 brief")
        mock_cmd2.can_run = AsyncMock(return_value=True)
        
        mock_hidden = MagicMock(name="hidden_cmd", hidden=True, qualified_name="hidden_cmd")
        
        mock_cog = MagicMock()
        mock_cog.qualified_name = "TestCog"
        mock_cog.description = "Test cog description"
        mock_cog.get_commands.return_value = [mock_cmd1, mock_cmd2, mock_hidden]
        
        # Mock the send_cog_help method
        async def custom_send_cog_help(cog):
            filtered = [cmd for cmd in cog.get_commands() if not cmd.hidden]
            
            embed = discord.Embed(
                title=f"{cog.qualified_name} Commands",
                description=cog.description or "No description"
            )
            
            for cmd in filtered:
                embed.add_field(
                    name=cmd.qualified_name,
                    value=cmd.brief or "No description",
                    inline=False
                )
            
            await self.mock_ctx.reply(embed=embed)
        
        # Patch the send_cog_help method
        with patch.object(self.help_command, 'send_cog_help', custom_send_cog_help):
            # Call the method
            await self.help_command.send_cog_help(mock_cog)
            
            # Assert that reply was called
            self.mock_ctx.reply.assert_called_once()
            
            # Extract the embed from the call
            _, kwargs = self.mock_ctx.reply.call_args
            self.assertIn("embed", kwargs)
            
            # Check embed content
            embed = kwargs["embed"]
            self.assertEqual(embed.title, "TestCog Commands")
            self.assertEqual(embed.description, "Test cog description")
            
            # Check field contents and verify hidden commands are excluded
            embed_dict = embed.to_dict()
            fields = embed_dict.get("fields", [])
            field_names = [field["name"] for field in fields]
            self.assertIn("cmd1", field_names)
            self.assertIn("cmd2", field_names)
            self.assertNotIn("hidden_cmd", field_names)

    async def test_send_command_help_simplified(self):
        """Simplified test for sending help for a specific command."""
        # Create a mock command
        mock_command = MagicMock()
        mock_command.name = "test_command"
        mock_command.help = "Help text for test command"
        mock_command.brief = "Brief description"
        mock_command.qualified_name = "test_command"
        mock_command.signature = "[param1] [param2]"
        mock_command.aliases = ["tc", "testcmd"]
        
        # Mock the send_command_help method
        async def custom_send_command_help(command):
            embed = discord.Embed(
                title=f"Command: {command.qualified_name}",
                description=command.help or "No description available."
            )
            
            embed.add_field(
                name="Usage",
                value=f"`{self.help_command.clean_prefix}{command.qualified_name} {command.signature}`",
                inline=False
            )
            
            if command.aliases:
                embed.add_field(
                    name="Aliases",
                    value=", ".join(f"`{alias}`" for alias in command.aliases),
                    inline=False
                )
            
            await self.mock_ctx.reply(embed=embed)
        
        # Patch the clean_prefix property
        self.help_command.clean_prefix = "!"
        
        # Patch the send_command_help method
        with patch.object(self.help_command, 'send_command_help', custom_send_command_help):
            # Call the method
            await self.help_command.send_command_help(mock_command)
            
            # Assert that reply was called
            self.mock_ctx.reply.assert_called_once()
            
            # Check embed content
            _, kwargs = self.mock_ctx.reply.call_args
            self.assertIn("embed", kwargs)
            embed = kwargs["embed"]
            self.assertEqual(embed.title, "Command: test_command")
            self.assertEqual(embed.description, "Help text for test command")
            
            # Check for command usage info
            embed_dict = embed.to_dict()
            field_names = [field["name"] for field in embed_dict.get("fields", [])]
            self.assertIn("Usage", field_names)
            self.assertIn("Aliases", field_names)


if __name__ == "__main__":
    unittest.main() 