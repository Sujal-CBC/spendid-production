from fastapi import APIRouter
from uuid import uuid4
from client import main
from app.models.user_input import UserInput,NewData

# its the end point where we are supposed to process user query and we also generate unique session id. 
router = APIRouter()

# Removed JSON home route to allow main.py to serve index.html at /

@router.post("/chat")
async def chat_endpoint(user_query : UserInput):
    from fastapi.responses import StreamingResponse
    from client import main_streaming
    
    session_id = user_query.session_id or str(uuid4())
    
    return StreamingResponse(
        main_streaming(user_query.message, session_id),
        media_type="text/event-stream"
    )

@router.get("/state/{session_id}")
async def get_state(session_id: str):
    from client import sm
    return sm.get(session_id)