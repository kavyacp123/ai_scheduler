import logging

# Initialize logger for the module
logger = logging.getLogger(__name__)

class MainLogicAgent:
    def __init__(self, calendar_agent, decision_agent):
        self.calendar_agent = calendar_agent
        self.decision_agent = decision_agent
        logger.info("MainLogicAgent initialized.")

        # Basic validation of injected agents
        if not hasattr(self.decision_agent, 'should_book') or not callable(getattr(self.decision_agent, 'should_book', None)):
            logger.error("DecisionAgent is missing the 'should_book' callable method.")
            # Depending on strictness, could raise TypeError:
            # raise TypeError("DecisionAgent must have a 'should_book' callable method.")
        if not hasattr(self.calendar_agent, 'book_appointment') or not callable(getattr(self.calendar_agent, 'book_appointment', None)):
            logger.error("CalendarAgent is missing the 'book_appointment' callable method.")
            # raise TypeError("CalendarAgent must have a 'book_appointment' callable method.")

    def handle_booking_request(self, request_data):
        """
        Handles a booking request by first consulting the DecisionAgent,
        then (if approved) booking with the CalendarAgent.

        Args:
            request_data (dict): Data for the booking request, to be passed to
                                 DecisionAgent and CalendarAgent.

        Returns:
            dict: A dictionary indicating the overall outcome of the request.
        """
        logger.debug(f"MainLogicAgent handling booking request: {request_data}")

        # Step 1: Consult DecisionAgent
        try:
            decision_result = self.decision_agent.should_book(request_data)
            if not isinstance(decision_result, dict): # Basic type check for robustness
                logger.error(f"DecisionAgent returned an unexpected type: {type(decision_result)}. Expected dict.")
                return {
                    'status': 'ERROR',
                    'reason': 'DecisionAgent returned an invalid response type.',
                    'details': f"Received: {decision_result}",
                    'endCall': False
                }
            logger.info(f"DecisionAgent result: {decision_result}")
        except Exception as e:
            logger.error(f"Unexpected error during decision_agent.should_book: {e}", exc_info=True)
            return {
                'status': 'ERROR',
                'reason': 'An unexpected error occurred while consulting DecisionAgent.',
                'details': str(e),
                'endCall': False
            }

        if not decision_result.get('approved'):
            logger.info("Booking not approved by DecisionAgent.")
            return {
                'status': 'REJECTED',
                'reason': decision_result.get('reason', 'Not specified by DecisionAgent'),
                'details': decision_result.get('details'),
                'endCall': False 
            }

        # Step 2: Book with CalendarAgent (if approved)
        logger.info("DecisionAgent approved booking. Proceeding with CalendarAgent.")
        try:
            booking_result = self.calendar_agent.book_appointment(request_data)
            if not isinstance(booking_result, dict): # Basic type check
                logger.error(f"CalendarAgent returned an unexpected type: {type(booking_result)}. Expected dict.")
                return {
                    'status': 'ERROR',
                    'reason': 'CalendarAgent returned an invalid response type.',
                    'details': f"Received: {booking_result}",
                    'endCall': False
                }
            logger.info(f"CalendarAgent booking result: {booking_result}")
        except Exception as e:
            logger.error(f"Unexpected error during calendar_agent.book_appointment: {e}", exc_info=True)
            return {
                'status': 'ERROR',
                'reason': 'An unexpected error occurred while booking with CalendarAgent.',
                'details': str(e),
                'endCall': False
            }

        if booking_result.get('success'):
            logger.info("Booking successful with CalendarAgent.")
            return {
                'status': 'BOOKED',
                'message': booking_result.get('message', 'Appointment booked successfully.'),
                'event_details': booking_result, # Contains event_id, htmlLink, etc.
                'endCall': True 
            }
        else:
            logger.warning("Booking failed with CalendarAgent.")
            return {
                'status': 'BOOKING_FAILED',
                'reason': booking_result.get('message', 'Booking failed as per CalendarAgent.'),
                'details': booking_result.get('details'), 
                'endCall': False
            }

# Example Usage (for illustration and manual testing)
if __name__ == '__main__':
    # Configure basic logging for testing
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Mock DecisionAgent
    class MockDecisionAgent:
        def __init__(self, approval_outcome):
            self.approval_outcome = approval_outcome
            if not callable(getattr(self, 'should_book', None)):
                 raise TypeError("MockDecisionAgent must have should_book")

        def should_book(self, request_data):
            logger.debug(f"MockDecisionAgent.should_book called with: {request_data}")
            return self.approval_outcome

    # Mock CalendarAgent
    class MockCalendarAgent:
        def __init__(self, booking_success_outcome):
            self.booking_success_outcome = booking_success_outcome
            if not callable(getattr(self, 'book_appointment', None)):
                 raise TypeError("MockCalendarAgent must have book_appointment")

        def book_appointment(self, request_data):
            logger.debug(f"MockCalendarAgent.book_appointment called with: {request_data}")
            return self.booking_success_outcome
            
    logger.info("\n--- Testing MainLogicAgent ---")

    sample_request = {'date': '2024-08-01', 'time': '10:00 AM', 'service': 'Dental Checkup'}

    # Scenario 1: DecisionAgent rejects
    decision_agent_reject = MockDecisionAgent({'approved': False, 'reason': 'TIME_UNAVAILABLE', 'details': 'Slot is outside business hours.'})
    calendar_agent_s1 = MockCalendarAgent({}) # Not called
    main_logic1 = MainLogicAgent(calendar_agent_s1, decision_agent_reject)
    result1 = main_logic1.handle_booking_request(sample_request)
    logger.info(f"S1 Result (DecisionAgent REJECTS): {result1}")
    assert result1['status'] == 'REJECTED'
    assert result1['reason'] == 'TIME_UNAVAILABLE'

    # Scenario 2: DecisionAgent approves, CalendarAgent books successfully
    decision_agent_approve = MockDecisionAgent({'approved': True, 'reason': 'NO_CONFLICT'})
    calendar_agent_success = MockCalendarAgent({
        'success': True, 
        'message': 'Appointment confirmed for Dental Checkup.', 
        'event_id': 'evt123', 
        'htmlLink': 'http://cal.example.com/evt123'
    })
    main_logic2 = MainLogicAgent(calendar_agent_success, decision_agent_approve)
    result2 = main_logic2.handle_booking_request(sample_request)
    logger.info(f"S2 Result (Decision approves, Calendar books): {result2}")
    assert result2['status'] == 'BOOKED'
    assert result2['event_details']['event_id'] == 'evt123'

    # Scenario 3: DecisionAgent approves, CalendarAgent fails booking
    calendar_agent_fail = MockCalendarAgent({
        'success': False, 
        'message': 'Calendar API quota exceeded.', 
        'details': {'error_code': 'QUOTA_EXCEEDED'}
    })
    main_logic3 = MainLogicAgent(calendar_agent_fail, decision_agent_approve) # Reusing decision_agent_approve
    result3 = main_logic3.handle_booking_request(sample_request)
    logger.info(f"S3 Result (Decision approves, Calendar FAILS): {result3}")
    assert result3['status'] == 'BOOKING_FAILED'
    assert result3['reason'] == 'Calendar API quota exceeded.'

    # Scenario 4: DecisionAgent throws an unexpected error
    class ErrorDecisionAgent:
        def should_book(self, request_data): # Ensure method is defined to pass __init__ check
            raise ValueError("Unexpected error in DecisionAgent")
            
    decision_agent_error = ErrorDecisionAgent()
    # Need a valid calendar agent for this test case as DA is called first
    main_logic4 = MainLogicAgent(calendar_agent_success, decision_agent_error) 
    result4 = main_logic4.handle_booking_request(sample_request)
    logger.info(f"S4 Result (DecisionAgent throws ERROR): {result4}")
    assert result4['status'] == 'ERROR'
    assert "consulting DecisionAgent" in result4['reason']
    assert "Unexpected error in DecisionAgent" in result4['details']
    
    # Scenario 5: CalendarAgent throws an unexpected error
    class ErrorCalendarAgent:
        def book_appointment(self, request_data): # Ensure method is defined
            raise ConnectionError("Cannot connect to Calendar API")

    calendar_agent_throws_error = ErrorCalendarAgent()
    main_logic5 = MainLogicAgent(calendar_agent_throws_error, decision_agent_approve) # Decision approves
    result5 = main_logic5.handle_booking_request(sample_request)
    logger.info(f"S5 Result (CalendarAgent throws ERROR): {result5}")
    assert result5['status'] == 'ERROR'
    assert "booking with CalendarAgent" in result5['reason']
    assert "Cannot connect to Calendar API" in result5['details']

    # Scenario 6: Misconfigured DecisionAgent (e.g. should_book not callable after init)
    logger.info("\n--- Testing Misconfiguration ---")
    class BrokenDecisionAgent:
        # No should_book method, or it's not callable
        pass
    
    broken_da_instance = BrokenDecisionAgent() 
    # This will log an error in MainLogicAgent.__init__ if the check is strict enough
    # To make it fail, we would need to make should_book exist but not be callable,
    # or for the hasattr check in init to be more stringent.
    # For this example, we'll simulate the case where it passes init but fails at call time.
    # We can do this by making should_book not callable on the instance.
    # However, the current __init__ check for callable should catch this.
    # Let's assume the __init__ logs an error.
    # If we want to test the try-except in handle_booking_request for this,
    # we'd need a DA that passes init but whose should_book becomes uncallable or raises TypeError.
    
    # Test with a DA whose should_book returns non-dict
    bad_response_da = MockDecisionAgent("not a dict") # should_book returns a string
    main_logic_bad_da_resp = MainLogicAgent(calendar_agent_success, bad_response_da)
    result_bad_da_resp = main_logic_bad_da_resp.handle_booking_request(sample_request)
    logger.info(f"Result with DA returning bad type: {result_bad_da_resp}")
    assert result_bad_da_resp['status'] == 'ERROR'
    assert "DecisionAgent returned an invalid response type" in result_bad_da_resp['reason']


    logger.info("\nAll MainLogicAgent example tests completed.")
```
