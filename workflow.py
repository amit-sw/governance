from copy import deepcopy
from enum import Enum
import os
import re
from typing import Literal

from pydantic import BaseModel, Field, create_model

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


class IntakeUpdate(BaseModel):
    field_id: RequestField
    value: str
    known: bool


class IntakeReview(BaseModel):
    summary: str
    questions: list[str] = Field(max_length=5)
    ready_for_assessment: bool
    readiness_reason: str
    unresolved_conflicts: list[str]


class RiskDimension(BaseModel):
    score: Literal[0, 1, 2, 3] | None
    rationale: str
    evidence_fields: list[RequestField]


class PolicyBlocker(BaseModel):
    status: Literal["applies", "does_not_apply", "unknown"]
    rationale: str
    evidence_fields: list[RequestField]


class RequestFinding(BaseModel):
    explanation: str
    evidence_fields: list[RequestField]


class MissingInformation(BaseModel):
    field_id: RequestField
    question: str


class AssessmentReview(BaseModel):
    summary: str
    missing_information: list[MissingInformation]
    conflicts: list[RequestFinding]
    existing_safeguards: list[RequestFinding]
    mitigations: list[str]


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
    settings = core.read_json(SETTINGS_PATH, {})
    if not isinstance(settings, dict):
        settings = {}
    model = settings.get("model", model)
    return {"model": model if model in MODELS else DEFAULT_MODEL}


def load_configuration():
    configuration = {
        "rubric": core.read_json(RUBRIC_PATH),
        "prompts": {name: (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8") for name in core.PROMPT_NAMES},
    }
    validate_configuration(configuration)
    return configuration


def validate_configuration(configuration):
    core.validate_configuration(configuration)
    if not configuration["rubric"]["name"].strip() or not configuration["rubric"]["version"].strip():
        raise ValueError("The rubric needs a name and version.")
    for dimension in configuration["rubric"]["dimensions"]:
        if not dimension["label"].strip() or not dimension["guidance"].strip() or any(not value.strip() for value in dimension["anchors"]):
            raise ValueError("Each dimension needs a label and four nonempty scoring anchors.")
    if any(not rule["rule"].strip() for rule in configuration["rubric"]["blocking_rules"]):
        raise ValueError("Blocking rules need nonempty instructions.")


def load_precedents():
    precedents = []
    for path in sorted(PRECEDENTS_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        title = next((line[2:].strip() for line in content.splitlines() if line.startswith("# ")), path.stem)
        precedents.append({"id": path.name, "title": title, "content": content})
    return precedents


def request_sources(case):
    sources = {
        f"message_{index}": {"kind": "user_message", "content": message["content"]}
        for index, message in enumerate(case["conversation"], 1)
        if message["role"] == "user" and message["content"].strip()
    }
    sources.update({
        f"field_{key}": {"kind": "request_field", "content": value}
        for key, value in case["request"].items() if not core.is_unknown(value)
    })
    return sources


def intake_schema(sources):
    source_id = Enum("SourceId", {key: key for key in sources}, type=str)
    update = create_model("SupportedUpdate", __base__=IntakeUpdate, source_ids=(list[source_id], ...))
    return create_model("IntakeResponse", __base__=IntakeReview, updates=(list[update], ...))


def apply_intake_updates(case, answer, sources):
    request = deepcopy(case["request"])
    provenance = deepcopy(case.get("request_sources", {}))
    values = {}
    for update in answer.updates:
        field_id = update.field_id.value
        evidence = [sources[item.value] | {"source_id": item.value} for item in update.source_ids]
        if not evidence:
            if field_id in core.MATERIAL_FIELDS:
                answer.unresolved_conflicts.append(f"Please confirm {core.FIELDS[field_id].lower()}.")
            continue
        value = update.value.strip()
        if not update.known:
            value = "Unknown" + (" — " + value if value and not core.is_unknown(value) else "")
        value = value or "Unknown"
        if field_id not in values:
            values[field_id] = []
            provenance[field_id] = []
        if value not in values[field_id]:
            values[field_id].append(value)
        provenance[field_id].extend(item for item in evidence if item not in provenance[field_id])
    for field_id, parts in values.items():
        unknown = any(core.is_unknown(part) for part in parts)
        request[field_id] = ("Unknown — " if unknown and not core.is_unknown(parts[0]) else "") + "\n".join(parts)
    case["request_sources"] = provenance
    case["unresolved_conflicts"] = list(dict.fromkeys(answer.unresolved_conflicts))
    return request


def review_intake(case, configuration, model=None):
    sources = request_sources(case)
    if not sources:
        raise ValueError("There is no submitted information to review.")
    answer = core.call_model(configuration["prompts"]["intake"], {
        "fields": core.FIELDS, "request": case["request"], "sources": sources,
        "conversation": case["conversation"], "material_fields": core.MATERIAL_FIELDS,
        "missing_fields": core.missing_fields(case["request"]), "rubric": configuration["rubric"],
    }, intake_schema(sources), model)
    return apply_intake_updates(case, answer, sources), answer


def intake_is_complete(request, answer):
    return answer.ready_for_assessment and not (
        core.missing_fields(request) or answer.questions or answer.unresolved_conflicts
    )


def intake_message(request, answer, ready):
    parts = [answer.summary]
    if answer.unresolved_conflicts:
        parts.append("Facts to clarify:\n\n" + "\n".join(f"- {item}" for item in dict.fromkeys(answer.unresolved_conflicts)))
    if answer.questions:
        questions = [re.sub(r"^(?:\s*\d+[.)]\s*)+", "", question.strip()) for question in answer.questions]
        parts.append("\n\n".join(f"{index}. {question}" for index, question in enumerate(questions, 1)))
    if ready:
        parts.append("**Intake complete → switching to ASSESSMENT.**\n\n" + answer.readiness_reason)
    elif not answer.questions:
        missing = core.missing_fields(request)
        if missing:
            labels = ", ".join(core.FIELDS[key].lower() for key in missing)
            parts.append("Still needed: " + labels + ". Provide these facts when known, or select **Assess input so far** for an incomplete assessment now.")
        else:
            parts.append(answer.readiness_reason)
    return "\n\n".join(parts)


def assessment_schema(rubric):
    dimensions = create_model("DimensionFindings", **{
        f"dimension_{index}": (RiskDimension, ...) for index, item in enumerate(rubric["dimensions"], 1)
    })
    blockers = create_model("BlockerFindings", **{
        f"blocker_{index}": (PolicyBlocker, ...) for index, item in enumerate(rubric["blocking_rules"], 1)
    })
    return create_model("AssessmentResponse", __base__=AssessmentReview,
                        dimensions=(dimensions, ...), blockers=(blockers, ...))


def request_evidence(fields, request):
    return [
        {"field_id": field_id, "quote": request[field_id]}
        for field_id in dict.fromkeys(fields) if not core.is_unknown(request.get(field_id, ""))
    ]


def dimension_findings(answer, request, rubric):
    findings = []
    for index, dimension in enumerate(rubric["dimensions"], 1):
        finding = answer["dimensions"][f"dimension_{index}"]
        evidence = request_evidence(finding["evidence_fields"], request)
        score = finding["score"] if evidence and finding["rationale"].strip() else None
        rationale = finding["rationale"].strip()
        if score != finding["score"] or not rationale:
            rationale = "This dimension needs supporting request facts before it can be scored. " + rationale
        findings.append({"criterion_id": dimension["id"], "score": score, "rationale": rationale, "evidence": evidence})
    return findings


def blocker_findings(answer, request, rubric):
    findings = []
    for index, rule in enumerate(rubric["blocking_rules"], 1):
        finding = answer["blockers"][f"blocker_{index}"]
        evidence = request_evidence(finding["evidence_fields"], request)
        status = finding["status"] if evidence and finding["rationale"].strip() else "unknown"
        rationale = finding["rationale"].strip()
        if status != finding["status"] or not rationale:
            rationale = "This rule needs supporting request facts before it can be resolved. " + rationale
        findings.append({"rule_id": rule["id"], "status": status, "rationale": rationale, "evidence": evidence})
    return findings


def supported_findings(findings, request, gaps):
    supported = []
    for finding in findings:
        evidence = request_evidence(finding["evidence_fields"], request)
        if evidence and finding["explanation"].strip():
            supported.append({"explanation": finding["explanation"], "evidence": evidence})
        else:
            fields = finding["evidence_fields"] or ["safeguards"]
            gaps.extend({"field_id": field_id, "question": f"Clarify {core.FIELDS[field_id].lower()}: {finding['explanation']}"} for field_id in fields)
    return supported


def build_assessment(answer, case, rubric):
    request = case["request"]
    gaps = [{"field_id": key, "question": f"Provide {core.FIELDS[key].lower()}."} for key in core.missing_fields(request)]
    gaps.extend(answer["missing_information"])
    gaps.extend({"field_id": "purpose", "question": f"Clarify conflicting facts: {value}"} for value in case.get("unresolved_conflicts", []))
    conflicts = supported_findings(answer["conflicts"], request, gaps)
    safeguards = supported_findings(answer["existing_safeguards"], request, gaps)
    gaps = list({(item["field_id"], item["question"]): item for item in gaps if item["question"].strip()}.values())
    assessment = {
        "summary": answer["summary"], "dimensions": dimension_findings(answer, request, rubric),
        "blockers": blocker_findings(answer, request, rubric), "missing_information": gaps,
        "conflicts": conflicts, "existing_safeguards": safeguards,
        "mitigations": list(dict.fromkeys(value.strip() for value in answer["mitigations"] if value.strip())),
    }
    return core.validate_assessment(assessment, request, rubric)


def assess_request(case, configuration, model):
    rubric = configuration["rubric"]
    answer = core.call_model(configuration["prompts"]["assessment"], {
        "request": case["request"], "fields": core.FIELDS, "rubric": rubric,
        "dimension_keys": {f"dimension_{index}": item["id"] for index, item in enumerate(rubric["dimensions"], 1)},
        "blocker_keys": {f"blocker_{index}": item["id"] for index, item in enumerate(rubric["blocking_rules"], 1)},
        "missing_fields": core.missing_fields(case["request"]),
        "unresolved_conflicts": case.get("unresolved_conflicts", []),
    }, assessment_schema(rubric), model)
    assessment = build_assessment(answer.model_dump(mode="json"), case, rubric)
    return {
        "id": str(core.uuid4()), "created_at": core.now(), "request_revision": case["revision"],
        "request": deepcopy(case["request"]), "configuration": deepcopy(configuration),
        "request_sources": deepcopy(case.get("request_sources", {})),
        "model": model, "assessment": assessment.model_dump(),
        "decision": core.recommendation_for(assessment, case["request"]),
        "matches": [], "comparison_status": "Not run",
    }


def comparison_schema(precedents):
    case_id = Enum("PrecedentId", {f"case_{index}": item["id"] for index, item in enumerate(precedents, 1)}, type=str)
    match = create_model("PrecedentMatch", __base__=core.Match, case_id=(case_id, ...))
    return create_model("PrecedentComparison", matches=(list[match], Field(max_length=3)))


def compare_precedents(request, precedents, configuration, model=None):
    if not precedents:
        return []
    comparison = core.call_model(configuration["prompts"]["comparison"], {
        "request": request,
        "cases": [{"case_id": item["id"], "markdown": item["content"]} for item in precedents],
    }, comparison_schema(precedents), model)
    available = {item["id"]: item for item in precedents}
    matches = {}
    for match in comparison.matches:
        case_id = match.case_id.value
        matches.setdefault(case_id, match.model_dump(mode="json") | {"precedent": deepcopy(available[case_id])})
    return list(matches.values())
