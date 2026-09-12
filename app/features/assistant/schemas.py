from typing import List, Literal, Optional
from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AssistantRequest(BaseModel):
    message: str
    conversation_history: Optional[List[ChatMessage]] = None


class AssistantResponse(BaseModel):
    response: str
    tools_used: List[str] = []
