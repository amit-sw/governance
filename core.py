import json
import os
import tomllib
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from openai import OpenAI
from pydantic import BaseModel, Field


FIELDS = {
    "title": "Use-case title",
    "owner": "Owner or team",
    "purpose": "Business problem and intended benefit",
    "tool": "AI tool and vendor",
    "use_type": "Agent, AI-enabled software, or other",
    "users": "Operators and output audience",
    "affected_people": "Who or what could be affected",
    "input_sources": "Input data sources",
    "data_categories": "Types of input data",
    "confidentiality": "Confidentiality, personal or privileged data",
    "outputs": "What the tool produces",
    "output_use": "How the output will be used",
    "autonomy": "Decisions and actions the tool can take",
    "human_review": "Human review and oversight",
    "access": "Access restrictions",
    "sharing": "External sharing and vendor data use",
    "retention": "Data retention and deletion",
    "safeguards": "Other safeguards and monitoring",
    "ip_rights": "Rights to use inputs and outputs",
}
MATERIAL_FIELDS = [key for key in FIELDS if key not in {"title", "owner"}]
PROMPT_NAMES = ("intake", "assessment", "comparison")
DEFAULT_MODEL = "gpt-6.1-sol"
BASE_DIR = Path(__file__).resolve().parent


class Evidence(BaseModel):
    field_id: str
    quote: str = Field(min_length=1)


class FieldUpdate(BaseModel):
    field_id: str
    value: str
    evidence_quote: str = Field(min_length=1)


class IntakeResult(BaseModel):
    summary: str
    updates: list[FieldUpdate]
    questions: list[str] = Field(max_length=2)


class Dimension(BaseModel):
    criterion_id: str
    score: int | None = Field(ge=0, le=3, strict=True)
    rationale: str = Field(min_length=1)
    evidence: list[Evidence]


class Blocker(BaseModel):
    rule_id: str
    status: Literal["applies", "does_not_apply", "unknown"]
    rationale: str = Field(min_length=1)
    evidence: list[Evidence]


class Gap(BaseModel):
    field_id: str
    question: str


class Finding(BaseModel):
    explanation: str
    evidence: list[Evidence] = Field(min_length=1)


class Assessment(BaseModel):
    summary: str
    dimensions: list[Dimension]
    blockers: list[Blocker]
    missing_information: list[Gap]
    conflicts: list[Finding]
    existing_safeguards: list[Finding]
    mitigations: list[str]


class Match(BaseModel):
    case_id: str
    relationship: Literal["possible_duplicate", "useful_precedent"]
    similarities: str
    differences: str


class Comparison(BaseModel):
    matches: list[Match] = Field(max_length=3)


class RubricDimension(BaseModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    guidance: str = Field(min_length=1)
    anchors: list[str] = Field(min_length=4, max_length=4)


class RubricRule(BaseModel):
    id: str = Field(min_length=1)
    label: str
    rule: str = Field(min_length=1)


class Rubric(BaseModel):
    name: str
    version: str
    note: str
    dimensions: list[RubricDimension] = Field(min_length=1)
    blocking_rules: list[RubricRule]


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ExternalDecision(BaseModel):
    outcome: Literal["approved", "approved_with_conditions", "rejected", "request_information"]
    date: str
    rationale: str
    conditions: list[str]
    source: str


class CaseRecord(BaseModel):
    id: str
    created_at: str
    updated_at: str
    request: dict[str, str]
    revision: int = Field(ge=1)
    confirmed: bool
    conversation: list[Message]
    reports: list[dict] = Field(default_factory=list)
    synthetic: bool = True
    external_decision: ExternalDecision | None = None


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else deepcopy(default)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def load_configuration(directory=BASE_DIR):
    directory = Path(directory)
    configuration = {
        "rubric": read_json(directory / "rubric.json"),
        "prompts": read_json(directory / "prompts.json"),
    }
    validate_configuration(configuration)
    return configuration


def validate_configuration(configuration):
    rubric = Rubric.model_validate(configuration["rubric"])
    for collection in (rubric.dimensions, rubric.blocking_rules):
        ids = [item.id for item in collection]
        if len(ids) != len(set(ids)):
            raise ValueError("Rubric IDs must be unique.")
    if set(configuration["prompts"]) != set(PROMPT_NAMES):
        raise ValueError("Prompts must contain intake, assessment, and comparison.")
    if any(not isinstance(value, str) or not value.strip() for value in configuration["prompts"].values()):
        raise ValueError("Each prompt must be nonempty text.")


def blank_request():
    return {key: "Unknown" for key in FIELDS}


def new_case(request=None):
    timestamp = now()
    return CaseRecord(
        id=str(uuid4()), created_at=timestamp, updated_at=timestamp,
        request=blank_request() | (request or {}), revision=1,
        confirmed=False, conversation=[],
    ).model_dump()


def update_request(case, request):
    if set(request) != set(FIELDS) or any(not isinstance(value, str) for value in request.values()):
        raise ValueError("A request must contain the named text fields.")
    request = {key: value.strip() or "Unknown" for key, value in request.items()}
    if request != case["request"]:
        case["request"] = request
        case["revision"] += 1
        case["confirmed"] = False
    case["updated_at"] = now()


def normalized(text):
    return " ".join(text.split()).casefold()


def is_unknown(value):
    text = normalized(value)
    return not text or text in {"n/a", "na", "unsure", "tbd", "not specified", "not known"} or text.startswith("unknown")


def missing_fields(request):
    return [key for key in MATERIAL_FIELDS if is_unknown(request.get(key, ""))]


def get_api_key():
    path = BASE_DIR / ".streamlit" / "secrets.toml"
    if path.exists():
        with path.open("rb") as file:
            return tomllib.load(file).get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    return os.getenv("OPENAI_API_KEY")


def validate_evidence(evidence, request):
    for item in evidence:
        if item.field_id not in FIELDS or item.field_id not in request:
            raise ValueError(f"Unknown evidence field: {item.field_id}")
        if not normalized(item.quote) or normalized(item.quote) not in normalized(request[item.field_id]):
            raise ValueError(f"Evidence is not present in the request: {item.field_id}")


def call_model(prompt, payload, schema, model=None):
    client = OpenAI(api_key=get_api_key(), max_retries=0, timeout=60)
    response = client.responses.parse(
        model=model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        store=False,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        text_format=schema,
    )
    if response.output_parsed is None:
        raise ValueError("The model returned no complete structured result. No assessment was saved.")
    return response.output_parsed


def clarify_request(case, configuration, model=None):
    result = call_model(configuration["prompts"]["intake"], {
        "fields": FIELDS, "request": case["request"],
        "conversation": case["conversation"], "missing_fields": missing_fields(case["request"]),
    }, IntakeResult, model)
    sources = [message["content"] for message in case["conversation"] if message["role"] == "user"]
    sources += list(case["request"].values())
    request = deepcopy(case["request"])
    for update in result.updates:
        if update.field_id not in FIELDS:
            raise ValueError(f"Unknown intake field: {update.field_id}")
        if not normalized(update.evidence_quote) or not any(normalized(update.evidence_quote) in normalized(source) for source in sources):
            raise ValueError("An intake update has no matching user-provided evidence.")
        request[update.field_id] = update.value
    return request, result


def validate_assessment(assessment, request, rubric):
    if not isinstance(assessment, Assessment):
        assessment = Assessment.model_validate(assessment)
    expected = {dimension["id"] for dimension in rubric["dimensions"]}
    actual = [dimension.criterion_id for dimension in assessment.dimensions]
    if set(actual) != expected or len(actual) != len(expected):
        raise ValueError("The assessment must cover every rubric dimension exactly once.")
    expected_rules = {rule["id"] for rule in rubric["blocking_rules"]}
    actual_rules = [blocker.rule_id for blocker in assessment.blockers]
    if set(actual_rules) != expected_rules or len(actual_rules) != len(expected_rules):
        raise ValueError("The assessment must check every blocking rule exactly once.")
    for dimension in assessment.dimensions:
        if dimension.score is not None and not dimension.evidence:
            raise ValueError("A scored dimension requires request evidence.")
        if dimension.score is not None and all(is_unknown(request.get(item.field_id, "")) for item in dimension.evidence):
            raise ValueError("Unknown facts cannot support a numerical score.")
        validate_evidence(dimension.evidence, request)
    for blocker in assessment.blockers:
        if blocker.status != "unknown" and not blocker.evidence:
            raise ValueError("A resolved blocker requires request evidence.")
        if blocker.status != "unknown" and all(is_unknown(request.get(item.field_id, "")) for item in blocker.evidence):
            raise ValueError("Unknown facts cannot resolve a blocker.")
        validate_evidence(blocker.evidence, request)
    for gap in assessment.missing_information:
        if gap.field_id not in FIELDS:
            raise ValueError(f"Unknown missing-information field: {gap.field_id}")
    for finding in assessment.conflicts + assessment.existing_safeguards:
        validate_evidence(finding.evidence, request)
    return assessment


def recommendation_for(assessment, request):
    scores = [item.score for item in assessment.dimensions if item.score is not None]
    highest = max(scores, default=None)
    known_risk = {None: "Unknown", 0: "Negligible", 1: "Low", 2: "Medium", 3: "High"}[highest]
    unresolved = bool(missing_fields(request) or assessment.missing_information or assessment.conflicts)
    unresolved |= any(item.score is None for item in assessment.dimensions)
    unresolved |= any(item.status == "unknown" for item in assessment.blockers)
    unresolved |= highest is None
    unresolved |= highest == 2 and not any(value.strip() for value in assessment.mitigations)
    if any(item.status == "applies" for item in assessment.blockers):
        recommendation = "Recommend not proceeding"
        reason = "An illustrative policy blocker applies."
    elif unresolved:
        recommendation = "Obtain more information"
        reason = "Material facts, contradictions, scores, or mitigation conditions remain unresolved."
    elif highest == 3:
        recommendation = "Recommend not proceeding in the current form"
        reason = "A high-risk dimension requires mitigation or specialist review."
    elif highest == 2:
        recommendation = "Recommend approval with stated conditions"
        reason = "The highest risk is medium; the listed mitigation conditions must be satisfied."
    else:
        recommendation = "Recommend approval"
        reason = "All dimensions are negligible or low, with sufficient information and no blocker."
    return {
        "overall_risk": f"Unresolved (known risk: {known_risk})" if unresolved else known_risk,
        "highest_known_risk": known_risk,
        "recommendation": recommendation, "reason": reason,
        "missing_fields": missing_fields(request),
    }


def assess_request(case, configuration, model=None):
    if not case["confirmed"]:
        raise ValueError("Confirm the request before assessing it.")
    assessment = call_model(configuration["prompts"]["assessment"], {
        "request": case["request"], "fields": FIELDS, "rubric": configuration["rubric"],
        "missing_fields": missing_fields(case["request"]),
    }, Assessment, model)
    validate_assessment(assessment, case["request"], configuration["rubric"])
    return {
        "id": str(uuid4()), "created_at": now(), "request_revision": case["revision"],
        "request": deepcopy(case["request"]), "configuration": deepcopy(configuration),
        "model": model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        "assessment": assessment.model_dump(),
        "decision": recommendation_for(assessment, case["request"]),
        "matches": [], "comparison_status": "Not run",
    }


def find_similar_cases(request, candidates, configuration, model=None, exclude_id=None):
    candidates = [case for case in candidates if case["id"] != exclude_id and case["confirmed"]]
    if not candidates:
        return []
    payload = [{
        "case_id": case["id"], "request": case["request"], "synthetic": case["synthetic"],
        "external_decision": case.get("external_decision"),
        "record_type": "External human outcome" if case.get("external_decision") else "Submission; no human decision",
    } for case in candidates]
    comparison = call_model(configuration["prompts"]["comparison"], {
        "request": request, "cases": payload,
    }, Comparison, model)
    ids = {case["id"] for case in candidates}
    seen = set()
    matches = []
    for match in comparison.matches:
        if match.case_id not in ids or match.case_id in seen:
            raise ValueError("A comparison must cite distinct available cases.")
        seen.add(match.case_id)
        case = next(case for case in candidates if case["id"] == match.case_id)
        snapshot = {key: deepcopy(case[key]) for key in ("id", "request", "revision", "synthetic", "external_decision")}
        matches.append(match.model_dump() | {"case": snapshot})
    return matches


def export_cases(cases):
    return {"format_version": 1, "cases": cases}


def import_cases(payload):
    if payload.get("format_version") != 1:
        raise ValueError("Expected case export format version 1.")
    cases = [CaseRecord.model_validate(item).model_dump() for item in payload["cases"]]
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Imported case IDs must be unique.")
    for case in cases:
        if set(case["request"]) - set(FIELDS):
            raise ValueError("Imported requests contain unknown fields.")
        case["request"] = blank_request() | case["request"]
        for report in case["reports"]:
            validate_configuration(report["configuration"])
            assessment = validate_assessment(report["assessment"], report["request"], report["configuration"]["rubric"])
            report["decision"] = recommendation_for(assessment, report["request"])
    return cases


def report_markdown(report):
    assessment = report["assessment"]
    decision = report["decision"]
    rubric = report["configuration"]["rubric"]
    labels = {item["id"]: item["label"] for item in rubric["dimensions"]}
    lines = [
        f"# {report['request']['title']}", "", "ADVISORY ASSESSMENT — not a final human decision.", "",
        "Illustrative sandbox rubric; no company-policy authority.", "",
        f"Request revision: {report['request_revision']} | Run: {report['created_at']} | Model: {report['model']}",
        f"Rubric: {rubric['name']} ({rubric['version']})", "",
        f"**Overall risk:** {decision['overall_risk']}", f"**Recommendation:** {decision['recommendation']}",
        "", decision["reason"], "", "## Summary", "", assessment["summary"], "", "## Dimension findings", "",
    ]
    for dimension in assessment["dimensions"]:
        score = dimension["score"] if dimension["score"] is not None else "Unknown"
        lines += [f"### {labels[dimension['criterion_id']]} ({dimension['criterion_id']}): {score}", "", dimension["rationale"], ""]
        lines += [f"- {item['field_id']}: {item['quote']}" for item in dimension["evidence"]]
        lines.append("")
    lines += ["## Blocking rules", ""]
    for blocker in assessment["blockers"]:
        lines += [f"- **{blocker['rule_id']} — {blocker['status']}**: {blocker['rationale']}"]
        lines += [f"  - {item['field_id']}: {item['quote']}" for item in blocker["evidence"]]
    lines += ["", "## Missing information", ""]
    lines += [f"- {FIELDS[key]} ({key})" for key in decision["missing_fields"]]
    lines += [f"- {item['field_id']}: {item['question']}" for item in assessment["missing_information"]]
    if any(item["score"] is None for item in assessment["dimensions"]):
        lines += ["- One or more rubric scores remain Unknown."]
    for title, key in (("Conflicting statements", "conflicts"), ("Existing safeguards", "existing_safeguards")):
        lines += ["", f"## {title}", ""]
        for finding in assessment[key]:
            lines += [f"- {finding['explanation']}"]
            lines += [f"  - {item['field_id']}: {item['quote']}" for item in finding["evidence"]]
    lines += ["", "## Proposed mitigation conditions", ""]
    lines += [f"- {item}" for item in assessment["mitigations"]]
    lines += ["", "## Similar submissions and precedents", "", report["comparison_status"], ""]
    for match in report["matches"]:
        case = match["case"]
        outcome = case.get("external_decision")
        label = "Fictional external human outcome" if outcome and case["synthetic"] else "Externally supplied human outcome (unverified)" if outcome else "Submission; no human decision"
        lines += [f"### {case['request']['title']} ({case['id']})", "", label,
                  f"Relationship: {match['relationship']}", f"Similarities: {match['similarities']}", f"Differences: {match['differences']}", ""]
        if outcome:
            lines += [f"Outcome: {outcome['outcome']} | Date: {outcome['date']} | Source: {outcome['source']}", outcome["rationale"], ""]
            lines += [f"- Condition: {item}" for item in outcome["conditions"]]
    lines += ["", "## Confirmed request snapshot", ""]
    lines += [f"- **{label}:** {report['request'][key]}" for key, label in FIELDS.items()]
    lines += ["", "Exact rubric and prompt snapshots are included in the JSON export."]
    return "\n".join(lines) + "\n"
