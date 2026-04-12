# Phase Flow

## Phase 1

```mermaid
sequenceDiagram
    participant Client as client.py scan
    participant Job as InventoryJob
    participant FS as PDF files
    participant Inv as inventory.py
    participant Reg as registry.py
    participant DB as SqliteStorage

    Client->>Job: run(targets)
    Job->>Job: resolve file and directory targets
    Job->>FS: stream selected PDFs
    loop each PDF
        Job->>Inv: extract hash, metadata, ToC, OCR/digital signals
        Inv-->>Job: DocumentRecord + FileStatRecord
    end
    Job->>Reg: merge scanned records
    Reg-->>Job: JobRecord
    Job->>DB: save Registry snapshot to SQLite
    DB-->>Client: persisted documents, file_stats, jobs
```

Phase 1 is offline only. It computes deterministic records from the filesystem and writes the
merged registry to SQLite. JSON is import/export only.

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

Phase 2 is online and prompt-driven. The scanned Phase 1 document stays canonical. LLM outputs
are stored as separate suggestion rows with prompt provenance and review/apply state.
