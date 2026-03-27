# app/state/state_manager.py 

# the basic level it is where things -> all things are update or add here
class StateManager:
    def __init__(self):
        # session_id → state
        self.store = {}

    def _default_state(self):
        return {
            "zipcode": None,
            "age": None,
            "number_of_people": None,
            "has_house": None,
            "salary": None,
            "is_net_salary": None,
            "past_credit_debt": None,
            "student_loan": None,
            "other_debt": None,
        }

    def get(self, session_id: str):
        return self.store.get(session_id, self._default_state())

    def update(self, session_id: str, new_data: dict):
        state = self.get(session_id)
        state.update(new_data)
        self.store[session_id] = state
        return state

    def is_complete(self, session_id: str):
        state = self.get(session_id)
        missing = [k for k, v in state.items() if v is None]
        return len(missing) == 0, missing