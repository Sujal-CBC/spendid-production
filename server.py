# app/workflow/engine.py

# this uses statemanger for updating state or verifing that we have collected all userinfo
from app.workflow.engine import WorkflowEngine
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv 
import requests
import os,sys,json

load_dotenv()
mcp = FastMCP("Spendid-mcp")

# core logic and real mcp starts from here

workflow = WorkflowEngine()

# for update the payload and next question
@mcp.tool(
    name="add-or-update-payload",
    description="It update the payload for like zipcode,age,salary,net_salary,number of people,has house,credit card debt,student loan,other debt"
)
def add_or_update_payload(new_data : dict,session_id : str) -> dict: 
    return workflow.process(session_id,new_data)

# for zipcode verification
@mcp.tool(
    name="verify-zipcode-or-city-name",
    description="It just verify the zipcode or city is in New-york or not" 
    )
def verify_location(city_or_zip : str | int) -> dict: 
    BASE_URL = os.getenv("ZIPCODE_URL")
    if city_or_zip.isnumeric(): 
        zip = int(city_or_zip)  
    else: 
        zip = city_or_zip
    try:
        params = {"search": zip}
        response = requests.get(BASE_URL, params=params)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return {"error": True, "message": str(e)}
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
    return {
        "location": plann["area_name"],
        "zip_code": plann["zip_code"]
    }

if __name__ == "__main__": 
    print("sever is running...") 
    mcp.run()