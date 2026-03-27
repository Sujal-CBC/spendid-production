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
def chat_endpoint(user_query : UserInput):
    session_id = user_query.session_id or str(uuid4())
    result = main(session_id, user_query.new_data.dict())
    return {"session_id": session_id, "result": result}