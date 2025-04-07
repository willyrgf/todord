import unittest
from unittest.mock import patch, MagicMock
import sys
from datetime import datetime
from pathlib import Path

# Add the parent directory to sys.path to import the module
sys.path.append(str(Path(__file__).parent.parent))

from todord import ConnectionMonitor


class TestConnectionMonitor(unittest.TestCase):
    def setUp(self):
        self.monitor = ConnectionMonitor(max_retries=3)

    def test_init(self):
        """Test initialization of the ConnectionMonitor."""
        self.assertEqual(self.monitor.max_retries, 3)
        self.assertEqual(self.monitor.consecutive_failures, 0)
        self.assertEqual(self.monitor.total_failures, 0)
        self.assertEqual(self.monitor.failure_types, {})
        self.assertIsNone(self.monitor.last_failure_time)
        self.assertIsNone(self.monitor.first_failure_time)

    @patch("todord.logger.info")
    def test_connection_successful_no_failures(self, mock_logger_info):
        """Test successful connection with no previous failures."""
        self.monitor.connection_successful()
        self.assertEqual(self.monitor.consecutive_failures, 0)
        mock_logger_info.assert_not_called()

    @patch("todord.logger.info")
    def test_connection_successful_after_failures(self, mock_logger_info):
        """Test successful connection after previous failures."""
        # Set up failures first
        self.monitor.consecutive_failures = 2
        
        # Call the method
        self.monitor.connection_successful()
        
        # Verify failures reset
        self.assertEqual(self.monitor.consecutive_failures, 0)
        
        # Verify log message
        mock_logger_info.assert_called_once()
        message = mock_logger_info.call_args[0][0]
        self.assertIn("2 consecutive failures", message)
        
    @patch("todord.datetime")
    @patch("todord.logger.warning")
    def test_connection_failed_first_failure(self, mock_logger_warning, mock_datetime):
        """Test the first connection failure."""
        # Mock the datetime.now() call
        now = datetime(2023, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = now
        
        # Call the method
        result = self.monitor.connection_failed("TestError")
        
        # Verify state changes
        self.assertEqual(self.monitor.consecutive_failures, 1)
        self.assertEqual(self.monitor.total_failures, 1)
        self.assertEqual(self.monitor.failure_types, {"TestError": 1})
        self.assertEqual(self.monitor.first_failure_time, now)
        self.assertEqual(self.monitor.last_failure_time, now)
        
        # Verify return value (shouldn't trigger exit yet)
        self.assertFalse(result)
        
        # Verify log message
        mock_logger_warning.assert_called_once()
        message = mock_logger_warning.call_args[0][0]
        self.assertIn("Connection failure #1: TestError", message)

    @patch("todord.datetime")
    @patch("todord.logger.warning")
    def test_connection_failed_subsequent_failure(self, mock_logger_warning, mock_datetime):
        """Test subsequent connection failures."""
        # Set up first failure
        first_time = datetime(2023, 1, 1, 12, 0, 0)
        self.monitor.consecutive_failures = 1
        self.monitor.total_failures = 1
        self.monitor.failure_types = {"TestError": 1}
        self.monitor.first_failure_time = first_time
        
        # Mock the datetime.now() call for the second failure
        second_time = datetime(2023, 1, 1, 12, 0, 30)  # 30 seconds later
        mock_datetime.now.return_value = second_time
        
        # Call the method
        result = self.monitor.connection_failed("TestError")
        
        # Verify state changes
        self.assertEqual(self.monitor.consecutive_failures, 2)
        self.assertEqual(self.monitor.total_failures, 2)
        self.assertEqual(self.monitor.failure_types, {"TestError": 2})
        self.assertEqual(self.monitor.first_failure_time, first_time)  # Should still be the first time
        self.assertEqual(self.monitor.last_failure_time, second_time)
        
        # Verify return value (still below max retries)
        self.assertFalse(result)

    @patch("todord.datetime")
    @patch("todord.logger.warning")
    @patch("todord.logger.critical")
    def test_connection_failed_max_retries(self, mock_logger_critical, mock_logger_warning, mock_datetime):
        """Test reaching max retry limit."""
        # Set up prior failures
        now = datetime(2023, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = now
        self.monitor.consecutive_failures = 2
        self.monitor.total_failures = 2
        self.monitor.failure_types = {"TestError": 2}
        
        # Call the method for the third failure (hitting max retries)
        result = self.monitor.connection_failed("TestError")
        
        # Verify state changes
        self.assertEqual(self.monitor.consecutive_failures, 3)
        self.assertEqual(self.monitor.total_failures, 3)
        self.assertEqual(self.monitor.failure_types, {"TestError": 3})
        
        # Verify return value (should trigger exit)
        self.assertTrue(result)
        
        # Verify critical log was called
        mock_logger_critical.assert_called_once()
        message = mock_logger_critical.call_args[0][0]
        self.assertIn("Maximum connection retries (3) reached", message)

    @patch("todord.datetime")
    @patch("todord.logger.warning")
    @patch("todord.logger.critical")
    def test_connection_failed_critical_error(self, mock_logger_critical, mock_logger_warning, mock_datetime):
        """Test critical error that should cause immediate exit."""
        # Set up prior failure
        now = datetime(2023, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = now
        self.monitor.consecutive_failures = 1
        self.monitor.total_failures = 1
        
        # Call the method with a critical error
        result = self.monitor.connection_failed("ConnectionClosed")
        
        # Verify state changes
        self.assertEqual(self.monitor.consecutive_failures, 2)
        self.assertEqual(self.monitor.total_failures, 2)
        self.assertEqual(self.monitor.failure_types, {"ConnectionClosed": 1})
        
        # Verify return value (should trigger exit for critical error after 2 failures)
        self.assertTrue(result)
        
        # Verify critical log was called
        mock_logger_critical.assert_called_once()
        message = mock_logger_critical.call_args[0][0]
        self.assertIn("Critical connection error", message)

    def test_get_status_report_no_failures(self):
        """Test status report with no failures."""
        report = self.monitor.get_status_report()
        self.assertEqual(report, "No connection failures detected")

    def test_get_status_report_with_failures(self):
        """Test status report with failures."""
        # Set up failures
        self.monitor.consecutive_failures = 2
        self.monitor.total_failures = 5
        self.monitor.failure_types = {"TestError": 3, "OtherError": 2}
        self.monitor.first_failure_time = datetime(2023, 1, 1, 12, 0, 0)
        self.monitor.last_failure_time = datetime(2023, 1, 1, 12, 5, 0)  # 5 minutes later
        
        # Get the report
        report = self.monitor.get_status_report()
        
        # Verify the report contains expected information
        self.assertIn("Connection Status Report:", report)
        self.assertIn("Total failures: 5", report)
        self.assertIn("Consecutive failures: 2", report)
        self.assertIn("First failure:", report)
        self.assertIn("Latest failure:", report)
        self.assertIn("Problem duration:", report)
        self.assertIn("TestError: 3", report)
        self.assertIn("OtherError: 2", report)


if __name__ == "__main__":
    unittest.main() 