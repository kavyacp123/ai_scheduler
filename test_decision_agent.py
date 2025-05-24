import unittest
from unittest.mock import MagicMock, patch
import logging
from datetime import datetime
import pytz

# Assuming decision_agent.py is in the same directory or accessible via PYTHONPATH
from decision_agent import DecisionAgent

# Suppress logging during tests to keep output clean
logging.disable(logging.CRITICAL)

class TestDecisionAgentInitialization(unittest.TestCase):

    def test_init_successful(self):
        mock_calendar_agent = MagicMock()
        mock_calendar_agent.timezone = pytz.timezone('America/New_York')
        # check_for_conflicts is implicitly checked by hasattr in __init__
        # If it's missing, AttributeError is raised.
        mock_calendar_agent.check_for_conflicts = MagicMock() 
        
        try:
            agent = DecisionAgent(mock_calendar_agent)
            self.assertIsNotNone(agent)
        except Exception as e:
            self.fail(f"Initialization failed unexpectedly: {e}")

    def test_init_missing_calendar_agent_timezone_logs_warning(self):
        mock_calendar_agent = MagicMock(spec=['check_for_conflicts']) # Missing timezone
        del mock_calendar_agent.timezone # Ensure it's not there

        with patch.object(logging.getLogger('decision_agent'), 'error') as mock_log_error:
            # The warning is logged in the original code, but the critical part is the defensive check in should_book.
            # Here, we test the __init__ checks.
            DecisionAgent(mock_calendar_agent) # Should not raise error based on provided code.
            # The original code logs an error if timezone is not a pytz.BaseTzInfo.
            # Let's refine this to check for the warning if timezone is entirely missing.
            # Based on the provided code, this specific case (missing timezone) logs an error.
            # This can be adjusted if the desired behavior is a warning instead.
            # The provided code:
            # if not hasattr(calendar_agent, 'timezone') or \
            #    not isinstance(getattr(calendar_agent, 'timezone', None), pytz.BaseTzInfo):
            #    logger.error(...)
            # This means if timezone is missing, error is logged.
            mock_log_error.assert_any_call("CalendarAgent misconfiguration: 'timezone' attribute is missing or not a valid Pytz timezone.")


    def test_init_invalid_calendar_agent_timezone_type_logs_error(self):
        mock_calendar_agent = MagicMock()
        mock_calendar_agent.timezone = "not_a_pytz_object"
        mock_calendar_agent.check_for_conflicts = MagicMock()
        
        with patch.object(logging.getLogger('decision_agent'), 'error') as mock_log_error:
            DecisionAgent(mock_calendar_agent)
            mock_log_error.assert_called_with(
                "CalendarAgent misconfiguration: 'timezone' attribute is missing or not a valid Pytz timezone."
            )

    def test_init_missing_check_for_conflicts_raises_attributeerror(self):
        mock_calendar_agent = MagicMock(spec=['timezone']) # Missing check_for_conflicts
        mock_calendar_agent.timezone = pytz.timezone('America/New_York')
        # Ensure check_for_conflicts is not present
        if hasattr(mock_calendar_agent, 'check_for_conflicts'):
            del mock_calendar_agent.check_for_conflicts
            
        with self.assertRaisesRegex(AttributeError, "CalendarAgent must have a 'check_for_conflicts' method."):
            DecisionAgent(mock_calendar_agent)


class TestDecisionAgentShouldBook(unittest.TestCase):

    def setUp(self):
        self.mock_calendar_agent = MagicMock()
        self.mock_calendar_agent.timezone = pytz.timezone('America/New_York')
        self.mock_calendar_agent.check_for_conflicts = MagicMock()
        
        # This will create an agent with a properly mocked calendar_agent for most tests
        self.agent = DecisionAgent(self.mock_calendar_agent)
        self.test_tz = self.mock_calendar_agent.timezone

    def test_should_book_missing_date(self):
        request = {'time': '10:00 AM'}
        expected_response = {'approved': False, 'reason': "MISSING_INPUT", 'details': "Date and time are required."}
        self.assertEqual(self.agent.should_book(request), expected_response)

    def test_should_book_missing_time(self):
        request = {'date': '2024-01-01'}
        expected_response = {'approved': False, 'reason': "MISSING_INPUT", 'details': "Date and time are required."}
        self.assertEqual(self.agent.should_book(request), expected_response)

    def test_should_book_invalid_datetime_format(self):
        request = {'date': '2024-01-01', 'time': 'invalid-time'}
        expected_response = {'approved': False, 'reason': "INVALID_DATETIME_FORMAT", 'details': "Could not parse: 2024-01-01 invalid-time"}
        self.assertEqual(self.agent.should_book(request), expected_response)

    def test_should_book_successful_localization_and_no_conflict_24hr(self):
        request = {'date': '2024-01-01', 'time': '14:30'} # 2:30 PM
        parsed_naive_dt = datetime(2024, 1, 1, 14, 30)
        localized_dt = self.test_tz.localize(parsed_naive_dt)
        
        self.mock_calendar_agent.check_for_conflicts.return_value = False
        
        response = self.agent.should_book(request)
        
        self.mock_calendar_agent.check_for_conflicts.assert_called_once_with(localized_dt)
        self.assertEqual(response, {'approved': True, 'reason': "NO_CONFLICT"})

    def test_should_book_successful_localization_and_no_conflict_ampm(self):
        request = {'date': '2024-01-01', 'time': '02:30 PM'}
        parsed_naive_dt = datetime(2024, 1, 1, 14, 30)
        localized_dt = self.test_tz.localize(parsed_naive_dt)

        self.mock_calendar_agent.check_for_conflicts.return_value = False
        
        response = self.agent.should_book(request)
        
        self.mock_calendar_agent.check_for_conflicts.assert_called_once_with(localized_dt)
        self.assertEqual(response, {'approved': True, 'reason': "NO_CONFLICT"})

    def test_should_book_calendar_agent_timezone_missing_in_should_book(self):
        # Test the defensive check within should_book, even if __init__ also warns.
        # Create a new agent with a calendar_agent that lacks the timezone attribute properly
        broken_calendar_agent = MagicMock(spec=['check_for_conflicts']) 
        del broken_calendar_agent.timezone # Ensure it's missing
        broken_agent = DecisionAgent(broken_calendar_agent)
        
        request = {'date': '2024-01-01', 'time': '10:00 AM'}
        expected_details = "CalendarAgent timezone not properly configured."
        response = broken_agent.should_book(request)
        self.assertEqual(response['approved'], False)
        self.assertEqual(response['reason'], "CONFIGURATION_ERROR")
        self.assertIn(expected_details, response['details'])

    def test_should_book_calendar_agent_timezone_invalid_type_in_should_book(self):
        broken_calendar_agent = MagicMock(spec=['check_for_conflicts'])
        broken_calendar_agent.timezone = "not_a_pytz_object" # Invalid type
        broken_agent = DecisionAgent(broken_calendar_agent)

        request = {'date': '2024-01-01', 'time': '10:00 AM'}
        expected_details = "CalendarAgent timezone not properly configured."
        response = broken_agent.should_book(request)
        self.assertEqual(response['approved'], False)
        self.assertEqual(response['reason'], "CONFIGURATION_ERROR")
        self.assertIn(expected_details, response['details'])


    def test_should_book_localize_raises_ambiguous_time_error(self):
        request = {'date': '2024-11-03', 'time': '01:30 AM'} # Example ambiguous time in NY
        parsed_naive_dt = datetime(2024, 11, 3, 1, 30)
        
        # Mock the localize method on the timezone object of the mock_calendar_agent
        self.mock_calendar_agent.timezone.localize = MagicMock(side_effect=pytz.exceptions.AmbiguousTimeError("Ambiguous time"))
        
        response = self.agent.should_book(request)
        
        self.mock_calendar_agent.timezone.localize.assert_called_once_with(parsed_naive_dt)
        self.assertEqual(response['approved'], False)
        self.assertEqual(response['reason'], "DATETIME_LOCALIZATION_ERROR")
        self.assertTrue("Ambiguous time" in response['details'])
        
        # Reset mock for other tests if needed, or ensure setUp re-mocks it.
        self.mock_calendar_agent.timezone.localize = MagicMock() 


    def test_should_book_localize_raises_non_existent_time_error(self):
        request = {'date': '2024-03-10', 'time': '02:30 AM'} # Example non-existent time in NY
        parsed_naive_dt = datetime(2024, 3, 10, 2, 30)

        self.mock_calendar_agent.timezone.localize = MagicMock(side_effect=pytz.exceptions.NonExistentTimeError("Non-existent time"))

        response = self.agent.should_book(request)
        
        self.mock_calendar_agent.timezone.localize.assert_called_once_with(parsed_naive_dt)
        self.assertEqual(response['approved'], False)
        self.assertEqual(response['reason'], "DATETIME_LOCALIZATION_ERROR")
        self.assertTrue("Non-existent time" in response['details'])
        self.mock_calendar_agent.timezone.localize = MagicMock()

    def test_should_book_localize_raises_unexpected_exception(self):
        request = {'date': '2024-01-01', 'time': '10:00 AM'}
        parsed_naive_dt = datetime(2024, 1, 1, 10, 0)
        self.mock_calendar_agent.timezone.localize = MagicMock(side_effect=ValueError("Unexpected localization failure"))

        response = self.agent.should_book(request)
        self.assertEqual(response['approved'], False)
        self.assertEqual(response['reason'], "DATETIME_LOCALIZATION_ERROR")
        self.assertTrue("Unexpected localization failure" in response['details'])
        self.mock_calendar_agent.timezone.localize = MagicMock()


    def test_should_book_conflict_detected(self):
        request = {'date': '2024-01-01', 'time': '10:00 AM'}
        self.mock_calendar_agent.check_for_conflicts.return_value = True
        
        response = self.agent.should_book(request)
        self.assertEqual(response, {'approved': False, 'reason': "CONFLICT_DETECTED"})

    def test_should_book_check_for_conflicts_raises_exception(self):
        request = {'date': '2024-01-01', 'time': '10:00 AM'}
        self.mock_calendar_agent.check_for_conflicts.side_effect = Exception("API Error")
        
        response = self.agent.should_book(request)
        expected_response = {'approved': False, 'reason': "CALENDAR_AGENT_ERROR", 'details': "API Error"}
        self.assertEqual(response, expected_response)

    def test_should_book_check_for_conflicts_attribute_error(self):
        # This tests the defensive try-except in should_book, __init__ should ideally prevent this.
        request = {'date': '2024-01-01', 'time': '10:00 AM'}
        # Make check_for_conflicts an invalid attribute for this specific test
        original_check_for_conflicts = self.agent.calendar_agent.check_for_conflicts
        del self.agent.calendar_agent.check_for_conflicts 
        
        response = self.agent.should_book(request)
        expected_response = {'approved': False, 'reason': "CONFIGURATION_ERROR", 'details': "CalendarAgent.check_for_conflicts not available."}
        self.assertEqual(response, expected_response)
        
        # Restore for other tests
        self.agent.calendar_agent.check_for_conflicts = original_check_for_conflicts


if __name__ == '__main__':
    # Re-enable logging if running tests directly and want to see output
    # logging.disable(logging.NOTSET) 
    # logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    unittest.main(argv=['first-arg-is-ignored'], exit=False)

```
