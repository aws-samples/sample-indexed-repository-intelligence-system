# Project Artifact Indexing and QA

This feature extends IRIS to index project artifacts (PPTX, DOCX, XLSX, PDF, MD, TXT, video) alongside the existing codebase indexing pipeline. Artifacts are discovered from a folder structure organized by project phase, extracted into text, summarized by LLM, and made queryable through the same chat, MCP, and API interfaces used for codebase queries.

## Overview

Many software projects have associated non-code materials: meeting presentations, design documents, readouts, reports, and technical specs. These artifacts contain valuable context about project decisions, timelines, and requirements that complement the codebase itself.

The artifact indexing feature brings these materials into the same query interface as the codebase, enabling questions like:

- "What was discussed in the first project meeting?"
- "Is there code in the codebase matching what was discussed in the meeting?"
- "What are the cost estimates from the final presentation?"

## Supported File Formats

| Format                         | Extractor                 | Notes                                              |
| ------------------------------ | ------------------------- | -------------------------------------------------- |
| `.pptx`                        | python-pptx               | Slides text + speaker notes                        |
| `.docx`                        | python-docx               | Paragraph text                                     |
| `.xlsx`                        | openpyxl                  | All sheets, row-by-row cell data                   |
| `.pdf`                         | pdfplumber                | Text extraction, optional OCR for image-only pages |
| `.md`, `.txt`                  | Built-in                  | Prefixed with source filename                      |
| `.mp4`, `.mov`, `.avi`, `.mkv` | AWS Transcribe (optional) | Metadata-only if transcription disabled            |

This table is maintained by hand. The authoritative list is the `ARTIFACT_FORMATS`
registry in `iris/artifacts/__init__.py` — every extension set, extractor lookup,
and format list in the code is derived from it. To add or remove a format, edit
the registry (and add a matching extractor), then update this table.

## Recommended Folder Structure

Artifacts are organized by project phase and material type. Files placed in recognized folders are automatically classified; files elsewhere are tagged as `unclassified`.

```
artifact_dir/
├── pre-project/
│   ├── readouts/          (.docx)
│   └── design_docs/       (.md, .txt)
├── during-project/
│   ├── presentations/     (.pptx)
│   ├── design_docs/       (.md, .txt)
│   ├── meetings/          (.mp4, .mov, .avi, .mkv, .md, .txt)
│   ├── reports/           (.pdf, .docx, .xlsx)
│   └── technical_docs/    (.md, .txt)
└── post-project/
    ├── readouts/          (.pptx, .docx)
    ├── roadmap/           (.md, .docx, .pdf)
    ├── production_readiness/ (.md, .docx, .pdf)
    └── constraints/       (.md, .docx, .pdf)
```

Files outside this structure are still discovered and indexed as `unclassified`.

## Quick Start

### 1. Configure artifact directory

Add the artifact directory path to `config.yaml`:

```yaml
artifact_dir: /path/to/your/artifacts
```

Or use the interactive `./deploy.sh` script which prompts for this during setup.

### 2. Index artifacts

```bash
# Index both codebase and artifacts
iris prepare

# Index artifacts only
iris prepare --artifact

# Index codebase only
iris prepare --code
```

### 3. Query

```bash
# Interactive chat (auto-routes between codebase and artifacts)
iris chat
```

Or via MCP tools:

- `codebase_artifact_query` — agent-based routing (uses orchestrator agent with retrieval tools)

## Indexing Pipeline

The pipeline follows a "mirror and extend" strategy, with artifact modules mirroring existing codebase modules:

```
discover_artifacts()
  → ArtifactCacheManager.has_changed()
  → extract_artifacts_parallel()     [with tqdm progress bar]
  → save per-artifact .md files
  → build_knowledge_base()           [optional, for human review]
  → summarize_artifacts()            [with tqdm progress bar]
  → artifact_overview.json
```

All steps are incremental — only changed files are re-processed.

### Pipeline Components

| Component     | File                                  | Purpose                                                          |
| ------------- | ------------------------------------- | ---------------------------------------------------------------- |
| Discovery     | `artifacts/artifact_discovery.py`     | Recursively finds supported files, classifies by phase/type      |
| Cache Manager | `artifacts/artifact_cache_manager.py` | SHA-256 hash-based change detection                              |
| Extractors    | `artifacts/artifact_extractors.py`    | Format-specific text extraction, parallel via ThreadPoolExecutor |
| Storage       | `artifacts/knowledge_base.py`         | Per-artifact `.md` files + optional assembled knowledge base     |
| Summarizer    | `artifacts/artifact_summarizer.py`    | LLM-based structured summarization                               |
| Orchestrator  | `generate_artifact_context.py`        | Coordinates the full pipeline                                    |

### Storage Layout

```
.iris_cache/<codebase-name>/
├── codebase_overview.json          (existing)
├── file_hashes.json                (existing)
├── artifact_overview.json          (new)
├── artifact_file_hashes.json       (new)
├── knowledge_base.md               (new, optional)
└── extracted_artifacts/            (new, primary retrieval source)
    ├── pre-project/
    │   └── readouts/
    │       └── kickoff_readout.docx.md
    ├── during-project/
    │   └── presentations/
    │       └── week1.pptx.md
    └── post-project/
        └── production_readiness/
            └── cost_analysis.pdf.md
```

Per-artifact `.md` files under `extracted_artifacts/` are the primary retrieval source at query time. The optional `knowledge_base.md` is a convenience output for human review and is not used for retrieval.

## Query Routing

### Agent-Based Approach (`codebase_artifact_query`)

The orchestrator agent decides which retrieval tools to invoke based on the query:

- `file_retrieval_agent` for codebase questions
- `artifact_retrieval_agent` for artifact questions
- Both when the query spans codebase and artifacts

The `artifact_retrieval_agent` uses a structured-output identifier agent (the `file_identifier` model) to select only the most relevant artifacts for the query, avoiding context window overflow.

## Entry Points

| Interface | Indexing                                   | Querying                                    |
| --------- | ------------------------------------------ | ------------------------------------------- |
| CLI       | `iris prepare`, `prepare --artifact` | `iris chat` (auto-routes)             |
| API       | `index_codebase_artifacts(config_path)`    | `chat_with_codebase_artifacts(config_path)` |
| MCP       | `codebase_artifact_context` tool           | `codebase_artifact_query`                   |

All entry points are backward-compatible — if `artifact_dir` is not configured, artifact indexing is skipped with zero overhead.

## Configuration

Add these to `config.yaml` (all optional with sensible defaults):

```yaml
# Path to project artifacts directory (skip if not set)
artifact_dir: /path/to/your/artifacts

# Maximum file size for extraction (bytes). Default: 30MB
artifact_max_file_size: 30000000

# Maximum file size for video files (bytes). Default: 300MB
artifact_video_max_file_size: 300000000

# Number of parallel extraction/summarization workers. Default: 4
artifact_max_workers: 4

# Generate assembled knowledge_base.md for human review. Default: true
artifact_generate_knowledge_base: true

# Enable OCR for image-only PDF pages. Default: false
artifact_ocr_enabled: false

# OCR provider: "llm" (Claude via Bedrock) or "textract". Default: llm
artifact_ocr_provider: llm

# Maximum pages to OCR per run (0 = unlimited). Default: 50
artifact_ocr_max_pages: 50

# Video transcription (requires S3 bucket for temporary upload)
artifact_transcription_enabled: false
artifact_transcribe_s3_bucket: ""
```

### MCP Tool Configuration

Enable artifact tools in `mcp_enabled_tools`:

```yaml
mcp_enabled_tools:
  - codebase_artifact_context
  - codebase_artifact_query
```

Or use `all` to enable everything.

## Architecture

### Module Map

```
iris/
├── artifacts/
│   ├── __init__.py                    # Data models, constants
│   ├── artifact_discovery.py          # File discovery + classification
│   ├── artifact_extractors.py         # Format-specific extractors
│   ├── artifact_cache_manager.py      # Hash-based change detection
│   ├── artifact_summarizer.py         # LLM summarization
│   └── knowledge_base.py             # Per-artifact storage + KB assembly
├── agents/
│   └── artifact_retrieval_agent.py    # Strands tool for artifact retrieval
└── generate_artifact_context.py       # Pipeline orchestrator

iris_mcp/
└── mcp_server.py                      # MCP server with codebase and artifact tools
```

### Relationship to Existing Codebase Modules

| Existing (Codebase)      | New (Artifacts)                |
| ------------------------ | ------------------------------ |
| `generate_context.py`    | `generate_artifact_context.py` |
| `CodebaseCacheManager`   | `ArtifactCacheManager`         |
| `file_retrieval_agent`   | `artifact_retrieval_agent`     |
| `codebase_overview.json` | `artifact_overview.json`       |
| `file_hashes.json`       | `artifact_file_hashes.json`    |

## Error Handling

The pipeline is designed to be resilient:

- Corrupted or unsupported files are logged and skipped; the pipeline continues
- Password-protected PDFs are logged and skipped
- Image-only PDF pages use OCR if enabled, otherwise a warning is logged
- LLM summarization failures retry once, then fall back to metadata-only summary
- Missing `artifact_dir` results in graceful skip (codebase-only mode)
- Corrupted cache JSON is treated as empty, triggering a full re-index
- Context window overflow is prevented by identifier-based artifact selection (only relevant artifacts are loaded)

## Troubleshooting

### No artifacts found

- Verify `artifact_dir` path in `config.yaml` exists and contains supported file types
- Check file extensions match the supported formats listed above

### Context window overflow during chat

- The `artifact_retrieval_agent` selects only relevant artifacts. If overflow still occurs, reduce the number of artifacts or increase `context_window_size` in config.

### OCR not working for image-only PDFs

- Set `artifact_ocr_enabled: true` in config
- For LLM-based OCR: ensure Bedrock model access is configured
- For Textract OCR: ensure AWS Textract permissions are available

### Video transcription not working

- Set `artifact_transcription_enabled: true`
- Configure `artifact_transcribe_s3_bucket` with a valid S3 bucket
- Ensure AWS Transcribe permissions and the S3 bucket are in the same region
- Install `ffmpeg` for keyframe extraction (optional, prompted during `./deploy.sh`)
