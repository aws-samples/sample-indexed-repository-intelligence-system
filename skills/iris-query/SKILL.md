---
name: iris-query
description: >
  Answer questions about a codebase — and about the project's artifacts, when
  they have been indexed — from precomputed summary files, so you start from an
  existing map instead of exploring from scratch. Especially useful for
  high-level comprehension: "what does this repo do", "how does X work", "where
  is Y implemented", "explain the architecture", "which files handle Z". If the
  repo also has an artifact index (presentations, meeting notes, readouts,
  reports, design docs, spreadsheets, PDFs, recordings), use it for project
  questions too: "what was decided in the kickoff meeting", "what are the cost
  estimates", "does the code match what the design doc describes". The summaries
  can answer a sufficiently high-level question on their own; more often they
  tell you what to read. Works best in repos IRIS has already indexed (they
  contain a .iris_cache/ directory), but ALSO use it in an unindexed repo when
  the user asks a comprehension question — it can index first, or answer
  natively and offer indexing for next time. Also handles IRIS setup, repair,
  and manual refresh ("reindex", "refresh the IRIS index"). Do NOT use for
  targeted edits to a file the user already named, or for exact string or
  pattern searches — Read and Grep are better there.
---

# IRIS Query

Answer questions from IRIS's precomputed indexes, then ground the answer in the
live source: code for the codebase, extracted text for artifacts.

IRIS builds up to **two indexes** into the same cache directory:

| Index | Built from | Files in `.iris_cache/<name>/` | Status |
|---|---|---|---|
| **Codebase** | the repo's source files | `codebase_overview.json`, `file_hashes.json` | always present in an indexed repo |
| **Artifacts** | a configured `artifact_dir` of project documents (pptx, docx, xlsx, pdf, md, txt, video) | `artifact_overview.json`, `artifact_file_hashes.json`, `extracted_artifacts/` | **optional** — only exists when `artifact_dir` was configured and indexed |

Both are **routing tables**: they tell you which files or artifacts matter for a
question so you can skip 10–20 exploratory tool calls. Neither is a source of
truth — the working tree is, for code; the extracted text under
`extracted_artifacts/` is, for artifacts.

Artifacts are opt-in, so **their absence is normal, not a fault**. Check whether
the artifact index exists, use it when it does, and never mention artifacts when
it doesn't.

Reading either index costs no AWS credentials, no Python environment, and no
IRIS install. Only *regenerating* them does.

## When the indexes help, and when they don't

| Question type | Approach |
|---|---|
| Purpose, architecture, "where do I start", "which files handle X" | **Codebase index first**, then read the files it points to |
| Exact line-level detail, string/pattern search, debugging a specific error, making edits | **Native Read/Grep only** — the index adds nothing and can mislead |
| "Why" questions spanning files; big-picture → specifics | Index for orientation, then native tools for precision |
| Decisions, timelines, requirements, costs, meeting content, "what did we agree" | **Artifact index** — this material is not in the code at all |
| "Does the code do what the design doc / meeting said?" | **Both**: artifact index for the intent, codebase index plus live reads for the implementation |

Never quote code, cite a line number, or describe a signature from a cached
summary. Summaries are prose written by an LLM at index time; they drift, and
they never contained line numbers to begin with. Read the file.

The same rule applies to artifacts, with one difference: there is no readable
"live" artifact — a `.pptx` or `.mp4` is not text. The extracted text under
`extracted_artifacts/` is as close to source as you get, so quote figures,
dates, and decisions from that, never from an artifact's summary.

## Script paths

`{skill_dir}` is the directory containing this SKILL.md. All commands below are
safe: they only read the cache and hash files. Run them without asking
permission. Only `iris_setup_lite.sh` without `--check` costs money, and it
prompts on its own.

**Windows:** run the `.sh` script through Git Bash or WSL —
`bash "{skill_dir}/scripts/iris_setup_lite.sh" --check`. The three Python scripts
are cross-platform; invoke them with `python` instead of `python3` if that is
what is on PATH.

| Script | Reads | Use for |
|---|---|---|
| `check_staleness.py` | both hash files | Step 1 — freshness of the codebase index and, when present, the artifact index |
| `extract_overview.py` | `codebase_overview.json` | Step 2 — code routing |
| `extract_artifacts.py` | `artifact_overview.json` + `extracted_artifacts/` | Step 2 — artifact routing, and artifact content |
| `iris_setup_lite.sh` | — | Tasks 2 and 3 — indexing and refresh |

## Task 1 — Codebase and Artifact Q&A (primary)

### Step 0. Work out which repo the question is about

Ask the user which repo the question is about if it's unclear — do not guess. To see what is known:

```bash
python3 {skill_dir}/scripts/check_staleness.py --list-repos
```

When the user names a repo, or you already know it, pass `--repo` explicitly.
That is always the most reliable form:

```bash
python3 {skill_dir}/scripts/check_staleness.py --repo /path/to/indexed-repo
```

### Step 1. Check staleness of both indexes. Every time.

```bash
python3 {skill_dir}/scripts/check_staleness.py --repo <repo_root>
```

One command covers both indexes. It is sub-second local hashing. Run it on every
invocation.

The output has two labelled sections and **two independent verdict lines**:

- `VERDICT:` — the codebase index, hashed against the working tree
- `ARTIFACT_VERDICT:` — the artifact index, hashed against `artifact_dir`.
  Printed only when the cache actually contains an artifact index; when it does
  not, the section says `no_artifact_index` and there is nothing more to do.

Branch on each independently. A fresh codebase index says nothing about artifact
freshness, and vice versa.

It finds the cache by globbing `<repo_root>/.iris_cache/*/codebase_overview.json`.
Don't construct that subdirectory name yourself: it is named after the folder name
*at index time*, which might differ whenever someone clones the repo under another
name. Note it looks only directly under `<repo_root>` — a cache one level down
belongs to a nested repo, and pairing it with the parent tree is what produces
nonsense drift.

Branch on the `VERDICT` line (codebase index):

| Verdict | What to do |
|---|---|
| `unindexed_repo` | The working directory is its own codebase and has no index. **Go to Task 2 and offer to index it** — do not answer from another repo's cache even if one is registered. |
| `no_cache` | This repo isn't indexed. Offer Task 2, then answer with native exploration regardless. Do not stall the question on setup. If the output names indexed repos in subdirectories, you pointed one level too high — re-run with `--repo <that-subdirectory>`. |
| `empty_cache` | A cache exists but tracks no files — usually a failed or interrupted indexing run. Treat it exactly like `no_cache`. |
| `cache_mismatch` | The cache describes a different tree than the directory being checked. Do not report its drift number. Re-resolve the repo (Step 0) and re-run. |
| `fresh` | Answer from the index as normal. |
| `small_drift` | Answer from the index, but **read every listed changed file live** — do not use their cached summaries. Add a one-line note that the cache is slightly stale. |
| `large_drift` | Tell the user the cache is substantially stale. Ask **once** whether to run a refresh (Task 3). Either way, **answer this turn from live reads** so the question still gets answered. |

Treat a file the check flagged as changed as having no cached summary at all,
even under `fresh` elsewhere in the repo. Same rule if the question centres on
files that changed: prefer live reads over a stale summary regardless of the
overall ratio.

Then branch on `ARTIFACT_VERDICT` (artifact index — optional, so most outcomes
here are informational rather than problems):

| Artifact verdict | What to do |
|---|---|
| `no_artifact_index` | No artifacts have been indexed. Answer from the codebase alone and **do not mention artifacts** — unless the output says an `artifact_dir` is configured with indexable artifacts, in which case offering to index them (Task 2) is worthwhile only if the question actually calls for project context. |
| `fresh` | Use the artifact index as normal. |
| `small_drift` | Use the index, but for the artifacts listed as changed read their extracted text (`extract_artifacts.py content <path>`) rather than trusting the summary. Note the slight staleness. |
| `large_drift` | Say the artifact index is substantially stale. Ask **once** whether to refresh (Task 3). Answer this turn from what is there, flagged. |
| `artifact_dir_unknown` | The index is queryable but freshness cannot be verified, because nothing records where `artifact_dir` points. Use it, say it is unverified, and if the user can name the path, re-run with `--artifact-dir <path>`. |
| `artifact_dir_missing` | Same handling. Normal for a cache committed on another machine: `artifact_dir` is an absolute, machine-specific path, while the index itself travels with the repo. |
| `artifact_dir_mismatch` | The directory checked is not the one the index describes. Do not report its drift number; re-run with the correct `--artifact-dir`. |
| `empty_artifact_index` / `artifact_index_unreadable` | A failed or interrupted run. Treat artifacts as unindexed; offer a refresh if the question needs them. |

`artifact_dir` cannot be derived from the repo root the way `codebase_dir` can —
it is an arbitrary path, often outside the repo — so the script looks for it in
`--artifact-dir`, then `$IRIS_ARTIFACT_DIR`, then the `artifact_dir` recorded in
`.iris_cache/iris_skill_config.yaml` by a previous indexing run, and finally the
IRIS clone's own `config.yaml` — that last one only when its `codebase_dir` is
this very repo, since otherwise it describes a different project's artifacts. Not
finding it degrades the artifact check to "unverified", never to an error.

If the script itself fails — wrong Python, unreadable cache, anything — say so
in one line and fall back to native exploration. A broken index layer must never
leave a question unanswered.

### Step 2. Extract information from the indexes.

Pull from the codebase index, the artifact index, or both, based on what the
question needs:

| Question is about | Pull from |
|---|---|
| Code: structure, behaviour, where something lives | `extract_overview.py` |
| Project: decisions, meetings, timelines, costs, requirements, designs as *stated* | `extract_artifacts.py` |
| Both: "does the implementation match what we agreed", "which code came out of that meeting" | both, artifacts first for intent, then code |

Skip the artifact index entirely when `ARTIFACT_VERDICT` was `no_artifact_index`.

#### 2a. Codebase index

`codebase_overview.json` can run to hundreds of KB or even more. Selecting
specific information to pull may be more benificial than loading the entire
`codebase_overview.json`. There is an `extract_overview.py` script that helps
with extracting information from the codebase overview file, but you don't
have to use that script. Pull only what the question needs. For example:

```bash
E="python3 {skill_dir}/scripts/extract_overview.py --repo <repo_root>"

$E stats                          # orientation: file count, languages, top-level dirs
$E tree --depth 1                 # directory rollup with per-file purposes
$E search "websocket auth"        # ranked keyword search over summaries (path hits weighted)
$E search "retry" --full          # same, with full entries
$E files iris/cli.py backend/     # full entries: exact path, suffix, or directory prefix
$E symbol ConnectionManager       # locate a class, method, or function
$E imports iris/utils/utils.py    # what it imports, and what imports it
$E list --dir frontend/src        # compact path + one-line purpose
```

- **"What does this repo do?"** → `stats`, then `tree --depth 1`. Read the README
  and the entry points it names.
- **"How does X work?" / "Where is Y?"** → `search "<terms>"`, then `files` on the
  top hits, then **read those files** for the actual answer.
- **Named symbol** → `symbol <name>`, then read the file it points to.

`tree.txt` and `file_paths.txt` sit next to the overview in the cache and are
cheap plain-text orientation if you prefer them to `stats`/`tree`.

`codebase_overview.json` is a flat JSON object: relative file path → summary entry.
One entry per indexed file. Every entry has exactly these six keys. Here is its
schema which could be useful if you'd like to query it using your own ways.
`references/details.md` has more detailed information about `codebase_overview.json`.

| Field | Type | Notes |
|---|---|---|
| `purpose` | string | Prose summary of the file. The main search target. |
| `genai_system` | `"Yes"` / `"No"` | Whether the file is part of a GenAI system. |
| `has_bugs` | `"No bugs"` / `"Potential bugs"` | LLM's impression at index time. A hint for where to look, never evidence. |
| `imported_files` | list of strings | Repo-relative paths this file imports based on LLM's understanding. |
| `classes` | object | Class name → `{purpose, methods{name → doc}}`. Empty `{}` for non-code files. |
| `functions` | object | Function name → docstring-ish summary. Empty `{}` for non-code files. |

If the extraction returns not enough useful information, use Grep or other tools
in addition. An empty index result means "not indexed", not "does not exist"
— files added after the last index, or excluded by `ignore_patterns`, are simply
absent.

#### 2b. Artifact index (only when one exists)

`extract_artifacts.py` is the artifact counterpart, with the same "pull only what
the question needs" discipline. `artifact_overview.json` is small compared to the
codebase overview, but the extracted text behind it is not.

```bash
A="python3 {skill_dir}/scripts/extract_artifacts.py --repo <repo_root>"

$A stats                              # orientation: counts by phase, type, format
$A tree                               # phase → type rollup with per-artifact purposes
$A search "cost estimate"             # ranked keyword search over summaries and topics
$A search "migration" --phase during-project     # same, filtered
$A files MedAgents_Cost_Analysis.xlsx # full summary entries (exact path, filename, or directory)
$A content during-project/reports/cost.xlsx      # EXTRACTED TEXT — the actual content
$A list --type meetings               # compact path + one-line purpose
```

- **"What was decided / discussed / estimated?"** → `search "<terms>"`, then
  `content` on the top hits. The summary routes; the extracted text answers.
- **"What material exists for this project?"** → `stats`, then `tree`.
- **Phase-scoped questions** ("before we started", "after handoff") → `list`
  or `search` with `--phase pre-project` / `during-project` / `post-project`.

`content` prints the extracted text from `extracted_artifacts/<path>.md`,
truncated at `--max-chars` (default 20000) so a long report cannot flood context.
Raise it, or read the printed file path directly, when you need more.

Each entry in `artifact_overview.json` has these seven keys. `references/details.md`
covers the schema in full.

| Field | Type | Notes |
|---|---|---|
| `purpose` | string | One-line reason the artifact exists. Main search target. |
| `summary` | string | Longer prose summary of the content. |
| `key_topics` | list of strings | Topics the LLM pulled out; searchable. |
| `project_phase` | string | `pre-project` / `during-project` / `post-project` / `unclassified`, from the folder layout. |
| `source_material_type` | string | `meetings`, `presentations`, `reports`, `design_docs`, `readouts`, `technical_docs`, `roadmap`, `production_readiness`, `constraints`, or `unclassified`. |
| `file_format` | string | `pptx`, `docx`, `xlsx`, `pdf`, `md`, `txt`, `mp4`, … |
| `related_artifacts` | list of strings | Other artifacts the LLM thought were related. A hint, not a guarantee. |

Two absences that are not errors: an artifact whose format is unsupported is
never indexed, and a video indexed without transcription enabled has
metadata-only content. `knowledge_base.md` in the cache is an assembled copy for
human review — do not load it for retrieval; it is the whole corpus in one file.

### Step 3. Route, verify, then answer

The indexes gave you candidates. Build the answer from the source those
candidates point at, unless the question is high level enough that the summaries
genuinely suffice:

- **Code candidates** → read the live files.
- **Artifact candidates** → read their extracted text (`content`). Do not quote a
  number, date, or decision that you only saw in an artifact summary.

For a question spanning both, keep the two straight in the answer: what the
artifacts *say was intended* and what the code *currently does* are different
claims, and where they disagree is usually the interesting part.

Mention staleness only when it affects the answer — a stale-cache caveat on
something you verified live is noise. If the artifact index was `unverified`
(unknown or missing `artifact_dir`) and the answer leans on artifact content, one
short clause is enough.

## Task 2 — Setup: indexing a repo that has no cache

This is a normal, expected path, not an error — most repos a user opens have
never been indexed. Anyone who has this skill installed almost certainly has an
IRIS clone locally, so indexing is usually possible.

Start by checking the environment — read-only, no cost, no writes:

```bash
bash {skill_dir}/scripts/iris_setup_lite.sh --check --repo <repo_root>
```

It reports the interpreter, credentials, the codebase cache, and the artifact
side: whether an artifact index exists, whether an `artifact_dir` is known, and
roughly how many artifacts sit in it.

Then branch on its exit code:

- **Exit 0** (`iris` importable): indexing is possible. **Ask the user how they
  want to proceed**, and make the trade-off concrete — quote the file count from
  the staleness check's `unindexed_repo` output:

  > This repo isn't indexed yet (~340 files). I can index it first — a few
  > minutes and some Bedrock cost — and then answer from the index, which is
  > faster and better-grounded for questions like this. Or I can answer right
  > now by reading the code directly, and you can index later. Which do you
  > prefer?

  Do not decide this silently in either direction. Indexing spends the user's
  money; skipping it without saying so hides a better option. If they choose to
  index:

  ```bash
  bash {skill_dir}/scripts/iris_setup_lite.sh --repo <repo_root>

  # or, to index project artifacts in the same run:
  bash {skill_dir}/scripts/iris_setup_lite.sh --repo <repo_root> \
       --artifact-dir /path/to/artifacts
  ```

  It writes `.iris_cache/iris_skill_config.yaml` with `codebase_dir` derived
  from the repo root on every run, then indexes, then registers the repo so it
  is findable from any working directory later. It deliberately does not use
  `iris prepare -c <dir>`: IRIS resolves the output directory from the config's
  `codebase_dir` in preference to that flag, so the bare CLI flag can write the
  cache into the wrong repo.

  Indexing is incremental, so re-running it later is cheap.

  **Artifacts are indexed only when a directory is named.** Unlike
  `codebase_dir`, `artifact_dir` cannot be derived from anything — it is a path
  only the user knows. The script resolves it from `--artifact-dir`, then
  `$IRIS_ARTIFACT_DIR`, then the value a previous run recorded in the skill
  config, then the IRIS clone's `config.yaml` when that config describes this
  repo — and indexes code alone when none of those produce a directory. So:

  - The user already mentioned an artifact/docs folder, or the `--check` output
    shows one → include it, no need to ask again.
  - A previous run recorded one → it is reused automatically. Nothing to do.
  - Nothing is known → **do not go hunting for one, and do not ask by default.**
    Index the codebase. Mention artifacts only if the question that triggered
    this was about project context (decisions, meetings, requirements) rather
    than code:

    > Indexed the codebase. If you also keep project material somewhere —
    > meeting notes, presentations, reports — point me at that folder and I can
    > index it too, which is what would answer this kind of question best.

  The path is written into the skill config, so it only needs supplying once per
  repo per machine. Note it is absolute and machine-specific: teammates who
  clone a committed `.iris_cache/` inherit the artifact *index* (summaries and
  extracted text) but not the directory, and can re-point it with
  `--artifact-dir` when they want to refresh.

  Pass `--no-artifacts` to index code only for one run without discarding the
  recorded path.

- **Exit 3** (no interpreter found that can import `iris`): **this does not mean
  IRIS is missing.** It means nothing recorded where it is. The script checks
  `--python`/`IRIS_PYTHON`, `~/.iris/config.json`, PATH, and IRIS clones sitting
  beside the repo — it does not scan the filesystem, because several venvs on one
  machine can import `iris` and guessing wrong causes confusing failures later.
  Most users who have this skill installed *do* have a clone.

  So **ask the user where their IRIS clone is** before suggesting anything else:

  > I could not find your IRIS installation automatically. If you have the IRIS
  > repo locally, what is its path? (I'll remember it for next time.) Otherwise
  > I can answer this question by reading the code directly.

  Then retry with that path — either form works:

  ```bash
  bash {skill_dir}/scripts/iris_setup_lite.sh --repo <repo_root> \
       --python /path/to/iris-clone/.venv/bin/python
  ```

  The interpreter is saved to `~/.iris/config.json` on first success, so this is
  a once-per-machine question. If they give a repo path rather than an
  interpreter, try `<that-path>/.venv/bin/python` and `<that-path>/venv/bin/python`.

  Only if they confirm they have no clone at all, give the install path — it is
  not on PyPI, so it must be cloned:

  ```bash
  git clone https://github.com/aws-samples/sample-indexed-repository-intelligence-system
  cd sample-indexed-repository-intelligence-system && ./deploy.sh   # option 5
  ```

  Never claim you can install the `iris` package yourself. And whichever way this
  goes, **answer the user's question natively this turn** — do not leave them
  holding only a setup instruction.

- **Exit 4** (no AWS credentials): indexing needs credentials, querying an
  existing cache does not. Tell them to run `aws configure` or `aws sso login`,
  or set `AWS_PROFILE` — then answer the question natively this turn.

If code summarization is possible, ask the user whether to proceed with it. If the user
prefers not to index now, proceed without IRIS. Do not proceed without IRIS unless you
have explicit consent from the user, when the iris-query skill is invoked.

After any successful indexing run, recommend the user to **commit `.iris_cache/`
and the skill folder**, if they would like their teammates get this for free
 from a plain `git clone`, as they will not think of it unprompted. That covers
the artifact index too — `artifact_overview.json` and `extracted_artifacts/`
travel with the repo even though the artifact directory itself does not.

## Task 3 — Manual refresh

When the user asks to refresh, reindex, or update the IRIS index, or when they
accept the offer after a `large_drift` verdict (codebase or artifact):

```bash
bash {skill_dir}/scripts/iris_setup_lite.sh --repo <repo_root>
```

This refreshes **both indexes** when the skill config records an `artifact_dir`,
and the codebase alone when it does not. Both sides are incremental and
idempotent — only changed files and changed artifacts reach Bedrock, and it is a
no-op when nothing changed. Requires the package plus credentials; the script
fails with specific guidance when either is absent.

Refresh variations, all optional:

```bash
# first time artifacts are being indexed for this repo, or re-pointing the path
... --repo <repo_root> --artifact-dir /path/to/artifacts

# skip artifacts this run (keeps the recorded path for next time)
... --repo <repo_root> --no-artifacts
```

If the artifact verdict was `artifact_dir_missing` or `artifact_dir_unknown`, a
refresh needs `--artifact-dir` before it can touch artifacts — the recorded path
is not reachable here. Say that rather than running a refresh that quietly
updates only the codebase. Artifact indexing costs more per file than code
(extraction, OCR, and transcription on top of summarization), so it is worth
naming as its own cost when asking.

**Never run this automatically.** Not after file edits, not on a schedule, not
"to be helpful". It costs Bedrock calls per changed file, needs credentials the
user may not have, and summaries of half-finished code are worse than slightly
stale ones. Freshness is handled at read time by Step 1.

One opt-in exception: if `IRIS_AUTO_PREPARE=1` is set in the environment, you may
refresh on `large_drift` — from either verdict — without asking, still failing
soft if the package or credentials are missing. Default is off.

For teams that want an always-fresh committed cache, the correct home for
event-driven refresh is a pre-commit hook or CI job running the indexing step —
not this skill. See `references/details.md`.

Kiro users get a manual refresh button by copying
`templates/iris_reindex_manual.kiro.hook` into `.kiro/hooks/`. Skip that on
other hosts.

## Reliability

- Verify after every setup or refresh step that the expected files exist; on
  failure report the **specific missing path**, not a generic error.
- Attempt any script at most **twice** before escalating to the user with the
  actual error output.
- Anything optional that fails — staleness check, extraction, indexing —
  degrades to native exploration. The user's question still gets an answer.
- The artifact layer degrades one step further: a missing, empty, or broken
  artifact index never blocks the codebase answer. Answer from the code and say
  what was unavailable, in one clause, only if the question needed it.

`references/details.md` covers both overview JSON schemas, every cache file, the
troubleshooting table for known error strings, and configuration notes.
