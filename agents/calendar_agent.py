import os
from datetime import datetime, timedelta
import pytz
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class CalendarAgent:
    def __init__(self):
        self.google_credentials = {
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
            'refresh_token': os.getenv('GOOGLE_REFRESH_TOKEN'),
            'calendar_id': os.getenv('GOOGLE_CALENDAR_ID', 'primary')
        }
        self.timezone = pytz.timezone('America/New_York')
        self._init_calendar_service()

    def _init_calendar_service(self):
        try:
            creds = Credentials(
                token=None,
                refresh_token=self.google_credentials['refresh_token'],
                client_id=self.google_credentials['client_id'],
                client_secret=self.google_credentials['client_secret'],
                token_uri='https://oauth2.googleapis.com/token'
            )
            self.calendar_service = build('calendar', 'v3', credentials=creds)
        except Exception as e:
            self.calendar_service = None

    def book_appointment(self, request):
        if not self.calendar_service:
            return {"success": False, "message": "Calendar service not available", "endCall": False}
        try:
            # Extract details
            date = request.get('date')
            time = request.get('time')
            service_type = request.get('service_type', 'General Appointment')
            raw_text = request.get('raw_text', '')
            # For demo, expect date as YYYY-MM-DD and time as HH:MM (24h) or HH:MM AM/PM
            if not date or not time:
                return {"success": False, "message": "Missing date or time.", "endCall": False}
            # Parse datetime
            try:
                # Try parsing time as HH:MM AM/PM
                try:
                    dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %I:%M %p")
                except ValueError:
                    dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
                dt = self.timezone.localize(dt)
            except Exception:
                return {"success": False, "message": "Invalid date/time format.", "endCall": False}
            # Check for conflicts
            if self.check_for_conflicts(dt):
                return {"success": False, "message": "Time slot is already booked. Please choose a different time.", "endCall": False}
            # Create event
            event = {
                'summary': service_type,
                'description': f"Appointment booked via agent\nOriginal request: {raw_text}",
                'start': {
                    'dateTime': dt.isoformat(),
                    'timeZone': str(self.timezone),
                },
                'end': {
                    'dateTime': (dt + timedelta(hours=1)).isoformat(),
                    'timeZone': str(self.timezone),
                },
                'attendees': [],
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 24 * 60},
                        {'method': 'popup', 'minutes': 15},
                    ],
                },
            }
            result = self.calendar_service.events().insert(
                calendarId=self.google_credentials['calendar_id'],
                body=event
            ).execute()
            return {"success": True, "message": f"Appointment booked for {dt.strftime('%A, %B %d at %I:%M %p')}", "event_id": result.get('id'), "event_link": result.get('htmlLink'), "endCall": False}
        except HttpError as e:
            return {"success": False, "message": f"Calendar API error: {e}", "endCall": False}
        except Exception as e:
            return {"success": False, "message": str(e), "endCall": False}

    def check_for_conflicts(self, appointment_dt):
        try:
            start_time = appointment_dt
            end_time = appointment_dt + timedelta(hours=1)
            events_result = self.calendar_service.events().list(
                calendarId=self.google_credentials['calendar_id'],
                timeMin=start_time.isoformat(),
                timeMax=end_time.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            return bool(events_result.get('items', []))
        except Exception:
            return False 