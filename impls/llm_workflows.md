# LLM Workflows — Current Backend State

## Overview

The backend now has three parallel LLM workflows:

1. document suggestion
2. taxonomy suggestion
3. ToC review suggestion

All three share the same architecture:

- prompt contract
- relational prompt persistence
- `(sha256, prompt_id)` duplicate gate
- single-document probe flow

They differ only in:

- prompt text
- allowed prompt input
- structured response schema
- suggestion table and repository

## Shared Architecture

Implemented in:

- [prompt_backed_suggestion.py](../pdfzx/src/pdfzx/db/services/prompt_backed_suggestion.py)
- [base.py](../pdfzx/src/pdfzx/llm/workflows/base.py)

Current split:

- shared service layer
  - prompt registration
  - duplicate gate
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

Current reusable objects:

- `PromptBackedSuggestionService`
- `SuggestionDecision`
- `PromptWorkflowDefinition`
- `probe_prompt_workflow(...)`
- `ProbeSuggestionResult`

## Workflow 1 — Document Suggestion

Implemented in:

- [llm_document_suggestion.py](../pdfzx/src/pdfzx/prompts/llm_document_suggestion.py)
- [document_suggestions.py](../pdfzx/src/pdfzx/db/repositories/document_suggestions.py)
- [llm_document_service.py](../pdfzx/src/pdfzx/db/services/llm_document_service.py)
- [document_suggestion.py](../pdfzx/src/pdfzx/llm/workflows/document_suggestion.py)
- [llm_suggestion.py](../pdfzx/src/pdfzx/llm_suggestion.py)

Purpose:

- suggest a conservative rename-oriented file name
- separate author, publisher, and edition hints
- attach small labels

Probe command:

- `probe-llm`

## Workflow 2 — Taxonomy Suggestion

Implemented in:

- [llm_taxonomy_suggestion.py](../pdfzx/src/pdfzx/prompts/llm_taxonomy_suggestion.py)
- [taxonomy_suggestions.py](../pdfzx/src/pdfzx/db/repositories/taxonomy_suggestions.py)
- [llm_taxonomy_service.py](../pdfzx/src/pdfzx/db/services/llm_taxonomy_service.py)
- [taxonomy_suggestion.py](../pdfzx/src/pdfzx/llm/workflows/taxonomy_suggestion.py)
- [llm_taxonomy.py](../pdfzx/src/pdfzx/llm_taxonomy.py)

Purpose:

- classify one taxonomy path from the allowed tree
- classify document type
- optionally suggest one missing subcategory

Probe command:

- `probe-taxonomy`

## Workflow 3 — ToC Review Suggestion

Implemented in:

- [llm_toc_review_suggestion.py](../pdfzx/src/pdfzx/prompts/llm_toc_review_suggestion.py)
- [toc_review_suggestions.py](../pdfzx/src/pdfzx/db/repositories/toc_review_suggestions.py)
- [llm_toc_review_service.py](../pdfzx/src/pdfzx/db/services/llm_toc_review_service.py)
- [toc_review_suggestion.py](../pdfzx/src/pdfzx/llm/workflows/toc_review_suggestion.py)
- [llm_toc_review.py](../pdfzx/src/pdfzx/llm_toc_review.py)

Purpose:

- judge whether the extracted ToC is structurally usable
- judge whether the ToC matches the document topic
- identify a likely preface or front-matter page when possible

Probe command:

- `probe-toc-review`

## Prompt Persistence And Idempotency

Implemented in:

- [models.py](../pdfzx/src/pdfzx/db/models.py)
- [prompts.py](../pdfzx/src/pdfzx/db/repositories/prompts.py)

Prompt rows are shared across many suggestion rows.

Current prompt identity is:

- `workflow_name`
- `model_provider`
- `model`
- `prompt_version`

Current gating rule:

- if a suggestion already exists for the same document and prompt, do not request again

This means the backend can answer:

- "for this document and this exact prompt version, should the API be called at all?"

before any online request is sent.

## Probe Flow

Current probe commands:

- `probe-llm`
- `probe-taxonomy`
- `probe-toc-review`

Current behavior:

- load one document from SQLite by `sha256`
- respect `PDFZX_ONLINE_FEATURES`
- require `PDFZX_OPENAI_API_KEY`
- skip the API call by default if the same document already has a suggestion for the same prompt
- `--force` bypasses the duplicate gate
- `--persist` stores the validated suggestion row into SQLite

This split is intentional:

- probe commands are for prompt verification and schema inspection
- batch commands remain separate work

## Shared Suggestion Lifecycle

All suggestion tables now share the same lifecycle fields through ORM mixin
`PromptSuggestionMixin`:

- `reasoning_summary`
- `status`
- `applied`
- `created_at`
- `updated_at`

This keeps review/apply semantics consistent across workflows.

## Not Implemented Yet

- batch LLM commands
- persistence of invalid/error suggestion attempts
- review/apply UI
- prompt checksum enforcement

## Verified

Focused tests currently prove:

- prompt upsert reuses the same prompt identity
- storing a suggestion for a document makes the next same-prompt request ineligible
- missing documents are rejected
- prompt inputs are built correctly for all three workflows
- persisted probe results cause later same-prompt probes to skip the API call
