from fastapi import FastAPI
from app.api.endpoints import router

# its just wrapper to everything we have 
app = FastAPI()
app.include_router(router)