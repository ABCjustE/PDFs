# Taxonomy Partitioning

The taxonomy workflow is node-based.

Current stages:

1. partition one node into child categories
2. inspect the proposed document assignments for that node
3. apply selected assignments into child memberships
4. recurse on a child node if it is still broad enough

## Data Model

Core tables:

- `taxonomy_nodes`
  - tree structure
- `taxonomy_node_documents`
  - current document membership for each node
- `taxonomy_assignments`
  - reviewable document-to-child assignment decisions
- `taxonomy_node_topic_terms`
  - normalized narrower terms attached to a node (valid to review, and used for assignment prompt)

Current persistence status:

- `run-taxonomy-partition` persists child nodes
- `run-taxonomy-assign` persists assignment rows
- `apply-taxonomy-assignments` mutates `taxonomy_node_documents`
- `taxonomy_node_topic_terms` is populated from partition generalization output and used in assignment prompts

## Partition Mechanism

Partitioning is a two-stage LLM flow.

Stage 1: proposal

- sample one or more batches from the target node's current memberships
- each batch prompt returns JSON with:
  - `categories`
  - `supporting`
- `categories` are broad category names
- `supporting` is a list of narrower topic groups, for example:

```json
{
  "categories": ["Computer Science", "Mathematics"],
  "supporting": [
    {
      "category": "Computer Science",
      "topics": ["Data Structures", "Algorithms"]
    },
    {
      "category": "Mathematics",
      "topics": ["Linear Algebra", "Calculus"]
    }
  ]
}
```

Stage 2: generalize

- merge the proposal JSONs from several batches
- return one final JSON in the same shape:
  - `categories`
  - `supporting`
- `category_limit` controls breadth:
  - smaller limit -> broader categories
  - larger limit -> keep more distinction

`run-taxonomy-partition` uses the final `categories` to create child nodes.

## Partition Commands

Probe proposal batches only:

```bash
python client.py probe-taxonomy-partition --node-path Root --chunk-size 50 --batch-offset 0 --batch-count 1 --category-limit 10
```

Probe proposal plus merged result:

```bash
python client.py probe-taxonomy-partition-generalize --node-path Root --chunk-size 50 --batch-offset 0 --batch-count 3 --category-limit 10
```

Persist a node partition:

```bash
python client.py run-taxonomy-partition --node-path Root --chunk-size 500 --batch-offset 0 --batch-count 7 --category-limit 10
```

Shared partition flags:

- `--node-path`
- `--chunk-size`
- `--batch-offset`
- `--batch-count`
- `--category-limit`
- repeated `--exclude-path-keyword`

Path-keyword exclusions are applied before batching. `PDFZX_TAXONOMY_EXCLUDE_PATH_KEYWORDS` provides a soft default list, and repeated CLI flags override that default list for the current command. Example:

```bash
python client.py probe-taxonomy-partition --node-path Root --exclude-path-keyword lectures --exclude-path-keyword archive --exclude-path-keyword inbox --exclude-path-keyword misc
```

`run-taxonomy-partition` behavior:

- if `Root` does not exist, it creates `Root`, syncs all documents into it, and exits
- otherwise it runs proposal batches, runs generalize, and persists child nodes
- rerunning a node replaces the existing child subtree under that node

## Assignment Commands

Probe assignment decisions without writing:

```bash
python client.py probe-taxonomy-assign --node-path Root --limit 10 --offset 0 --exclude-path-keyword lectures --exclude-path-keyword archive
```

Persist pending assignment rows:

```bash
python client.py run-taxonomy-assign --node-path Root --require-digital --require-toc --limit 100 --offset 0 --max-concurrency 5 --exclude-path-keyword lectures --exclude-path-keyword archive
```

Inspect readable assignment rows:

```bash
python client.py show-taxonomy-assignments --node-path Root --status pending --limit 50 --offset 0
```

Apply high-confidence assignments:

```bash
python client.py apply-taxonomy-assignments --node-path Root --minimum-confidence high --exclude-path-keyword lectures --exclude-path-keyword archive --exclude-path-keyword inbox --exclude-path-keyword misc
```

Assignment behavior:

- assignment uses the node's existing child labels as allowed child targets
- assignment also includes child topic terms to clarify similar child labels
- the prompt may also decide a document should stay at the current node
- `run-taxonomy-assign` writes `taxonomy_assignments` with `status="pending"` for `child` decisions
- `stay` decisions are also persisted so later runs skip them by default
- persisted `stay` decisions use `status="rejected"` with no assigned child
- `--force` re-requests and overwrites existing assignment rows
- existing rows are skipped by default
- `--output-ndjson` writes durable per-item progress
- repeated `--exclude-path-keyword` values are applied before probing or assignment runs
- `PDFZX_TAXONOMY_EXCLUDE_PATH_KEYWORDS` provides the default shared exclude list for partition, assignment, and apply workflows unless CLI exclusions are passed

Apply behavior:

- only qualifying pending rows are applied
- applied documents move from the parent node membership to the assigned child node membership
- assignment status changes from `pending` to `applied`
- excluded path keywords are skipped and left untouched

Shared exclusion behavior:

- `probe-taxonomy-partition`
- `probe-taxonomy-partition-generalize`
- `run-taxonomy-partition`
- `probe-taxonomy-assign`
- `run-taxonomy-assign`
- `apply-taxonomy-assignments`
- all of these commands accept repeated `--exclude-path-keyword`
- if no CLI exclusions are passed, they fall back to `PDFZX_TAXONOMY_EXCLUDE_PATH_KEYWORDS`

## Inspection Commands

Show direct membership counts per node:

```bash
python client.py show-taxonomy-node-stats --depth 1
```

Show documents under one node:

```bash
python client.py show-taxonomy-node-documents --node-path 'Root/Physics' --limit 50 --offset 0
```

## Typical Operator Loop

Example for one node:

```bash
python client.py run-taxonomy-partition --node-path 'Root/Computer Science'
python client.py run-taxonomy-assign --node-path 'Root/Computer Science' --limit 100 --offset 0 --max-concurrency 5 --exclude-path-keyword lectures --exclude-path-keyword archive
python client.py show-taxonomy-assignments --node-path 'Root/Computer Science' --status pending --limit 50 --offset 0
python client.py apply-taxonomy-assignments --node-path 'Root/Computer Science' --minimum-confidence high
python client.py show-taxonomy-node-stats --depth 2
```

## Manual Adjustment

After `run-taxonomy-partition`, child nodes are created in `taxonomy_nodes`.

Before assignment, it is valid to adjust those child nodes manually, for example:

- add a missing child node
- rename a child node
- delete an unwanted child node

That manual review step is often useful before running assignment on a new node.
