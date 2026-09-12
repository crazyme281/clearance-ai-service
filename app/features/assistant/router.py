from fastapi import APIRouter, Depends

from app.security import CurrentUser, get_current_user
from app.features.assistant.schemas import AssistantRequest, AssistantResponse
from app.features.assistant.service import chat_with_assistant

router = APIRouter(prefix="/assistant", tags=["Zora AI Assistant"])


@router.post("/chat", response_model=AssistantResponse)
async def assistant_chat(
    request: AssistantRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Chat with Zora. Identity comes ONLY from the Supabase session token in
    the Authorization header — the request body never carries a student ID.
    """
    return await chat_with_assistant(user, request.message, request.conversation_history)
