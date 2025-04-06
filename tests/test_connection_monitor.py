import unittest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add the parent directory to sys.path to import the module
sys.path.append(str(Path(__file__).parent.parent))

from todord import ConnectionMonitor


class TestConnectionMonitor(unittest.TestCase):
    def setUp(self):
        self.monitor = ConnectionMonitor()

    def test_initial_state(self):
        """Test initial state of connection monitor."""
        # Check the attributes that actually exist in the class
        self.assertEqual(self.monitor.consecutive_failures, 0)
        self.assertEqual(self.monitor.total_failures, 0)
        self.assertEqual(len(self.monitor.failure_types), 0)
        self.assertIsNone(self.monitor.last_failure_time)
        self.assertIsNone(self.monitor.first_failure_time)

    def test_connection_successful(self):
        """Test successful connection tracking."""
        # First trigger a failure to test resetting
        self.monitor.connection_failed("test_error")
        self.assertEqual(self.monitor.consecutive_failures, 1)
        
        # Record a successful connection
        self.monitor.connection_successful()

        # Verify state changes using the correct attribute names
        self.assertEqual(self.monitor.consecutive_failures, 0)
        self.assertEqual(self.monitor.total_failures, 1)  # Total failures remains

    def test_connection_failed(self):
        """Test failed connection tracking."""
        # Record a failed connection
        result = self.monitor.connection_failed("test_error")

        # Verify state changes
        self.assertEqual(self.monitor.consecutive_failures, 1)
        self.assertEqual(self.monitor.total_failures, 1)
        self.assertIn("test_error", self.monitor.failure_types)
        self.assertEqual(self.monitor.failure_types["test_error"], 1)
        self.assertIsNotNone(self.monitor.last_failure_time)
        self.assertIsNotNone(self.monitor.first_failure_time)
        # Should not have reached max retries yet
        self.assertFalse(result)

    def test_multiple_connection_attempts(self):
        """Test tracking multiple connection attempts."""
        # Record a mix of successful and failed connections
        self.monitor.connection_successful()  # Initial connection
        self.monitor.connection_failed("test_error")  # Fail
        result = self.monitor.connection_failed("another_error")  # Fail again
        
        # Check state after two failures
        self.assertEqual(self.monitor.consecutive_failures, 2)
        self.assertEqual(self.monitor.total_failures, 2)
        self.assertEqual(self.monitor.failure_types["test_error"], 1)
        self.assertEqual(self.monitor.failure_types["another_error"], 1)
        
        # Default max_retries is 3, so we shouldn't have reached it yet
        self.assertFalse(result)
        
        # Record a successful connection
        self.monitor.connection_successful()
        
        # Check that consecutive failures was reset
        self.assertEqual(self.monitor.consecutive_failures, 0)
        # But total failures remains
        self.assertEqual(self.monitor.total_failures, 2)

    def test_max_retries_reached(self):
        """Test that max retries trigger the correct return value."""
        # Create a monitor with a low max_retries
        monitor = ConnectionMonitor(max_retries=2)
        
        # Trigger failures up to max_retries
        monitor.connection_failed("error1")
        result = monitor.connection_failed("error2")
        
        # Should have reached max retries
        self.assertTrue(result)
        self.assertEqual(monitor.consecutive_failures, 2)
        self.assertEqual(monitor.total_failures, 2)

    def test_get_status_report(self):
        """Test status report generation."""
        # Record some connection events to generate a report
        self.monitor.connection_failed("test_error")
        self.monitor.connection_failed("another_error")
        
        # Generate report
        report = self.monitor.get_status_report()
        
        # Verify the report content
        self.assertIn("Connection Status Report", report)
        self.assertIn("Total failures: 2", report)
        self.assertIn("Consecutive failures: 2", report)
        self.assertIn("test_error", report)
        self.assertIn("another_error", report)


if __name__ == "__main__":
    unittest.main() 