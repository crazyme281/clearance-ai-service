"""
Read-only lookup tools for staff and institution admins. These let Zora
answer "where is <student> in clearance" and "what's left for them" for
MULTIPLE named students — unlike the student-side tools in
clearance_tools.py, which are bound to exactly one student (the caller).

Scope is still bound server-side, never by the LLM:
  - Staff (department_officer/faculty_officer/bursary/registry) only ever
    see students whose current workflow includes a stage that role
    reviews, scoped to their own department if they have one — the same
    role-match + department-match logic the officer queue's RLS helper
    `is_reviewer_for_stage` uses, reimplemented here in Python because
    this service connects with the service-role key, which bypasses RLS
    entirely.
  - institution_admin sees every student in their own institution.

There is no write path in this file at all — nothing here can approve,
reject, or otherwise change a student's clearance. That's what "shouldn't
be allowed to change where they are" means in practice: the capability
just doesn't exist for the AI to call, not a prompt asking it not to.
"""
from typing import Optional
from app.db import get_service_client
from app.tools.clearance_tools import get_clearance_status, get_clearance_requirements


def _staff_visible_request_ids(role: str, department_id: Optional[int]) -> set:
    svc = get_service_client()
    res = (
        svc.table("clearance_stage_instances")
        .select("clearance_request_id, clearance_requests(student_profiles(department_id))")
        .eq("approver_role", role)
        .execute()
    )
    ids = set()
    for row in res.data or []:
        cr = row.get("clearance_requests") or {}
        sp = cr.get("student_profiles") or {}
        if department_id is None or sp.get("department_id") == department_id:
            ids.add(row["clearance_request_id"])
    return ids


def _summarize_requests(request_ids) -> list:
    if not request_ids:
        return []
    svc = get_service_client()
    res = (
        svc.table("clearance_requests")
        .select("id, status, student_profiles(matric_number, level, programme, profiles(first_name, last_name))")
        .in_("id", list(request_ids))
        .execute()
    )
    out = []
    for r in res.data or []:
        sp = r.get("student_profiles") or {}
        p = sp.get("profiles") or {}
        out.append({
            "matric_number": sp.get("matric_number"),
            "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
            "programme": sp.get("programme"),
            "level": sp.get("level"),
            "overall_status": r["status"],
        })
    return out


def list_my_students(role: str, department_id: Optional[int]) -> dict:
    """Every student currently in this staff member's review scope, by name, with overall status."""
    ids = _staff_visible_request_ids(role, department_id)
    students = _summarize_requests(ids)
    return {"students": students, "count": len(students)}


def list_institution_students(institution_id: int) -> dict:
    """Every student in this admin's institution, by name, with overall status."""
    svc = get_service_client()
    res = (
        svc.table("clearance_requests")
        .select("id, status, institution_id, student_profiles(matric_number, level, programme, profiles(first_name, last_name))")
        .eq("institution_id", institution_id)
        .execute()
    )
    students = []
    for r in res.data or []:
        sp = r.get("student_profiles") or {}
        p = sp.get("profiles") or {}
        students.append({
            "matric_number": sp.get("matric_number"),
            "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
            "programme": sp.get("programme"),
            "level": sp.get("level"),
            "overall_status": r["status"],
        })
    return {"students": students, "count": len(students)}


def _find_student_id_by_matric(matric_number: str) -> Optional[int]:
    svc = get_service_client()
    res = (
        svc.table("student_profiles")
        .select("id")
        .ilike("matric_number", matric_number.strip())
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0]["id"] if rows else None


def get_student_status_for_staff(matric_number: str, role: str, department_id: Optional[int]) -> dict:
    """Full clearance status + outstanding requirements for one named student — read-only.
    Refuses if the student isn't within this staff member's review scope."""
    student_id = _find_student_id_by_matric(matric_number)
    if student_id is None:
        return {"error": f"No student found with matric number '{matric_number}'."}

    visible_ids = _staff_visible_request_ids(role, department_id)
    svc = get_service_client()
    req_ids = {r["id"] for r in (svc.table("clearance_requests").select("id").eq("student_id", student_id).execute().data or [])}
    if not (req_ids & visible_ids):
        return {"error": "That student isn't in your review scope."}

    return {
        "clearance_status": get_clearance_status(student_id),
        "outstanding_requirements": get_clearance_requirements(student_id),
    }


def get_student_status_for_admin(matric_number: str, institution_id: int) -> dict:
    """Same as get_student_status_for_staff, scoped to institution instead of role/department."""
    student_id = _find_student_id_by_matric(matric_number)
    if student_id is None:
        return {"error": f"No student found with matric number '{matric_number}'."}

    svc = get_service_client()
    sp_res = svc.table("student_profiles").select("institution_id").eq("id", student_id).single().execute()
    if (sp_res.data or {}).get("institution_id") != institution_id:
        return {"error": "That student isn't in your institution."}

    return {
        "clearance_status": get_clearance_status(student_id),
        "outstanding_requirements": get_clearance_requirements(student_id),
    }


# Separate registries per caller type — deliberately not merged into one
# dict keyed only by tool name, since get_student_status takes different
# scoping args for staff vs admin and each must only ever be reachable
# with the CALLING user's own scope, never a value the LLM supplies.
STAFF_TOOL_REGISTRY = {
    "list_my_students": list_my_students,
    "get_student_status": get_student_status_for_staff,
}
ADMIN_TOOL_REGISTRY = {
    "list_institution_students": list_institution_students,
    "get_student_status": get_student_status_for_admin,
}
