---
name: iris-query
description: >
  Answer questions about a codebase from a precomputed codebase summary file, so
  you start from an existing map of the repo instead of exploring from scratch.
  Especially useful for high-level comprehension: "what does this repo do", "how
  does X work", "where is Y implemented", "explain the architecture", "which
  files handle Z". The summary can answer a sufficiently high-level question on
  its own; more often it tells you which files to read. Works best in repos IRIS
  has already indexed (they contain a .iris_cache/ directory), but ALSO use it in
  an unindexed repo when the user asks a comprehension question — it can index
  the repo first, or answer natively and offer indexing for next time. Also
  handles IRIS summary setup, repair, and manual refresh ("reindex", "refresh the
  IRIS index"). Do NOT use for targeted edits to a file the user already named,
  or for exact string or pattern searches — Read and Grep are better there.
---

# IRIS Query

Answer codebase questions from IRIS's precomputed index, then ground the answer in live code.

IRIS indexes a repo by having an LLM summarize every file, storing the result in
`.iris_cache/<name>/codebase_overview.json`. That index is a **routing table**:
it tells you which files matter for a question so you can skip 10–20 exploratory
tool calls. It is not a source of truth about current code — the working tree is.

Reading the index costs no AWS credentials, no Python environment, and no IRIS
install. Only *regenerating* it does.

## When the index helps, and when it doesn't

| Question type | Approach |
|---|---|
| Purpose, architecture, "where do I start", "which files handle X" | **Index first**, then read the files it points to |
| Exact line-level detail, string/pattern search, debugging a specific error, making edits | **Native Read/Grep only** — the index adds nothing and can mislead |
| "Why" questions spanning files; big-picture → specifics | Index for orientation, then native tools for precision |

Never quote code, cite a line number, or describe a signature from a cached
summary. Summaries are prose written by an LLM at index time; they drift, and
they never contained line numbers to begin with. Read the file.

## Script paths

`{skill_dir}` is the directory containing this SKILL.md. All commands below are
safe: they only read the cache and hash files. Run them without asking
permission. Only `iris_setup_lite.sh` without `--check` costs money, and it
prompts on its own.

**Windows:** run the `.sh` script through Git Bash or WSL —
`bash "{skill_dir}/scripts/iris_setup_lite.sh" --check`. The two Python scripts
are cross-platform; invoke them with `python` instead of `python3` if that is
what is on PATH.

## Task 1 — Codebase Q&A (primary)

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

### Step 1. Check staleness. Every time.

```bash
python3 {skill_dir}/scripts/check_staleness.py --repo <repo_root>
```

This is sub-second local hashing. Run it on every invocation.

It finds the cache by globbing `<repo_root>/.iris_cache/*/codebase_overview.json`.
Don't construct that subdirectory name yourself: it is named after the folder name
*at index time*, which might differ whenever someone clones the repo under another
name. Note it looks only directly under `<repo_root>` — a cache one level down
belongs to a nested repo, and pairing it with the parent tree is what produces
nonsense drift.

Branch on the `VERDICT` line:

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

If the script itself fails — wrong Python, unreadable cache, anything — say so
in one line and fall back to native exploration. A broken index layer must never
leave a question unanswered.

### Step 2. Extract information from the index.

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

### Step 3. Route, verify, then answer

The index gave you candidate files. You often need to build the answer from what
the live code in the candidate files says, unless the question is very high level
and you feel you have enough information by just reading the summaries.

Mention cache staleness only when it affects the answer — a stale-cache caveat
on an answer you verified live is noise.

## Task 2 — Setup: indexing a repo that has no cache

This is a normal, expected path, not an error — most repos a user opens have
never been indexed. Anyone who has this skill installed almost certainly has an
IRIS clone locally, so indexing is usually possible.

Start by checking the environment — read-only, no cost, no writes:

```bash
bash {skill_dir}/scripts/iris_setup_lite.sh --check --repo <repo_root>
```

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
  ```

  It writes `.iris_cache/iris_skill_config.yaml` with `codebase_dir` derived
  from the repo root on every run, then indexes, then registers the repo so it
  is findable from any working directory later. It deliberately does not use
  `iris prepare -c <dir>`: IRIS resolves the output directory from the config's
  `codebase_dir` in preference to that flag, so the bare CLI flag can write the
  cache into the wrong repo.

  Indexing is incremental, so re-running it later is cheap.

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
 from a plain `git clone`, as they will not think of it unprompted.

## Task 3 — Manual refresh

When the user asks to refresh, reindex, or update the IRIS index, or when they
accept the offer after a `large_drift` verdict:

```bash
bash {skill_dir}/scripts/iris_setup_lite.sh --repo <repo_root>
```

Indexing is incremental and idempotent — only changed files reach Bedrock, and
it is a no-op when nothing changed. Requires the package plus credentials; the
script fails with specific guidance when either is absent.

**Never run this automatically.** Not after file edits, not on a schedule, not
"to be helpful". It costs Bedrock calls per changed file, needs credentials the
user may not have, and summaries of half-finished code are worse than slightly
stale ones. Freshness is handled at read time by Step 1.

One opt-in exception: if `IRIS_AUTO_PREPARE=1` is set in the environment, you may
refresh on `large_drift` without asking — still failing soft if the package or
credentials are missing. Default is off.

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

`references/details.md` covers the overview JSON schema, every cache file, the
troubleshooting table for known error strings, and configuration notes.
