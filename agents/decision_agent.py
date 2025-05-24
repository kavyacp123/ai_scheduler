import os
import requests
from datetime import datetime

class DecisionAgent:
    def __init__(self, calendar_agent):
        self.calendar_agent = calendar_agent

    def should_book(self, request, call_info):
        date = request.get('date')
        time = request.get('time')
        if not date or not time:
            return False
        # Parse datetime (expects 'YYYY-MM-DD' and 'HH:MM' 24h format)
        try:
            dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        except Exception:
            try:
                dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %I:%M %p")
            except Exception:
                return False
        # Use CalendarAgent to check for conflicts
        if self.calendar_agent.check_for_conflicts(dt):
            return False  # Conflict found, do not approve
        return True  # No conflict, approve 