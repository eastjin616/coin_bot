# backend/routers/chat.py
from fastapi import APIRouter
from pydantic import BaseModel, field_validator
from backend.ai.chat_agent import ask_agent

router = APIRouter()

class ChatRequest(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v):
        if not v.strip():
            raise ValueError("message는 비어있을 수 없습니다.")
        return v.strip()

@router.post("/chat")
def chat(req: ChatRequest):
    answer = ask_agent(req.message)
    return {"answer": answer}
