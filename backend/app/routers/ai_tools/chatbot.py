"""
AI Chatbot Router
─────────────────────────────────────────
Route prefix : /api/v1/ai/chatbot
Required role: any authenticated user

Endpoints:
  POST /chat   — Send message, get AI response (streaming)
"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.dependencies import get_current_user, CurrentUser
from app.services.ai_service import AIService

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    conversation_history: list[dict] = []


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """AI Chatbot dengan Claude API — streaming response."""
    service = AIService()
    return StreamingResponse(
        service.stream_chat(request.message, request.conversation_history, user),
        media_type="text/event-stream",
    )
