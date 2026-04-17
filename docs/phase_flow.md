# Phase Flow

## Phase 1

```mermaid
sequenceDiagram
    participant Client as client.py scan
    participant Job as InventoryJob
    participant FS as PDF files
    participant Inv as inventory.py
    participant Reg as registry.py
    participant Store as SqliteStorage
    participant DB as SQLite

    Client->>Job: run(targets)
    Job->>Job: resolve PDF paths under root
    Job->>FS: read selected PDFs
    loop each PDF
        Job->>Inv: process_pdf(path, root, config)
        Inv-->>Job: DocumentRecord
    end
    Job->>Reg: merge(records, paths, root, job_id)
    Reg-->>Job: updated Registry + ScanJobRecord
    Job->>Store: save(registry)
    Store->>DB: rewrite current Phase 1 state
```

Phase 1 is an offline batch scan.
Its current persistence model is SQLite-backed, but the merge still happens through the in-memory
`Registry` contract.

Current Phase 1 state split:

- canonical document state
  - `documents`
  - `document_paths`
  - `document_toc`
- batch scan state
  - `scanned_file_in_job`
  - `scan_jobs`

Practical meaning:

- `document_paths` answers which relative paths currently belong to a document
- `scanned_file_in_job` answers what the last scan run saw at a path
- legacy JSON key for that scan-state map: `file_stats`

`db.json` is not the normal write target anymore.
It is retained only for import/export and compatibility.

## Phase 2

```mermaid
sequenceDiagram
    participant Client as client.py probe-llm / probe-taxonomy-* / run-taxonomy-*
    participant DB as SQLite
    participant WF as LLM workflow
    participant PR as PromptRepository
    participant SR as SuggestionRepository
    participant API as OpenAI API

    Client->>DB: load Document by sha256
    Client->>WF: build prompt input
    WF->>PR: upsert prompt(workflow, model, version)
    WF->>SR: find existing suggestion by (sha256, prompt_id)
    alt existing suggestion and not --force
        SR-->>Client: skip API request
    else request needed
        WF->>API: send structured prompt payload
        API-->>WF: validated structured response
        opt --persist
            WF->>SR: save suggestion row
        end
        WF-->>Client: prompt_input + parsed_response
    end
```

Phase 2 is online and prompt-driven.
It consumes Phase 1 document state from SQLite and stores prompt-backed suggestions separately from
the canonical scanned document record.
