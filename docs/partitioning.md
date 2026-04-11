`taxonomy_partitioning` is currently a partial persisted workflow:

- root/node bootstrap exists
- generalized child-node creation exists
- document-to-child assignment is not implemented yet

## What Is Implemented

Deterministic batching:

- [pdfzx/src/pdfzx/partitioning/sampler.py](../pdfzx/src/pdfzx/partitioning/sampler.py)
  - `seeded_shuffle(items, seed=...)`
  - `chunk_items(items, chunk_size=...)`

Batch accumulation prompt:

- [pdfzx/src/pdfzx/prompts/taxonomy_partition_proposal.py](../pdfzx/src/pdfzx/prompts/taxonomy_partition_proposal.py)
  - takes one shuffled chunk of document summaries
  - returns an accumulated candidate taxonomy bag
  - keeps `sha256` in Python-side summaries for traceability
  - strips `sha256` before sending the prompt payload to the model

Batch accumulation runner:

- [pdfzx/src/pdfzx/partitioning/proposal.py](../pdfzx/src/pdfzx/partitioning/proposal.py)
  - `propose_taxonomy_bags(...)`

Final generalization prompt:

- [pdfzx/src/pdfzx/prompts/taxonomy_partition_generalize.py](../pdfzx/src/pdfzx/prompts/taxonomy_partition_generalize.py)
  - takes accumulated categories plus counts
  - collapses them into a compact parent-layer bag

Final generalization runner:

- [pdfzx/src/pdfzx/partitioning/generalize.py](../pdfzx/src/pdfzx/partitioning/generalize.py)
  - `generalize_taxonomy_bag(...)`

Client probes:

- [client.py](../client.py)
  - `probe-taxonomy-partition`
  - `probe-taxonomy-partition-generalize`
  - `run-taxonomy-partition`

Tree persistence:

- [pdfzx/src/pdfzx/db/models.py](../pdfzx/src/pdfzx/db/models.py)
  - `TaxonomyNode`
  - `TaxonomyNodeDocument`
  - `TaxonomyAssignment`

- [pdfzx/src/pdfzx/db/repositories/taxonomy_tree.py](../pdfzx/src/pdfzx/db/repositories/taxonomy_tree.py)
  - `ensure_root_node(...)`
  - `sync_root_documents(...)`
  - `ensure_child_node(...)`
  - membership and assignment CRUD helpers

## Commands

Bootstrap root only:

```bash
python client.py bootstrap-taxonomy-root
```

Probe accumulation only:

```bash
python client.py probe-taxonomy-partition --chunk-size 20 --batch-index 0 --batch-count 3 --carry-bag
```

Probe accumulation plus final generalization:

```bash
python client.py probe-taxonomy-partition-generalize --chunk-size 500 --batch-index 0 --batch-count 7
```

Run persisted node partitioning:

```bash
python client.py run-taxonomy-partition --node-path Root --chunk-size 500 --batch-index 0 --batch-count 7
```

`run-taxonomy-partition` behavior:

- if `Root` does not exist, it creates `Root`, syncs all current document hashes into it, and exits
- rerun the same command after bootstrap to execute the LLM partition flow
- successful runs persist child `TaxonomyNode` rows under the target parent node
- no document assignment is written yet

Shared partition args:

- `--chunk-size`
- `--batch-index`
- `--batch-count`
- `--bag`
- `--bag-size-limit`
- `--carry-bag`

`run-taxonomy-partition` also takes:

- `--node-path`

## Current Workflow

The current probing flow is:

1. load document `sha256`s from SQLite
2. apply `PDFZX_PARTITION_SEED`
3. split by `PDFZX_PARTITION_CHUNK_SIZE` or `--chunk-size`
4. run one or more accumulation batches
5. optionally carry the accumulated bag forward
6. count candidate category outputs
7. run final generalization over those counts

The current persisted run adds one more step:

8. create child nodes under the target parent from the generalized taxonomy bag

This is enough to test top-layer discovery and persist child nodes, but not enough to recursively partition documents yet.

## What Improved

The earlier one-stage prompt tended to produce narrow local outputs such as:

- `Physics Solutions`
- `Quantum Mechanics`
- `Mathematics Analysis`

That was not suitable for a parent layer.

The current two-stage design improved this by separating:

- batch-local accumulation
- final collapse/generalization

In practice, larger probes with more coverage produced a more useful generalized bag.

## Practical Result

For a collection of roughly `4k` documents, a run using:

- chunk size `200`
- batch count `10`

gave a noticeably more representative parent-layer taxonomy than small local probes.

That means the current implementation is useful for:

- exploratory top-layer category discovery
- prompt iteration
- checking stability across seeds

## What Is Not Implemented Yet

Missing pieces:

- prompt-driven document assignment into child nodes
- persistence of `TaxonomyAssignment` rows from an assignment workflow
- recursive partitioning of child nodes as a higher-level orchestration flow

## Tree Model

Implemented tables:

### `taxonomy_nodes`

- `id`
- `parent_id`
- `name`
- `path`
- `depth`
- `status`

### `taxonomy_node_documents`

- `node_id`
- `sha256`

Composite key:

- `(node_id, sha256)`

### `taxonomy_assignments`

- `node_id`
- `sha256`
- `assigned_child_id`
- `confidence`
- `status`

Suggested `status` values:

- `pending`
- `applied`
- `rejected`
- `manual_touched`

## Why The Composite Key Is Enough

Taxonomy identity is per canonical document, not per path.

If several files share the same `sha256`, they are the same document for taxonomy purposes.

So:

- no complex identity key is needed
- `(node_id, sha256)` is the natural composite key for both membership and assignment

## Recommended Next Step

The next backend milestone is:

- implement one-by-one document assignment from a parent node into its existing child nodes

That should write `TaxonomyAssignment` rows first, before mutating child memberships.
