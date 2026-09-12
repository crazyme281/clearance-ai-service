import json
import logging
from typing import List, Optional

from groq import Groq

from app import config
from app.security import CurrentUser
from app.tools.definitions import TOOLS
from app.tools.clearance_tools import TOOL_REGISTRY, STUDENT_SCOPED_TOOLS
from app.features.assistant.schemas import ChatMessage, AssistantResponse
from app.db import get_service_client

logger = logging.getLogger(__name__)

_groq_client: Optional[Groq] = None


def _client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=config.GROQ_API_KEY)
    return _groq_client


SYSTEM_PROMPT = """You are Zora, a clearance assistant for a university clearance system.
You help students understand their clearance status, what they still need to
submit, which stage is holding things up, and who is reviewing it.

Rules:
- Only use the tools provided to get real data. Never invent a clearance
  status, a document name, or an officer's name.
- If a tool returns "not_started" or empty data, tell the student plainly
  and suggest they start/check with the clearance office — don't guess.
- Keep answers short and mobile-friendly (a few sentences, not an essay).
- You cannot look up any student other than the one you're currently
  talking to — you have no way to do that, so don't claim otherwise.
"""

MAX_TOOL_ROUNDS = 4


async def chat_with_assistant(user: CurrentUser, message: str, history: Optional[List[ChatMessage]]) -> AssistantResponse:
    messages = [{"role": "system", "content": SYSTEM_PROMPT + f"\n\nThe student's first name is {user.first_name}."}]
    if history:
        for m in history[-10:]:  # cap context sent per turn
            messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": message})

    tools_used: List[str] = []

    for _ in range(MAX_TOOL_ROUNDS):
        completion = _client().chat.completions.create(
            model=config.GROQ_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.4,
            max_tokens=800,
        )
        choice = completion.choices[0].message
        tool_calls = getattr(choice, "tool_calls", None)

        if not tool_calls:
            reply = (choice.content or "").strip()
            _log_turn(user, "user", message)
            _log_turn(user, "assistant", reply, tools_used)
            return AssistantResponse(response=reply, tools_used=tools_used)

        # Model wants to call one or more tools.
        messages.append({
            "role": "assistant",
            "content": choice.content or "",
            "tool_calls": [tc.model_dump() for tc in tool_calls],
        })

        for tc in tool_calls:
            name = tc.function.name
            fn = TOOL_REGISTRY.get(name)
            if fn is None:
                result = {"error": f"Unknown tool '{name}'"}
            else:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                if name in STUDENT_SCOPED_TOOLS:
                    if user.student_id is None:
                        result = {"error": "This account has no student profile."}
                    else:
                        args["student_id"] = user.student_id  # bind server-side, ignore any LLM-supplied value
                        result = fn(**args)
                else:
                    result = fn(**args)
                tools_used.append(name)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": name,
                "content": json.dumps(result, default=str),
            })

    # Ran out of tool-call rounds — ask the model for a final plain answer.
    completion = _client().chat.completions.create(
        model=config.GROQ_MODEL,
        messages=messages + [{"role": "user", "content": "Please summarize what you found so far, plainly."}],
        temperature=0.4,
        max_tokens=600,
    )
    reply = (completion.choices[0].message.content or "").strip()
    _log_turn(user, "user", message)
    _log_turn(user, "assistant", reply, tools_used)
    return AssistantResponse(response=reply, tools_used=tools_used)


def _log_turn(user: CurrentUser, role: str, content: str, tools_used: Optional[List[str]] = None) -> None:
    try:
        get_service_client().table("ai_chat_logs").insert({
            "profile_id": user.profile_id,
            "role": role,
            "content": content,
            "tool_calls": tools_used or None,
        }).execute()
    except Exception:
        logger.exception("Failed to write ai_chat_logs row (non-fatal)")
