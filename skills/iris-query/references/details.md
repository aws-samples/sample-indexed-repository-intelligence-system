# IRIS Query — Reference

Supporting detail for the `iris-query` skill: cache layout, both overview JSON
schemas, troubleshooting, and configuration notes. SKILL.md is the workflow; this
is the lookup table.

## Cache layout

IRIS writes its index to `<output_dir>/<codebase-folder-name>/`, where
`output_dir` defaults to `.iris_cache` relative to the indexed repo. The
artifact files appear only when `artifact_dir` was configured and indexed:

```
<repo-root>/
├── .iris_cache/
│   ├── iris_skill_config.yaml      # written by iris_setup_lite.sh (not by IRIS itself)
│   └── <folder-name-at-index-time>/
│       ├── codebase_overview.json  # per-file LLM summaries — the codebase index
│       ├── file_hashes.json        # relative path -> SHA-256, drives change detection
│       ├── codebase_metadata.json  # {"evaluation_timestamp": ISO-8601}
│       ├── file_paths.txt          # newline-separated indexed paths
│       ├── tree.txt                # ASCII directory tree, rooted at the folder name
│       ├── artifact_overview.json      # optional: per-artifact LLM summaries
│       ├── artifact_file_hashes.json   # optional: artifact-relative path -> SHA-256
│       ├── artifact_file_paths.txt     # optional: discovered artifact paths
│       ├── artifact_tree.txt           # optional: artifact directory tree
│       ├── extracted_artifacts/        # optional: extracted TEXT, the retrieval source
│       │   └── <phase>/<type>/<name>.<ext>.md
│       ├── knowledge_base.md           # optional: whole corpus assembled for humans
│       ├── conversation_history.json  # IRIS chat/MCP history; unused by this skill
│       └── logs/                   # per-run indexing logs
```

Both indexes share one cache directory, and that directory is named after the
*codebase* folder. There is no separate artifact cache: `artifact_dir` supplies
the content, `codebase_dir` decides where the results land.

**The subdirectory name is a trap.** It comes from the folder name *at index
time* (`utils.py: construct_output_dir` uses `Path(codebase_dir).name`). Clone
the repo under a different name and the cache folder no longer matches the
current directory. Always discover it by glob:

```bash
ls .iris_cache/*/codebase_overview.json
```

Both bundled Python scripts do this already. When several caches exist (someone
indexed under two folder names), they pick the most recently modified.

### Portability

The cache is portable as committed. Every key in `file_hashes.json`,
`codebase_overview.json`, and `file_paths.txt` is a **relative** path;
`tree.txt` is display-only; metadata is a timestamp. Nothing needs rewriting
after a clone, a rename, or a move — on the **query** path.

The artifact files are portable in the same way, with one asymmetry worth
knowing: artifact keys are relative to `artifact_dir`, and `extracted_artifacts/`
carries the artifact *text* inside the cache. So a teammate who clones a
committed cache can fully query artifacts — summaries and content — without ever
having the artifact directory. What they cannot do is verify freshness or refresh,
because those need the source files.

The only absolute paths live in config files (`codebase_dir`, `artifact_dir`,
`context_file`). That is why the **regeneration** path must always re-derive
`codebase_dir` from the current repo root, and why `iris_setup_lite.sh` rewrites
it on every run rather than trusting a committed value. `artifact_dir` is the
exception that cannot be derived — see "Artifact directory resolution".

## `codebase_overview.json` schema

A flat JSON object: relative file path → summary entry. One entry per indexed
file. Every entry has exactly these six keys.

```json
{
  "backend/websocket_server.py": {
    "purpose": "WebSocket server for IRIS chatbot that handles real-time bidirectional communication…",
    "genai_system": "Yes",
    "has_bugs": "No bugs",
    "imported_files": ["backend/session_manager.py", "iris/utils/utils.py"],
    "classes": {
      "ConnectionManager": {
        "purpose": "Manages active WebSocket connections, maps connections to session IDs…",
        "methods": {
          "connect": "Accepts a new WebSocket connection, generates session ID…",
          "disconnect": "Handles WebSocket disconnection by removing connection…"
        }
      }
    },
    "functions": {
      "websocket_endpoint": "Main WebSocket endpoint handler that manages connection lifecycle…"
    }
  }
}
```

| Field | Type | Notes |
|---|---|---|
| `purpose` | string | Prose summary of the file. The main search target. |
| `genai_system` | `"Yes"` / `"No"` | Whether the file is part of a GenAI system. |
| `has_bugs` | `"No bugs"` / `"Potential bugs"` | LLM's impression at index time. A hint for where to look, never evidence. |
| `imported_files` | list of strings | Repo-relative paths this file imports based on LLM's understanding. |
| `classes` | object | Class name → `{purpose, methods{name → doc}}`. Empty `{}` for non-code files. |
| `functions` | object | Function name → docstring-ish summary. Empty `{}` for non-code files. |

Notes that matter when reasoning over this data:

- **No line numbers anywhere.** Any line-level claim must come from reading the file.
- Non-code files (Markdown, YAML, logs) get a `purpose` with empty
  `classes`/`functions`.
- Files excluded by `ignore_patterns`, or exceeding `max_file_size` (2 MB), are
  absent entirely. Absence means "not indexed", never "does not exist".
- Summaries are generated per file with no cross-file review, so two entries can
  describe the same interaction inconsistently. The live code settles it.

## `artifact_overview.json` schema (optional index)

A flat JSON object: artifact path *relative to `artifact_dir`* → summary entry.
One entry per successfully indexed artifact.

```json
{
  "during-project/reports/MedAgents_Cost_Analysis.xlsx": {
    "purpose": "Analyze and optimize the cost of using AWS Bedrock and Claude models…",
    "source_material_type": "reports",
    "project_phase": "during-project",
    "file_format": "xlsx",
    "key_topics": ["Bedrock pricing", "token costs", "optimization"],
    "related_artifacts": [],
    "summary": "Cost analysis covering per-token pricing, projected monthly spend…"
  }
}
```

| Field | Type | Notes |
|---|---|---|
| `purpose` | string | One-line reason the artifact exists. Main search target. |
| `summary` | string | Longer prose summary of the content. |
| `key_topics` | list of strings | Topics pulled out by the LLM; searchable. |
| `project_phase` | string | `pre-project` / `during-project` / `post-project` / `unclassified` |
| `source_material_type` | string | `meetings`, `presentations`, `reports`, `design_docs`, `readouts`, `technical_docs`, `roadmap`, `production_readiness`, `constraints`, `unclassified` |
| `file_format` | string | Bare extension: `pptx`, `docx`, `xlsx`, `pdf`, `md`, `txt`, `mp4`, `mov`, `avi`, `mkv` |
| `related_artifacts` | list of strings | LLM's guess at related artifacts. A hint, not a guarantee. |

`project_phase` and `source_material_type` come from the **folder layout**, not
from content: `artifact_discovery._classify_path` matches the first two path
components against a known phase/type map, and anything else is `unclassified`.
An `unclassified` artifact is still fully indexed — it just was not filed in the
recommended structure.

### Extracted text — the artifact retrieval source

`extracted_artifacts/<artifact path>.md` holds the text pulled out of each
artifact, with a small YAML header (`source`, `project_phase`,
`source_material_type`, `file_format`). Note `.md` is appended to the *full*
filename, extension included (`report.pdf` → `report.pdf.md`), so two artifacts
with the same stem cannot collide.

This is what to read before quoting anything. A summary is a paraphrase of a
paraphrase; the extracted text is the artifact's own words.

Extraction quality varies by format, and knowing the failure modes prevents
wrong conclusions:

| Format | Extracted | Watch for |
|---|---|---|
| `.pptx` | slide text + speaker notes | layout and images are lost; a diagram-only slide extracts as almost nothing |
| `.docx` | paragraph text | tables flatten |
| `.xlsx` | every sheet, row by row | formulas appear as values only |
| `.pdf` | text via pdfplumber | image-only pages need `artifact_ocr_enabled`; without it they are skipped with a warning |
| `.md`, `.txt` | verbatim | — |
| video | Transcribe transcript + keyframe analysis | **only when `artifact_transcription_enabled`** — otherwise metadata only, so an "empty" meeting recording usually means transcription was off, not that nothing was said |

`knowledge_base.md` is every extracted artifact concatenated, grouped by phase
and type. It exists for human review and report generation. Do not load it for
retrieval — it is the whole corpus in one file.

## Change detection

Both indexes use the same mechanism, over separate hash files. `check_staleness.py`
runs the codebase check always and the artifact check whenever the cache contains
an artifact index, reporting `VERDICT` and `ARTIFACT_VERDICT` independently.

`file_hashes.json` maps relative path → SHA-256 of file bytes
(`hashlib.sha256(content).hexdigest()`, per
`iris/file_system/file_utils.py: hash_file_content`). `check_staleness.py`
recomputes those hashes and compares:

- **modified** — path in cache, hash differs
- **deleted** — path in cache, file absent from disk
- **new** — file on disk, not in cache, and not ignored
- **unreadable** — path in cache, file present but unreadable (permissions)

Drift ratio = (modified + deleted + new) ÷ tracked files. Default threshold for
`large_drift` is 15%; override with `--threshold`.

| Verdict | Exit | Meaning |
|---|---|---|
| `fresh` | 0 | No drift; cached summaries match the working tree |
| `no_cache` | 1 | No `codebase_overview.json` directly under the repo |
| `empty_cache` | 1 | Cache exists but tracks zero files (failed or interrupted indexing) |
| `cache_mismatch` | 1 | Cache describes a different tree; drift figures would be noise |
| `unindexed_repo` | 1 | Working dir is its own codebase with no index — offer to index it |
| `ambiguous_repo` | 1 | Several repos registered, working dir inside none of them |
| `small_drift` | 2 | Drift below threshold; read the listed files live |
| `large_drift` | 2 | Drift at or above threshold; offer a refresh, answer live this turn |

### Artifact drift

`artifact_file_hashes.json` maps **artifact_dir-relative** path → SHA-256, and is
compared exactly the same way. New-artifact detection mirrors
`artifact_discovery.discover_artifacts` rather than the codebase walk: supported
extensions only, Office lock files (`~$…`) skipped, files over
`artifact_max_file_size` (30 MB) or `artifact_video_max_file_size` (300 MB)
dropped. There are no `ignore_patterns` on the artifact side.

`ARTIFACT_VERDICT` values, and what each one means for an answer:

| Artifact verdict | Meaning |
|---|---|
| `no_artifact_index` | No artifact index in this cache. The normal state for a code-only repo — not an error, and not worth mentioning to the user unless they asked about artifacts |
| `fresh` | Artifact summaries match the artifact directory |
| `small_drift` | Below threshold; read the listed artifacts' extracted text instead of their summaries |
| `large_drift` | At or above threshold; offer a refresh, answer flagged this turn |
| `artifact_dir_unknown` | Index exists, but nothing records where `artifact_dir` points, so freshness is unverifiable. The index is still usable |
| `artifact_dir_missing` | The recorded `artifact_dir` does not exist here — normal for a cache committed on another machine. Index still usable |
| `artifact_dir_mismatch` | The directory checked is not the one the index describes (overlap below 25%, same test as `cache_belongs_to_repo`). Do not report a drift figure |
| `empty_artifact_index` | Hash file tracks nothing — failed or interrupted run |
| `artifact_index_unreadable` | `artifact_file_hashes.json` missing or corrupt |

Exit codes stay driven by the codebase verdict, with one addition: a `fresh`
codebase paired with artifact `small_drift`/`large_drift` exits 2, because the
cache as a whole is stale. Artifact states that merely prevent *verification*
(`artifact_dir_unknown`, `artifact_dir_missing`, `no_artifact_index`) never change
the exit code — artifacts are optional, and an optional index must not turn a good
codebase answer into a failure. Pass `--no-artifacts` to skip the artifact check.

### Artifact directory resolution

`artifact_dir` is the one path in the system that cannot be derived. `codebase_dir`
is just the repo root; `artifact_dir` is wherever the user keeps project material,
usually outside the repo entirely. So it is resolved from, in order:

| # | Source | Notes |
|---|---|---|
| 1 | `--artifact-dir` | Explicit always wins. `iris_setup_lite.sh` exits 1 if the path does not exist, rather than indexing nothing and looking successful |
| 2 | `$IRIS_ARTIFACT_DIR` | Per-shell override |
| 3 | `.iris_cache/iris_skill_config.yaml` → `artifact_dir` | Written by `iris_setup_lite.sh` on every indexing run. The normal path after first setup |
| 4 | `<iris_repo>/config.yaml` → `artifact_dir` | Only when that config's `codebase_dir` resolves to **this** repo. Covers repos indexed by IRIS directly (`iris prepare`, `deploy.sh`), where the path exists nowhere else. `iris_repo` comes from `~/.iris/config.json` |
| — | Otherwise | Codebase only when indexing; "unverified" when checking staleness |

The `codebase_dir` guard on step 4 is load-bearing. IRIS's `config.yaml` describes
one project at a time, so its `artifact_dir` belongs to whatever `codebase_dir`
names; reading it for any other repo would pair this cache with an unrelated
project's artifacts, which reads as a real answer rather than an error.

A named directory that does not exist is handled by who named it: an explicit
`--artifact-dir`/`$IRIS_ARTIFACT_DIR` fails the indexing run (a typo should not
look like success), while a *recorded* path that is unreachable degrades to
codebase-only with a warning (the expected state after cloning someone else's
cache, and no reason to block a codebase refresh). `--check` never fails on
either; it reports.

The template placeholder `/path/to/your/artifacts`, blank values, and `null` all
count as "not configured" — matching `iris/artifacts/__init__.py:resolve_artifact_dir`.

`iris_setup_lite.sh` writes the key **explicitly on every run**, as a path or as
`artifact_dir: null`. The null is not redundant: the skill config is merged *over*
the IRIS clone's `config.yaml`, so omitting the key would inherit whatever
`artifact_dir` that config names and index an unrelated directory's artifacts into
this repo's cache. For the same reason the script passes an explicit
`mode="both"`/`mode="codebase"` to `index_codebase_artifacts` rather than letting
the merged config decide.

Both scripts read the skill config with a line scan rather than a YAML parse, for
the same reason `~/.iris/config.json` is read with `sed` and not `jq`: the query
path must work on a machine with nothing installed.

## Install scope and repo resolution

The skill can be installed at two scopes, and the difference is not cosmetic:

| Scope | Path | Active when |
|---|---|---|
| User-level | `~/.claude/skills/`, `~/.kiro/skills/`, `~/.cline/skills/` | Every session, any working directory |
| Project-level | `<repo>/.claude/skills/`, `<repo>/.kiro/skills/` | Only when the assistant opens that repo |

### Per-host directories

One `SKILL.md` folder serves all three hosts, but they scan different roots.
Verified against the shipped Cline 4.1.4 bundle (`next/dist/extension.js`), not
inferred from docs:

| Host | Project roots | Global roots |
|---|---|---|
| Claude Code | `<repo>/.claude/skills/` | `~/.claude/skills/` |
| Kiro | `<repo>/.kiro/skills/` | `~/.kiro/skills/` |
| Cline | `.clinerules/skills/`, `.cline/skills/`, **`.claude/skills/`**, `.agents/skills/` | `~/.cline/skills/`, `~/.agents/skills/` |

Two consequences worth knowing:

- **Project-level installs cover Claude Code and Cline with one copy.** Cline
  scans `<repo>/.claude/skills/`, so `deploy.sh` writes a single folder for both
  rather than duplicating it. Committing `.claude/skills/` serves both hosts.
- **User-level installs do not.** Cline's global roots are `~/.cline/skills/` and
  `~/.agents/skills/`; it deliberately does **not** read `~/.claude/skills/`.
  A user-level install therefore needs its own copy under `~/.cline/skills/`.

Cline predates Agent Skills with `.clinerules/` (plain instruction Markdown, no
frontmatter, always loaded). Skills are the better fit here because they load on
demand from the `description`, rather than consuming context in every session.
Nothing in this skill needs `.clinerules/`.

The Kiro refresh hook is Kiro-specific and repo-scoped, so it is installed only
alongside a project-level Kiro install.

Project-level is what makes the committed zero-install team flow work
(`git clone` and you have it). But it is invisible when the assistant opens
somewhere else — a workspace root, a different project — which is common. That is
why `deploy.sh` offers both and defaults to installing both.

A user-level install means the working directory is frequently unrelated to any
indexed repo, so the scripts resolve the target repo rather than assuming `.`:

1. `--repo` if given — honoured exactly, always the most reliable form
2. The nearest enclosing indexed repo at or above the working directory
3. The registered repo that contains the working directory
4. **If the working directory is itself an unindexed codebase → `unindexed_repo`**
   (see below); the registry is deliberately *not* consulted
5. The only registered repo, when exactly one is known
6. Otherwise: exit non-zero listing candidates, so the agent can ask

Step 4 exists to prevent a specific wrong answer. Without it, opening an
unindexed project while exactly one other repo happened to be registered made the
skill answer confidently **about the wrong codebase** — indistinguishable from a
correct answer. `looks_like_a_codebase()` detects the situation cheaply: a project
marker (`.git`, `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, …) or
any source file within two directory levels. Over-detecting is safe, since the
result is an offer to index; under-detecting is what causes wrong answers.

A directory that is *not* a codebase — a scratch folder, a docs directory, a
home-like directory — still falls through to the registry, which is what makes
cross-directory queries work.

Whenever the repo was inferred rather than passed explicitly, the scripts print
`[resolved repo: <path>  (via <how>)]` to stderr. That line exists so a wrong
inference is visible instead of silently shaping an answer.

### Indexing a repo that has no cache

Most repos a user opens have never been indexed — this is a normal path, not an
error. Anyone with the skill installed almost certainly has an IRIS clone
locally, so indexing is usually possible without any new install.

`iris_setup_lite.sh --check` looks for an interpreter that can `import iris`, in
this order — first hit wins:

| # | Source | Notes |
|---|---|---|
| 1 | `--python` / `IRIS_PYTHON` | Explicit always wins; warns if it cannot import `iris` |
| 2 | `~/.iris/config.json` → `python` | Written by `deploy.sh` at install time, or remembered from a previous success. The normal path |
| 3 | `~/.iris/config.json` → `iris_repo` | Only if `python` went stale; retries that clone's `.venv`/`venv` |
| 4 | `python3`/`python` on PATH | Covers an already-activated venv |
| 5 | Venv beside an `iris` console script | |
| 6 | Named IRIS clone beside the repo | `sample-indexed-repository-intelligence-system`, `code-intelligence`, `iris`, `IRIS` at the repo, its parent, or grandparent — the layout `deploy.sh` produces |
| — | **Otherwise: ask the user** | Never guessed at |

Every step names a specific candidate. **There is deliberately no filesystem
scan.** An earlier version walked `$HOME` for any venv that could import `iris`;
it was removed because a developer machine commonly has several — an IRIS clone,
an editable install of a sibling checkout, a general project venv — and a
directory walk picks among them by traversal order rather than correctness. On
the author's machine three venvs qualified, and the scan wrote the wrong one into
the config during testing. It also cost ~3.4s on a large `$HOME` to guess at
something the user can state exactly in one answer.

**Exit 3 does not mean IRIS is absent.** It means nothing recorded its location.
The correct response is to ask the user for their clone path and remember it —
not to tell them to install IRIS, and not to guess. This was a real failure: a
clone six levels below `$HOME` reported "regeneration is unavailable on this
machine" while working perfectly.

### `~/.iris/config.json`

```json
{
  "version": 1,
  "python": "/abs/path/to/iris-clone/.venv/bin/python",
  "iris_repo": "/abs/path/to/iris-clone"
}
```

Two writers:

- **`deploy.sh`**, during "Agent Skill Installation". It already knows both paths
  (`$SCRIPT_DIR` and the venv it just validated), so recording them means the
  skill never has to search. This is the normal case.
- **`iris_setup_lite.sh`**, on any successful resolution the config did not
  already describe — covering skills installed by hand, or a user who supplied
  the path when asked.

`iris_repo` is a second chance at discovery: if `python` goes stale (venv
rebuilt, interpreter upgraded) but the clone is still present, its `.venv`/`venv`
is retried before any filesystem scan. The skill preserves `iris_repo` when it
rewrites the file, so it never discards what the installer knew.

Read with `sed`, not `jq` — this must work on a machine with nothing installed.
Stale entries fail their `import iris` check and fall through to re-discovery, so
the file is self-healing; delete it to force a fresh search. `IRIS_HOME` moves
this file and the repo registry together.

**Why `$HOME` and not the skill folder.** Storing the path inside
`skills/iris-query/` would be self-contained but wrong three ways: `deploy.sh`
does `rm -rf` on the skill directory when upgrading an existing install, so it
would be destroyed on every upgrade; project-level skill folders are *committed*,
so an absolute path would travel to teammates' machines where it is meaningless
(the drift class spec P2 warns about); and with user-level plus project-level
installs there would be several copies to keep in sync instead of one.

If none of that finds IRIS, clone it — the package is not on PyPI:

```bash
git clone https://github.com/aws-samples/sample-indexed-repository-intelligence-system
cd sample-indexed-repository-intelligence-system
./deploy.sh          # then pick "Agent Skill Installation"
```

Already have a clone? Skip re-cloning and point the script at its interpreter:

```bash
export IRIS_PYTHON=/path/to/iris-clone/.venv/bin/python
# or: bash iris_setup_lite.sh --python /path/to/.venv/bin/python --repo <repo>
```

`--check` also prints an approximate indexable-file count, because indexing cost
scales with it and the user is about to be asked whether to spend it. The count
comes from the same walk and ignore rules as new-file detection, so it reflects
what would actually reach Bedrock (177 for IRIS's own repo, matching its cache
exactly).

The skill asks the user whether to wait for indexing or get an immediate answer
from a normal code read. Neither is assumed: indexing spends money, and silently
skipping it hides the better long-term option.

### The registry

`~/.iris/indexed_repos.json` (override the directory with `IRIS_HOME`) records
which repos have been indexed:

```json
{
  "version": 1,
  "repos": [
    {"root": "/abs/path/to/repo", "indexed_at": "2026-08-05T12:00:00+00:00"}
  ]
}
```

It lives outside every skill folder so that reinstalling or upgrading the skill
does not wipe it, and so Claude Code and Kiro installs share one list.

Entries are **validated on read, never trusted**: the root must still be a
directory, and the cache path is re-derived by glob rather than read from the
file, because the cache subdirectory name changes if a repo is re-indexed under a
different folder name. Dead entries are skipped silently.

`deploy.sh` and `iris_setup_lite.sh` both register a repo after a successful
index. Registration is best-effort — a registry write failure never fails an
indexing run, since the registry is a discovery convenience, not a source of
truth. Manage it directly with:

```bash
python3 scripts/check_staleness.py --list-repos            # show known repos
python3 scripts/check_staleness.py --repo <path> --register  # add one
```

The registry is purely a convenience. Passing `--repo` always works without it.

### Why cache discovery is not recursive

`find_cache_dir` looks only at `<repo_root>/.iris_cache/`. An earlier version
fell back to `*/.iris_cache/*/` when that missed, which meant running from a
directory containing several indexed repos silently picked one repo's cache and
hashed it against the parent tree — producing drift figures in the thousands of
percent rather than an error. A cache one level down belongs to a nested repo.
Resolve the repo instead (above).

`cache_belongs_to_repo` is the backstop: it samples up to 60 tracked paths and
requires at least 25% to exist under the target tree. Unrelated repos still share
generic names (`README.md`, `config.yaml`), so a greater-than-zero test is not
enough — measured against IRIS's own cache, the correct repo scores ~0.85 and an
unrelated sibling ~0.10.

New-file detection needs its own ignore logic, since IRIS's live config isn't
available to a consumer with no install. `check_staleness.py` carries a
conservative subset of `config_template.yaml`'s `ignore_patterns` plus the
repo's `.gitignore`, matched by a small stdlib gitignore-style matcher. It errs
toward over-ignoring: a false "new file" would wrongly inflate drift. Pass
`--no-new` to skip new-file detection and compare only tracked files.

The bundled scripts intentionally do not replicate `pathspec`'s full gitignore
semantics. When exact parity matters, the authoritative answer comes from
running IRIS itself.

## Why the skill reads the index instead of calling the MCP server

IRIS ships an MCP server with a `codebase_artifact_query` tool. This skill
deliberately does not use it for Q&A:

- **Cost.** `codebase_artifact_query` runs its own LLM agent, so the assistant
  pays for a second model to answer a question it could answer itself.
- **Lost context.** That agent doesn't see the conversation — what the user
  already asked, already rejected, or is editing right now.
- **Credentials.** It needs AWS access at question time. Reading the cache needs
  none, which is what makes the zero-install consumer flow work.

The two integrations coexist and `deploy.sh` presents them as separate options.
The MCP server remains the right choice for hosts without Agent Skills support,
and for IRIS's own chat and UI surfaces.

## Environment variables

| Variable | Effect |
|---|---|
| `IRIS_AUTO_PREPARE=1` | Permits refresh on `large_drift` without asking. Default off. |
| `IRIS_PYTHON` | Interpreter `iris_setup_lite.sh` should use. Same as `--python`. |
| `IRIS_ARTIFACT_DIR` | Artifact directory for staleness checks and indexing. Same as `--artifact-dir`, and outranked by it. |
| `IRIS_HOME` | Directory for `config.json` and `indexed_repos.json`. Default `~/.iris`. |
| `AWS_PROFILE` / `AWS_ACCESS_KEY_ID` … | Standard AWS credential resolution, used only when indexing. |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `No .iris_cache/*/codebase_overview.json under this repo` | Repo not indexed, or cache not committed | Run Task 2 setup; or ask whoever indexed it to commit `.iris_cache/` |
| Cache folder name ≠ repo folder name | Repo cloned or renamed since indexing | Harmless. Glob discovery handles it; never rebuild the name by hand |
| `Could not find an interpreter that can import iris` (exit 3) | IRIS exists but outside the searched roots, or its venv lacks the package | **Ask the user for their clone path**, then pass `--python <clone>/.venv/bin/python`. It is remembered afterwards. Only clone IRIS if they have none |
| `This repo is NOT indexed` | Normal for any repo nobody has indexed yet | Offer to index it — see "Indexing a repo that has no cache" |
| `Cannot index: no AWS credentials found` | No credentials in the environment | `aws configure`, `aws sso login`, or set `AWS_PROFILE`. Queries still work without |
| `AccessDeniedException` from Bedrock during indexing | Model access not granted in a configured region | Request access for every model/region pair in `config.yaml`'s `model_configuration` |
| `ThrottlingException` during indexing | Bedrock rate limits under parallel summarization | Retry; add more model-region pairs to `file_summarizer.models` to spread load |
| `ConfigNotFound: config.yaml or config_template.yaml not found` | Running outside an IRIS install | Pass `--python` pointing at the IRIS venv, or run from the IRIS repo |
| Indexing takes very long | Large repo, few model-region pairs | Add pairs to `file_summarizer.models`; tighten `ignore_patterns` |
| Cache appears out of date right after indexing | Files changed during the run, or the run partially failed | Re-run indexing; check `.iris_cache/<name>/logs/` for the failing file |
| `No codebase overview available` (from the MCP server) | Index missing for the path that server was configured with | Run indexing for that codebase; verify the server's `codebase_dir` |
| Question-relevant files are absent from the index | Excluded by `ignore_patterns`, or over `max_file_size` (2 MB) | Expected. Use Grep/Read for those files |
| `No .iris_cache/*/artifact_overview.json under this repo` | Artifacts were never indexed — the normal state, since they are opt-in | Answer from the codebase. Offer artifact indexing only if the question needs project context and the user has an artifact folder |
| `ARTIFACT_VERDICT: artifact_dir_unknown` | The cache carries an artifact index but nothing records the source directory (common with a cache indexed by IRIS's own `config.yaml` rather than by this skill) | Query it anyway and say freshness is unverified; re-run with `--artifact-dir <path>` if the user can name it |
| `ARTIFACT_VERDICT: artifact_dir_missing` | Recorded `artifact_dir` is another machine's absolute path | Expected for a committed cache. Re-point with `--artifact-dir` only when a refresh is wanted |
| `Artifact directory does not exist: …` (exit 1 from setup) | Typo, or a path that moved | Pass the real path, or `--no-artifacts` to index code only |
| `artifact status: skipped` during indexing | IRIS resolved no usable `artifact_dir` — the path exists but holds no supported formats | Check the folder contents against the supported list (pptx/docx/xlsx/pdf/md/txt/video) |
| An artifact is indexed but its extracted text is nearly empty | Image-only PDF with OCR disabled, a diagram-only slide deck, or a video with transcription disabled | Enable `artifact_ocr_enabled` / `artifact_transcription_enabled` in `config.yaml` and reindex, or treat the artifact as unavailable |
| Artifact summaries exist for files the user deleted | Deleted artifacts stay in the overview until a refresh | Reported as `deleted_artifacts` by the staleness check; refresh to clear |

## Keeping a committed cache fresh

Event-driven freshness belongs in version control tooling, not in a skill —
skills cannot reliably fire on file events, and reindexing mid-edit produces
summaries of half-written code.

A pre-commit hook, refreshing only when source files are staged:

```bash
#!/bin/bash
# .git/hooks/pre-commit  (or a pre-commit framework hook)
if git diff --cached --name-only | grep -qE '\.(py|js|jsx|ts|tsx|go|rs|java)$'; then
    bash path/to/skills/iris-query/scripts/iris_setup_lite.sh --repo "$(git rev-parse --show-toplevel)" --yes || exit 0
    git add .iris_cache
fi
```

Trade-offs: it needs the IRIS package and AWS credentials on every committer's
machine, and it adds Bedrock latency to `git commit`. A scheduled CI job that
reindexes and commits the refreshed cache avoids both, at the price of a cache
that trails the default branch slightly. Either beats reindexing per edit.

`|| exit 0` matters: a Bedrock hiccup should never block a commit.

## Related source files

Useful when verifying this skill's behaviour against IRIS itself:

| Path | Relevance |
|---|---|
| `iris/file_system/file_utils.py` | `hash_file_content`, cache load/save, `collect_files` |
| `iris/file_system/cache_manager.py` | Change detection and cache-consistency logic |
| `iris/utils/utils.py` | `construct_output_dir` (the folder-name behaviour), config merge |
| `iris/api.py` | `index_codebase_artifacts(config_path=…, mode=…)`, the entry point the setup script drives |
| `iris/cli.py` | `iris prepare` (`--code` / `--artifact`) / `iris chat` CLI surface |
| `config_template.yaml` | Model configuration, `ignore_patterns`, size limits, every `artifact_*` option |
| `iris/artifacts/__init__.py` | `ARTIFACT_FORMATS` (the authoritative format list), `resolve_artifact_dir`, folder-classification map |
| `iris/artifacts/artifact_discovery.py` | Which files become artifacts, and how phase/type are assigned |
| `iris/artifacts/knowledge_base.py` | `extracted_artifacts/` naming and `knowledge_base.md` assembly |
| `iris/generate_artifact_context.py` | The artifact pipeline end to end |
| `docs/artifact-indexing.md` | Feature-level documentation for artifact indexing |
