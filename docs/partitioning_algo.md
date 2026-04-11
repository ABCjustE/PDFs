`taxonomy_partitioning` is currently an experimental two-stage LLM workflow for finding a sensible
top-layer taxonomy over a large PDF collection.

The current implementation is intentionally simple:

- read all document `sha256`s from SQLite
- apply a stable seeded shuffle
- split into fixed-size chunks
- run an accumulation prompt over one or more consecutive chunks
- optionally carry the accumulated bag forward across chunks
- count the accumulated category outputs
- run a final generalization prompt that collapses those candidates into a parent-layer bag

## Current Code

Deterministic ordering and chunking:

- [pdfzx/src/pdfzx/partitioning/sampler.py](../pdfzx/src/pdfzx/partitioning/sampler.py)
  - `seeded_shuffle(items, seed=...)`
  - `chunk_items(items, chunk_size=...)`

Accumulation-stage prompt:

- [pdfzx/src/pdfzx/prompts/taxonomy_partition_proposal.py](../pdfzx/src/pdfzx/prompts/taxonomy_partition_proposal.py)
  - batch-local category accumulation
  - broad candidate categories, not final collapse

Accumulation-stage prompt runner:

- [pdfzx/src/pdfzx/partitioning/proposal.py](../pdfzx/src/pdfzx/partitioning/proposal.py)
  - `propose_taxonomy_bags(...)`

Final generalization prompt:

- [pdfzx/src/pdfzx/prompts/taxonomy_partition_generalize.py](../pdfzx/src/pdfzx/prompts/taxonomy_partition_generalize.py)
  - collapse overlapping candidates into a parent-layer bag
  - can keep `Others` for minority topics

Final generalization runner:

- [pdfzx/src/pdfzx/partitioning/generalize.py](../pdfzx/src/pdfzx/partitioning/generalize.py)
  - `generalize_taxonomy_bag(...)`

Client probes:

- [client.py](../client.py)
  - `probe-taxonomy-partition`
  - `probe-taxonomy-partition-generalize`

## Why The Two Stages Matter

The earlier one-stage prompt was too chunk-local. It tended to output narrow or unstable labels such as:

- `Physics Solutions`
- `Quantum Mechanics`
- `Mathematics Analysis`

That is not a good parent-layer taxonomy. The model was trying to both:

- notice local chunk structure
- decide the final broad taxonomy

in the same call.

The current design separates those jobs:

1. accumulation
- collect candidate categories from representative chunks
- allow some redundancy
- bias toward broad umbrellas, but do not force final collapse yet

2. generalization
- look at the accumulated candidate set and counts
- merge near-duplicates
- generalize narrow descendants upward
- keep `Others` for minority categories when needed

## Prompt Payload Notes

For partition accumulation, the Python-side summary keeps `sha256` for traceability, but the prompt
serializer strips it before sending the request to the model.

That logic is in:

- [pdfzx/src/pdfzx/prompts/taxonomy_partition_proposal.py](../pdfzx/src/pdfzx/prompts/taxonomy_partition_proposal.py)

This keeps debugging and local verification possible without wasting prompt space on document hashes.

## Practical Guidance

Small probes are useful for debugging prompt behavior.

Examples:

- one chunk
- a few consecutive chunks
- with or without carry-forward bag state

But for a meaningful parent-layer taxonomy over a collection with thousands of documents, the probes
need more coverage.

Observed tradeoff:

- small chunk count and small chunk size
  - cheaper
  - more local overfitting
  - more unstable narrow categories

- larger chunk size and more consecutive chunks
  - higher token cost
  - better coverage
  - more representative parent-layer categories

In practice, a larger run such as:

- chunk size `200`
- batch count `10`

produced a much more reasonable generalized bag for a roughly `4k` document collection.

So the current recommendation is:

- use small probes to debug the prompts
- use larger representative runs when the goal is to draft a serious top-layer taxonomy

## Current Limitation

This is still a chunk-based approximation. The accumulation prompt only sees chunk-local evidence and
the carried bag, not the entire collection at once.

So this is best treated as:

- a practical exploratory workflow
- not yet a final authoritative taxonomy builder

The next quality check is stability across seeds:

- rerun the same generalization probe with a different `PDFZX_PARTITION_SEED`
- compare whether the final broad taxonomy remains mostly the same

If it stays similar across seeds, the parent-layer taxonomy is likely capturing real structure rather
than one shuffle artifact.
