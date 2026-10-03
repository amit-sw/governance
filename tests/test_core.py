import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import core


@pytest.fixture
def configuration():
    return core.load_configuration()


@pytest.fixture
def request_data():
    return core.read_json(core.BASE_DIR / "examples.json")["cases"][0]["request"]


def assessment_for(configuration, request_data, score=1):
    return core.Assessment(
        summary="Synthetic assessment for deterministic rule testing.",
        dimensions=[core.Dimension(
            criterion_id=item["id"], score=score, rationale="Illustrative evidence.",
            evidence=[core.Evidence(field_id="purpose", quote=request_data["purpose"])],
        ) for item in configuration["rubric"]["dimensions"]],
        blockers=[core.Blocker(
            rule_id=item["id"], status="does_not_apply", rationale="Illustrative evidence.",
            evidence=[core.Evidence(field_id="autonomy", quote=request_data["autonomy"])],
        ) for item in configuration["rubric"]["blocking_rules"]],
        missing_information=[], conflicts=[], existing_safeguards=[], mitigations=[],
    )


@pytest.mark.parametrize("scores,conditions,expected", [
    ([0, 0, 0, 0, 0, 0], [], "Recommend approval"),
    ([1, 0, 1, 0, 0, 0], [], "Recommend approval"),
    ([2, 0, 0, 0, 0, 0], ["Independent human verification"], "Recommend approval with stated conditions"),
    ([2, 0, 0, 0, 0, 0], [], "Obtain more information"),
    ([3, 0, 0, 0, 0, 0], [], "Recommend not proceeding in the current form"),
    ([None, 0, 0, 0, 0, 0], [], "Obtain more information"),
])
def test_highest_severity_controls_recommendation(configuration, request_data, scores, conditions, expected):
    assessment = assessment_for(configuration, request_data)
    for dimension, score in zip(assessment.dimensions, scores):
        dimension.score = score
    assessment.mitigations = conditions
    assert core.recommendation_for(assessment, request_data)["recommendation"] == expected


def test_missing_information_conflicts_and_blockers(configuration, request_data):
    assessment = assessment_for(configuration, request_data)
    incomplete = request_data | {"retention": "Unknown"}
    decision = core.recommendation_for(assessment, incomplete)
    assert decision["recommendation"] == "Obtain more information"
    assert decision["missing_fields"] == ["retention"]
    assert decision["overall_risk"].startswith("Unresolved")
    assessment.blockers[0].status = "unknown"
    assert core.recommendation_for(assessment, request_data)["recommendation"] == "Obtain more information"
    assessment.blockers[0].status = "applies"
    assert core.recommendation_for(assessment, incomplete)["recommendation"] == "Recommend not proceeding"
    assessment.blockers[0].status = "does_not_apply"
    assessment.conflicts = [core.Finding(explanation="Contradictory statement", evidence=[core.Evidence(field_id="autonomy", quote=request_data["autonomy"])])]
    assert core.recommendation_for(assessment, request_data)["recommendation"] == "Obtain more information"


@pytest.mark.parametrize("bad_score", [-1, 4, 1.5, "1", True])
def test_scores_are_strict_integers(bad_score):
    with pytest.raises(ValidationError):
        core.Dimension(criterion_id="D1", score=bad_score, rationale="Evidence", evidence=[])


@pytest.mark.parametrize("field,quote", [("imaginary", "text"), ("purpose", "Invented evidence"), ("purpose", "   ")])
def test_invalid_evidence_rejected(request_data, field, quote):
    with pytest.raises(ValueError):
        core.validate_evidence([core.Evidence(field_id=field, quote=quote)], request_data)


def test_assessment_requires_complete_rubric_coverage(configuration, request_data):
    assessment = assessment_for(configuration, request_data)
    core.validate_assessment(assessment, request_data, configuration["rubric"])
    assessment.dimensions.pop()
    with pytest.raises(ValueError, match="every rubric dimension"):
        core.validate_assessment(assessment, request_data, configuration["rubric"])
    assessment = assessment_for(configuration, request_data)
    assessment.blockers[1].rule_id = assessment.blockers[0].rule_id
    with pytest.raises(ValueError, match="every blocking rule"):
        core.validate_assessment(assessment, request_data, configuration["rubric"])


def test_unknown_evidence_cannot_justify_low_score(configuration, request_data):
    assessment = assessment_for(configuration, request_data)
    assessment.dimensions[0].evidence = [core.Evidence(field_id="confidentiality", quote="Unknown")]
    with pytest.raises(ValueError, match="Unknown facts"):
        core.validate_assessment(assessment, request_data | {"confidentiality": "Unknown"}, configuration["rubric"])


def test_intake_updates_need_user_evidence(monkeypatch, configuration, request_data):
    case = core.new_case(request_data)
    case["conversation"] = [{"role": "user", "content": "We use ExampleAI for this task."}]
    result = core.IntakeResult(summary="Known facts", updates=[core.FieldUpdate(field_id="tool", value="ExampleAI", evidence_quote="We use ExampleAI")], questions=["What data is used?"])
    monkeypatch.setattr(core, "call_model", lambda *args: result)
    updated, _ = core.clarify_request(case, configuration)
    assert updated["tool"] == "ExampleAI"
    result.updates[0].evidence_quote = "Invented source"
    with pytest.raises(ValueError, match="user-provided evidence"):
        core.clarify_request(case, configuration)
    with pytest.raises(ValidationError):
        core.IntakeResult(summary="Too many questions", updates=[], questions=["One?", "Two?", "Three?"])


def test_report_snapshots_and_json_roundtrip(monkeypatch, tmp_path, configuration, request_data):
    case = core.new_case(request_data)
    case["confirmed"] = True
    original_configuration = deepcopy(configuration)
    assessment = assessment_for(configuration, request_data)
    monkeypatch.setattr(core, "call_model", lambda *args: assessment)
    report = core.assess_request(case, configuration)
    case["reports"].append(report)
    core.update_request(case, request_data | {"title": "Changed request"})
    configuration["rubric"]["version"] = "new version"
    assert not case["confirmed"]
    assert case["revision"] == 2
    assert report["request"]["title"] == request_data["title"]
    assert report["configuration"] == original_configuration
    path = tmp_path / "history.json"
    core.write_json(path, core.export_cases([case]))
    restored = core.import_cases(core.read_json(path))[0]
    assert restored == case
    markdown = core.report_markdown(report)
    assert "ADVISORY" in markdown
    assert "Confirmed request snapshot" in markdown
    assert "OPENAI_API_KEY" not in path.read_text()


def test_unconfirmed_request_cannot_be_assessed(configuration):
    with pytest.raises(ValueError, match="Confirm"):
        core.assess_request(core.new_case(), configuration)


def test_comparison_checks_ids_excludes_drafts_and_does_not_copy_nested_reports(monkeypatch, configuration, request_data):
    current = core.new_case(request_data)
    previous = core.new_case(request_data)
    previous["confirmed"] = True
    previous["reports"] = [{"large": "nested report"}]
    draft = core.new_case()
    captured = {}
    comparison = core.Comparison(matches=[core.Match(case_id=previous["id"], relationship="possible_duplicate", similarities="Equivalent purpose", differences="Different wording")])

    def compare(prompt, payload, schema, model):
        captured.update(payload)
        return comparison

    monkeypatch.setattr(core, "call_model", compare)
    matches = core.find_similar_cases(request_data, [current, previous, draft], configuration, exclude_id=current["id"])
    assert [item["case_id"] for item in captured["cases"]] == [previous["id"]]
    assert "reports" not in matches[0]["case"]
    assert captured["cases"][0]["record_type"] == "Submission; no human decision"
    comparison.matches[0].case_id = "nonexistent"
    with pytest.raises(ValueError, match="available cases"):
        core.find_similar_cases(request_data, [previous], configuration)


def test_empty_comparison_never_invents_a_precedent(monkeypatch, configuration, request_data):
    monkeypatch.setattr(core, "call_model", lambda *args: core.Comparison(matches=[]))
    examples = core.import_cases(core.read_json(core.BASE_DIR / "examples.json"))
    assert core.find_similar_cases(request_data, examples, configuration) == []
    assert core.find_similar_cases(request_data, [], configuration) == []


def test_scoring_payload_excludes_past_decisions(monkeypatch, configuration, request_data):
    captured = {}

    def assess(prompt, payload, schema, model):
        captured.update(payload)
        return assessment_for(configuration, request_data)

    monkeypatch.setattr(core, "call_model", assess)
    case = core.new_case(request_data)
    case["confirmed"] = True
    core.assess_request(case, configuration)
    assert set(captured) == {"request", "fields", "rubric", "missing_fields"}


def test_sdk_uses_structured_outputs_without_stored_state_or_retries(monkeypatch):
    captured = {}
    expected = core.Comparison(matches=[])

    def parse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_parsed=expected)

    def client(**kwargs):
        captured["client"] = kwargs
        return SimpleNamespace(responses=SimpleNamespace(parse=parse))

    monkeypatch.setattr(core, "OpenAI", client)
    assert core.call_model("Instructions", {}, core.Comparison) == expected
    assert captured["store"] is False
    assert captured["text_format"] is core.Comparison
    assert captured["client"]["max_retries"] == 0


def test_seed_and_evaluation_collections_are_distinct():
    cases = core.import_cases(core.read_json(core.BASE_DIR / "examples.json"))
    holdouts = core.read_json(core.BASE_DIR / "evaluation_cases.json")["cases"]
    assert len(cases) == 20
    assert len(holdouts) == 10
    assert all(case["synthetic"] and case["external_decision"] for case in cases)
    assert {case["id"] for case in cases}.isdisjoint({case["id"] for case in holdouts})
    assert len({case["external_decision"]["outcome"] for case in cases}) == 4
