import httpx
import pytest
from openai import APIConnectionError
from streamlit.testing.v1 import AppTest

import core
import workflow
from test_core import assessment_for


@pytest.fixture
def request_data():
    return core.read_json(core.BASE_DIR / "examples.json")["cases"][0]["request"]


@pytest.fixture
def app(monkeypatch, tmp_path):
    configuration = workflow.load_configuration()
    rubric_path = tmp_path / "rubric.json"
    prompts_dir = tmp_path / "prompts"
    precedents_dir = tmp_path / "precedents"
    prompts_dir.mkdir()
    precedents_dir.mkdir()
    core.write_json(rubric_path, configuration["rubric"])
    for name, prompt in configuration["prompts"].items():
        (prompts_dir / f"{name}.md").write_text(prompt)
    (precedents_dir / "example.md").write_text("# Example precedent\n\nSynthetic.\n\n## Request\nPublic research.\n\n## Decision\nApproved.\n\n## Why\nHuman review.\n")
    monkeypatch.setattr(workflow, "RUBRIC_PATH", rubric_path)
    monkeypatch.setattr(workflow, "PROMPTS_DIR", prompts_dir)
    monkeypatch.setattr(workflow, "PRECEDENTS_DIR", precedents_dir)
    monkeypatch.setattr(core, "get_api_key", lambda: None)
    monkeypatch.setattr(core, "call_model", lambda *args, **kwargs: pytest.fail("Unexpected model call"))
    return AppTest.from_file(str(core.BASE_DIR / "app.py"), default_timeout=15).run()


def button(app, label):
    return next(item for item in app.button if item.label == label)


def ready_review(request):
    return workflow.IntakeReview(
        summary="The user supplied a complete synthetic request.",
        updates=[core.FieldUpdate(field_id=key, value=value, evidence_quote=value) for key, value in request.items()],
        questions=[], ready_for_assessment=True,
        readiness_reason="The material facts and controls are stated.", unresolved_conflicts=[],
    )


def install_model(monkeypatch, request, calls):
    monkeypatch.setattr(core, "get_api_key", lambda: "test-key-not-used")

    def model(prompt, payload, schema, model=None):
        calls.append(schema)
        if schema is workflow.IntakeReview:
            return ready_review(request)
        if schema is core.Assessment:
            return assessment_for(workflow.load_configuration(), payload["request"])
        return core.Comparison(matches=[])

    monkeypatch.setattr(core, "call_model", model)


def test_tabs_and_reruns_do_not_call_ai_or_save_requests(app, tmp_path):
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Guided Intake", "History & Precedents", "Rubrics", "Prompts"]
    assert len(app.chat_input) == 1
    assert not app.radio
    assert not app.selectbox
    app.run()
    assert not app.exception
    assert not (tmp_path / "history.json").exists()


def test_complete_chat_automatically_assesses_once(app, monkeypatch, request_data):
    calls = []
    install_model(monkeypatch, request_data, calls)
    app.chat_input[0].set_value("\n".join(request_data.values())).run()
    assert not app.exception
    state = app.session_state["active_request"]
    assert state["mode"] == "assessment"
    assert state["report"]["decision"]["recommendation"] == "Recommend approval"
    assert calls == [workflow.IntakeReview, core.Assessment, core.Comparison]
    app.run()
    app.run()
    assert calls == [workflow.IntakeReview, core.Assessment, core.Comparison]


def test_unknown_material_facts_prevent_automatic_assessment(app, monkeypatch):
    calls = []
    monkeypatch.setattr(core, "get_api_key", lambda: "test-key-not-used")

    def model(prompt, payload, schema, model=None):
        calls.append(schema)
        return workflow.IntakeReview(
            summary="An incomplete request.", updates=[], questions=[],
            ready_for_assessment=True, readiness_reason="Model says complete.", unresolved_conflicts=[],
        )

    monkeypatch.setattr(core, "call_model", model)
    app.chat_input[0].set_value("I want a meeting assistant.").run()
    assert not app.exception
    assert app.session_state["active_request"]["mode"] == "intake"
    assert app.session_state["active_request"]["report"] is None
    assert calls == [workflow.IntakeReview]


def test_assessment_api_failure_keeps_chat_and_requires_explicit_retry(app, monkeypatch, request_data):
    calls = []
    monkeypatch.setattr(core, "get_api_key", lambda: "test-key-not-used")

    def model(prompt, payload, schema, model=None):
        calls.append(schema)
        if schema is workflow.IntakeReview:
            return ready_review(request_data)
        raise APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/responses"))

    monkeypatch.setattr(core, "call_model", model)
    message = "\n".join(request_data.values())
    app.chat_input[0].set_value(message).run()
    assert not app.exception
    state = app.session_state["active_request"]
    assert state["report"] is None
    assert state["assessment_failed"]
    assert state["case"]["conversation"][0]["content"] == message
    assert button(app, "Retry assessment")
    app.run()
    assert calls == [workflow.IntakeReview, core.Assessment]


def test_correction_returns_current_request_to_intake(app, monkeypatch, request_data):
    install_model(monkeypatch, request_data, [])
    app.chat_input[0].set_value("\n".join(request_data.values())).run()
    corrected = "The tool will send messages automatically."
    answer = workflow.IntakeReview(
        summary=corrected,
        updates=[core.FieldUpdate(field_id="autonomy", value=corrected, evidence_quote=corrected)],
        questions=["Who authorizes the sending and can stop it?"],
        ready_for_assessment=False, readiness_reason="The revised autonomy needs clarification.",
        unresolved_conflicts=[],
    )
    monkeypatch.setattr(core, "call_model", lambda *args, **kwargs: answer)
    app.chat_input[0].set_value(corrected).run()
    assert not app.exception
    state = app.session_state["active_request"]
    assert state["mode"] == "intake"
    assert state["report"] is None
    assert state["case"]["request"]["autonomy"] == corrected


def test_rubric_and_prompt_edits_save_to_separate_files_without_ai(app, tmp_path):
    next(item for item in app.text_input if item.label == "Rubric version").set_value("0.2-reviewed")
    button(app, "Save rubric").click().run()
    assert not app.exception
    assert core.read_json(tmp_path / "rubric.json")["version"] == "0.2-reviewed"
    next(item for item in app.text_area if item.key.startswith("intake_")).set_value("Revised intake instructions.")
    button(app, "Save intake prompt").click().run()
    assert not app.exception
    assert (tmp_path / "prompts" / "intake.md").read_text() == "Revised intake instructions.\n"


def test_completeness_requires_resolved_conflicts_and_no_followup(request_data):
    answer = ready_review(request_data)
    assert workflow.intake_is_complete(request_data, answer)
    answer.unresolved_conflicts = ["Unclear whether outputs are reviewed before use."]
    assert not workflow.intake_is_complete(request_data, answer)
    answer.unresolved_conflicts = []
    answer.questions = ["Who reviews the output?"]
    assert not workflow.intake_is_complete(request_data, answer)


def test_markdown_matches_validate_ids_and_keep_their_source_snapshot(app, monkeypatch, request_data):
    precedents = workflow.load_precedents()
    match = core.Match(case_id="unavailable.md", relationship="useful_precedent", similarities="Public inputs.", differences="Different purpose.")
    monkeypatch.setattr(core, "call_model", lambda *args, **kwargs: core.Comparison(matches=[match]))
    with pytest.raises(ValueError, match="available Markdown precedents"):
        workflow.compare_precedents(request_data, precedents, workflow.load_configuration())
    match.case_id = precedents[0]["id"]
    matches = workflow.compare_precedents(request_data, precedents, workflow.load_configuration())
    original = precedents[0]["content"]
    precedents[0]["content"] = "Changed later."
    assert matches[0]["precedent"]["content"] == original
