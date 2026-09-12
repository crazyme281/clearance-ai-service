"""
OpenAI-style tool definitions handed to the LLM. Deliberately, none of the
student-scoped tools expose a student/user-identity parameter — the model
can request "run get_clearance_status" but cannot choose whose status it
gets back. See app/tools/clearance_tools.py and app/features/assistant/service.py.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_clearance_status",
            "description": "Get the current student's overall clearance status and a breakdown of every stage (department, faculty, bursary, etc.) with its approval state.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pending_clearance",
            "description": "Get only the clearance stages the current student has NOT yet completed, in order.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_clearance_requirements",
            "description": "Get the documents and payments the current student still needs to submit/settle for clearance.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_application_details",
            "description": "Get a summary of the current student's profile and their clearance application record (matric number, level, programme, submission/completion dates).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_clearance_stage",
            "description": "Explain in plain language what a named clearance stage checks for (e.g. 'Department', 'Faculty', 'Bursary', 'Library', 'Institution'). Does not require student data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stage_name": {
                        "type": "string",
                        "description": "The stage to explain, e.g. 'Bursary'",
                    }
                },
                "required": ["stage_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_officer_information",
            "description": "Find out who (name, designation, contact) is assigned to review the current student's next pending clearance stage.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]
