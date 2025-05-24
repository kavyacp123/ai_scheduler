import logging
from datetime import datetime
import pytz # Added for type checking and potential use in example

# Initialize logger for the module
logger = logging.getLogger(__name__)

class DecisionAgent:
    def __init__(self, calendar_agent):
        self.calendar_agent = calendar_agent
        # It's good practice to check if the injected dependency has the necessary attributes.
        # The actual check for a valid pytz timezone object is done per-call in should_book
        # to allow flexibility or if the calendar_agent might be initialized later in some frameworks.
        if not hasattr(self.calendar_agent, 'timezone'):
            logger.warning("Provided calendar_agent does not appear to have a 'timezone' attribute. This might lead to errors if not a valid pytz object.")
        if not hasattr(self.calendar_agent, 'check_for_conflicts'):
            logger.error("Provided calendar_agent does not have a 'check_for_conflicts' method.")
            raise AttributeError("calendar_agent must have a 'check_for_conflicts' method.")


    def should_book(self, request):
        """
        Determines if an appointment should be booked based on date, time, and calendar conflicts.

        Args:
            request (dict): A dictionary containing appointment details, expected to have
                            'date' (str, YYYY-MM-DD) and 'time' (str, HH:MM or HH:MM AM/PM).

        Returns:
            dict: A dictionary with:
                  - 'approved' (bool): True if booking is recommended, False otherwise.
                  - 'reason' (str): A code or message indicating the reason for the decision.
                  - 'details' (str, optional): Additional details for some reasons.
        """
        date_str = request.get('date')
        time_str = request.get('time')

        if not date_str or not time_str:
            logger.warning("Decision: Not approved. Missing date or time in request: date='{}', time='{}'".format(date_str, time_str))
            return {"approved": False, "reason": "MISSING_INPUT", "details": "Date or time not provided."}

        dt_str = f"{date_str} {time_str}"
        parsed_dt_naive = None

        try:
            # Try parsing with 24-hour format first
            parsed_dt_naive = datetime.strptime(dt_str, '%Y-%m-%d %H:%M')
        except ValueError:
            # Try parsing with AM/PM format
            try:
                parsed_dt_naive = datetime.strptime(dt_str, '%Y-%m-%d %I:%M %p')
            except ValueError:
                logger.warning(f"Decision: Not approved. Invalid date/time format: '{dt_str}'.")
                return {"approved": False, "reason": "INVALID_DATETIME_FORMAT", "details": f"Could not parse '{dt_str}'. Use YYYY-MM-DD HH:MM or YYYY-MM-DD hh:mm AM/PM."}
        
        # Critical Fix: Localize the naive datetime using CalendarAgent's timezone
        localized_dt = None
        
        calendar_agent_tz = getattr(self.calendar_agent, 'timezone', None)
        if not isinstance(calendar_agent_tz, pytz.BaseTzInfo): # Check if it's a valid pytz timezone
            logger.error("Decision: Not approved. CalendarAgent is missing a valid 'timezone' attribute (expected pytz.BaseTzInfo) for localization.")
            return {"approved": False, "reason": "CONFIGURATION_ERROR", "details": "CalendarAgent timezone not configured correctly for localization."}
        
        try:
            localized_dt = calendar_agent_tz.localize(parsed_dt_naive)
            logger.debug(f"Successfully localized '{parsed_dt_naive}' to '{localized_dt.isoformat()}' using timezone '{str(calendar_agent_tz)}'.")
        except Exception as e: # Catches pytz errors like AmbiguousTimeError, NonExistentTimeError
            logger.error(f"Decision: Not approved. Error localizing datetime '{parsed_dt_naive}' with timezone '{calendar_agent_tz}': {e}", exc_info=True)
            return {"approved": False, "reason": "DATETIME_LOCALIZATION_ERROR", "details": f"Could not localize date/time: {str(e)}"}

        # Now, check for conflicts using the localized datetime
        try:
            if self.calendar_agent.check_for_conflicts(localized_dt):
                logger.info(f"Decision: Not approved. Conflict detected by CalendarAgent for {localized_dt.isoformat()}.")
                return {"approved": False, "reason": "CONFLICT_DETECTED"}
            else:
                logger.info(f"Decision: Approved. No conflict found for {localized_dt.isoformat()}.")
                return {"approved": True, "reason": "NO_CONFLICT"}
        except AttributeError as ae: # If calendar_agent is missing check_for_conflicts (should be caught at init but good to be safe)
            logger.error(f"Decision: Not approved. CalendarAgent is missing 'check_for_conflicts' method: {ae}", exc_info=True)
            return {"approved": False, "reason": "CONFIGURATION_ERROR", "details": "CalendarAgent check_for_conflicts method missing."}
        except Exception as e:
            logger.error(f"Decision: Not approved. Error during conflict check with CalendarAgent: {e}", exc_info=True)
            return {"approved": False, "reason": "CALENDAR_AGENT_ERROR", "details": f"Error calling check_for_conflicts: {str(e)}"}

# Example Usage (for illustration and manual testing)
if __name__ == '__main__':
    # Configure basic logging for testing
    logging.basicConfig(level=logging.DEBUG, # Use DEBUG to see all logs from the agent
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Mock CalendarAgent for testing DecisionAgent independently
    class MockCalendarAgent:
        def __init__(self, timezone_str='America/New_York', conflict_on_hour=True, has_valid_timezone=True, has_conflict_method=True):
            self.conflict_on_hour = conflict_on_hour
            self.has_conflict_method = has_conflict_method
            if has_valid_timezone:
                try:
                    self.timezone = pytz.timezone(timezone_str)
                    logger.info(f"MockCalendarAgent initialized with timezone: {self.timezone}")
                except pytz.exceptions.UnknownTimeZoneError:
                    self.timezone = pytz.timezone('UTC') # Fallback for mock
                    logger.warning(f"MockCalendarAgent: Unknown timezone '{timezone_str}', defaulting to UTC.")
            else:
                self.timezone = "not a real timezone object" # To test bad configuration

        def check_for_conflicts(self, datetime_obj):
            if not self.has_conflict_method:
                raise AttributeError("Simulated missing check_for_conflicts")
                
            # Ensure we receive a timezone-aware datetime
            if not isinstance(datetime_obj, datetime) or datetime_obj.tzinfo is None or datetime_obj.tzinfo.utcoffset(datetime_obj) is None:
                logger.error(f"MockCalendarAgent.check_for_conflicts received a NAIVE or non-datetime object: {datetime_obj}")
                raise TypeError("MockCalendarAgent.check_for_conflicts expects an aware datetime object.")
            
            logger.info(f"MockCalendarAgent: Checking conflicts for {datetime_obj.isoformat()} (Timezone: {datetime_obj.tzinfo})")
            # Simple mock logic: conflict if it's on the hour (if configured)
            if self.conflict_on_hour:
                return datetime_obj.minute == 0 
            return False # No conflict by default

    logger.info("\n--- Testing DecisionAgent ---")

    # Scenario 1: Valid input, no conflict (e.g., 10:30 AM NY)
    mock_cal_agent_s1 = MockCalendarAgent(timezone_str='America/New_York', conflict_on_hour=False)
    decision_agent_s1 = DecisionAgent(mock_cal_agent_s1)
    request1 = {'date': '2024-07-15', 'time': '10:30 AM'}
    result1 = decision_agent_s1.should_book(request1)
    logger.info(f"S1 Request: {request1}, Result: {result1}")
    assert result1['approved'] is True and result1['reason'] == "NO_CONFLICT"

    # Scenario 2: Valid input, conflict (e.g., 10:00 AM NY)
    mock_cal_agent_s2 = MockCalendarAgent(timezone_str='America/New_York', conflict_on_hour=True)
    decision_agent_s2 = DecisionAgent(mock_cal_agent_s2)
    request2 = {'date': '2024-07-15', 'time': '10:00 AM'}
    result2 = decision_agent_s2.should_book(request2)
    logger.info(f"S2 Request: {request2}, Result: {result2}")
    assert result2['approved'] is False and result2['reason'] == "CONFLICT_DETECTED"
    
    # Scenario 2b: Valid input, no conflict (e.g., 10:30 AM NY, calendar agent finds conflicts on hour)
    request2b = {'date': '2024-07-15', 'time': '10:30 AM'}
    result2b = decision_agent_s2.should_book(request2b) # Using same agent as S2
    logger.info(f"S2b Request: {request2b}, Result: {result2b}")
    assert result2b['approved'] is True and result2b['reason'] == "NO_CONFLICT"

    # Scenario 3: Missing date
    decision_agent_s3 = DecisionAgent(mock_cal_agent_s1) # Calendar agent doesn't matter here
    request3 = {'time': '10:00 AM'}
    result3 = decision_agent_s3.should_book(request3)
    logger.info(f"S3 Request: {request3}, Result: {result3}")
    assert result3['approved'] is False and result3['reason'] == "MISSING_INPUT"

    # Scenario 4: Invalid time format
    request4 = {'date': '2024-07-15', 'time': '10-00-00 AM'}
    result4 = decision_agent_s3.should_book(request4)
    logger.info(f"S4 Request: {request4}, Result: {result4}")
    assert result4['approved'] is False and result4['reason'] == "INVALID_DATETIME_FORMAT"

    # Scenario 5: CalendarAgent with invalid timezone attribute type
    mock_cal_agent_s5 = MockCalendarAgent(has_valid_timezone=False)
    decision_agent_s5 = DecisionAgent(mock_cal_agent_s5) 
    request5 = {'date': '2024-07-15', 'time': '10:30 AM'}
    result5 = decision_agent_s5.should_book(request5)
    logger.info(f"S5 Request (cal agent with invalid tz type): {request5}, Result: {result5}")
    assert result5['approved'] is False and result5['reason'] == "CONFIGURATION_ERROR"
    assert "expected pytz.BaseTzInfo" in result5['details']
    
    # Scenario 6: CalendarAgent that raises an error during conflict check
    class ErrorMockCalendarAgent(MockCalendarAgent):
        def check_for_conflicts(self, datetime_obj):
            if not isinstance(datetime_obj, datetime) or datetime_obj.tzinfo is None or datetime_obj.tzinfo.utcoffset(datetime_obj) is None: # Basic check from parent
                raise TypeError("MockCalendarAgent.check_for_conflicts expects an aware datetime object.")
            logger.info(f"MockCalendarAgent: Checking conflicts for {datetime_obj.isoformat()} (Timezone: {datetime_obj.tzinfo})")
            raise RuntimeError("Simulated API error in CalendarAgent")

    mock_cal_agent_s6 = ErrorMockCalendarAgent()
    decision_agent_s6 = DecisionAgent(mock_cal_agent_s6)
    request6 = {'date': '2024-07-15', 'time': '10:30 AM'}
    result6 = decision_agent_s6.should_book(request6)
    logger.info(f"S6 Request (erroring calendar agent): {request6}, Result: {result6}")
    assert result6['approved'] is False and result6['reason'] == "CALENDAR_AGENT_ERROR"
    
    # Scenario 7: NonExistentTimeError (e.g. "spring forward" 2:30 AM usually doesn't exist)
    # In 2024, for America/New_York, DST starts March 10th, 2:00 AM becomes 3:00 AM.
    mock_cal_agent_s7 = MockCalendarAgent(timezone_str='America/New_York', conflict_on_hour=False)
    decision_agent_s7 = DecisionAgent(mock_cal_agent_s7)
    request7 = {'date': '2024-03-10', 'time': '02:30 AM'} 
    result7 = decision_agent_s7.should_book(request7)
    logger.info(f"S7 Request (non-existent time): {request7}, Result: {result7}")
    assert result7['approved'] is False and result7['reason'] == "DATETIME_LOCALIZATION_ERROR"
    # Pytz message for NonExistentTimeError is typically "2024-03-10 02:30:00 is an invalid time in America/New_York"
    # or similar, so checking for "invalid time" or "does not exist" is reasonable.
    assert "invalid time" in result7['details'] or "does not exist" in result7['details']

    # Scenario 8: AmbiguousTimeError (e.g. "fall back" 1:30 AM occurs twice)
    # In 2024, for America/New_York, DST ends Nov 3rd. 1:00 AM to 1:59:59 AM occurs twice.
    # pytz.localize by default sets is_dst=False for ambiguous times, avoiding an error.
    # So, this specific test case will pass localization with default pytz behavior.
    request8 = {'date': '2024-11-03', 'time': '01:30 AM'} 
    result8 = decision_agent_s7.should_book(request8) # Using same agent as S7
    logger.info(f"S8 Request (ambiguous time, default pytz handling): {request8}, Result: {result8}")
    assert result8['approved'] is True and result8['reason'] == "NO_CONFLICT"


    logger.info("\nAll example tests completed.")
```
