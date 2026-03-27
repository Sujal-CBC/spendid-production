# app/workflow/engine.py

# this uses statemanger for updating state or verifing that we have collected all userinfo
from app.state.state_manager import StateManager 
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv 
import requests
import os,sys,json

load_dotenv()

sm = StateManager()
mcp = FastMCP("Spendid-mcp")

# simple class of workflow....
class WorkflowEngine:
    def __init__(self):
        self.sm = sm

    def process(self, session_id: str, new_data: dict):
        # 1. Update state
        state = self.sm.update(session_id, new_data)

        # 2. Check missing fields
        complete, missing = self.sm.is_complete(session_id)
        if not complete:
            # Return next question(s) for LLM to ask user
            return {"next_fields": missing, "state": state}

        # 3. All required fields are filled → trigger APIs
        # For now, just simulate
        api_results = self.run_api_pipeline(state)

        # 4. Return results
        return {"state": state, "api_results": api_results}

    def run_api_pipeline(self, state):
        # Placeholder: actual API calls go here
        return {"message": "ask for final approval"}
