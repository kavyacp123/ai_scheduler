import os
import requests

class UserAgent:
    def __init__(self, main_logic_agent):
        self.main_logic_agent = main_logic_agent
        self.vapi_endpoint = os.getenv('VAPI_AI_ENDPOINT')  # Set this in your .env
        self.vapi_api_key = os.getenv('VAPI_AI_API_KEY')    # If needed

    def handle_user_message(self, message, call_info):
        structured_request = self.extract_intent_with_vapi(message)
        return self.main_logic_agent.handle_booking_request(structured_request, call_info)

    def extract_intent_with_vapi(self, message):
        text = message.get('content', '') if isinstance(message, dict) else str(message)
        if not self.vapi_endpoint:
            # fallback to default extraction if Vapi AI is not configured
            return {
                "intent": "book_appointment",
                "date": None,
                "time": None,
                "service_type": "General Appointment",
                "raw_text": text
            }
        try:
            payload = {"text": text}
            headers = {"Content-Type": "application/json"}
            if self.vapi_api_key:
                headers["Authorization"] = f"Bearer {self.vapi_api_key}"
            response = requests.post(self.vapi_endpoint, json=payload, headers=headers, timeout=10)
            data = response.json()
            # Adjust the following lines based on Vapi AI's actual response format
            return {
                "intent": data.get("intent", "book_appointment"),
                "date": data.get("date"),
                "time": data.get("time"),
                "service_type": data.get("service_type", "General Appointment"),
                "raw_text": text
            }
        except Exception as e:
            # fallback to default extraction on error
            return {
                "intent": "book_appointment",
                "date": None,
                "time": None,
                "service_type": "General Appointment",
                "raw_text": text
            } 