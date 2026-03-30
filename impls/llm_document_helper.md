# LLM Document Helper — Current Backend State

## Implemented

The backend contract now has three layers for document suggestions:

1. prompt contract
2. relational persistence
3. idempotency gate
4. single-document probe flow

The first workflow now also sits on a shared LLM workflow architecture instead of a
document-specific probe implementation.

No OpenAI API call orchestration is implemented yet.

## Shared Workflow Architecture

Implemented in:

- [prompt_backed_suggestion.py](../pdfzx/src/pdfzx/db/services/prompt_backed_suggestion.py)
- [base.py](../pdfzx/src/pdfzx/llm/workflows/base.py)
- [document_suggestion.py](../pdfzx/src/pdfzx/llm/workflows/document_suggestion.py)

Current split:

- shared service layer
  - prompt registration
  - `(sha256, prompt_id)` duplicate gate
  - response persistence against an existing document
- shared probe runner
  - load document from SQLite
  - build structured prompt input
  - call OpenAI structured output
  - optionally persist validated response
- workflow definition
  - system prompt
  - input builder
  - user-prompt serializer
  - response model
  - workflow-specific service wiring

This means `document suggestion` is now the first concrete implementation of a reusable
workflow pattern rather than a one-off path.

Why this matters:

- taxonomy suggestion can reuse the same probe/batch skeleton
- ToC review suggestion can reuse the same probe/batch skeleton
- prompt/version gating stays uniform across workflows
- future batch commands can share the same orchestration style

Current reusable objects:

- `PromptBackedSuggestionService`
- `SuggestionDecision`
- `PromptWorkflowDefinition`
- `probe_prompt_workflow(...)`
- `ProbeSuggestionResult`

## Prompt Contract

Implemented in:

- [llm_document_suggestion.py](../pdfzx/src/pdfzx/prompts/llm_document_suggestion.py)

Current contract:

- input uses only basic document facts
- excludes ToC
- excludes full text
- strict structured response schema is defined before any API code

Key objects:

- `LlmDocumentSuggestionPromptInput`
- `LlmDocumentSuggestionResponse`
- `LLM_DOCUMENT_SUGGESTION_SYSTEM_PROMPT`
- `LLM_DOCUMENT_SUGGESTION_PROMPT_VERSION = "v1"`

## Relational Persistence

Implemented in:

- [models.py](../pdfzx/src/pdfzx/db/models.py)
- [prompts.py](../pdfzx/src/pdfzx/db/repositories/prompts.py)
- [document_suggestions.py](../pdfzx/src/pdfzx/db/repositories/document_suggestions.py)

Current persistence shape:

- `prompts`
- `llm_document_suggestions`

Key decision:

- suggestions link to `prompt_id`
- idempotency is therefore based on `(sha256, prompt_id)`

This is cleaner than using ad hoc `(sha256, model, prompt_version)` logic everywhere.

## Idempotency Gate

Implemented in:

- [llm_document_service.py](../pdfzx/src/pdfzx/db/services/llm_document_service.py)

Current service:

- `LlmDocumentSuggestionService`

Capabilities:

- ensure active prompt record exists
- decide whether an API request should be sent for a document
- store validated response into `llm_document_suggestions`

Current gating rule:

- if a suggestion already exists for the same document and prompt, do not request again

Decision object:

- `SuggestionDecision`
  - `should_request`
  - `reason`
  - `prompt_id`

## What This Means

The backend can now answer the key workflow question before any online call:

- "for this document and this prompt version, should the API be called at all?"

That avoids repeated spend and repeated unstable output.

## Single-Document Probe

Implemented in:

- [llm_suggestion.py](../pdfzx/src/pdfzx/llm_suggestion.py)
- [client.py](../client.py) via `probe-llm`

Purpose:

- verify prompt input/output on one document before batch mode
- inspect the exact prompt payload sent to the model
- inspect the validated structured response
- optionally persist that one result

Current behavior:

- loads one document from SQLite by `sha256`
- respects `PDFZX_ONLINE_FEATURES`
- requires `PDFZX_OPENAI_API_KEY`
- skips the API call by default if the same document already has a suggestion for the same prompt
- `--force` can bypass that gate
- `--persist` can store the validated result into SQLite

This split is intentional:

- `probe-llm` is for prompt verification
- batch `suggest-llm` is still deferred

## Not Implemented Yet

- OpenAI client call
- batch `suggest-llm` command
- response validation cleanup layer beyond strict schema
- persistence of invalid/error suggestion attempts
- human review/apply flow

## Verified

Focused tests currently prove:

- prompt upsert reuses the same prompt identity
- storing a suggestion for a document makes the next request ineligible
- storing a suggestion for a missing document is rejected
- a one-document probe builds prompt input correctly
- a persisted probe result causes the next same-prompt probe to skip the API call
