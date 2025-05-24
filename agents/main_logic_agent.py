class MainLogicAgent:
    def __init__(self, calendar_agent, decision_agent):
        self.calendar_agent = calendar_agent
        self.decision_agent = decision_agent

    def handle_booking_request(self, request, call_info):
        # 1. Check with decision agent
        approved = self.decision_agent.should_book(request, call_info)
        if not approved:
            return {"message": "Not approved to book at this time.", "endCall": False}
        # 2. Book with calendar agent
        result = self.calendar_agent.book_appointment(request)
        return result 