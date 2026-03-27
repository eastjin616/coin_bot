# backend/routers/chat.py
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from backend.ai.chat_agent import ask_agent

logger = logging.getLogger(__name__)

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
    try:
        answer = ask_agent(req.message)
    except Exception as e:
        logger.error(f"Agent 실행 오류: {e}")
        raise HTTPException(status_code=500, detail="AI 에이전트 오류가 발생했습니다.")
    return {"answer": answer}
