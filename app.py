from flask import Flask, request, jsonify
from agents.user_agent import UserAgent
from agents.main_logic_agent import MainLogicAgent
from agents.calendar_agent import CalendarAgent
from agents.decision_agent import DecisionAgent
import requests
import re
from datetime import datetime, timedelta
import pytz
import os
import logging
from typing import Dict, List, Optional, Tuple
import json

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize agents
calendar_agent = CalendarAgent()
decision_agent = DecisionAgent(calendar_agent)
main_logic_agent = MainLogicAgent(calendar_agent, decision_agent)
user_agent = UserAgent(main_logic_agent)

@app.route('/vapi/webhook', methods=['POST'])
def vapi_webhook():
    data = request.get_json()
    message = data.get('message', {})
    call_info = data.get('call', {})
    response = user_agent.handle_user_message(message, call_info)
    return jsonify(response)

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'})

@app.route('/available-slots/<date>', methods=['GET'])
def get_available_slots(date):
    """Get available slots for a date (format: YYYY-MM-DD)"""
    try:
        slots = calendar_agent.get_available_slots(date)
        return jsonify({
            'date': date,
            'available_slots': slots
        })
    except Exception as e:
        logger.error(f"Error getting available slots: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/test', methods=['POST'])
def test_booking():
    """Test endpoint for debugging"""
    try:
        test_data = {
            'message': {'content': 'I want to book an appointment for tomorrow at 2 PM'},
            'call': {'id': 'test-call-123'}
        }
        response = user_agent.handle_user_message(test_data['message'], test_data['call'])
        return jsonify(response)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Environment check
    required_env_vars = ['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REFRESH_TOKEN']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.warning(f"Missing environment variables: {missing_vars}")
        logger.warning("Some features may not work properly")
    
    logger.info("Environment check:")
    logger.info(f"- Google Client ID: {'Set' if os.getenv('GOOGLE_CLIENT_ID') else 'Missing'}")
    logger.info(f"- Google Client Secret: {'Set' if os.getenv('GOOGLE_CLIENT_SECRET') else 'Missing'}")
    logger.info(f"- Google Refresh Token: {'Set' if os.getenv('GOOGLE_REFRESH_TOKEN') else 'Missing'}")
    logger.info(f"- Decision AI Endpoint: {os.getenv('DECISION_AI_ENDPOINT', 'Not set')}")
    
    port = int(os.getenv('PORT', 3000))
    app.run(host='0.0.0.0', port=port, debug=False) 