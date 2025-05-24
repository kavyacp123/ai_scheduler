import os
import logging
from datetime import datetime, timedelta
import pytz # type: ignore
from google.oauth2.credentials import Credentials # type: ignore
from googleapiclient.discovery import build # type: ignore
from googleapiclient.errors import HttpError # type: ignore

# Initialize logger for the module
logger = logging.getLogger(__name__)

class CalendarAgent:
    def __init__(self, default_event_duration_hours=1, timezone_str='America/New_York'):
        self.google_credentials = {
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
            'refresh_token': os.getenv('GOOGLE_REFRESH_TOKEN'),
            'calendar_id': os.getenv('GOOGLE_CALENDAR_ID', 'primary')
        }

        # Validate essential credentials
        if not all([self.google_credentials['client_id'],
                    self.google_credentials['client_secret'],
                    self.google_credentials['refresh_token']]):
            error_msg = "Missing critical Google API credentials (CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN). Please set environment variables."
            logger.critical(error_msg)
            # In a real application, you might have a more sophisticated way to handle this,
            # like setting a state that prevents operations, but raising an error is clear.
            raise ValueError(error_msg)

        try:
            self.timezone = pytz.timezone(timezone_str)
            logger.info(f"CalendarAgent initialized with timezone: {timezone_str}")
        except pytz.exceptions.UnknownTimeZoneError:
            default_tz = 'UTC'
            logger.error(f"Unknown timezone '{timezone_str}'. Defaulting to '{default_tz}'.")
            self.timezone = pytz.timezone(default_tz)

        if not isinstance(default_event_duration_hours, (int, float)) or default_event_duration_hours <= 0:
            logger.warning(f"Invalid default_event_duration_hours '{default_event_duration_hours}'. Must be a positive number. Defaulting to 1 hour.")
            self.event_duration_hours = 1.0
        else:
            self.event_duration_hours = float(default_event_duration_hours)
        logger.info(f"CalendarAgent initialized with event duration: {self.event_duration_hours} hours.")
        
        self.calendar_service = None # Initialize to None
        self._init_calendar_service()

    def _init_calendar_service(self):
        try:
            creds = Credentials(
                token=None, # No initial token, rely on refresh token
                refresh_token=self.google_credentials['refresh_token'],
                token_uri='https://oauth2.googleapis.com/token',
                client_id=self.google_credentials['client_id'],
                client_secret=self.google_credentials['client_secret']
            )
            # Consider explicit refresh if issues arise or to confirm validity early
            # from google.auth.transport.requests import Request
            # if creds.expired and creds.refresh_token:
            #     creds.refresh(Request())

            self.calendar_service = build('calendar', 'v3', credentials=creds)
            logger.info("Google Calendar service initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Google Calendar service: {e}", exc_info=True)
            self.calendar_service = None # Ensure it's None if initialization fails

    def book_appointment(self, request):
        if not self.calendar_service:
            logger.error("Attempted to book appointment, but Calendar service is not initialized.")
            return {"success": False, "message": "Calendar service not available. Please check server logs."}

        raw_text = request.get('raw_text', '')
        service_type = request.get('service_type', 'Appointment')
        date_str = request.get('date')
        time_str = request.get('time')

        if not date_str or not time_str:
            logger.warning("Booking attempt failed: Missing date or time in request.")
            return {"success": False, "message": "Missing date or time for the appointment."}

        try:
            datetime_str = f"{date_str} {time_str}"
            dt_naive = None
            # Try parsing with AM/PM format first
            try:
                dt_naive = datetime.strptime(datetime_str, '%Y-%m-%d %I:%M %p')
            except ValueError:
                # Try parsing with 24-hour format
                try:
                    dt_naive = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M')
                except ValueError:
                    logger.warning(f"Invalid date/time format provided: '{datetime_str}'.")
                    return {"success": False, "message": "Invalid date/time format. Use YYYY-MM-DD HH:MM or YYYY-MM-DD hh:mm AM/PM."}
            
            localized_proposed_start = self.timezone.localize(dt_naive)
            
            # Check for conflicts using the robust method
            if self.check_for_conflicts(localized_proposed_start):
                logger.info(f"Booking attempt failed: Conflict detected for {localized_proposed_start.isoformat()}")
                return {"success": False, "message": "The requested time slot is already booked or conflicts with another event."}

            proposed_end_dt = localized_proposed_start + timedelta(hours=self.event_duration_hours)

            event_body = {
                'summary': service_type,
                'description': f"Booked via API. Original request: {raw_text}",
                'start': {
                    'dateTime': localized_proposed_start.isoformat(),
                    'timeZone': str(self.timezone),
                },
                'end': {
                    'dateTime': proposed_end_dt.isoformat(),
                    'timeZone': str(self.timezone),
                },
                'attendees': [], # Can be extended if attendee info is provided
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': int(24 * 60)},
                        {'method': 'popup', 'minutes': 15},
                    ],
                },
            }

            event = self.calendar_service.events().insert(
                calendarId=self.google_credentials['calendar_id'], 
                body=event_body
            ).execute()
            
            logger.info(f"Appointment '{service_type}' booked successfully. Event ID: {event.get('id')} from {localized_proposed_start.isoformat()} to {proposed_end_dt.isoformat()}")
            return {
                "success": True,
                "message": f"{service_type} successfully booked for {date_str} at {time_str}.",
                "event_id": event.get('id'),
                "event_link": event.get('htmlLink'),
                "endCall": False # As per original design, caller decides if flow ends
            }

        except HttpError as e:
            # Extract safe error details. Avoid logging raw e.content unless sanitized.
            error_status = e.resp.status if hasattr(e, 'resp') else 'Unknown'
            # Safely get error_details. In older library versions, it might be on e.details
            error_details_attr = getattr(e, 'error_details', None)
            if error_details_attr is None and hasattr(e, '_get_reason'): # older google-api-python-client
                 error_details_msg = e._get_reason()
            elif isinstance(error_details_attr, (list, tuple)) and error_details_attr:
                 error_details_msg = str(error_details_attr[0]) # Take the first error detail
            elif isinstance(error_details_attr, str):
                 error_details_msg = error_details_attr
            else:
                 error_details_msg = "No additional details provided by API."

            logger.error(f"Google Calendar API HttpError during booking: Status {error_status}, Details: {error_details_msg}", exc_info=True) 
            return {"success": False, "message": f"Failed to book appointment due to a calendar service error (Code: {error_status}). Please try again later."}
        except Exception as e:
            logger.error(f"An unexpected error occurred during booking: {e}", exc_info=True)
            return {"success": False, "message": f"An unexpected error occurred: {str(e)}"}

    def check_for_conflicts(self, proposed_start_dt_localized):
        if not self.calendar_service:
            logger.warning("Conflict check attempted, but Calendar service is not initialized. Assuming conflict.")
            return True # Assume conflict if service is down to be safe

        try:
            proposed_end_dt_localized = proposed_start_dt_localized + timedelta(hours=self.event_duration_hours)

            # Define a query window to fetch potentially overlapping events.
            # We fetch events that start somewhat before our proposed_end and end somewhat after our proposed_start.
            # A broader window ensures we don't miss events due to strict API filtering on start times.
            # Max typical event duration on either side should be safe. Let's use 8 hours as a heuristic for "long events".
            # For Google API, timeMin and timeMax must be in UTC for the query.
            safety_margin_hours = max(8.0, self.event_duration_hours * 2.0) # Ensure float for timedelta
            
            query_time_min_utc_dt = (proposed_start_dt_localized - timedelta(hours=safety_margin_hours)).astimezone(pytz.utc)
            query_time_max_utc_dt = (proposed_end_dt_localized + timedelta(hours=safety_margin_hours)).astimezone(pytz.utc)
            
            query_time_min_iso = query_time_min_utc_dt.isoformat()
            query_time_max_iso = query_time_max_utc_dt.isoformat()
            
            logger.debug(f"Checking conflicts for slot (localized): {proposed_start_dt_localized.isoformat()} to {proposed_end_dt_localized.isoformat()}")
            logger.debug(f"Conflict query window (UTC): timeMin={query_time_min_iso}, timeMax={query_time_max_iso}")

            events_result = self.calendar_service.events().list(
                calendarId=self.google_credentials['calendar_id'],
                timeMin=query_time_min_iso,
                timeMax=query_time_max_iso,
                singleEvents=True, # Important for expanding recurring events into single instances
                orderBy='startTime' # Process events chronologically
            ).execute()
            
            items = events_result.get('items', [])
            if not items:
                logger.debug("No events found in the broad query window. No conflicts.")
                return False

            for event in items:
                event_summary = event.get('summary', 'N/A')
                event_id = event.get('id')
                
                event_start_str = event['start'].get('dateTime', event['start'].get('date'))
                event_end_str = event['end'].get('dateTime', event['end'].get('date'))

                # Parse event times. Google Calendar API returns ISO format.
                # 'dateTime' includes timezone offset (usually UTC), 'date' is for all-day events.
                if 'T' in event_start_str: # Indicates a specific time (dateTime)
                    event_start_dt_aware = datetime.fromisoformat(event_start_str)
                else: # Indicates an all-day event ('date')
                    event_start_date_naive = datetime.strptime(event_start_str, '%Y-%m-%d').date()
                    # All-day events start at midnight. Assume calendar's default timezone if not specified,
                    # but Google typically implies UTC or uses the calendar's primary timezone.
                    # For robust comparison, localize to self.timezone if it's an all-day event from a known calendar.
                    # However, Google API usually returns all-day event dates that can be treated as starting at 00:00 UTC.
                    # For simplicity and consistency, we'll localize to self.timezone.
                    event_start_dt_aware = self.timezone.localize(datetime.combine(event_start_date_naive, datetime.min.time()))


                if 'T' in event_end_str: # Indicates a specific time (dateTime)
                    event_end_dt_aware = datetime.fromisoformat(event_end_str)
                else: # Indicates an all-day event ('date')
                    event_end_date_naive = datetime.strptime(event_end_str, '%Y-%m-%d').date()
                    # For all-day events, the 'end' date is exclusive. (e.g., ends at start of this day)
                    event_end_dt_aware = self.timezone.localize(datetime.combine(event_end_date_naive, datetime.min.time()))
                
                # Convert event times to the agent's configured timezone for consistent comparison.
                # proposed_start_dt_localized and proposed_end_dt_localized are already in self.timezone.
                event_start_localized = event_start_dt_aware.astimezone(self.timezone)
                event_end_localized = event_end_dt_aware.astimezone(self.timezone)

                logger.debug(f"Checking against existing event: '{event_summary}' (ID: {event_id}) from {event_start_localized.isoformat()} to {event_end_localized.isoformat()}")

                # The core conflict logic: (event_start < proposed_end) AND (event_end > proposed_start)
                is_overlapping = (event_start_localized < proposed_end_dt_localized and 
                                  event_end_localized > proposed_start_dt_localized)

                if is_overlapping:
                    logger.info(f"Conflict DETECTED with event: '{event_summary}' (ID: {event_id}). Proposed slot: {proposed_start_dt_localized.isoformat()} - {proposed_end_dt_localized.isoformat()}. Existing event: {event_start_localized.isoformat()} - {event_end_localized.isoformat()}")
                    return True # Found a conflict

            logger.debug("No conflicts found after checking all events in the window.")
            return False # No conflicts found

        except HttpError as e:
            error_status = e.resp.status if hasattr(e, 'resp') else 'Unknown'
            error_details_attr = getattr(e, 'error_details', None)
            if error_details_attr is None and hasattr(e, '_get_reason'): 
                 error_details_msg = e._get_reason()
            elif isinstance(error_details_attr, (list, tuple)) and error_details_attr:
                 error_details_msg = str(error_details_attr[0])
            elif isinstance(error_details_attr, str):
                 error_details_msg = error_details_attr
            else:
                 error_details_msg = "No additional details provided by API."
            logger.error(f"Google Calendar API HttpError during conflict check: Status {error_status}, Details: {error_details_msg}", exc_info=True)
            return True # Assume conflict on API error to be safe
        except Exception as e:
            logger.error(f"An unexpected error occurred during conflict check: {e}", exc_info=True)
            return True # Assume conflict on other errors to be safe

# Example Usage (for local testing, not part of the class definition)
if __name__ == '__main__':
    # Configure basic logging for testing
    logging.basicConfig(level=logging.INFO, # Set to DEBUG for more verbose output from the agent
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # --- IMPORTANT ---
    # Mock or set REAL environment variables for local testing.
    # If using real credentials, ensure they are for a test calendar.
    # Example:
    # os.environ['GOOGLE_CLIENT_ID'] = 'YOUR_CLIENT_ID_HERE.apps.googleusercontent.com'
    # os.environ['GOOGLE_CLIENT_SECRET'] = 'YOUR_CLIENT_SECRET_HERE'
    # os.environ['GOOGLE_REFRESH_TOKEN'] = 'YOUR_REFRESH_TOKEN_HERE'
    # os.environ['GOOGLE_CALENDAR_ID'] = 'primary' # Or your test calendar ID, e.g., 'your_email@gmail.com'

    if not all(os.getenv(var) for var in ['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REFRESH_TOKEN']):
        logger.error("CRITICAL: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN environment variables must be set for testing.")
        logger.info("Skipping CalendarAgent instantiation and tests due to missing credentials.")
    else:
        logger.info("Attempting to initialize CalendarAgent with example configuration...")
        try:
            # Test with a non-default duration and timezone if desired
            agent = CalendarAgent(default_event_duration_hours=1.0, timezone_str='America/New_York') # Example: 'Europe/London'
            
            if agent.calendar_service:
                logger.info("CalendarAgent initialized successfully.")

                # --- Test Conflict Check ---
                # Create a timezone-naive datetime first, then localize it as the methods expect.
                # Replace with a date and time you want to test for conflicts.
                # Ensure this datetime corresponds to the agent's configured timezone.
                # Example: Test for a slot on August 15, 2024, at 10:00 AM in agent's timezone.
                # test_datetime_naive = datetime(2024, 8, 15, 10, 0, 0) 
                # test_datetime_localized = agent.timezone.localize(test_datetime_naive)
                
                # logger.info(f"Running conflict check for slot starting at: {test_datetime_localized.isoformat()} (Duration: {agent.event_duration_hours} hours)")
                # has_conflict = agent.check_for_conflicts(test_datetime_localized)
                # logger.info(f"Conflict check result for {test_datetime_localized.isoformat()}: {'Conflict Exists' if has_conflict else 'No Conflict'}")

                # --- Test Booking (Optional - uncomment to run) ---
                # Be cautious: this will create an event in the configured Google Calendar.
                # booking_request_example = {
                #     'raw_text': 'Test booking from script for 1hr meeting',
                #     'service_type': 'Dev Test Service (1hr)',
                #     'date': '2024-12-25', # Choose a future date
                #     'time': '04:00 PM'    # Time in agent's timezone
                # }
                # logger.info(f"Attempting to book appointment with request: {booking_request_example}")
                # booking_response = agent.book_appointment(booking_request_example)
                # logger.info(f"Booking response: {booking_response}")
                # if booking_response.get('success'):
                #     logger.info(f"Event Link: {booking_response.get('event_link')}")

            else:
                logger.error("CalendarAgent service could not be initialized. Check credentials and previous logs.")
                
        except ValueError as ve: # Catch initialization errors specifically
            logger.error(f"CalendarAgent initialization failed: {ve}")
        except Exception as ex:
            logger.error(f"An unexpected error occurred during example usage: {ex}", exc_info=True)
```
