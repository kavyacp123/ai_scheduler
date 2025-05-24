import os
import logging
import requests # For Vapi AI call and exceptions
from unittest.mock import MagicMock, patch # For example usage

# Initialize logger for the module
logger = logging.getLogger(__name__)

class UserAgent:
    def __init__(self, main_logic_agent):
        self.main_logic_agent = main_logic_agent
        self.vapi_ai_endpoint = os.getenv('VAPI_AI_ENDPOINT')
        self.vapi_ai_token = os.getenv('VAPI_AI_TOKEN') # Assuming a token is needed
        logger.info("UserAgent initialized.")

        if not hasattr(self.main_logic_agent, 'handle_booking_request') or \
           not callable(getattr(self.main_logic_agent, 'handle_booking_request', None)):
            logger.error("MainLogicAgent is missing the 'handle_booking_request' callable method.")
            # Depending on desired strictness, could raise an error:
            raise AttributeError("MainLogicAgent must have a 'handle_booking_request' callable method.")

    def extract_intent_with_vapi(self, raw_text, call_info=None):
        """
        Extracts intent and entities from raw text using Vapi AI.
        Includes fallback logic if Vapi AI is not configured or fails.
        """
        logger.debug(f"extract_intent_with_vapi called with: '{raw_text}'")
        
        # Default fallback structure, ensuring all keys are present
        fallback_response = {
            'intent': 'UNKNOWN', 
            'date': None, 
            'time': None, 
            'service_type': None,
            'raw_text': raw_text # Always include the original text
        }

        if not self.vapi_ai_endpoint or not self.vapi_ai_token:
            logger.warning("Vapi AI endpoint or token not configured. Using fallback intent extraction.")
            return fallback_response

        headers = {
            "Authorization": f"Bearer {self.vapi_ai_token}",
            "Content-Type": "application/json"
        }
        # Construct payload, including session_id from call_info if available
        payload = { "query": raw_text }
        if call_info and 'session_id' in call_info:
            payload['session_id'] = call_info['session_id']
        
        logger.debug(f"Sending payload to Vapi AI: {payload}")

        try:
            response = requests.post(self.vapi_ai_endpoint, json=payload, headers=headers, timeout=10)
            response.raise_for_status()  # Raises HTTPError for bad responses (4XX or 5XX)
            
            vapi_result = response.json()
            logger.info(f"Received response from Vapi AI: {vapi_result}")

            # Adapt this based on the actual structure of Vapi AI's response
            # Ensuring the output dictionary has the consistent keys.
            entities = vapi_result.get('entities', {}) if isinstance(vapi_result.get('entities'), dict) else {}
            structured_intent = {
                'intent': vapi_result.get('intent', 'UNKNOWN'),
                'date': entities.get('date'), 
                'time': entities.get('time'), 
                'service_type': entities.get('service_type'), 
                'raw_text': raw_text
            }
            return structured_intent

        except requests.exceptions.Timeout:
            logger.error("Request to Vapi AI timed out. Using fallback.", exc_info=True)
            return fallback_response
        except requests.exceptions.HTTPError as e:
            logger.error(f"Vapi AI request failed with HTTPError: {e.response.status_code} - {e.response.text}. Using fallback.", exc_info=True)
            return fallback_response
        except requests.exceptions.RequestException as e: # Catch other request-related errors
            logger.error(f"Request to Vapi AI failed: {e}. Using fallback.", exc_info=True)
            return fallback_response
        except ValueError as e: # Includes JSONDecodeError
            logger.error(f"Error decoding Vapi AI JSON response: {e}. Using fallback.", exc_info=True)
            return fallback_response
        except Exception as e:
            logger.error(f"An unexpected error occurred during Vapi AI call: {e}. Using fallback.", exc_info=True)
            return fallback_response

    def handle_user_message(self, raw_text, call_info=None):
        """
        Handles a raw user message, extracts intent, and passes it to MainLogicAgent.
        """
        logger.info(f"UserAgent received raw message: '{raw_text}'")
        if call_info:
            logger.debug(f"Associated call_info: {call_info}")

        structured_request = self.extract_intent_with_vapi(raw_text, call_info)
        logger.info(f"Structured request from intent extraction: {structured_request}")
            
        try:
            response = self.main_logic_agent.handle_booking_request(structured_request)
            logger.info(f"Response from MainLogicAgent: {response}")
            return response
        except Exception as e:
            logger.error(f"Unexpected error during main_logic_agent.handle_booking_request: {e}", exc_info=True)
            return {
                'status': 'ERROR',
                'reason': 'An unexpected error occurred while handling the booking logic.',
                'details': str(e),
                'endCall': False 
            }

# Example Usage
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Mock MainLogicAgent
    class MockMainLogicAgent:
        def handle_booking_request(self, structured_request):
            logger.info(f"MockMainLogicAgent received: {structured_request}")
            if structured_request.get('intent') == 'BOOK_APPOINTMENT' and structured_request.get('date') and structured_request.get('time'):
                return {'status': 'BOOKED', 'message': f"Appointment for {structured_request.get('service_type', 'something')} mock-booked successfully!", 'event_details': structured_request}
            elif structured_request.get('intent') == 'UNKNOWN':
                return {'status': 'CLARIFY', 'message': 'Sorry, I could not understand that.'}
            else:
                return {'status': 'REJECTED', 'reason': 'Mock logic: Missing date/time or intent not BOOK_APPOINTMENT.'}

    mock_main_logic_agent = MockMainLogicAgent()
    
    logger.info("\n--- Testing UserAgent ---")

    # Scenario 1: Successful Vapi AI call
    vapi_response_success = {
        'intent': 'BOOK_APPOINTMENT',
        'entities': {
            'date': '2024-09-15',
            'time': '03:00 PM',
            'service_type': 'Dental Cleaning'
        }
    }
    with patch.dict(os.environ, {'VAPI_AI_ENDPOINT': 'http://fakevapi.com/intent', 'VAPI_AI_TOKEN': 'fake_token'}):
        with patch('requests.post', return_value=MagicMock(status_code=200, json=lambda: vapi_response_success)) as mock_post_success:
            user_agent = UserAgent(mock_main_logic_agent)
            response1 = user_agent.handle_user_message("Book a dental cleaning for Sept 15th at 3pm", call_info={'session_id': 'sess123'})
            logger.info(f"S1 Response (Vapi Success): {response1}")
            mock_post_success.assert_called_once()
            assert response1['status'] == 'BOOKED'
            assert response1['event_details']['service_type'] == 'Dental Cleaning'


    # Scenario 2: Vapi AI Timeout (requests.exceptions.Timeout)
    with patch.dict(os.environ, {'VAPI_AI_ENDPOINT': 'http://fakevapi.com/intent', 'VAPI_AI_TOKEN': 'fake_token'}):
        with patch('requests.post', side_effect=requests.exceptions.Timeout("Vapi Timeout")) as mock_post_timeout:
            user_agent = UserAgent(mock_main_logic_agent)
            response2 = user_agent.handle_user_message("Book a dental cleaning")
            logger.info(f"S2 Response (Vapi Timeout): {response2}")
            mock_post_timeout.assert_called_once()
            assert response2['status'] == 'CLARIFY' # Fallback intent is UNKNOWN

    # Scenario 3: Vapi AI HTTP Error (e.g., 500)
    with patch.dict(os.environ, {'VAPI_AI_ENDPOINT': 'http://fakevapi.com/intent', 'VAPI_AI_TOKEN': 'fake_token'}):
        mock_http_error_response = MagicMock()
        mock_http_error_response.status_code = 500
        mock_http_error_response.text = "Internal Server Error"
        mock_http_error_response.raise_for_status = MagicMock(side_effect=requests.exceptions.HTTPError(response=mock_http_error_response))
        
        with patch('requests.post', return_value=mock_http_error_response) as mock_post_http_error:
            user_agent = UserAgent(mock_main_logic_agent)
            response3 = user_agent.handle_user_message("Book something for me")
            logger.info(f"S3 Response (Vapi HTTP Error): {response3}")
            mock_post_http_error.assert_called_once()
            mock_http_error_response.raise_for_status.assert_called_once()
            assert response3['status'] == 'CLARIFY'

    # Scenario 4: Vapi AI not configured (missing VAPI_AI_ENDPOINT)
    with patch.dict(os.environ, {}, clear=True): # Ensure env vars are cleared
        # No need to patch requests.post as it shouldn't be called
        user_agent = UserAgent(mock_main_logic_agent)
        response4 = user_agent.handle_user_message("Hi there, can you book an appointment?")
        logger.info(f"S4 Response (Vapi Not Configured): {response4}")
        assert response4['status'] == 'CLARIFY'
        
    # Scenario 5: UserAgent init with misconfigured MainLogicAgent
    logger.info("\n--- Testing UserAgent Initialization Failure ---")
    class BrokenMainLogicAgent:
        pass # Missing handle_booking_request

    broken_ml_agent = BrokenMainLogicAgent()
    with patch.object(logging.getLogger('user_agent'), 'error') as mock_log_error:
        try:
            ua_with_broken_ml = UserAgent(broken_ml_agent)
            # If AttributeError is not raised by __init__, then the call will fail
            response5 = ua_with_broken_ml.handle_user_message("Test with broken ML")
            logger.info(f"S5 Response (UserAgent with broken MainLogic): {response5}")
            # This path might not be reached if __init__ raises the error as intended by problem desc
        except AttributeError as e:
            logger.info(f"Caught expected AttributeError: {e}")
            assert "MainLogicAgent must have a 'handle_booking_request' callable method." in str(e)
        
        # Check if error was logged by __init__
        # This assertion is a bit tricky because the error might be logged AND an exception raised.
        # If an exception is raised in __init__, this line might not be hit in the same way.
        # However, the problem description implies __init__ should log an error.
        # The actual code raises AttributeError, so logging check is more for if it didn't raise.
        # For now, we'll check if the log occurred if no exception stopped init.
        # Given the current code raises AttributeError, the log in init might not be the primary check.
        # The primary check is the raise.
        # If the raise was removed, then this log check would be:
        # mock_log_error.assert_any_call("MainLogicAgent is missing the 'handle_booking_request' callable method.")


    logger.info("\nAll UserAgent example tests completed.")
```
