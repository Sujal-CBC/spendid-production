import os, json

# the basic level it is where things -> all things are update or add here
class StateManager:
    def __init__(self, storage_path="session_data/sessions.json"):
        self.storage_path = storage_path
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        self.store = {}
        self._load()

    def _load(self):
        if os.path.exists(self.storage_path):
            with open(self.storage_path, "r") as f:
                try:
                    self.store = json.load(f)
                except json.JSONDecodeError:
                    self.store = {}
        else:
            self.store = {}

    def _save(self):
        with open(self.storage_path, "w") as f:
            json.dump(self.store, f, indent=4)

    def _get_raw(self, session_id: str):
        return self.store.get(session_id, self._default_state())

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
            "api_results": {},
        }

    def get(self, session_id: str):
        self._load() # Refresh from disk
        return self._get_raw(session_id)

    def update(self, session_id: str, new_data: dict):
        self._load()
        state = self._get_raw(session_id)
        state.update(new_data)
        self.store[session_id] = state
        self._save()
        return state

    def overwrite_api_results(self, session_id: str, api_results: dict):
        """Completely replace api_results with new data (not merge)"""
        self._load()
        state = self._get_raw(session_id)
        state["api_results"] = api_results  # Full replacement, not merge
        self.store[session_id] = state
        self._save()
        return state

    def is_complete(self, session_id: str):
        state = self.get(session_id)
        # Check core fields for completeness
        core_fields = [
            "zipcode", "age", "number_of_people", "has_house", "salary", 
            "is_net_salary", "past_credit_debt", "student_loan", "other_debt"
        ]
        missing = [k for k in core_fields if state.get(k) is None]
        return len(missing) == 0, missing