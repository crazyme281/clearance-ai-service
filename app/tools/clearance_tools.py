"""
Tool implementations for the clearance assistant.

Every function here takes `student_id` (student_profiles.id) as a plain
Python argument supplied by app/features/assistant/service.py from the
authenticated request — NEVER from LLM-generated tool-call arguments.
The LLM only ever supplies non-identity parameters (e.g. a stage name to
explain). This keeps a compromised or confused prompt from being able to
ask "get_clearance_status for student 4821" and read someone else's data.
"""
from typing import Optional
from app.db import get_service_client

STAGE_EXPLAINERS = {
    "department": (
        "Your Department clearance confirms you have no outstanding issues "
        "with your home department — course registration, project/thesis "
        "submission, lecturer sign-off, etc. It's usually the first stage."
    ),
    "faculty": (
        "Faculty clearance is reviewed by your Faculty Officer after your "
        "department signs off. It checks faculty-wide requirements across "
        "all departments in your faculty."
    ),
    "bursary": (
        "Bursary clearance confirms you have no outstanding fees or "
        "financial obligations to the institution. Payment records are "
        "checked here."
    ),
    "institution": (
        "Institution-level clearance is the final stage, confirming every "
        "prior stage (department, faculty, bursary, library, etc.) has "
        "been approved before your certificate/transcript is released."
    ),
    "library": (
        "Library clearance confirms you've returned all borrowed books and "
        "settled any library fines."
    ),
}


def _student_row(student_id: int) -> dict:
    svc = get_service_client()
    res = (
        svc.table("student_profiles")
        .select("id, matric_number, level, programme, department_id, faculty_id, institution_id")
        .eq("id", student_id)
        .single()
        .execute()
    )
    return res.data or {}


def _latest_request(student_id: int) -> Optional[dict]:
    svc = get_service_client()
    res = (
        svc.table("clearance_requests")
        .select("*")
        .eq("student_id", student_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def get_clearance_status(student_id: int) -> dict:
    """Overall clearance status + per-stage breakdown for the student's active request."""
    request = _latest_request(student_id)
    if not request:
        return {"status": "not_started", "message": "No clearance request has been created yet."}

    svc = get_service_client()
    stages_res = (
        svc.table("clearance_stage_instances")
        .select("stage_order, stage_name, approver_role, status, reviewed_at, sla_deadline")
        .eq("clearance_request_id", request["id"])
        .order("stage_order")
        .execute()
    )
    stages = stages_res.data or []
    approved = sum(1 for s in stages if s["status"] == "approved")

    return {
        "overall_status": request["status"],
        "academic_year": request.get("academic_year"),
        "semester": request.get("semester"),
        "stages_total": len(stages),
        "stages_approved": approved,
        "stages": stages,
    }


def get_pending_clearance(student_id: int) -> dict:
    """Just the stages that are NOT yet approved, in order."""
    status = get_clearance_status(student_id)
    if status.get("status") == "not_started":
        return status
    pending = [s for s in status["stages"] if s["status"] != "approved"]
    return {"pending_stages": pending, "count": len(pending)}


def get_clearance_requirements(student_id: int) -> dict:
    """What documents/payments are required, and which the student has/hasn't satisfied."""
    student = _student_row(student_id)
    svc = get_service_client()

    reqs_res = (
        svc.table("clearance_requirements")
        .select("id, department_id, requirement_type, name, description, is_mandatory")
        .eq("institution_id", student.get("institution_id"))
        .execute()
    )
    requirements = [
        r for r in (reqs_res.data or [])
        if r["department_id"] is None or r["department_id"] == student.get("department_id")
    ]

    docs_res = (
        svc.table("student_documents")
        .select("requirement_id, status")
        .eq("student_id", student_id)
        .execute()
    )
    pay_res = (
        svc.table("payment_records")
        .select("requirement_id, status")
        .eq("student_id", student_id)
        .execute()
    )
    satisfied_doc_ids = {d["requirement_id"] for d in (docs_res.data or []) if d["status"] == "verified"}
    satisfied_pay_ids = {p["requirement_id"] for p in (pay_res.data or []) if p["status"] == "verified"}
    satisfied = satisfied_doc_ids | satisfied_pay_ids

    outstanding = [r for r in requirements if r["is_mandatory"] and r["id"] not in satisfied]
    return {
        "total_requirements": len(requirements),
        "outstanding": outstanding,
        "outstanding_count": len(outstanding),
    }


def get_application_details(student_id: int) -> dict:
    """Summary of the student's profile + their clearance request record."""
    student = _student_row(student_id)
    request = _latest_request(student_id)
    return {
        "matric_number": student.get("matric_number"),
        "level": student.get("level"),
        "programme": student.get("programme"),
        "request_status": request["status"] if request else "not_started",
        "submitted_at": request.get("submitted_at") if request else None,
        "completed_at": request.get("completed_at") if request else None,
    }


def explain_clearance_stage(stage_name: str) -> dict:
    """Plain-language explanation of what a given clearance stage checks. No student data involved."""
    key = stage_name.strip().lower()
    explanation = STAGE_EXPLAINERS.get(key)
    if not explanation:
        return {
            "stage_name": stage_name,
            "explanation": "I don't have a specific description for that stage — "
                            "it may be institution-specific. Please check with the clearance office.",
        }
    return {"stage_name": stage_name, "explanation": explanation}


def get_officer_information(student_id: int) -> dict:
    """Who is assigned to the student's current pending stage, if anyone."""
    pending = get_pending_clearance(student_id)
    stages = pending.get("pending_stages") or []
    if not stages:
        return {"message": "No pending stage — nothing currently awaiting an officer."}

    current = stages[0]
    svc = get_service_client()
    request = _latest_request(student_id)
    stage_res = (
        svc.table("clearance_stage_instances")
        .select("assigned_to")
        .eq("clearance_request_id", request["id"])
        .eq("stage_order", current["stage_order"])
        .single()
        .execute()
    )
    assigned_to = (stage_res.data or {}).get("assigned_to")
    if not assigned_to:
        return {
            "stage_name": current["stage_name"],
            "message": "This stage hasn't been assigned to a specific officer yet.",
        }

    staff_res = (
        svc.table("staff_profiles")
        .select("designation, office_contact, profiles(first_name, last_name, email)")
        .eq("profile_id", assigned_to)
        .single()
        .execute()
    )
    return {"stage_name": current["stage_name"], "officer": staff_res.data or {}}


# Name -> callable, used by the tool-calling loop to dispatch.
TOOL_REGISTRY = {
    "get_clearance_status": get_clearance_status,
    "get_pending_clearance": get_pending_clearance,
    "get_clearance_requirements": get_clearance_requirements,
    "get_application_details": get_application_details,
    "explain_clearance_stage": explain_clearance_stage,
    "get_officer_information": get_officer_information,
}

# Tools that take a student_id bound server-side (all of them do except the
# pure-explainer, which takes no identity at all).
STUDENT_SCOPED_TOOLS = {
    "get_clearance_status",
    "get_pending_clearance",
    "get_clearance_requirements",
    "get_application_details",
    "get_officer_information",
}
