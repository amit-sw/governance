from copy import deepcopy
from enum import Enum
import os

from pydantic import BaseModel, Field

import core


RUBRIC_PATH = core.BASE_DIR / "rubric.json"
PROMPTS_DIR = core.BASE_DIR / "prompts"
PRECEDENTS_DIR = core.BASE_DIR / "precedents"
SETTINGS_PATH = core.BASE_DIR / "data" / "settings.json"
DEFAULT_MODEL = "gpt-5.6-luna"
MODELS = {
    "gpt-6.1-sol": "GPT-6.1-Sol",
    "gpt-5.6-terra": "GPT-5.6-Terra",
    "gpt-5.6-luna": "GPT-5.6-Luna",
}


RequestField = Enum("RequestField", {key: key for key in core.FIELDS}, type=str)


class IntakeUpdate(core.FieldUpdate):
    field_id: RequestField


class IntakeReview(core.IntakeResult):
    updates: list[IntakeUpdate]
    questions: list[str] = Field(max_length=5)
    ready_for_assessment: bool
    readiness_reason: str = Field(min_length=1)
    unresolved_conflicts: list[str]


class RequestReference(BaseModel):
    field_id: RequestField


class RiskDimension(core.Dimension):
    evidence: list[RequestReference]


class PolicyBlocker(core.Blocker):
    evidence: list[RequestReference]


class RequestFinding(core.Finding):
    evidence: list[RequestReference] = Field(min_length=1)


class AssessmentReview(core.Assessment):
    dimensions: list[RiskDimension]
    blockers: list[PolicyBlocker]
    conflicts: list[RequestFinding]
    existing_safeguards: list[RequestFinding]


def assess_request(case, configuration, model):
    answer = core.call_model(configuration["prompts"]["assessment"], {
        "request": case["request"], "fields": core.FIELDS,
        "rubric": configuration["rubric"],
        "missing_fields": core.missing_fields(case["request"]),
    }, AssessmentReview, model)
    result = answer.model_dump(mode="json")
    for group in ("dimensions", "blockers", "conflicts", "existing_safeguards"):
        for finding in result[group]:
            for reference in finding["evidence"]:
                reference["quote"] = case["request"][reference["field_id"]]
    assessment = core.validate_assessment(result, case["request"], configuration["rubric"])
    return {
        "id": str(core.uuid4()), "created_at": core.now(), "request_revision": case["revision"],
        "request": deepcopy(case["request"]), "configuration": deepcopy(configuration),
        "model": model, "assessment": assessment.model_dump(),
        "decision": core.recommendation_for(assessment, case["request"]),
        "matches": [], "comparison_status": "Not run",
    }


def new_session():
    return {
        "case": core.new_case(), "mode": "intake", "report": None,
        "configuration": None, "readiness_reason": "", "error": None,
        "request_seconds": None, "assessment_seconds": None, "pending_assessment": False,
        "intake_seconds": None, "assessment_origin": "manual", "assessment_model": None,
        "intake_failed": False, "assessment_failed": False, "comparison_failed": False,
    }


def load_settings():
    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    settings = core.read_json(SETTINGS_PATH, {"model": model if model in MODELS else DEFAULT_MODEL})
    if settings["model"] not in MODELS:
        raise ValueError("Choose one of the supported models in the settings file.")
    return settings


def load_configuration():
    configuration = {
        "rubric": core.read_json(RUBRIC_PATH),
        "prompts": {name: (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8") for name in core.PROMPT_NAMES},
    }
    core.validate_configuration(configuration)
    return configuration


def load_precedents():
    precedents = []
    for path in sorted(PRECEDENTS_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        title = next((line[2:].strip() for line in content.splitlines() if line.startswith("# ")), path.stem)
        precedents.append({"id": path.name, "title": title, "content": content})
    return precedents


def review_intake(case, configuration, model=None):
    answer = core.call_model(configuration["prompts"]["intake"], {
        "fields": core.FIELDS, "request": case["request"],
        "conversation": case["conversation"], "material_fields": core.MATERIAL_FIELDS,
        "missing_fields": core.missing_fields(case["request"]), "rubric": configuration["rubric"],
    }, IntakeReview, model)
    sources = [item["content"] for item in case["conversation"] if item["role"] == "user"]
    sources += list(case["request"].values())
    request = deepcopy(case["request"])
    updated_fields = {}
    for update in answer.updates:
        field_id = update.field_id.value
        quote = core.normalized(update.evidence_quote)
        if not quote or not any(quote in core.normalized(source) for source in sources):
            raise ValueError("An intake update has no matching user-provided evidence.")
        value = update.value.strip() or "Unknown"
        values = updated_fields.setdefault(field_id, [])
        if value not in values:
            values.append(value)
    for field_id, values in updated_fields.items():
        request[field_id] = "\n".join(values)
    return request, answer


def intake_is_complete(request, answer):
    return answer.ready_for_assessment and not (
        core.missing_fields(request) or answer.questions or answer.unresolved_conflicts
    )


def intake_message(request, answer, ready):
    parts = [answer.summary]
    if answer.unresolved_conflicts:
        parts.append("Facts to clarify:\n\n" + "\n".join(f"- {item}" for item in answer.unresolved_conflicts))
    questions = answer.questions
    if questions:
        parts.append("\n\n".join(f"{index}. {question}" for index, question in enumerate(questions, 1)))
    if ready:
        parts.append("**Intake complete → switching to ASSESSMENT.**\n\n" + answer.readiness_reason)
    elif not questions:
        missing = core.missing_fields(request)
        if missing:
            labels = ", ".join(core.FIELDS[key].lower() for key in missing)
            parts.append("Automatic assessment will wait for the unresolved facts: " + labels + ". Provide them here when known, or select **Assess input so far** for an incomplete assessment now.")
        else:
            parts.append(answer.readiness_reason)
    return "\n\n".join(parts)


def compare_precedents(request, precedents, configuration, model=None):
    if not precedents:
        return []
    comparison = core.call_model(configuration["prompts"]["comparison"], {
        "request": request,
        "cases": [{"case_id": item["id"], "markdown": item["content"]} for item in precedents],
    }, core.Comparison, model)
    available = {item["id"]: item for item in precedents}
    matches = []
    seen = set()
    for match in comparison.matches:
        if match.case_id not in available or match.case_id in seen:
            raise ValueError("A comparison must cite distinct available Markdown precedents.")
        seen.add(match.case_id)
        matches.append(match.model_dump() | {"precedent": deepcopy(available[match.case_id])})
    return matches
