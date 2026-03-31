from fastapi import APIRouter
from uuid import uuid4
from client import main
from app.models.user_input import UserInput,NewData

# its the end point where we are supposed to process user query and we also generate unique session id. 
router = APIRouter()

@router.get("/") 
def home(): 
    return {"Message":"Welcome to home page of SPENDiD"}

@router.post("/chat")
async def chat_endpoint(user_query : UserInput):
    session_id = user_query.session_id or str(uuid4())
    # update state with new_data if present, though main doesn't explicitly take new_data yet except maybe internally.
    # main takes user_text and session_id
    result = await main(user_query.message, session_id)
    return {"session_id": session_id, "result": result}