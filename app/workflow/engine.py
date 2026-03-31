# app/workflow/engine.py

# this uses statemanger for updating state or verifing that we have collected all userinfo
from app.state.state_manager import StateManager 
from app.constants.constant import TRANSFORMER,CATEGORY_MAP
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv 
import requests
import os,json

load_dotenv()

sm = StateManager()
mcp = FastMCP("Spendid-mcp")

# simple class of workflow....
class WorkflowEngine:
    def __init__(self):
        self.sm = sm

    def generate_saving(self, payload: dict) -> int:
        API_KEY = os.getenv("SPENDiD_API_KEY")
        BASE_URL = os.getenv("NET_ANNUAL_URL")
        LENDING_URL = os.getenv("LENDING_URL")
        headers = {"x-api-key": API_KEY}

        # ── Step 1: resolve net annual income ────────────────────────────────────
        try:
            if payload.get("is_net_salary") is not True:
                url = f"{BASE_URL}/net-income"
                params = {
                    "gross": int(payload["salary"] * 12),
                    "zip": payload["zipcode"],
                }
                response = requests.get(url, headers=headers, params=params, timeout=30)
                response.raise_for_status()
                net_annual_income = response.json().get("net_annual_income", payload["salary"] * 12)
            else:
                net_annual_income = payload["salary"] * 12
        except Exception:
            net_annual_income = payload["salary"] * 12

        # ── Step 2: compute total annual debt ────────────────────────────────────
        total_debt = sum(
            (payload.get(k) or 0)
            for k in ("past_credit_debt", "student_loan", "other_debt")
        ) * 12

        # ── Step 3: call lending API ──────────────────────────────────────────────
        try:
            if not LENDING_URL:
                return int(net_annual_income * 0.1)
            lending_payload = {
                "budget": {
                    "health_insurance": 0,
                    "mortgage_and_rent": None,
                    "other_debt_payments": int(total_debt),
                    "savings": 0,
                    "vehicle_purchase_and_lease": None,
                },
                "demographics": {
                    "age": payload["age"],
                    "household_members": payload["number_of_people"],
                    "is_homeowner": payload["has_house"],
                    "net_annual_income": int(net_annual_income),
                    "zip": str(payload["zipcode"]),
                },
            }
            res = requests.post(url=LENDING_URL, headers=headers, json=lending_payload, timeout=30)
            res.raise_for_status()
            savings_data = res.json()
            # cash_excess is annual — return as-is
            return int(savings_data["elements"]["cash_excess"])
        except Exception:
            # Fallback: 10% of net annual income
            return int(net_annual_income * 0.1) 

    def process(self, session_id: str, new_data: dict):
        # 1. Update state
        state = self.sm.update(session_id, new_data)

        # 2. Check missing fields
        complete, missing = self.sm.is_complete(session_id)
        if not complete:
            # Return next question(s) for LLM to ask user
            return {"next_fields": missing, "state": state}

        # 3. All required fields are filled → trigger APIs
        api_results = self.run_api_pipeline(state) 

        # 4. Return results
        return {"api_results": api_results, "next_fields": []}

    def run_api_pipeline(self, payload):
        # Placeholder: actual API calls go here
        BASE_URL = os.getenv("NET_ANNUAL_URL")
        API_KEY = os.getenv("SPENDiD_API_KEY")
        headers = {"x-api-key": API_KEY} 
        if payload['is_net_salary'] is not True:
        # salary is GROSS annual → convert to net via API
            url = f"{BASE_URL}/net-income"
            params = {
                "gross": int(payload['salary'] * 12),  # Salary is monthly, convert to annual gross
                "zip": payload["zipcode"]
            }
            try:
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                net_annual_income = response.json().get("net_annual_income")
            except Exception as e:
                net_annual_income = payload['salary'] * 12
        else:
            # salary is NET annual → use directly
            net_annual_income = payload['salary']*12  

        total_debt = sum(payload.get(k) or 0 for k in ("past_credit_debt", "student_loan", "other_debt"))
        total_debt*=12
        saving = self.generate_saving(payload)

        # budget/generate logic here
        payload_for_budget_generate = {
            "budget":{
                "health_insurance" : 0,
                "mortgage_and_rent":None,
                "other_debt_payments":int(total_debt), 
                "savings": int(saving),
                "vehicle_purchase_and_lease":None
            },
        "demographics": {
            "age": payload["age"],
            "household_members": payload["number_of_people"],
            "is_homeowner": payload["has_house"],
            "net_annual_income": net_annual_income,
            "zip": f"{(payload['zipcode'])}",
        },
        "transformer": TRANSFORMER
        }
        budget_generate_url = os.getenv("BUDGET_GENERATE_URL")
        if not budget_generate_url:
            raise ValueError("BUDGET_GENERATE_URL not set")

        try:
            response_for_budget_generate = requests.post(
                url=budget_generate_url,
                headers=headers,
                json=payload_for_budget_generate
            )
            response_for_budget_generate.raise_for_status()
            data_bud = response_for_budget_generate.json()
        except Exception as e:
            raise ValueError(f"Failed to generate budget: {e}")

        # Divide all numeric values by 12
        for i in data_bud:
            for j in data_bud[i]:
                if isinstance(data_bud[i][j], (int, float)):
                    data_bud[i][j] //= 12
        
        os.makedirs("session_data", exist_ok=True)
        
        # Model Generate logic here.
        payload_for_model_generate = {
            "demographics": {
                "age": payload["age"],
                "household_members": payload["number_of_people"],
                "is_homeowner": payload["has_house"],
                "net_annual_income": int(net_annual_income),
                "zip": f"{payload['zipcode']}",
                "total_debt": total_debt
            },
            "transformer": TRANSFORMER
        }
        model_generate_url = os.getenv("MODEL_GENERATE_URL")
        try:
            if model_generate_url:
                response_for_model_generate = requests.post(
                    url=model_generate_url,
                    headers=headers,
                    json=payload_for_model_generate
                )
                response_for_model_generate.raise_for_status()
                data_model = response_for_model_generate.json()
                for i in data_model:
                    for j in data_model[i]:
                        if isinstance(data_model[i][j], (int, float)):
                            data_model[i][j] //= 12
            else:
                data_model = {}
        except Exception:
            data_model = {}

        # generate the peers above score 
        payload_for_peers_above = {
            "budget":{
                "health_insurance" : data_bud.get('transformed', {}).get('Health Insurance', 0),
                "other_debt_payments":int(total_debt), 
                "savings": int(saving),
            },
            "demographics": {
                "age": payload["age"],
                "household_members": payload["number_of_people"],
                "is_homeowner": payload["has_house"],
                "net_annual_income": net_annual_income,
                "zip": f"{(payload['zipcode'])}",
            }
        } 
        
        url_peers_top = os.getenv("ABOVE_PEERS_URL")
        if url_peers_top:
            try:
                response_for_peers_top = requests.post(
                    url=url_peers_top,
                    headers=headers,
                    json=payload_for_peers_above
                )
                response_for_peers_top.raise_for_status()
                peers = response_for_peers_top.json().get('breakeven', 0)
                data_bud.setdefault("transformed", {})["peers"] = float(peers)
            except Exception:
                pass

        return data_bud 
    
    def updating_values(self,new_payload: dict) -> dict:
        updated_values = {}
        for key in new_payload:
            if key in CATEGORY_MAP:
                value_to_multiply = int(12 / len(CATEGORY_MAP[key]))
                for i in CATEGORY_MAP[key]:
                    updated_values[i] = new_payload[key] * value_to_multiply
            else:
                print(f"Key '{key}' not found in CATEGORY_MAP. Skipping.")
        return updated_values


    def generate_saving_for_update_api(self,payload_with_new_values: dict, payload: dict) -> int:
        API_KEY = os.getenv("SPENDiD_API_KEY")
        BASE_URL = os.getenv("NET_ANNUAL_URL")
        headers = {"x-api-key": API_KEY}

        if payload["is_net_salary"] is not True:
            url = f"{BASE_URL}/net-income"
            params = {
                "gross": payload["salary"] * 12,
                "zip": payload["zipcode"]
            }
            try:
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                net_annual_income = response.json().get("net_annual_income")
            except Exception:
                net_annual_income = payload["salary"] * 12
        else:
            net_annual_income = payload["salary"] * 12

        demographics = {
            "age": payload["age"],
            "household_members": payload["number_of_people"],
            "is_homeowner": payload["has_house"],
            "net_annual_income": int(net_annual_income),
            "zip": f"{payload['zipcode']}",
        }

        budget_vals = self.updating_values(payload_with_new_values)

        os.makedirs("session_data", exist_ok=True)
        try:
            with open("session_data/generate_budget.json", "r") as f:
                data = json.load(f)
            budget_vals.setdefault("health_insurance", data.get("transformed", {}).get("Health Insurance", 0))
            budget_vals.setdefault("other_debt_payments", data.get("budget", {}).get("other_debt_payments", 0))
            budget_vals.setdefault("savings", data.get("budget", {}).get("savings", 0))
        except Exception:
            pass

        budget_vals.setdefault("mortgage_and_rent", None)
        budget_vals.setdefault("vehicle_purchase_and_lease", None)

        payload_for_api = {
            "budget": budget_vals,
            "demographics": demographics
        }

        lending_url = os.getenv("LENDING_URL")
        try:
            if lending_url:
                res = requests.post(url=lending_url, headers=headers, json=payload_for_api)
                res.raise_for_status()
                savings = res.json()
                return int(savings["elements"]["cash_excess"])
            return int(net_annual_income * 0.1)
        except Exception:
            return int(net_annual_income * 0.1)


    def _merge_updates(self,accumulated_updates: dict | None, new_updates: dict | None) -> dict:
        merged = dict(accumulated_updates or {})
        merged.update(new_updates or {})
        return merged


    def generate_budget_update(
        self,
        payload_with_new_values: dict,
        payload: dict,
        *,
        accumulated_updates: dict | None = None,
    ) -> dict:
        payload_with_new_values = self._merge_updates(accumulated_updates, payload_with_new_values)
        merged_updates = payload_with_new_values

        API_KEY = os.getenv("SPENDiD_API_KEY")
        BASE_URL = os.getenv("NET_ANNUAL_URL")
        headers = {"x-api-key": API_KEY}

        if payload["is_net_salary"] is not True:
            url = f"{BASE_URL}/net-income"
            params = {
                "gross": payload["salary"] * 12,
                "zip": payload["zipcode"]
            }
            try:
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                net_annual_income = response.json().get("net_annual_income")
            except Exception:
                net_annual_income = payload["salary"] * 12
        else:
            net_annual_income = payload["salary"] * 12

        demographics = {
            "age": payload["age"],
            "household_members": payload["number_of_people"],
            "is_homeowner": payload["has_house"],
            "net_annual_income": int(net_annual_income),
            "zip": f"{payload['zipcode']}",
        }

        savings = self.generate_saving_for_update_api(payload_with_new_values, payload)
        budget_payload = self.updating_values(payload_with_new_values)

        os.makedirs("session_data", exist_ok=True)
        try:
            with open("session_data/generate_budget.json", "r") as f:
                data = json.load(f)
            budget_payload.setdefault("health_insurance", data.get("transformed", {}).get("Health Insurance", 0))
            budget_payload.setdefault("other_debt_payments", data.get("budget", {}).get("other_debt_payments", 0))
        except Exception:
            pass

        budget_payload.setdefault("mortgage_and_rent", None)
        budget_payload["savings"] = savings
        budget_payload.setdefault("vehicle_purchase_and_lease", None)

        payload_for_budget_generate = {
            "budget": budget_payload,
            "demographics": demographics,
            "transformer": TRANSFORMER
        }

        generate_budget_url = os.getenv("BUDGET_GENERATE_URL")
        try:
            res_of_generate_budget = requests.post(
                url=generate_budget_url,
                headers=headers,
                json=payload_for_budget_generate
            )
            res_of_generate_budget.raise_for_status()
            data_bud = res_of_generate_budget.json()
            for i in data_bud:
                for j in data_bud[i]:
                    if isinstance(data_bud[i][j], (int, float)):
                        data_bud[i][j] //= 12
        except Exception as e:
            raise ValueError(f"Budget generate error: {e}")

        # Model generate
        payload_for_model_generate = {
            "demographics": demographics,
            "transformer": TRANSFORMER
        }
        model_generate_url = os.getenv("MODEL_GENERATE_URL")
        try:
            if model_generate_url:
                res_of_model_generate = requests.post(
                    url=model_generate_url,
                    headers=headers,
                    json=payload_for_model_generate
                )
                res_of_model_generate.raise_for_status()
                data_model = res_of_model_generate.json()
                for i in data_model:
                    for j in data_model[i]:
                        if isinstance(data_model[i][j], (int, float)):
                            data_model[i][j] //= 12
            else:
                data_model = {}
        except Exception:
            data_model = {}

        total_debt = sum(payload.get(k) or 0 for k in ("past_credit_debt", "student_loan", "other_debt"))
        total_debt*=12
        payload_for_peers_above = {
            "budget":{
                "health_insurance" : data_bud.get('transformed', {}).get('Health Insurance', 0),
                "other_debt_payments":int(total_debt), 
                "savings": int(savings),
            },
            "demographics": {
                "age": payload["age"],
                "household_members": payload["number_of_people"],
                "is_homeowner": payload["has_house"],
                "net_annual_income": net_annual_income,
                "zip": f"{(payload['zipcode'])}",
            }
        } 
        url_peers_top = os.getenv("ABOVE_PEERS_URL")
        if url_peers_top:
            try:
                response_for_peers_top = requests.post(
                    url=url_peers_top,
                    headers=headers,
                    json=payload_for_peers_above
                )
                response_for_peers_top.raise_for_status()
                peers = response_for_peers_top.json().get('breakeven', 0)
                data_bud.setdefault("transformed", {})["peers"] = float(peers)
            except Exception:
                pass

        return {
            "merged_updates": merged_updates,
            "budget_data": data_bud,
            "model_data": data_model,
        }
