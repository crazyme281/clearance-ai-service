import json
import logging
from typing import List, Optional

from groq import Groq

from app import config
from app.security import CurrentUser
from app.tools.definitions import STUDENT_TOOLS, STAFF_TOOLS, ADMIN_TOOLS
from app.tools.clearance_tools import TOOL_REGISTRY as STUDENT_TOOL_REGISTRY, STUDENT_SCOPED_TOOLS
from app.tools.staff_tools import STAFF_TOOL_REGISTRY, ADMIN_TOOL_REGISTRY
from app.features.assistant.schemas import ChatMessage, AssistantResponse
from app.db import get_service_client

logger = logging.getLogger(__name__)

_groq_client: Optional[Groq] = None


def _client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=config.GROQ_API_KEY)
    return _groq_client


STUDENT_SYSTEM_PROMPT = """You are Zora, a clearance assistant for a university clearance system.
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

STAFF_SYSTEM_PROMPT = """You are Zora, a clearance assistant for university clearance staff.
You help this officer see where students in their review scope stand —
what a student has completed, what's still outstanding, and who else is
involved — by name or matric number.

Rules:
- Only use the tools provided to get real data. Never invent a status, a
  document name, or a student's details.
- If you don't have a student's matric number yet, call list_my_students
  first to find them by name, then use get_student_status for detail.
- You can only see students within this officer's own review scope
  (their role and department) — if a lookup says a student isn't in
  scope, say so plainly rather than guessing why.
- You have NO ability to approve, reject, or otherwise change a student's
  clearance — you are read-only. If asked to change something, say
  clearly that decisions have to be made from the review queue itself,
  not through you.
- Keep answers short and mobile-friendly.
"""

ADMIN_SYSTEM_PROMPT = """You are Zora, a clearance assistant for an institution admin.
You help them see where any student in their institution stands in the
clearance process — what's done, what's outstanding — by name or matric
number.

Rules:
- Only use the tools provided to get real data. Never invent a status, a
  document name, or a student's details.
- If you don't have a student's matric number yet, call
  list_institution_students first to find them by name, then use
  get_student_status for detail.
- You have NO ability to approve, reject, or otherwise change a student's
  clearance, and no ability to change staff/faculty/department records —
  you are read-only. If asked to change something, say clearly that has
  to be done from the Admin Console itself, not through you.
- Keep answers short and mobile-friendly.
"""

MAX_TOOL_ROUNDS = 4


def _tools_config(user: CurrentUser):
    """
    Picks the system prompt, tool definitions, and a dispatch function for
    the caller's role. The dispatch function is where server-side scope
    binding actually happens — it's the only thing standing between "the
    LLM asked for get_student_status" and a real database query, and it
    injects the caller's own role/department/institution every time,
    ignoring anything the LLM supplied for those fields.
    """
    if user.role == "student":
        def dispatch(name: str, args: dict) -> dict:
            fn = STUDENT_TOOL_REGISTRY.get(name)
            if fn is None:
                return {"error": f"Unknown tool '{name}'"}
            if name in STUDENT_SCOPED_TOOLS:
                if user.student_id is None:
                    return {"error": "This account has no student profile."}
                args["student_id"] = user.student_id
            return fn(**args)

        prompt = STUDENT_SYSTEM_PROMPT + f"\n\nThe student's first name is {user.first_name}."
        return prompt, STUDENT_TOOLS, dispatch

    if user.role == "institution_admin":
        def dispatch(name: str, args: dict) -> dict:
            fn = ADMIN_TOOL_REGISTRY.get(name)
            if fn is not None:
                if name == "list_institution_students":
                    args = {"institution_id": user.institution_id}
                elif name == "get_student_status":
                    args = {"matric_number": args.get("matric_number", ""), "institution_id": user.institution_id}
                return fn(**args)
            # explain_clearance_stage lives in the student tool registry but
            # takes no identity, so it's safe to share across roles.
            fn = STUDENT_TOOL_REGISTRY.get(name)
            if fn is None:
                return {"error": f"Unknown tool '{name}'"}
            return fn(**args)

        prompt = ADMIN_SYSTEM_PROMPT + f"\n\nThe admin's first name is {user.first_name}."
        return prompt, ADMIN_TOOLS, dispatch

    # Any operational staff role (department_officer, faculty_officer, bursary, registry).
    def dispatch(name: str, args: dict) -> dict:
        fn = STAFF_TOOL_REGISTRY.get(name)
        if fn is not None:
            if name == "list_my_students":
                args = {"role": user.role, "department_id": user.department_id}
            elif name == "get_student_status":
                args = {"matric_number": args.get("matric_number", ""), "role": user.role, "department_id": user.department_id}
            return fn(**args)
        fn = STUDENT_TOOL_REGISTRY.get(name)
        if fn is None:
            return {"error": f"Unknown tool '{name}'"}
        return fn(**args)

    prompt = STAFF_SYSTEM_PROMPT + f"\n\nThe officer's first name is {user.first_name}, reviewing as {user.role}."
    return prompt, STAFF_TOOLS, dispatch


async def chat_with_assistant(user: CurrentUser, message: str, history: Optional[List[ChatMessage]]) -> AssistantResponse:
    system_prompt, tools, dispatch = _tools_config(user)

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for m in history[-10:]:  # cap context sent per turn
            messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": message})

    tools_used: List[str] = []

    for _ in range(MAX_TOOL_ROUNDS):
        completion = _client().chat.completions.create(
            model=config.GROQ_MODEL,
            messages=messages,
            tools=tools,
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
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = dispatch(name, args)
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
