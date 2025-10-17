# main.py
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import asyncio
import os

from handlers import handle_task
from dotenv import load_dotenv
load_dotenv()


app = FastAPI()

class Attachment(BaseModel):
    name: str
    url: str  # base64-encoded data URI

class TaskRequest(BaseModel):
    email: str
    secret: str
    task: str
    round: int
    nonce: str
    brief: str
    checks: List[str]
    evaluation_url: str
    attachments: Optional[List[Attachment]] = []

@app.post("/api/task")
async def receive_task(req: TaskRequest):

    expected_secret = os.getenv("STUDENT_SECRET")
    print(expected_secret)
    if req.secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")


    try:
        await asyncio.to_thread(handle_task, req)
        return {"status": "ok", "message": "Task received and being processed."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
