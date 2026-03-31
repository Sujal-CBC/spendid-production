from fastapi import FastAPI
from app.api.endpoints import router

# its just wrapper to everything we have 
from fastapi.staticfiles import StaticFiles
import os 


app = FastAPI()

# Mount static files
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(router)

@app.get("/")
async def read_index():
    from fastapi.responses import FileResponse
    return FileResponse("static/index.html")