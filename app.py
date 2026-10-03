import hashlib
import json
from copy import deepcopy
from time import perf_counter

import streamlit as st
from openai import APIError

import core
import workflow


WELCOME_MESSAGE = "What would you like to use AI for? Describe the problem and the tool you have in mind. I’ll help clarify the details before assessment. You can answer **Unknown** when you do not have a fact yet."


def initialize_session():
    st.session_state.selected_model = workflow.load_settings()["model"]
    if "active_request" not in st.session_state:
        st.session_state.active_request = workflow.new_session()
    state = st.session_state.active_request
    state.setdefault("request_seconds", None)
    state.setdefault("assessment_seconds", None)
    state.setdefault("pending_assessment", False)
    state.setdefault("intake_seconds", None)
    state.setdefault("assessment_origin", "manual")
    state.setdefault("assessment_model", None)
    return state


def selected_model():
    return st.session_state.selected_model


def run_ai(state, operation, label="Thinking…"):
    state["error"] = None
    if not core.get_api_key():
        state["error"] = "Add OPENAI_API_KEY to .streamlit/secrets.toml before continuing. Your chat remains in this session."
        return None
    try:
        started = perf_counter()
        with st.spinner(label, show_time=True):
            result = operation()
        st.caption(f"Completed in {perf_counter() - started:.1f} seconds.")
        return result
    except APIError as error:
        state["error"] = f"OpenAI request failed: {error}. Your chat remains in this session. Retry when ready."
        return None
    except ValueError as error:
        state["error"] = f"The model response could not be validated: {error} Your chat remains in this session. Retry when ready."
        return None


def show_message(container, role, content):
    with container:
        with st.chat_message(role):
            st.markdown(content)


def compare_precedents(state, precedents):
    state["comparison_failed"] = True
    report = state["report"]
    report["comparison_status"] = "Precedent comparison has not completed."
    matches = run_ai(state, lambda: workflow.compare_precedents(
        report["request"], precedents, report["configuration"], report["model"],
    ), "Thinking… comparing precedents")
    if matches is not None:
        report["matches"] = matches
        report["comparison_status"] = "Comparison complete." if matches else "Comparison complete; no relevant precedents found."
        state["comparison_failed"] = False


def assess_current_request(state, precedents, manual=False):
    state["assessment_failed"] = True
    started = perf_counter()
    case = deepcopy(state["case"])
    case["confirmed"] = True
    if manual:
        st.info("Assessing the information supplied so far. Unknown facts remain unresolved.")
    else:
        st.info("Intake complete → switching to ASSESSMENT")
    report = run_ai(state, lambda: workflow.assess_request(case, state["configuration"], state["assessment_model"]), "Thinking… assessing the request")
    if report is not None:
        state["report"] = report
        state["assessment_failed"] = False
        compare_precedents(state, precedents)
    state["assessment_seconds"] = perf_counter() - started


def continue_intake(state, configuration, precedents, chat):
    state["intake_failed"] = True
    result = run_ai(state, lambda: workflow.review_intake(state["case"], configuration, selected_model()), "Thinking… reviewing your request")
    if result is None:
        return
    request, answer = result
    core.update_request(state["case"], request)
    state["intake_failed"] = False
    ready = workflow.intake_is_complete(request, answer)
    content = workflow.intake_message(request, answer, ready)
    state["case"]["conversation"].append({"role": "assistant", "content": content})
    show_message(chat, "assistant", content)
    if ready:
        state["mode"] = "assessment"
        state["case"]["confirmed"] = True
        state["configuration"] = deepcopy(configuration)
        state["readiness_reason"] = answer.readiness_reason
        state["assessment_origin"] = "automatic"
        state["pending_assessment"] = True


def submit_message(state, message, configuration, precedents, chat):
    started = perf_counter()
    state["mode"] = "intake"
    state["report"] = None
    state["case"]["confirmed"] = False
    state["assessment_failed"] = False
    state["comparison_failed"] = False
    state["pending_assessment"] = False
    state["case"]["conversation"].append({"role": "user", "content": message})
    show_message(chat, "user", message)
    continue_intake(state, configuration, precedents, chat)
    state["request_seconds"] = perf_counter() - started
    state["intake_seconds"] = state["request_seconds"]


@st.dialog("Current request", width="large", dismissible=True, on_dismiss="rerun")
def request_dialog(state):
    st.caption("These are the facts extracted from the chat. Correct any fact by sending another message.")
    st.table([{"Field": label, "Provided facts": state["case"]["request"][key]} for key, label in core.FIELDS.items()])
    if st.button("Close", key="close_request"):
        st.rerun()


@st.dialog("Conversation so far", width="large", dismissible=True, on_dismiss="rerun")
def conversation_dialog(state):
    st.caption("Use the copy icon at the top right of the text below to copy the entire conversation.")
    messages = [{"role": "assistant", "content": WELCOME_MESSAGE}] + state["case"]["conversation"]
    text = "\n\n---\n\n".join(f"## {message['role'].title()}\n\n{message['content']}" for message in messages)
    st.code(text, language=None, wrap_lines=True)
    if st.button("Close", key="close_conversation"):
        st.rerun()


@st.dialog("Assessment", width="large", dismissible=True, on_dismiss="rerun")
def assessment_dialog(state, configuration, precedents):
    pending = state.pop("pending_assessment", False)
    retry = False
    if not pending and state["assessment_failed"]:
        retry = st.button("Retry assessment", key="modal_retry_assessment")
    if pending or retry:
        started = perf_counter()
        state["configuration"] = deepcopy(configuration)
        state["assessment_model"] = selected_model()
        state["report"] = None
        state["comparison_failed"] = False
        if state["intake_failed"]:
            result = run_ai(state, lambda: workflow.review_intake(state["case"], configuration, state["assessment_model"]), "Thinking… extracting the facts supplied so far")
            if result is None:
                state["assessment_failed"] = True
                state["assessment_seconds"] = perf_counter() - started
                st.error(state["error"])
                st.caption(f"Total assessment time: {state['assessment_seconds']:.1f} seconds.")
                return
            core.update_request(state["case"], result[0])
            state["intake_failed"] = False
        assess_current_request(state, precedents, manual=state["assessment_origin"] == "manual")
        state["assessment_seconds"] = perf_counter() - started
        if state["assessment_origin"] == "automatic":
            state["request_seconds"] = (state["intake_seconds"] or 0) + state["assessment_seconds"]
    if state["error"]:
        st.error(state["error"])
    if state["assessment_seconds"] is not None:
        st.caption(f"Total assessment time: {state['assessment_seconds']:.1f} seconds.")
        if state["assessment_origin"] == "automatic":
            st.caption(f"Total chat request time: {state['request_seconds']:.1f} seconds.")
    if state["report"] is not None:
        render_assessment(state["report"], configuration)
    if state["comparison_failed"] and st.button("Retry precedent comparison", key="modal_retry_comparison"):
        compare_precedents(state, precedents)
        st.rerun(scope="fragment")
    if st.button("Close", key="close_assessment"):
        st.rerun()


def render_findings(title, findings):
    if findings:
        st.markdown(f"#### {title}")
        for finding in findings:
            st.markdown(f"- {finding['explanation']}")
            for evidence in finding["evidence"]:
                st.caption(f"{evidence['field_id']}: {evidence['quote']}")


def render_assessment(report, configuration):
    st.divider()
    st.subheader("Assessment")
    st.caption("ADVISORY — final human decisions remain outside this app.")
    decision = report["decision"]
    assessment = report["assessment"]
    rubric = report["configuration"]["rubric"]
    labels = {item["id"]: item["label"] for item in rubric["dimensions"]}
    st.markdown(f"**{decision['recommendation']}** · Overall risk: **{decision['overall_risk']}**")
    st.write(decision["reason"])
    st.write(assessment["summary"])
    if report["configuration"] != configuration:
        st.info("The rubric or prompts have changed since this assessment. Send a chat message to review the request with the current settings.")
    st.table([{
        "Dimension": f"{item['criterion_id']} · {labels[item['criterion_id']]}",
        "Score": "Unknown" if item["score"] is None else str(item["score"]),
        "Explanation": item["rationale"],
    } for item in assessment["dimensions"]])
    with st.expander("Evidence and rubric references"):
        for item in assessment["dimensions"]:
            st.markdown(f"**{item['criterion_id']} · {labels[item['criterion_id']]}**")
            for evidence in item["evidence"]:
                st.markdown(f"- `{evidence['field_id']}`: {evidence['quote']}")
        for blocker in assessment["blockers"]:
            st.markdown(f"**{blocker['rule_id']} · {blocker['status']}** — {blocker['rationale']}")
            for evidence in blocker["evidence"]:
                st.markdown(f"- `{evidence['field_id']}`: {evidence['quote']}")
    missing = [core.FIELDS[key] for key in decision["missing_fields"]]
    missing += [item["question"] for item in assessment["missing_information"]]
    missing += [f"Provide evidence to score {labels[item['criterion_id']]}: {item['rationale']}" for item in assessment["dimensions"] if item["score"] is None]
    missing += [f"Resolve {item['rule_id']}: {item['rationale']}" for item in assessment["blockers"] if item["status"] == "unknown"]
    missing += [f"Clarify conflicting facts: {item['explanation']}" for item in assessment["conflicts"]]
    if missing:
        st.warning("This assessment is incomplete. Provide the information below to enable a full assessment.")
        st.markdown("#### Information needed for a full assessment")
        for question in dict.fromkeys(missing):
            st.markdown(f"- {question}")
    for blocker in assessment["blockers"]:
        if blocker["status"] != "does_not_apply":
            st.warning(f"{blocker['rule_id']} · {blocker['status']}: {blocker['rationale']}")
    render_findings("Conflicting statements", assessment["conflicts"])
    render_findings("Existing safeguards", assessment["existing_safeguards"])
    if assessment["mitigations"]:
        st.markdown("#### Proposed conditions and mitigations")
        for condition in assessment["mitigations"]:
            st.markdown(f"- {condition}")
    st.markdown("#### Related precedents")
    st.caption(report["comparison_status"])
    for match in report["matches"]:
        st.markdown(f"**{match['precedent']['title']}** · {match['relationship'].replace('_', ' ')}")
        st.write(f"Similarities: {match['similarities']}")
        st.write(f"Differences: {match['differences']}")
        with st.expander(f"Read {match['case_id']}"):
            st.markdown(match["precedent"]["content"])
    with st.expander("Facts, rubric, and prompts used for this assessment"):
        st.caption(f"Run: {report['created_at']} · Model: {report['model']}")
        st.json({"request": report["request"], "configuration": report["configuration"]})


def render_intake(state, configuration, precedents):
    history_space = "17rem" if state["request_seconds"] is not None else "15rem"
    st.html("""
        <style>
        .stMainBlockContainer {padding: 4rem 1rem .75rem; max-width: none;}
        .st-key-chat_history, [data-testid='stLayoutWrapper']:has(> .st-key-chat_history) {height: calc(100dvh - SPACE) !important; min-height: 100px; flex: 0 0 auto !important;}
        .st-key-show_request button {color: #2563eb; background: #eff6ff; border-color: #bfdbfe;}
        .st-key-assess_request button {color: #15803d; background: #f0fdf4; border-color: #bbf7d0;}
        .st-key-show_conversation button {color: #9333ea; background: #faf5ff; border-color: #e9d5ff;}
        .st-key-start_over button {color: #c2410c; background: #fff7ed; border-color: #fed7aa;}
        </style>
    """.replace("SPACE", history_space))
    heading, controls = st.columns([7, 3], vertical_alignment="center")
    heading.markdown("### AI Use-Case Assistant")
    with controls:
        with st.container(horizontal=True, horizontal_alignment="right", gap="small"):
            show_request = st.button("", icon=":material/description:", help="Show current request", key="show_request")
            assess_now = st.button("", icon=":material/fact_check:", help="Assess input so far", key="assess_request", disabled=not state["case"]["conversation"])
            show_conversation = st.button("", icon=":material/forum:", help="Conversation so far", key="show_conversation")
            start_over = st.button("", icon=":material/restart_alt:", help="Start over", key="start_over")
    if start_over:
        st.session_state.active_request = workflow.new_session()
        st.rerun()
    with st.container(border=True):
        chat = st.container(height=450, border=False, key="chat_history")
        if state["case"]["conversation"]:
            for item in state["case"]["conversation"]:
                show_message(chat, item["role"], item["content"])
        else:
            show_message(chat, "assistant", WELCOME_MESSAGE)
        if state["error"] and state["intake_failed"]:
            with chat:
                st.error(state["error"])
                st.caption("Send another message to retry intake, or use the assessment icon above.")
        if state["request_seconds"] is not None:
            st.caption(f"Total time for the last chat request: {state['request_seconds']:.1f} seconds.")
        message = st.chat_input("Describe your intended use", key=f"intake_chat_{state['case']['id']}")
        if message and message.strip():
            with chat:
                submit_message(state, message.strip(), configuration, precedents, chat)
            st.rerun()
    if assess_now:
        state["assessment_origin"] = "manual"
        state["pending_assessment"] = True
    if show_request:
        request_dialog(state)
    elif show_conversation:
        conversation_dialog(state)
    elif state["pending_assessment"]:
        assessment_dialog(state, configuration, precedents)


def render_precedents(precedents):
    st.subheader("History & Precedents")
    st.write("Each precedent is a Markdown file describing a request, a recorded decision, and the reasons. The supplied examples and human decisions are fictional.")
    st.caption(f"Add or edit .md files in {workflow.PRECEDENTS_DIR}. Changes are read on the next app rerun.")
    for precedent in precedents:
        with st.expander(precedent["title"]):
            st.caption(precedent["id"])
            st.markdown(precedent["content"])


def render_rubrics(configuration):
    st.subheader("Rubrics")
    st.write("Edit the illustrative policy guidance, scoring anchors, and blocking rules. Changes apply to subsequent assessments.")
    st.caption(f"Stored separately in {workflow.RUBRIC_PATH}.")
    rubric = deepcopy(configuration["rubric"])
    configuration_key = hashlib.sha256(json.dumps(rubric, sort_keys=True).encode()).hexdigest()[:12]
    with st.form("rubric_editor"):
        rubric["name"] = st.text_input("Rubric name", rubric["name"], key=f"name_{configuration_key}")
        rubric["version"] = st.text_input("Rubric version", rubric["version"], key=f"version_{configuration_key}")
        rubric["note"] = st.text_area("Rubric note", rubric["note"], key=f"note_{configuration_key}")
        for dimension in rubric["dimensions"]:
            with st.expander(f"{dimension['id']} · {dimension['label']}"):
                prefix = f"{configuration_key}_{dimension['id']}"
                dimension["label"] = st.text_input("Dimension label", dimension["label"], key=f"{prefix}_label")
                dimension["guidance"] = st.text_area("Guidance", dimension["guidance"], key=f"{prefix}_guidance")
                for score, anchor in enumerate(dimension["anchors"]):
                    dimension["anchors"][score] = st.text_area(f"Score {score} anchor", anchor, key=f"{prefix}_{score}")
        for rule in rubric["blocking_rules"]:
            with st.expander(f"{rule['id']} · {rule['label']}"):
                prefix = f"{configuration_key}_{rule['id']}"
                rule["label"] = st.text_input("Rule label", rule["label"], key=f"{prefix}_label")
                rule["rule"] = st.text_area("Blocking rule", rule["rule"], height=160, key=f"{prefix}_rule")
        if st.form_submit_button("Save rubric", type="primary"):
            core.validate_configuration({"rubric": rubric, "prompts": configuration["prompts"]})
            core.write_json(workflow.RUBRIC_PATH, rubric)
            st.rerun()


def render_prompts(configuration):
    st.subheader("Prompts")
    st.write("Intake, assessment, and comparison have separate instructions. Edit a prompt here or edit its Markdown file directly.")
    for name, prompt in configuration["prompts"].items():
        prompt_key = hashlib.sha256(prompt.encode()).hexdigest()[:12]
        with st.expander(name.title(), expanded=name == "intake"):
            st.caption(str(workflow.PROMPTS_DIR / f"{name}.md"))
            with st.form(f"prompt_{name}"):
                edited = st.text_area("Instructions", prompt, height=380, key=f"{name}_{prompt_key}")
                if st.form_submit_button(f"Save {name} prompt", type="primary"):
                    updated = deepcopy(configuration)
                    updated["prompts"][name] = edited
                    core.validate_configuration(updated)
                    (workflow.PROMPTS_DIR / f"{name}.md").write_text(edited.strip() + "\n", encoding="utf-8")
                    st.rerun()


def render_settings():
    st.subheader("Settings")
    st.write("Choose the model for subsequent intake, assessment, and precedent comparisons.")
    with st.form("model_settings"):
        model = st.selectbox("Model", list(workflow.MODELS), index=list(workflow.MODELS).index(selected_model()), format_func=lambda value: workflow.MODELS[value])
        if st.form_submit_button("Save settings", type="primary"):
            core.write_json(workflow.SETTINGS_PATH, {"model": model})
            st.session_state.selected_model = model
            st.success(f"Settings saved. New AI requests will use {workflow.MODELS[model]}.")
    st.caption(f"Current model: {workflow.MODELS[selected_model()]}. Existing assessments retain the model used for their run.")


def main():
    st.set_page_config(page_title="AI Governance Assistant", page_icon="◈", layout="wide")
    configuration = workflow.load_configuration()
    precedents = workflow.load_precedents()
    state = initialize_session()
    pages = [
        st.Page(lambda: render_intake(state, configuration, precedents), title="Guided Intake", url_path="intake", default=True),
        st.Page(lambda: render_precedents(precedents), title="History & Precedents", url_path="precedents"),
        st.Page(lambda: render_rubrics(configuration), title="Rubrics", url_path="rubrics"),
        st.Page(lambda: render_prompts(configuration), title="Prompts", url_path="prompts"),
        st.Page(render_settings, title="Settings", url_path="settings"),
    ]
    page = st.navigation(pages, position="top")
    page.run()


main()
