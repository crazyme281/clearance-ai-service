from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, status

from app.db import get_anon_client, get_service_client


@dataclass
class CurrentUser:
    profile_id: str          # uuid, from auth.users / profiles
    role: str
    first_name: str
    student_id: Optional[int]  # student_profiles.id, if role == 'student'
    institution_id: Optional[int]


async def get_current_user(authorization: str = Header(None)) -> CurrentUser:
    """
    Verifies the bearer token the Ionic app got from Supabase Auth, then
    resolves it server-side to a profile + (if applicable) student_profiles
    row. This is the ONLY place a student's identity enters the request —
    every tool call downstream uses current_user.student_id, never a value
    supplied by the request body or invented by the LLM.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )
    token = authorization.split(" ", 1)[1].strip()

    anon = get_anon_client()
    try:
        auth_response = anon.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

    user = getattr(auth_response, "user", None)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

    svc = get_service_client()
    profile_res = (
        svc.table("profiles")
        .select("id, role, first_name, institution_id")
        .eq("id", user.id)
        .single()
        .execute()
    )
    if not profile_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No profile found for this account")

    profile = profile_res.data
    student_id = None
    if profile["role"] == "student":
        sp_res = (
            svc.table("student_profiles")
            .select("id")
            .eq("profile_id", user.id)
            .single()
            .execute()
        )
        if sp_res.data:
            student_id = sp_res.data["id"]

    return CurrentUser(
        profile_id=profile["id"],
        role=profile["role"],
        first_name=profile["first_name"],
        student_id=student_id,
        institution_id=profile.get("institution_id"),
    )
