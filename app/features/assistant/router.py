from fastapi import APIRouter, Depends, HTTPException, status

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
    # Same gate as the review queue: a staff account that isn't active yet
    # (or was suspended) gets no access to student data through Zora either.
    if user.role not in ("student", "institution_admin") and user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account is not yet approved for this")

    return await chat_with_assistant(user, request.message, request.conversation_history)
