# LLM New Prompt

## Prompt Row Identity

LLM prompt rows are not created per API call.

Current prompt identity is:

- `workflow_name`
- `model_provider`
- `model`
- `prompt_version`

This means:

- the same workflow/model/version reuses the same `prompts` row
- many suggestion rows can point to the same `prompt_id`
- a new prompt row is created only when that identity changes

## Current Versioning Rule

Prompt evolution is currently driven by `PROMPT_VERSION`, not by prompt-text hashing.

Example:

- `LLM_DOCUMENT_SUGGESTION_PROMPT_VERSION = "v1"`
- later prompt change:
  - update prompt text
  - bump version to `v2`

Then:

- old suggestions remain linked to the `v1` prompt row
- new suggestions use a new `v2` prompt row

## Important Risk

If prompt text changes but `PROMPT_VERSION` is not bumped:

- the existing `prompts` row is reused
- prompt provenance becomes inaccurate
- idempotency may incorrectly treat the changed prompt as the old one

So the current contract depends on explicit version discipline.

## Current Recommendation

When prompt meaning changes:

1. update the prompt text
2. bump `PROMPT_VERSION`
3. let the service upsert a new prompt row

## Future Hardening

The next useful safeguard is a `prompt_checksum` field derived from prompt text.

That would allow:

- detection of accidental prompt drift
- stronger prompt provenance
- optional enforcement that version bumps match text changes

Current state is acceptable for development, but checksum-based validation would make the
workflow safer as prompt count and batch usage grow.
