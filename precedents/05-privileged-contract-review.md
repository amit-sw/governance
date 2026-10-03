# Privileged contract review in a public chatbot

Synthetic example. The request, vendor, reviewer, and human decision below are fictional.

## Request

Two legal staff want CounselChat, an AI-enabled public chatbot, to summarize company-owned contracts and counsel's privileged negotiation notes. The summaries would remain inside the legal team. A lawyer would compare every summary with the source before using it; the tool could not send messages, negotiate, sign, or change contracts.

The inputs include confidential commercial terms and privileged legal communications. The fictional public vendor is explicitly unapproved for these inputs and may retain them for training without company permission. Individual password-protected accounts provide access, but the team has no control over vendor deletion or reuse. Local summaries would be deleted after the matter closes. The company owns the documents but has not permitted the vendor's training use. There are no additional disclosure controls beyond lawyer review of the output.

## Decision

**Rejected** by a fictional human reviewer on 2026-09-18, under the illustrative starter rubric, version 0.1.

## Why

B1 applies to privileged and confidential material sent to an explicitly unsuitable vendor. Confidentiality and vendor exposure are high (D1, D2). Lawyer review may help identify summary errors (D5), but it cannot undo disclosure of the inputs. Company ownership does not itself authorize every reuse of those inputs (D6).

## Conditions for reconsideration

Use a tool expressly suitable for this data and permitted purpose with defined retention and training restrictions, or restrict a demonstration to synthetic contracts and notes. Document the handling controls before reconsideration.
