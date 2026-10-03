# User Tutorial

Describe one intended use of AI, answer a few questions, and review an advisory risk assessment. The assistant helps you identify risks and missing information. Final decisions remain with your human reviewers; the starter rubric is illustrative.

The screenshots follow one example conversation. Your questions and scores will depend on your answers. Every screenshot is open by default inside a bordered frame. You can collapse a screenshot if you want to skim the instructions.

## 1. Start a conversation

Choose **Guided Intake** in the top navigation. Type into **Describe your intended use** at the bottom of the chat, then select the send arrow.

Explain the problem you want to solve, the AI tool you plan to use, and what it will do. You do not need all the details to begin.

Try this fictional example while learning:

> I want to use an AI tool to turn meeting transcripts into summaries and action items. It sends drafts only to me. I check them before sharing, and it cannot take other actions.

The assistant summarizes your request and usually asks four or five questions together when several details are missing. Answer in one message. You can choose its suggested options, describe another answer, or say **Unknown**.

For example: **1: B. 2: Only my team. 3: Unknown.** Describe the facts that are true for your own use case; do not guess at vendor terms or permissions.

![Guided Intake — an opening request, five questions, and a numbered reply](screenshots/Screenshot%202026-10-02%20at%206.01.45%E2%80%AFPM.png)

While the assistant reviews your answers, keep the chat open. The spinner shows that it is working and displays elapsed time.

![Reviewing answers — follow-up questions, the thinking indicator, and the input box](screenshots/Screenshot%202026-10-02%20at%206.04.11%E2%80%AFPM.png)

## 2. Get to know the four icons

These small buttons appear to the right of **AI Use-Case Assistant**. Hover over one to see its label.

| Button | What it does |
|---|---|
| Blue document — **Show current request** | Opens the structured facts and supporting messages. Check that the assistant understood you correctly. |
| Green checklist — **Assess input so far** | Starts an assessment of the information submitted so far, even if some details are unknown. |
| Purple conversation — **Conversation so far** | Opens the complete conversation. Use the copy icon at the top right of the text block to copy it elsewhere. |
| Orange restart — **Start over** | Clears the current conversation and request so you can begin again. Copy anything you need first. |

Close a dialog with **Close** or its **×** to return to the chat. Viewing the current request or conversation makes no AI call.

## 3. Read your assessment

When the request is sufficiently described, the chat shows **Intake complete → switching to ASSESSMENT** and opens the assessment dialog automatically. You can also select the green checklist whenever you want a partial assessment.

During AI work, a thinking indicator shows elapsed time. The completed request shows the total time taken.

![Assessment in progress — the dialog stays open while precedents are compared](screenshots/Screenshot%202026-10-02%20at%206.06.43%E2%80%AFPM.png)

In the report, look at:

- **Recommendation and overall risk:** the assistant's advisory outcome.
- **Dimension scores:** 0 negligible, 1 low, 2 medium, 3 high, or Unknown.
- **Information needed for a full assessment:** the facts still required. Unknown does not mean low risk and can prevent an approval recommendation.
- **Blockers and proposed conditions:** reasons not to proceed or safeguards to consider. Proposed safeguards are not treated as already implemented.
- **Evidence and related precedents:** supporting request facts and comparable earlier cases. The supplied historical decisions are fictional and do not automatically determine your outcome.

In this example, **Obtain more information** appears alongside **Unresolved (known risk: Medium)**. Some risks can be scored, but the remaining uncertainties still prevent an approval recommendation.

![Assessment overview — advisory recommendation, known risk, and dimension scores](screenshots/Screenshot%202026-10-02%20at%206.07.12%E2%80%AFPM.png)

Scroll down within the assessment dialog to find **Information needed for a full assessment**. These questions tell you what to provide next. A blocker marked **unknown** means it still needs clarification, not that it has been ruled out.

![Missing information — follow-up questions and an unresolved blocker](screenshots/Screenshot%202026-10-02%20at%206.07.22%E2%80%AFPM.png)

Keep **Existing safeguards** separate from **Proposed conditions and mitigations**. The former describes supplied facts; the latter lists actions to consider or arrange.

![Safeguards and mitigations — supplied controls, supporting facts, and proposed conditions](screenshots/Screenshot%202026-10-02%20at%206.07.30%E2%80%AFPM.png)

For each related precedent, read both **Similarities** and **Differences**. Open its **Read…** panel to see the original example. A similar use case is context, not an automatic approval.

![Related precedents — comparisons explaining similarities and important differences](screenshots/Screenshot%202026-10-02%20at%206.07.43%E2%80%AFPM.png)

## 4. Correct or complete your request

Close the assessment dialog and send another chat message to add missing details or correct a misunderstanding. Be explicit, for example: **Correction: the tool sends drafts only to me; it does not email anyone else.**

The assistant reviews the updated request. A complete request can still have high risk; completeness is not approval.

If the assistant shows **Facts to clarify**, answer those points explicitly. In this example it asks the user to distinguish access within their organization from the vendor's processing access, and to describe the actual controls.

![Clarifying the request — ambiguous facts, targeted questions, and the user's answers](screenshots/Screenshot%202026-10-02%20at%206.06.00%E2%80%AFPM.png)

Even after intake is complete, the assessment may identify more detailed information it needs. Return to the chat and answer the report's questions, then select **Assess input so far** again when ready.

## 5. Explore the other pages

**History & Precedents** contains example requests, decisions, and reasons. **Rubrics** explains the scoring criteria and blockers. **Prompts** contains the assistant's instructions. Rubrics and prompts can be edited and saved when you want to refine this prototype.

On **History & Precedents**, open an example to read its request, recorded outcome, and reasoning.

![History and Precedents — six fictional examples you can open and read](screenshots/Screenshot%202026-10-02%20at%206.08.03%E2%80%AFPM.png)

On **Rubrics**, expand a dimension or blocker to inspect its guidance. If you change it, select **Save rubric**. You do not need to edit the rubric to use the chat.

![Rubrics — editable criteria, blocking rules, and the Save rubric button](screenshots/Screenshot%202026-10-02%20at%206.08.22%E2%80%AFPM.png)

On **Prompts**, open Intake, Assessment, or Comparison to read its instructions. Save an edited prompt with its own save button. These are separate from your use-case conversation.

![Prompts — separate instruction editors and their save buttons](screenshots/Screenshot%202026-10-02%20at%206.08.35%E2%80%AFPM.png)

In **Settings**, choose a model and select **Save settings**. The default is GPT-5.6-Luna. Changes apply to later AI requests; existing reports retain the model used for their run.

![Settings — the model selector, Save settings, and the currently selected model](screenshots/Screenshot%202026-10-02%20at%206.08.44%E2%80%AFPM.png)

## 6. If a step does not finish

Your conversation stays available in the current session. Use **Retry last message**, **Retry assessment**, or **Retry precedent comparison** as offered. You do not need to retype your answers. If the message asks for an API key or quota change, contact the app owner; an unavailable model can be changed in Settings.

The app keeps one active request. Switching pages preserves the conversation, but refreshing the browser or restarting the app can clear it. Copy **Conversation so far** before leaving if you want to keep your work.
