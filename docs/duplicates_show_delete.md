# Duplicate Documents

This note covers the two operator commands for inspecting duplicate documents and deleting duplicate paths.

## Meaning

A duplicate document here means:

- one `sha256`
- more than one row in `document_paths`

This is path duplication for the same canonical document identity. It is not based on file name, ToC, or digital-only filtering.

## Show Duplicates

Use:

```bash
uv run python client.py show-duplicate-docs
```

Optional paging:

```bash
uv run python client.py show-duplicate-docs --limit 50 --offset 0
```

Current behavior:

- default output is unlimited
- output starts with the viewed range and total duplicate document count
- each duplicate document is shown as a block
- each duplicate path is printed on its own line

Example shape:

```text
Showing duplicate documents 1-1 of 1
some-book.pdf (2 paths)
  shelf-a/some-book.pdf
  shelf-b/some-book.pdf
```

## Delete Paths

Delete by direct relative path:

```bash
uv run python client.py delete-document-paths --rel-path 'Books/a.pdf'
```

Delete multiple paths directly:

```bash
uv run python client.py delete-document-paths \
  --rel-path 'Books/a.pdf' \
  --rel-path 'Books/b.pdf'
```

Delete from an input file:

```bash
uv run python client.py delete-document-paths --input to_del.txt
```

You can combine both:

```bash
uv run python client.py delete-document-paths \
  --input to_del.txt \
  --rel-path 'Books/c.pdf'
```

`to_del.txt` format:

- one relative PDF path per line
- blank lines ignored
- lines starting with `#` ignored

Delete behavior:

- deletes only when both exist:
  - the file exists on disk under `PDFZX_PDF_ROOT`
  - the matching row exists in `document_paths`
- if either side is missing, the command reports the mismatch and does not partially delete
- deletes the matching row from `scanned_file_in_job` if present
- keeps the `documents` row
