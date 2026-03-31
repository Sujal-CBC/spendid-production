from fastapi.testclient import TestClient
from main import app
import sys, json

client = TestClient(app)

def test_chat():
    payload = {
        "session_id": "test_session_123",
        "message": "Hi, my zipcode is 90210",
        "new_data": {
            "zipcode": "90210"
        }
    }
    print("Sending request to /chat...")
    response = client.post("/chat", json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")

if __name__ == "__main__":
    test_chat()
