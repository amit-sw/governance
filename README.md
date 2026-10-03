# AI Use-Case Governance Assistant

A local Streamlit sandbox for Ralph and Jeremy to refine guided intake and evidence-backed governance assessments. The rubric, historical requests, vendors, and recorded human decisions are illustrative. The app gives advisory recommendations; final human decisions remain outside it.

## Run locally

Use Python 3.12 or later. From this folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml` to contain your project API key:

```toml
OPENAI_API_KEY = "your-api-key"
```

Create the key on the [OpenAI API keys page](https://platform.openai.com/api-keys) and configure API billing for the project. A ChatGPT subscription is separate from API access. The secrets file is ignored by Git and its contents are not copied into requests or configuration. `OPENAI_API_KEY` in the environment is supported as a fallback. The key is read on each AI action.

Start the app:

```sh
streamlit run app.py --server.address 127.0.0.1
```

Open [localhost:8501](http://localhost:8501), or the local URL printed by Streamlit. If an already-running app shows a file-change notification, choose **Rerun** to load the updated interface.

The Streamlit default model is `gpt-5.6-luna`. The **Settings** page offers GPT-6.1-Sol, GPT-5.6-Terra, and GPT-5.6-Luna. Save the selected model to apply it to subsequent intake, assessment, and comparison calls. Settings are saved in `data/settings.json` and survive restarts; the selected model takes precedence over `OPENAI_MODEL`. Before settings are saved, a supported `OPENAI_MODEL` value supplies the default. Model availability depends on the API project. Browsing precedents and editing configuration do not need an API key.

## Use the five pages

- **Guided Intake:** Describe one use case in the enclosed chat, with scrollable messages and the input at the bottom. The assistant summarizes the supplied facts and asks four or five focused questions together when several facts are missing, with fewer questions when little remains. Useful questions offer labeled choices plus Other and Unknown. Correct facts by sending another message; select **Show current request** to inspect the structured facts in a dismissible modal. Unknown answers remain unanswered.
- **History & Precedents:** Read the Markdown files describing earlier requests, fictional recorded human outcomes, reasons, and conditions. Six examples include low-risk use, conditional approval, policy blockers, employment impact, and incomplete information. Two customer-email cases illustrate different outcomes for similar purposes with different vendor controls.
- **Rubrics:** Edit the six dimensions, their 0–3 scoring anchors, and illustrative blocking rules. **Save rubric** writes `rubric.json`.
- **Prompts:** Edit intake, assessment, or comparison instructions separately. Each save writes its corresponding Markdown file in `prompts/`.
- **Settings:** Choose and save the model for subsequent AI requests. Existing assessment reports keep their original model.

Intake automatically switches to **ASSESSMENT MODE** when the model considers the request sufficiently described and Python confirms that no material field, follow-up question, or reported contradiction remains unresolved. The transition is visible in the chat, then the app opens the same assessment modal used by the assessment icon. A complete high-risk proposal can proceed to assessment; completeness does not mean approval. There is no separate assessment page or final-approval action. Navigation uses `st.Page` and `st.navigation`, so only the selected page runs.

Assessment first scores the request against the current rubric, then separately compares it with the Markdown precedents. The automatic report appears in the assessment modal and includes scores, explanations, evidence, blockers, safeguards, mitigation conditions, and relevant prior cases. Reports retain the request, rubric, prompts, and matched precedent text used for that run. Changes to configuration do not silently rewrite an existing report.

**Assess input so far** opens a dismissible assessment modal and assesses the submitted information even if intake is incomplete. It does not mark the intake complete. Missing fields, unresolved dimension evidence, blocker checks, and conflicting facts are listed as information needed for a full assessment. Unknown facts remain unknown and cannot support an approval recommendation. The modal shows total assessment time; opening the current-request modal or dismissing either modal does not call the model. Each assessment-button click intentionally starts a new assessment, while interacting with an open dialog does not automatically repeat it.

Guided Intake expands to the browser content area, with message height adapting to the viewport and a bottom input. It contains the chat and a compact headline with four colorful icon buttons on the right: **Show current request**, **Assess input so far**, **Conversation so far**, and **Start over**. Hover over an icon to see its label. **Conversation so far** opens a dismissible modal containing the complete conversation in a text block with a copy icon; copying or opening the dialog makes no model call. Assessment results appear only in the modal; dismissing it returns to the chat without repeating any model calls. The input placeholder is **Describe your intended use**.

Sending a correction returns the same request to intake and replaces the current report when assessment completes again. **Start over** clears the current chat and request. There is no saved-request selector, request database, import/export workflow, or multiple-report history in the Streamlit app.

The request exists only in Streamlit session state. Normal widget reruns preserve it; a browser refresh, replaced connection, or server restart can reset it, as described in the [Streamlit session-state documentation](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state). Rubric and prompt edits are saved to files. Older `data/history.json` files are left untouched and are no longer read or written by the Streamlit app.

## Completeness and recommendation rules

Material fields cover purpose, tool and type, users and affected people, inputs and sensitivity, outputs and use, autonomy, oversight, access, sharing, retention, other safeguards, and IP permissions. Title and owner can remain Unknown. Empty values, Unknown, unsure, TBD, not known, not specified, and unexplained N/A count as unanswered. For an inapplicable field, provide a reason such as “No external sharing; outputs stay with the two named reviewers.”

The highest known dimension score determines risk. Explicit blockers override the recommendation. Otherwise missing facts, conflicts, unknown scores, or unresolved blocker checks require more information. High risk means not proceeding in the current form; medium risk requires stated mitigation conditions; negligible or low risk supports advisory approval. Historical approval or rejection never changes these rules.

## Files and functions

| File or directory | Purpose |
|---|---|
| `app.py` | Streamlit layout, chat actions, assessment progress, and configuration editors |
| `workflow.py` | Streamlit intake readiness, prompt loading, and Markdown precedent comparison |
| `core.py` | Existing SDK calls, evidence validation, and deterministic assessment rules; unchanged in this UI revision |
| `data/settings.json` | Saved model selection; no requests or credentials |
| `rubric.json` | Editable dimensions, scoring anchors, and blocking rules |
| `prompts/intake.md` | Guided conversation and readiness instructions |
| `prompts/assessment.md` | Dimension findings, evidence, and blocker instructions |
| `prompts/comparison.md` | Similarity and precedent instructions |
| `precedents/*.md` | Six fictional historical requests, decisions, reasons, and conditions |
| `evaluation_cases.json` | Existing synthetic requests for future manual evaluation |
| `colab_starter.ipynb` | Existing notebook; its workflow has not been updated yet |

The code uses ordinary functions and small Pydantic models, with no source comments or docstrings. `workflow.py` and `core.py` do not import Streamlit. The legacy `prompts.json` and `examples.json` remain available for the unchanged Colab notebook; the Streamlit app uses the Markdown prompts and precedents instead.

Add another precedent by creating a `.md` file in `precedents/` with a title and sections for **Request**, **Decision**, **Why**, and any **Conditions**. Clearly state whether it is fictional or an externally recorded human outcome. Files are read on each app rerun. For this small collection, one structured model comparison considers all precedent text and returns up to three matches, or none. Shared tool names alone do not establish equivalence.

## API actions and failures

Calls use the [Responses API with structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), `store=False`, a 60-second timeout, and no SDK retry loops. [Response storage guidance](https://developers.openai.com/api/docs/guides/migrate-to-responses#4-decide-when-to-store-state) describes the storage setting.

AI calls start only when a chat message is submitted, **Assess input so far** is selected, or a visible retry button is selected. Every model call shows a thinking spinner with elapsed time. The completed chat request shows its total time, including any automatic assessment and comparison. A successful intake review can trigger assessment and comparison in that same action. Ordinary widget reruns and page navigation do not repeat AI operations.

Python checks score ranges, known reference IDs, quoted evidence, and complete rubric coverage. Readiness also checks missing material fields independently of the model. These checks cannot establish whether every interpretation is factually correct; human review of the reasoning is still needed.

One narrow OpenAI API-error boundary preserves the in-session request and displays a retry action. A failed assessment produces no recommendation. If only the precedent comparison fails, the valid assessment stays visible and comparison can be retried independently. Structured-output validation and local file errors use ordinary Python/Streamlit errors. There are no fabricated assessments or automatic recovery loops.

## Validation status

Tests are paused at the user's request. No automated tests or live OpenAI evaluations were run for this UI revision. The core test files describe recommendation rules. UI test definitions must be aligned with the new page and modal interactions before a future authorized run.

When manual evaluation is authorized, use synthetic requests to review targeted questions, unknown facts, corrections, readiness, evidence, conflicting precedents, and materially different uses of the same tool. Ralph and Jeremy should refine the rubric and prompts based on the usefulness and consistency of those explanations.

## Colab

The notebook and its existing shared-core interfaces remain unchanged for now. It still uses the earlier confirmation, assessment, and JSON import/export workflow with `core.py`, `rubric.json`, `prompts.json`, and `examples.json`. Updating the notebook to the new chat and Markdown workflow is a separate next step.
