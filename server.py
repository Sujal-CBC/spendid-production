# app/workflow/engine.py

# this uses statemanger for updating state or verifing that we have collected all userinfo
from app.workflow.engine import WorkflowEngine 
from app.state.state_manager import StateManager
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv 
import requests
import os,sys,json

load_dotenv()
mcp = FastMCP("Spendid-mcp")

# core logic and real mcp starts from here

workflow = WorkflowEngine() 
sm = StateManager()

# for zipcode verification
@mcp.tool(
    name="verify-zipcode-or-city-name",
    description="It just verify the zipcode or city is in New-york or not" 
    )
def verify_location(session_id : str, city_or_zip : str | int) -> dict: 
    BASE_URL = os.getenv("ZIPCODE_URL")
    if isinstance(city_or_zip, str) and city_or_zip.isnumeric(): 
        zip = int(city_or_zip)  
    else: 
        zip = city_or_zip
    try:
        params = {"search": zip}
        url = f"{BASE_URL}search={params['search']}"
        print(url)

        response = requests.get(url)
        print("response:", response)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
    print(response, "api-response", file=sys.stderr) 
    if response.status_code != 200:
        return {
            "error": True,
            "status": response.status_code,
            "message": response.text
        }
    data = response.json()
    if "plans" not in data or len(data["plans"]) == 0:
        return {
            "error": True,
            "message": f"No data found for {zip}"
        }
    plann = data["plans"][0]
    params = {
        "zipcode" : plann['zip_code']
    } 
    sm.update(session_id,params) 
    print({
        "valid" : "valid",
        "location": plann["area_name"],
        "zip_code": plann["zip_code"]
    },"ppppp")
    return {
        "valid" : "valid",
        "location": plann["area_name"],
        "zip_code": plann["zip_code"]
    }

# for update the payload and next question
@mcp.tool(
    name="add-or-update-payload",
    description="Update user profile data. Pass only the fields that are being provided or changed."
)
def add_or_update_payload(
    session_id : str,
    zipcode: str | None = None,
    age: int | None = None,
    number_of_people: int | None = None,
    has_house: bool | None = None,
    salary: int | None = None,
    is_net_salary: bool | None = None,
    past_credit_debt: float | None = None,
    student_loan: float | None = None,
    other_debt: float | None = None
) -> dict: 
    # Extract all provided fields into a dict, excluding session_id
    new_data = {} 
    if age is not None and (age < 18 or age > 120):
        return {"error": True, "message": "Age must be between 18 and 120."} 
    if number_of_people is not None and number_of_people not in range(1,6): 
        return {"error":True, "message":"Number of people must be between 1 to 5"}
    locs = locals()
    fields = [
        "zipcode", "age", "number_of_people", "has_house", "salary", 
        "is_net_salary", "past_credit_debt", "student_loan", "other_debt"
    ]
    for field in fields:
        if locs.get(field) is not None:
            new_data[field] = locs[field]
            
    return workflow.process(session_id, new_data)

# for explicit budget generation
@mcp.tool(
    name="generate-budget",
    description="Trigger the SPENDiD API pipeline to generate a full budget once the payload is complete."
)
def generate_budget(session_id: str) -> dict:
    state = workflow.sm.get(session_id)
    complete, missing = workflow.sm.is_complete(session_id)
    if not complete:
        return {"error": True, "message": f"Payload incomplete. Missing: {missing}"}
    api_results = workflow.run_api_pipeline(state)
    # Use overwrite to completely replace api_results (not merge)
    workflow.sm.overwrite_api_results(session_id, api_results)
    return {"state": state, "api_results": api_results}

# for updating specific lifestyle expenses
@mcp.tool(
    name="update-budget-category",
    description="Update a specific lifestyle category (e.g., 'Dining Out', 'Groceries', 'Car Payments', 'Transportation Fares') with a new monthly value."
)
def update_budget_category(session_id: str, updates: dict) -> dict:
    state = workflow.sm.get(session_id)

    res = workflow.generate_budget_update(
        payload_with_new_values=updates,
        payload=state,
        accumulated_updates=state.get("api_results", {}).get("merged_updates", {})
    )

    workflow.sm.overwrite_api_results(session_id, res)
    return res




if __name__ == "__main__": 
    print("sever is running...")  
    # verify_location("123","12345") 
    mcp.run()