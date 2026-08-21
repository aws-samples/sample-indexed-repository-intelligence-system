#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Lightweight IRIS setup / refresh for the iris-query skill.
#
# Scope, deliberately narrow: this script FINISHES setup, it does not own it.
# It writes a skill-local config and runs indexing. It never installs the iris
# package (not on PyPI) and never modifies user code.
#
# Two modes:
#   --check    Report environment status only. No writes, no cost. Always safe.
#   (default)  Write config + run indexing. Costs Bedrock calls; needs AWS creds.
#
# Artifacts are optional. When an artifact directory is known — --artifact-dir,
# $IRIS_ARTIFACT_DIR, or the value recorded in a previous run's skill config —
# project artifacts are indexed alongside the codebase. Otherwise only the
# codebase is indexed.
#
# Usage:
#   iris_setup_lite.sh --check [--repo DIR] [--artifact-dir DIR]
#   iris_setup_lite.sh [--repo DIR] [--python PATH] [--yes]
#                      [--artifact-dir DIR | --no-artifacts]
#
# Windows: run under Git Bash or WSL —
#   bash "/path/to/skills/iris-query/scripts/iris_setup_lite.sh" --check
#
# Exit codes:
#   0  success
#   1  usage / environment error
#   3  iris package not importable (caller should print install guidance)
#   4  AWS credentials missing
#   5  indexing failed (config was still written; cache may be partial)

set -uo pipefail

REPO_ROOT=""
PYTHON_BIN="${IRIS_PYTHON:-}"
CHECK_ONLY=false
ASSUME_YES=false
# Artifact directory for the optional artifact index. Empty means "not known
# yet"; resolution order is --artifact-dir, $IRIS_ARTIFACT_DIR, then the value
# recorded in the existing skill config.
ARTIFACT_DIR="${IRIS_ARTIFACT_DIR:-}"
ARTIFACT_DIR_SOURCE=""
NO_ARTIFACTS=false

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅ $1${NC}"; }
err()  { echo -e "${RED}❌ $1${NC}" >&2; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
info() { echo -e "${BLUE}ℹ️  $1${NC}"; }

usage() {
    sed -n '5,31p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --check)  CHECK_ONLY=true; shift ;;
        --repo)   REPO_ROOT="${2:-}"; shift 2 ;;
        --python) PYTHON_BIN="${2:-}"; shift 2 ;;
        --artifact-dir) ARTIFACT_DIR="${2:-}"; ARTIFACT_DIR_SOURCE="--artifact-dir"; shift 2 ;;
        --no-artifacts) NO_ARTIFACTS=true; shift ;;
        --yes|-y) ASSUME_YES=true; shift ;;
        -h|--help) usage 0 ;;
        *) err "Unknown argument: $1"; usage 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Resolve the repo root. Derived from the filesystem, never from a stored
# config value: a committed config carries the indexer's absolute path, which
# is wrong on every other machine.
# ---------------------------------------------------------------------------
if [ -z "$REPO_ROOT" ]; then
    if REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
        :
    else
        REPO_ROOT="$PWD"
    fi
fi
if [ ! -d "$REPO_ROOT" ]; then
    err "Not a directory: $REPO_ROOT"
    exit 1
fi
REPO_ROOT="$(cd "$REPO_ROOT" && pwd)"
REPO_NAME="$(basename "$REPO_ROOT")"

# ---------------------------------------------------------------------------
# Find a Python interpreter that can import iris.
# ---------------------------------------------------------------------------
can_import_iris() {
    [ -n "${1:-}" ] && [ -x "$1" ] && "$1" -c "import iris" >/dev/null 2>&1
}

# Where the remembered interpreter lives. Shares ~/.iris with the repo registry
# so one directory holds all cross-session state, and survives skill upgrades.
iris_config_file() {
    echo "${IRIS_HOME:-$HOME/.iris}/config.json"
}

read_config_field() {
    local field="$1" cfg; cfg="$(iris_config_file)"
    [ -f "$cfg" ] || return 1
    # Deliberately not jq: this must work on a machine with nothing installed.
    sed -n "s/.*\"$field\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$cfg" | head -1
}

read_remembered_python() {
    read_config_field python
}

remember_python() {
    local py="$1" cfg repo; cfg="$(iris_config_file)"
    # Preserve iris_repo if deploy.sh (or an earlier run) recorded it — this
    # function is also the config's only writer on the skill side, so dropping
    # the field would discard information the installer knew.
    repo="$(read_config_field iris_repo 2>/dev/null || true)"
    mkdir -p "$(dirname "$cfg")" 2>/dev/null || return 1
    if [ -n "$repo" ]; then
        printf '{\n  "version": 1,\n  "python": "%s",\n  "iris_repo": "%s"\n}\n' \
            "$py" "$repo" > "$cfg" 2>/dev/null || return 1
    else
        printf '{\n  "version": 1,\n  "python": "%s"\n}\n' "$py" > "$cfg" 2>/dev/null || return 1
    fi
    return 0
}

# Bounded breadth-first scan for a venv that can import iris.
#
# Exists because clones are routinely nested far deeper than a fixed probe list
# anticipates (the author's own sits 6 levels below $HOME). Depth-limited and
# prune-heavy so it stays fast on a large home directory: -prune skips the
# expensive subtrees entirely rather than filtering after the fact.
# NOTE: a filesystem scan for "any venv that can import iris" used to live here.
# It was removed deliberately. On a developer machine several venvs can import
# iris — an IRIS clone, an editable install of a sibling checkout, a general
# project venv — and a directory walk picks among them by traversal order, not by
# correctness. That silently selected the wrong interpreter in testing. It also
# cost seconds on a large $HOME while only ever guessing at something the user
# can state exactly. deploy.sh now records the authoritative path at install
# time (~/.iris/config.json), so the honest fallback when that is absent is to
# ask, not to guess.

find_python() {
    # 1. Explicit --python / $IRIS_PYTHON wins.
    if [ -n "$PYTHON_BIN" ]; then
        if can_import_iris "$PYTHON_BIN"; then
            echo "$PYTHON_BIN"; return 0
        fi
        warn "Specified interpreter cannot import iris: $PYTHON_BIN" >&2
    fi

    # 2. An interpreter recorded by deploy.sh, or remembered from a previous
    # successful run. Checked early: it is a single exec and makes every later
    # session instant regardless of working directory.
    local remembered
    if remembered="$(read_remembered_python)" && [ -n "$remembered" ]; then
        if can_import_iris "$remembered"; then
            echo "$remembered"; return 0
        fi
        # Stale (venv rebuilt, python upgraded). Before re-searching, try the
        # recorded clone directly — the repo usually outlives its venv path.
        local recorded_repo venv exe
        recorded_repo="$(read_config_field iris_repo 2>/dev/null || true)"
        if [ -n "$recorded_repo" ] && [ -d "$recorded_repo" ]; then
            for venv in ".venv" "venv"; do
                for exe in "bin/python" "Scripts/python.exe"; do
                    if can_import_iris "$recorded_repo/$venv/$exe"; then
                        echo "$recorded_repo/$venv/$exe"; return 0
                    fi
                done
            done
        fi
    fi

    # 3. Whatever python is already on PATH (covers an activated venv).
    for candidate in python3 python; do
        local resolved
        resolved="$(command -v "$candidate" 2>/dev/null)" || continue
        if can_import_iris "$resolved"; then
            echo "$resolved"; return 0
        fi
    done

    # 4. The `iris` console script implies a venv next to it.
    local cli
    if cli="$(command -v iris 2>/dev/null)"; then
        local sibling="$(dirname "$cli")/python"
        if can_import_iris "$sibling"; then
            echo "$sibling"; return 0
        fi
    fi

    # 5. A named IRIS clone immediately beside the repo, or one level up. This is
    # the layout deploy.sh itself produces, so it is a strong signal rather than
    # a guess — and it is only a handful of execs. Deliberately narrow: it
    # matches known clone directory names, never "any venv that has iris".
    local base clone venv exe path
    for base in "$REPO_ROOT" "$REPO_ROOT/.." "$REPO_ROOT/../.."; do
        [ -d "$base" ] || continue
        for clone in "sample-indexed-repository-intelligence-system" \
                     "code-intelligence" "iris" "IRIS"; do
            for venv in ".venv" "venv"; do
                for exe in "bin/python" "Scripts/python.exe"; do
                    path="$base/$clone/$venv/$exe"
                    if can_import_iris "$path"; then
                        echo "$path"; return 0
                    fi
                done
            done
        done
    done

    # No filesystem scan. See the note above scan_for_iris_python's former home:
    # guessing among several iris-capable venvs picked wrongly in practice. When
    # the recorded config is absent, the caller asks the user instead.
    return 1
}

IRIS_REPO_URL="https://github.com/aws-samples/sample-indexed-repository-intelligence-system"

print_install_guidance() {
    # Never claim IRIS is absent from the machine — it usually is not. All that
    # is known is that no interpreter *this script could find* imports iris, and
    # the most common reason is a clone nested deeper than the search reaches.
    cat <<EOF

Could not find a Python interpreter that can import iris.
This does NOT necessarily mean IRIS is missing — nothing recorded its location
(checked: --python/IRIS_PYTHON, $(iris_config_file), PATH, and IRIS clones beside
this repo). The location is not guessed at, because several venvs on one machine
can import iris and picking the wrong one produces confusing failures later.

ASK THE USER where their IRIS clone is, then re-run with that path:

  bash <this-script> --python /path/to/iris-clone/.venv/bin/python --repo <repo>
  # or: export IRIS_PYTHON=/path/to/iris-clone/.venv/bin/python

The path is remembered in $(iris_config_file) after the first success, so this
only needs answering once per machine.

Only if the user has no clone at all — the package is not on PyPI:

  git clone $IRIS_REPO_URL
  cd sample-indexed-repository-intelligence-system
  ./deploy.sh          # then pick "Agent Skill Installation"

Querying an EXISTING cache needs none of this — only building one does.
EOF
}

CACHE_PARENT="$REPO_ROOT/.iris_cache"
SKILL_CONFIG="$CACHE_PARENT/iris_skill_config.yaml"

# This script's own directory, so it can reuse the sibling Python helpers.
SELF_DIR_EARLY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Resolve the optional artifact directory.
#
# Unlike codebase_dir, artifact_dir cannot be derived from the repo root: it is
# an arbitrary path the user chose, usually outside the repo. So it has to be
# supplied once and then remembered in the skill config, which is also where
# check_staleness.py looks when it verifies artifact freshness.
#
# Placeholder shipped in config_template.yaml, treated as "not configured" —
# same rule as iris/artifacts/__init__.py:resolve_artifact_dir.
# ---------------------------------------------------------------------------
ARTIFACT_PLACEHOLDER="/path/to/your/artifacts"

# Deliberately not a YAML parser: these files are flat `key: value` scalars, and
# this must work on a machine with nothing installed.
read_yaml_scalar() {
    local file="$1" key="$2"
    [ -f "$file" ] || return 1
    sed -n "s/^${key}[[:space:]]*:[[:space:]]*\(.*\)$/\1/p" "$file" \
        | head -1 | tr -d "\"'" | sed 's/[[:space:]]*$//'
}

# artifact_dir from the IRIS clone's own config.yaml — but only when that config
# describes THIS repo. That config covers one project at a time, so its
# artifact_dir belongs to whatever codebase_dir it names; using it for a
# different repo would index an unrelated project's artifacts into this cache.
read_iris_config_artifact_dir() {
    local recorded_repo cfg described described_abs
    recorded_repo="$(read_config_field iris_repo 2>/dev/null || true)"
    [ -n "$recorded_repo" ] || return 1
    cfg="$recorded_repo/config.yaml"
    described="$(read_yaml_scalar "$cfg" codebase_dir || true)"
    [ -n "$described" ] || return 1
    described_abs="$(cd "$described" 2>/dev/null && pwd || true)"
    [ "$described_abs" = "$REPO_ROOT" ] || return 1
    read_yaml_scalar "$cfg" artifact_dir
}

# Resolution order matches check_staleness.py, so a refresh indexes exactly the
# artifacts the staleness check verifies.
if [ "$NO_ARTIFACTS" = true ]; then
    ARTIFACT_DIR=""
    ARTIFACT_DIR_SOURCE="--no-artifacts"
elif [ -n "$ARTIFACT_DIR" ]; then
    ARTIFACT_DIR_SOURCE="${ARTIFACT_DIR_SOURCE:-IRIS_ARTIFACT_DIR}"
else
    for candidate_source in "skill config (previous run)" "IRIS config.yaml"; do
        case "$candidate_source" in
            "skill config"*) CANDIDATE="$(read_yaml_scalar "$SKILL_CONFIG" artifact_dir || true)" ;;
            *)               CANDIDATE="$(read_iris_config_artifact_dir || true)" ;;
        esac
        case "${CANDIDATE:-}" in
            ""|null|Null|NULL|"~"|"$ARTIFACT_PLACEHOLDER") continue ;;
            *) ARTIFACT_DIR="$CANDIDATE"; ARTIFACT_DIR_SOURCE="$candidate_source"; break ;;
        esac
    done
fi
ARTIFACT_DIR_SOURCE="${ARTIFACT_DIR_SOURCE:-none}"

# Expand a leading ~ that survived quoting, then check the path is real. What
# happens next depends on who supplied it, because the two cases mean different
# things: a path the user just typed that does not exist is a typo worth failing
# on, while a recorded path that does not exist is the expected state on a
# machine that cloned someone else's cache — that must degrade to codebase-only,
# not block a refresh.
ARTIFACT_DIR_MISSING=false
if [ -n "$ARTIFACT_DIR" ]; then
    ARTIFACT_DIR="${ARTIFACT_DIR/#\~/$HOME}"
    if [ -d "$ARTIFACT_DIR" ]; then
        ARTIFACT_DIR="$(cd "$ARTIFACT_DIR" && pwd)"
    else
        ARTIFACT_DIR_MISSING=true
        case "$ARTIFACT_DIR_SOURCE" in
            "--artifact-dir"|"IRIS_ARTIFACT_DIR")
                if [ "$CHECK_ONLY" != true ]; then
                    err "Artifact directory does not exist: $ARTIFACT_DIR (via $ARTIFACT_DIR_SOURCE)"
                    echo "Pass a real path with --artifact-dir, or --no-artifacts to index code only." >&2
                    exit 1
                fi
                ;;
            *)
                # Recorded elsewhere and unreachable here: keep going without it.
                MISSING_ARTIFACT_DIR="$ARTIFACT_DIR"
                ARTIFACT_DIR=""
                ;;
        esac
    fi
fi

report_status() {
    echo ""
    info "Repo root:  $REPO_ROOT"

    # Existing cache, discovered by glob — never by rebuilding the folder name.
    local found_cache=""
    while IFS= read -r overview; do
        [ -n "$overview" ] || continue
        found_cache="$(dirname "$overview")"
        break
    done < <(find "$CACHE_PARENT" -maxdepth 2 -name codebase_overview.json 2>/dev/null | sort)

    if [ -n "$found_cache" ]; then
        ok "Cache present: $found_cache"
        if [ "$(basename "$found_cache")" != "$REPO_NAME" ]; then
            info "Cache folder is '$(basename "$found_cache")' but repo is '$REPO_NAME' — normal for a renamed clone; queries still work."
        fi
    else
        warn "No cache found under $CACHE_PARENT — this repo is not indexed yet"
        # Show the scale up front: indexing cost scales with file count, and the
        # user is about to be asked whether to spend it.
        if [ -f "$SELF_DIR_EARLY/check_staleness.py" ]; then
            local probe_py count
            probe_py="$(command -v python3 || command -v python || true)"
            if [ -n "$probe_py" ]; then
                count="$("$probe_py" -c "
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, '$SELF_DIR_EARLY')
try:
    from check_staleness import count_indexable_files
    print(count_indexable_files('$REPO_ROOT'))
except Exception:
    print('')
" 2>/dev/null)"
                [ -n "$count" ] && info "Indexable files: ~$count (indexing cost scales with this)"
            fi
        fi
    fi

    # Artifacts: optional, so every state here is legitimate. Report the index
    # and the directory separately — a cache can carry artifact summaries while
    # the directory that produced them is absent (a teammate's committed cache).
    if [ -n "$found_cache" ] && [ -f "$found_cache/artifact_overview.json" ]; then
        local artifact_count
        artifact_count="$(grep -c '"purpose"' "$found_cache/artifact_overview.json" 2>/dev/null || echo "?")"
        ok "Artifact index present (~$artifact_count artifacts summarized)"
    else
        info "No artifact index — this repo is codebase-only so far"
    fi

    if [ "$NO_ARTIFACTS" = true ]; then
        info "Artifacts disabled for this run (--no-artifacts)"
    elif [ "$ARTIFACT_DIR_MISSING" = true ]; then
        case "$ARTIFACT_DIR_SOURCE" in
            "--artifact-dir"|"IRIS_ARTIFACT_DIR")
                warn "Artifact dir does not exist: $ARTIFACT_DIR (via $ARTIFACT_DIR_SOURCE)"
                info "Fix the path before indexing — an indexing run would refuse it."
                ;;
            *)
                warn "Recorded artifact dir is not reachable here: ${MISSING_ARTIFACT_DIR:-?} (via $ARTIFACT_DIR_SOURCE)"
                info "Normal for a cache built on another machine. Existing artifact summaries"
                info "stay queryable; pass --artifact-dir DIR to refresh them from this machine."
                ;;
        esac
    elif [ -n "$ARTIFACT_DIR" ]; then
        ok "Artifact dir: $ARTIFACT_DIR (via $ARTIFACT_DIR_SOURCE)"
        if [ -f "$SELF_DIR_EARLY/check_staleness.py" ]; then
            local probe_py acount
            probe_py="$(command -v python3 || command -v python || true)"
            if [ -n "$probe_py" ]; then
                acount="$("$probe_py" -c "
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, '$SELF_DIR_EARLY')
try:
    from check_staleness import count_indexable_artifacts
    print(count_indexable_artifacts('$ARTIFACT_DIR'))
except Exception:
    print('')
" 2>/dev/null)"
                [ -n "$acount" ] && info "Indexable artifacts: ~$acount (PPTX/DOCX/XLSX/PDF/MD/TXT/video)"
            fi
        fi
    else
        info "No artifact dir known — pass --artifact-dir DIR to index project artifacts too"
    fi

    if [ -f "$SKILL_CONFIG" ]; then
        ok "Skill config present: $SKILL_CONFIG"
    else
        info "No skill config yet (written on first indexing run)"
    fi

    if PY="$(find_python)"; then
        ok "iris package importable via: $PY"
        local version
        version="$("$PY" -c "import importlib.metadata as m; print(m.version('iris'))" 2>/dev/null || echo "unknown")"
        info "iris version: $version"
        IRIS_AVAILABLE=true
        # Remember it so later sessions — which may start from any directory,
        # with a different PATH — resolve instantly instead of re-searching.
        local previously; previously="$(read_remembered_python 2>/dev/null || true)"
        if [ "$previously" != "$PY" ] && remember_python "$PY"; then
            info "Remembered this interpreter in $(iris_config_file)"
        fi
    else
        # Careful wording: the search failed, which is not the same as IRIS
        # being absent. Claiming the latter sends users off to re-clone
        # something they already have.
        warn "Could not find an interpreter that can import iris."
        info "IRIS may still be installed — the search may just not have reached it."
        info "Ask the user for their IRIS clone path and pass --python (or IRIS_PYTHON)."
        IRIS_AVAILABLE=false
    fi

    if [ -n "${AWS_ACCESS_KEY_ID:-}" ] || [ -n "${AWS_PROFILE:-}" ] || [ -f "$HOME/.aws/credentials" ]; then
        ok "AWS credentials appear configured"
        AWS_AVAILABLE=true
    else
        warn "No AWS credentials detected — indexing would fail."
        AWS_AVAILABLE=false
    fi
    echo ""
}

if [ "$CHECK_ONLY" = true ]; then
    report_status
    if [ "${IRIS_AVAILABLE:-false}" != true ]; then
        print_install_guidance
        exit 3
    fi
    exit 0
fi

# ---------------------------------------------------------------------------
# Indexing path.
# ---------------------------------------------------------------------------
report_status

if [ "${IRIS_AVAILABLE:-false}" != true ]; then
    err "Cannot index: the iris package is not importable."
    print_install_guidance >&2
    exit 3
fi

if [ "${AWS_AVAILABLE:-false}" != true ]; then
    err "Cannot index: no AWS credentials found."
    echo "Configure credentials (aws configure / aws sso login / AWS_PROFILE), then retry." >&2
    exit 4
fi

if [ "$ASSUME_YES" != true ]; then
    warn "Indexing calls AWS Bedrock and incurs cost (only changed files are processed)."
    if [ -n "$ARTIFACT_DIR" ]; then
        warn "Artifacts in $ARTIFACT_DIR will be indexed as well."
    fi
    printf "Proceed with indexing %s? [y/N]: " "$REPO_ROOT"
    read -r reply
    case "${reply:-N}" in
        [Yy]*) ;;
        *) info "Aborted; nothing was written."; exit 0 ;;
    esac
fi

mkdir -p "$CACHE_PARENT" || { err "Could not create $CACHE_PARENT"; exit 1; }

# Write a skill-local config rather than editing the IRIS repo's config.yaml.
# iris merges this over its base config, so models and ignore_patterns are
# inherited while codebase_dir/output_dir point at THIS repo.
# codebase_dir is rewritten every run — that is the drift fix required on the
# regeneration path (a committed config would carry the indexer's path).
# artifact_dir is written explicitly on every run — as a path when one is known,
# as null otherwise. Null is not redundant: this config is merged OVER the IRIS
# clone's config.yaml, so leaving the key out would silently inherit whatever
# artifact_dir that config happens to name, and index some unrelated directory's
# artifacts into this repo's cache.
if [ -n "$ARTIFACT_DIR" ]; then
    ARTIFACT_DIR_LINE="artifact_dir: $ARTIFACT_DIR"
    INDEX_MODE="both"
else
    ARTIFACT_DIR_LINE="artifact_dir: null"
    INDEX_MODE="codebase"
fi

cat > "$SKILL_CONFIG" <<EOF
# Written by the iris-query skill's iris_setup_lite.sh — safe to regenerate.
# codebase_dir is derived from the repo root on every run; do not hand-edit it,
# and do not rely on it after moving or renaming the repo.
codebase_dir: $REPO_ROOT
output_dir: .iris_cache
context_file: null
# artifact_dir: optional. Machine-specific absolute path, so it will not be
# valid for teammates who clone a committed .iris_cache/ — they can re-point it
# with --artifact-dir. null means "index the codebase only".
$ARTIFACT_DIR_LINE
EOF
ok "Wrote skill config: $SKILL_CONFIG"

if [ "$INDEX_MODE" = "both" ]; then
    info "Indexing $REPO_ROOT + artifacts in $ARTIFACT_DIR (incremental — only changed files call Bedrock)..."
else
    info "Indexing $REPO_ROOT (incremental — only changed files call Bedrock)..."
fi

# Drive the Python API, not `iris prepare -c`: construct_output_dir() prefers
# the config's codebase_dir over the -c flag, so the CLI flag alone would write
# the cache into the wrong repo. Passing config_path keeps both consistent.
"$PY" - "$SKILL_CONFIG" "$INDEX_MODE" <<'PYEOF'
import sys

config_path, mode = sys.argv[1], sys.argv[2]

# mode is decided by the shell above: "both" when an artifact directory is known,
# "codebase" otherwise. Never left to the merged config to decide, so a run can
# only ever index the artifacts this script was pointed at.
try:
    from iris.api import index_codebase_artifacts
except ImportError as exc:
    print(f"Could not import iris.api: {exc}", file=sys.stderr)
    sys.exit(3)

try:
    results = index_codebase_artifacts(config_path=config_path, mode=mode)
except Exception as exc:
    print(f"Indexing raised {type(exc).__name__}: {exc}", file=sys.stderr)
    sys.exit(5)

result = results["codebase_result"]
if result is None:
    print("Indexing returned no codebase result", file=sys.stderr)
    sys.exit(5)


def report(label, res, processed_attr):
    status = getattr(res, "status", "unknown")
    message = getattr(res, "message", "") or ""
    processed = getattr(res, processed_attr, None) or []
    print(f"{label} status: {status}")
    if message:
        print(f"{label} message: {message}")
    if status == "no_op":
        print(f"{label} index already current — nothing to regenerate.")
    else:
        print(f"{label} items processed: {len(processed)}")
        for path in processed[:20]:
            print(f"  ~ {path}")
        if len(processed) > 20:
            print(f"  ... and {len(processed) - 20} more")
    return status


code_status = report("codebase", result, "processed_files")

# Artifacts are optional and secondary: an artifact failure is reported but does
# not fail the run, because the codebase index is what the skill needs at
# minimum. A silent skip would be worse than either.
artifact_result = results.get("artifact_result")
if mode == "both":
    if artifact_result is None:
        print(
            "artifact status: skipped (iris resolved no usable artifact_dir — "
            "check the path exists and holds supported formats)",
            file=sys.stderr,
        )
    else:
        artifact_status = report("artifact", artifact_result, "processed_artifacts")
        if artifact_status == "error":
            print(
                "Artifact indexing failed; the codebase index is unaffected.",
                file=sys.stderr,
            )

sys.exit(0 if code_status in ("update_complete", "no_op") else 5)
PYEOF
INDEX_RC=$?

if [ "$INDEX_RC" -ne 0 ]; then
    err "Indexing failed (exit $INDEX_RC)."
    # Don't promise a queryable cache without checking: a failed run can leave
    # the overview empty, and claiming otherwise sends the assistant to a cache
    # that answers nothing.
    LEFTOVER=""
    while IFS= read -r overview; do
        [ -n "$overview" ] || continue
        if [ -s "$overview" ] && ! grep -q '^[[:space:]]*{[[:space:]]*}[[:space:]]*$' "$overview" 2>/dev/null; then
            LEFTOVER="$(dirname "$overview")"
            break
        fi
    done < <(find "$CACHE_PARENT" -maxdepth 2 -name codebase_overview.json 2>/dev/null | sort)

    if [ -n "$LEFTOVER" ]; then
        info "A previous index is still present and queryable: $LEFTOVER"
        info "It may be stale — check with check_staleness.py before relying on it."
    else
        info "No usable index is present; answer from live code reads for now."
    fi
    exit 5
fi

# Verify the expected artifacts landed, and report the specific missing path.
VERIFIED=""
while IFS= read -r overview; do
    [ -n "$overview" ] || continue
    VERIFIED="$(dirname "$overview")"
    break
done < <(find "$CACHE_PARENT" -maxdepth 2 -name codebase_overview.json 2>/dev/null | sort)

if [ -z "$VERIFIED" ]; then
    err "Indexing reported success but no codebase_overview.json exists under $CACHE_PARENT"
    exit 5
fi
for required in codebase_overview.json file_hashes.json; do
    if [ ! -f "$VERIFIED/$required" ]; then
        err "Expected file missing after indexing: $VERIFIED/$required"
        exit 5
    fi
done

ok "Index ready: $VERIFIED"

# Verify the artifact side separately, and only warn: a missing artifact index
# after an artifact run is a real problem to report, but not a reason to fail a
# successful codebase index.
if [ "$INDEX_MODE" = "both" ]; then
    ARTIFACT_OK=true
    for required in artifact_overview.json artifact_file_hashes.json; do
        if [ ! -f "$VERIFIED/$required" ]; then
            warn "Artifact file missing after indexing: $VERIFIED/$required"
            ARTIFACT_OK=false
        fi
    done
    if [ "$ARTIFACT_OK" = true ]; then
        ok "Artifact index ready: $VERIFIED/artifact_overview.json"
    else
        info "Artifacts are unusable for now; the codebase index still answers questions."
        info "Check that $ARTIFACT_DIR holds supported formats (pptx/docx/xlsx/pdf/md/txt/video)."
    fi
fi

# Record the repo so the skill can find it later even when the assistant's
# working directory is somewhere else entirely (a user-level skill install is
# active in every session, not just sessions opened inside this repo).
# Best-effort: a registry failure must not fail a successful indexing run.
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SELF_DIR/check_staleness.py" ]; then
    REG_PY="$(command -v python3 || command -v python || true)"
    if [ -n "$REG_PY" ]; then
        if "$REG_PY" "$SELF_DIR/check_staleness.py" --repo "$REPO_ROOT" --register >/dev/null 2>&1; then
            ok "Registered this repo for cross-directory queries"
        else
            warn "Could not update the indexed-repo registry (queries still work with --repo)"
        fi
    fi
fi

echo ""
info "Commit .iris_cache/ (and the skill folder) so teammates get this for free —"
info "they then need only 'git clone', with no IRIS install and no AWS access."
if [ "$INDEX_MODE" = "both" ]; then
    info "That includes the artifact index: artifact_overview.json and"
    info "extracted_artifacts/ travel with the repo, even though $ARTIFACT_DIR does not."
fi
