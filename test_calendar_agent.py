import unittest
from unittest.mock import patch, MagicMock, call
import os
import logging
from datetime import datetime, timedelta
import pytz

# Assuming calendar_agent.py is in the same directory or accessible via PYTHONPATH
from calendar_agent import CalendarAgent 

# Suppress logging during tests to keep output clean, unless specifically testing logging.
logging.disable(logging.CRITICAL)

class TestCalendarAgentInitialization(unittest.TestCase):
    def setUp(self):
        self.valid_env_vars = {
            'GOOGLE_CLIENT_ID': 'test_client_id',
            'GOOGLE_CLIENT_SECRET': 'test_client_secret',
            'GOOGLE_REFRESH_TOKEN': 'test_refresh_token',
            'GOOGLE_CALENDAR_ID': 'primary'
        }

    @patch.dict(os.environ, {}, clear=True) # Start with no env vars
    @patch('calendar_agent.build') # Mock the build function
    @patch('calendar_agent.Credentials') # Mock Credentials
    def test_init_successful_default_params(self, mock_credentials, mock_build):
        with patch.dict(os.environ, self.valid_env_vars):
            agent = CalendarAgent()
            self.assertIsNotNone(agent.calendar_service)
            self.assertEqual(agent.event_duration_hours, 1.0)
            self.assertEqual(str(agent.timezone), 'America/New_York')
            mock_credentials.assert_called_once_with(
                token=None,
                refresh_token='test_refresh_token',
                token_uri='https://oauth2.googleapis.com/token',
                client_id='test_client_id',
                client_secret='test_client_secret'
            )
            mock_build.assert_called_once_with('calendar', 'v3', credentials=mock_credentials.return_value)

    @patch.dict(os.environ, {}, clear=True)
    @patch('calendar_agent.build')
    @patch('calendar_agent.Credentials')
    def test_init_successful_custom_params(self, mock_credentials, mock_build):
        with patch.dict(os.environ, self.valid_env_vars):
            agent = CalendarAgent(default_event_duration_hours=2.5, timezone_str='Europe/London')
            self.assertIsNotNone(agent.calendar_service)
            self.assertEqual(agent.event_duration_hours, 2.5)
            self.assertEqual(str(agent.timezone), 'Europe/London')

    @patch.dict(os.environ, {}, clear=True)
    def test_init_failure_missing_client_id(self):
        env_vars_missing_id = self.valid_env_vars.copy()
        del env_vars_missing_id['GOOGLE_CLIENT_ID']
        with patch.dict(os.environ, env_vars_missing_id):
            with self.assertRaisesRegex(ValueError, "Missing critical Google API credentials"):
                CalendarAgent()

    @patch.dict(os.environ, {}, clear=True)
    @patch('calendar_agent.build') # Still need to mock these as init tries to use them
    @patch('calendar_agent.Credentials')
    def test_init_invalid_timezone_defaults_to_utc(self, mock_credentials, mock_build):
        # Temporarily enable logging for this specific test if we want to check log output
        logging.disable(logging.NOTSET) 
        with patch.object(logging.getLogger('calendar_agent'), 'error') as mock_log_error:
            with patch.dict(os.environ, self.valid_env_vars):
                agent = CalendarAgent(timezone_str='Invalid/Timezone')
                self.assertEqual(str(agent.timezone), 'UTC')
                mock_log_error.assert_called_with("Unknown timezone 'Invalid/Timezone'. Defaulting to 'UTC'.")
        logging.disable(logging.CRITICAL) # Disable again

    @patch.dict(os.environ, {}, clear=True)
    @patch('calendar_agent.build')
    @patch('calendar_agent.Credentials')
    def test_init_invalid_duration_defaults_to_1(self, mock_credentials, mock_build):
        logging.disable(logging.NOTSET)
        with patch.object(logging.getLogger('calendar_agent'), 'warning') as mock_log_warning:
            with patch.dict(os.environ, self.valid_env_vars):
                agent_zero = CalendarAgent(default_event_duration_hours=0)
                self.assertEqual(agent_zero.event_duration_hours, 1.0)
                mock_log_warning.assert_any_call("Invalid default_event_duration_hours '0'. Must be a positive number. Defaulting to 1 hour.")
                
                agent_neg = CalendarAgent(default_event_duration_hours=-5)
                self.assertEqual(agent_neg.event_duration_hours, 1.0)
                mock_log_warning.assert_any_call("Invalid default_event_duration_hours '-5'. Must be a positive number. Defaulting to 1 hour.")
        logging.disable(logging.CRITICAL)

    @patch.dict(os.environ, {}, clear=True)
    @patch('calendar_agent.Credentials') # Mock Credentials
    @patch('calendar_agent.build', side_effect=Exception("API Build Failed"))
    def test_init_calendar_service_build_failure(self, mock_build, mock_credentials):
        logging.disable(logging.NOTSET)
        with patch.object(logging.getLogger('calendar_agent'), 'error') as mock_log_error:
            with patch.dict(os.environ, self.valid_env_vars):
                agent = CalendarAgent()
                self.assertIsNone(agent.calendar_service)
                mock_log_error.assert_called_with(
                    "Failed to initialize Google Calendar service: API Build Failed",
                    exc_info=True
                )
        logging.disable(logging.CRITICAL)


class TestCalendarAgentConflictCheck(unittest.TestCase):
    def setUp(self):
        self.valid_env_vars = {
            'GOOGLE_CLIENT_ID': 'test_client_id',
            'GOOGLE_CLIENT_SECRET': 'test_client_secret',
            'GOOGLE_REFRESH_TOKEN': 'test_refresh_token',
        }
        with patch.dict(os.environ, self.valid_env_vars):
            # Mock the build process for the agent used in these tests
            with patch('calendar_agent.build') as self.mock_build, \
                 patch('calendar_agent.Credentials') as self.mock_creds:
                self.mock_calendar_service = MagicMock()
                self.mock_build.return_value = self.mock_calendar_service
                self.agent = CalendarAgent(timezone_str='America/New_York', default_event_duration_hours=1)
        
        self.test_tz = pytz.timezone('America/New_York')
        self.mock_events_list_execute = self.mock_calendar_service.events().list().execute

    def _create_localized_datetime(self, year, month, day, hour, minute):
        return self.test_tz.localize(datetime(year, month, day, hour, minute))

    def _get_api_event(self, start_dt_iso, end_dt_iso, is_all_day=False):
        if is_all_day:
            return {'start': {'date': start_dt_iso[:10]}, 'end': {'date': end_dt_iso[:10]}} # YYYY-MM-DD
        return {'start': {'dateTime': start_dt_iso}, 'end': {'dateTime': end_dt_iso}}

    def test_check_conflicts_no_events_returned(self):
        self.mock_events_list_execute.return_value = {'items': []}
        proposed_start = self._create_localized_datetime(2024, 1, 1, 10, 0)
        self.assertFalse(self.agent.check_for_conflicts(proposed_start))

    def test_check_conflicts_direct_conflict(self):
        proposed_start = self._create_localized_datetime(2024, 1, 1, 10, 0) # 10:00 - 11:00
        event_start_iso = proposed_start.isoformat()
        event_end_iso = (proposed_start + timedelta(hours=1)).isoformat()
        self.mock_events_list_execute.return_value = {
            'items': [self._get_api_event(event_start_iso, event_end_iso)]
        }
        self.assertTrue(self.agent.check_for_conflicts(proposed_start))

    def test_check_conflicts_overlap_starts_before(self):
        proposed_start = self._create_localized_datetime(2024, 1, 1, 10, 0) # Slot 10:00 - 11:00
        event_start = self._create_localized_datetime(2024, 1, 1, 9, 30)  # Event 09:30 - 10:30
        event_end = event_start + timedelta(hours=1)
        self.mock_events_list_execute.return_value = {
            'items': [self._get_api_event(event_start.isoformat(), event_end.isoformat())]
        }
        self.assertTrue(self.agent.check_for_conflicts(proposed_start))
        
    def test_check_conflicts_overlap_ends_after(self):
        proposed_start = self._create_localized_datetime(2024, 1, 1, 10, 0) # Slot 10:00 - 11:00
        event_start = self._create_localized_datetime(2024, 1, 1, 10, 30) # Event 10:30 - 11:30
        event_end = event_start + timedelta(hours=1)
        self.mock_events_list_execute.return_value = {
            'items': [self._get_api_event(event_start.isoformat(), event_end.isoformat())]
        }
        self.assertTrue(self.agent.check_for_conflicts(proposed_start))

    def test_check_conflicts_event_contains_slot(self):
        proposed_start = self._create_localized_datetime(2024, 1, 1, 10, 0) # Slot 10:00 - 11:00
        event_start = self._create_localized_datetime(2024, 1, 1, 9, 0)   # Event 09:00 - 12:00
        event_end = event_start + timedelta(hours=3)
        self.mock_events_list_execute.return_value = {
            'items': [self._get_api_event(event_start.isoformat(), event_end.isoformat())]
        }
        self.assertTrue(self.agent.check_for_conflicts(proposed_start))

    def test_check_conflicts_slot_contains_event(self):
        self.agent.event_duration_hours = 2 # Agent books 2 hour slot
        proposed_start = self._create_localized_datetime(2024, 1, 1, 10, 0) # Slot 10:00 - 12:00
        event_start = self._create_localized_datetime(2024, 1, 1, 10, 30) # Event 10:30 - 11:30 (1hr)
        event_end = event_start + timedelta(hours=1)
        self.mock_events_list_execute.return_value = {
            'items': [self._get_api_event(event_start.isoformat(), event_end.isoformat())]
        }
        self.assertTrue(self.agent.check_for_conflicts(proposed_start))
        self.agent.event_duration_hours = 1 # Reset for other tests

    def test_check_conflicts_adjacent_no_overlap_ends_at_start(self):
        proposed_start = self._create_localized_datetime(2024, 1, 1, 10, 0) # Slot 10:00 - 11:00
        event_start = self._create_localized_datetime(2024, 1, 1, 9, 0)   # Event 09:00 - 10:00
        event_end = proposed_start # Event ends exactly when slot starts
        self.mock_events_list_execute.return_value = {
            'items': [self._get_api_event(event_start.isoformat(), event_end.isoformat())]
        }
        self.assertFalse(self.agent.check_for_conflicts(proposed_start))

    def test_check_conflicts_adjacent_no_overlap_starts_at_end(self):
        proposed_start = self._create_localized_datetime(2024, 1, 1, 10, 0) # Slot 10:00 - 11:00
        proposed_end = proposed_start + timedelta(hours=self.agent.event_duration_hours)
        event_start = proposed_end # Event starts exactly when slot ends
        event_end = event_start + timedelta(hours=1)
        self.mock_events_list_execute.return_value = {
            'items': [self._get_api_event(event_start.isoformat(), event_end.isoformat())]
        }
        self.assertFalse(self.agent.check_for_conflicts(proposed_start))
        
    def test_check_conflicts_all_day_event_overlap(self):
        proposed_start = self._create_localized_datetime(2024, 1, 1, 10, 0) # Slot Jan 1, 10:00 - 11:00
        # All-day event for Jan 1st. API returns dates.
        event_start_iso_date = "2024-01-01" 
        event_end_iso_date = "2024-01-02" # All-day events are exclusive of end date
        self.mock_events_list_execute.return_value = {
            'items': [self._get_api_event(event_start_iso_date, event_end_iso_date, is_all_day=True)]
        }
        self.assertTrue(self.agent.check_for_conflicts(proposed_start))

    def test_check_conflicts_all_day_event_no_overlap(self):
        proposed_start = self._create_localized_datetime(2024, 1, 2, 10, 0) # Slot Jan 2, 10:00 - 11:00
        event_start_iso_date = "2024-01-01"
        event_end_iso_date = "2024-01-02"
        self.mock_events_list_execute.return_value = {
            'items': [self._get_api_event(event_start_iso_date, event_end_iso_date, is_all_day=True)]
        }
        self.assertFalse(self.agent.check_for_conflicts(proposed_start))

    def test_check_conflicts_api_http_error(self):
        self.mock_events_list_execute.side_effect = HttpError(MagicMock(status=500), b"Server Error")
        proposed_start = self._create_localized_datetime(2024, 1, 1, 10, 0)
        self.assertTrue(self.agent.check_for_conflicts(proposed_start)) # Fail-safe: assume conflict

    def test_check_conflicts_service_unavailable(self):
        self.agent.calendar_service = None # Simulate service init failure
        proposed_start = self._create_localized_datetime(2024, 1, 1, 10, 0)
        self.assertTrue(self.agent.check_for_conflicts(proposed_start))


class TestCalendarAgentBookAppointment(unittest.TestCase):
    def setUp(self):
        self.valid_env_vars = {
            'GOOGLE_CLIENT_ID': 'test_client_id',
            'GOOGLE_CLIENT_SECRET': 'test_client_secret',
            'GOOGLE_REFRESH_TOKEN': 'test_refresh_token',
        }
        with patch.dict(os.environ, self.valid_env_vars):
            with patch('calendar_agent.build') as self.mock_build, \
                 patch('calendar_agent.Credentials'): # Mock credentials too
                self.mock_calendar_service = MagicMock()
                self.mock_build.return_value = self.mock_calendar_service
                self.agent = CalendarAgent(timezone_str='America/New_York', default_event_duration_hours=1.0)
        
        self.mock_check_conflicts = MagicMock()
        self.agent.check_for_conflicts = self.mock_check_conflicts # Patch instance method

        self.mock_events_insert_execute = self.mock_calendar_service.events().insert().execute
        self.test_tz = pytz.timezone('America/New_York')

    def test_book_appointment_successful(self):
        self.mock_check_conflicts.return_value = False # No conflicts
        mock_event_response = {'id': 'test_event_id', 'htmlLink': 'test_link'}
        self.mock_events_insert_execute.return_value = mock_event_response

        request_data = {
            'raw_text': 'Book a meeting',
            'service_type': 'Client Meeting',
            'date': '2024-07-15',
            'time': '02:00 PM' # 14:00
        }
        response = self.agent.book_appointment(request_data)

        self.assertTrue(response['success'])
        self.assertEqual(response['event_id'], 'test_event_id')
        self.mock_check_conflicts.assert_called_once()
        
        # Verify event body
        expected_start_dt = self.test_tz.localize(datetime(2024, 7, 15, 14, 0, 0))
        expected_end_dt = expected_start_dt + timedelta(hours=1.0)
        
        call_args = self.mock_events_insert_execute.call_args
        self.assertIsNotNone(call_args)
        actual_body = call_args[1]['body'] # kwargs['body']
        
        self.assertEqual(actual_body['summary'], 'Client Meeting')
        self.assertEqual(actual_body['start']['dateTime'], expected_start_dt.isoformat())
        self.assertEqual(actual_body['end']['dateTime'], expected_end_dt.isoformat())
        self.assertEqual(actual_body['start']['timeZone'], str(self.test_tz))

    def test_book_appointment_missing_date(self):
        request_data = {'service_type': 'Meeting', 'time': '10:00 AM'}
        response = self.agent.book_appointment(request_data)
        self.assertFalse(response['success'])
        self.assertEqual(response['message'], "Missing date or time for the appointment.")

    def test_book_appointment_invalid_datetime_format(self):
        request_data = {'date': '2024-13-01', 'time': '99:00 AM'} # Invalid month and time
        response = self.agent.book_appointment(request_data)
        self.assertFalse(response['success'])
        self.assertIn("Invalid date/time format", response['message'])

    def test_book_appointment_conflict_detected(self):
        self.mock_check_conflicts.return_value = True # Conflict
        request_data = {'date': '2024-07-15', 'time': '02:00 PM'}
        response = self.agent.book_appointment(request_data)
        self.assertFalse(response['success'])
        self.assertEqual(response['message'], "The requested time slot is already booked or conflicts with another event.")

    def test_book_appointment_service_unavailable(self):
        self.agent.calendar_service = None
        request_data = {'date': '2024-07-15', 'time': '02:00 PM'}
        response = self.agent.book_appointment(request_data)
        self.assertFalse(response['success'])
        self.assertEqual(response['message'], "Calendar service not available. Please check server logs.")

    def test_book_appointment_http_error_on_insert(self):
        self.mock_check_conflicts.return_value = False
        # Simulate HttpError from Google API client
        mock_resp = MagicMock()
        mock_resp.status = 403
        mock_resp.reason = "Forbidden"
        self.mock_events_insert_execute.side_effect = HttpError(mock_resp, b'{"error": {"message": "Forbidden"}}')
        
        request_data = {'date': '2024-07-15', 'time': '02:00 PM'}
        response = self.agent.book_appointment(request_data)
        self.assertFalse(response['success'])
        self.assertTrue("Failed to book appointment due to a calendar service error (Code: 403)" in response['message'])
        
    def test_book_appointment_unexpected_exception(self):
        self.mock_check_conflicts.return_value = False
        self.mock_events_insert_execute.side_effect = Exception("Something broke")
        request_data = {'date': '2024-07-15', 'time': '02:00 PM'}
        response = self.agent.book_appointment(request_data)
        self.assertFalse(response['success'])
        self.assertEqual(response['message'], "An unexpected error occurred: Something broke")


if __name__ == '__main__':
    # Re-enable logging if running tests directly and want to see output
    # logging.disable(logging.NOTSET) 
    # logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    unittest.main(argv=['first-arg-is-ignored'], exit=False)

```
