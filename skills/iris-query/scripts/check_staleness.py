# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Detect drift between an IRIS cache and the current working tree.

Stdlib-only by design: this runs for consumers who cloned a repo containing a
committed .iris_cache/ and have no venv, no iris package, and no AWS access.

Re-hashes every file tracked in file_hashes.json (SHA-256, mirroring
iris/file_system/file_utils.py:hash_file_content) and reports new / modified /
deleted files plus a drift ratio and a verdict the agent can branch on.

Usage:
    python3 check_staleness.py [--repo DIR] [--cache DIR] [--threshold 0.15]
                               [--json] [--quiet] [--no-new] [--limit N]

Exit codes:
    0  fresh (no drift)
    1  usage / environment error (no cache found, unreadable cache)
    2  stale (any drift, small or large)
"""

import argparse
import fnmatch
import hashlib
import json
import os
import sys
from pathlib import Path

# Mirrors config_template.yaml max_file_size / max_notebook_size. IRIS skips
# oversized files at index time, so they must not be reported as "new" here.
MAX_FILE_SIZE = 2_000_000
MAX_NOTEBOOK_SIZE = 2_000_000_000

# Conservative subset of config_template.yaml ignore_patterns. Used only for
# new-file detection (deleted/modified detection is exact, driven by the cache).
# Kept in sync by hand; over-ignoring here is safer than under-ignoring, since a
# false "new file" would wrongly inflate drift.
DEFAULT_IGNORE_PATTERNS = [
    ".git/",
    ".gitlab/",
    ".github/",
    ".idea/",
    ".vscode/",
    ".iris_cache/",
    ".claude/",
    ".kiro/",
    "__pycache__/",
    ".ruff_cache/",
    ".pytest_cache/",
    ".mypy_cache/",
    "node_modules/",
    "build/",
    "_build/",
    "_templates/",
    "dist/",
    "downloads/",
    "codebase-output/",
    "output/",
    "outputs/",
    "test/",
    "archive/",
    "eggs/",
    "develop-eggs/",
    "*.egg-info/",
    "*.egg",
    "*.py[cod]",
    "*$py.class",
    "*.so",
    ".Python",
    ".installed.cfg",
    ".env/",
    ".venv/",
    ".venv_dev/",
    "env/",
    "venv/",
    "venv_dev/",
    "ENV/",
    ".coverage",
    ".DS_Store",
    "repl_state/",
    "cdk.out/",
    "codebase_artifacts/",
    ".ash/",
    "package-lock.json",
    "uv.lock",
    "*.lock",
    "*.log",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.bmp",
    "*.ico",
    "*.svg",
    "*.zip",
    "*.gz",
    "*.tar",
    "*.jar",
    "*.class",
    "*.exe",
    "*.pdf",
    "*.mp4",
    "*.mov",
]


class IgnoreSpec:
    """Minimal gitignore-style matcher over a pattern list.

    Supports the subset IRIS's own ignore_patterns rely on: directory patterns
    (trailing /), anchored patterns (leading /), glob wildcards, ** segments,
    and negation (!). Not a full gitignore implementation — it exists so
    new-file detection can run without the pathspec dependency.
    """

    def __init__(self, patterns):
        self.rules = []
        for raw in patterns:
            pattern = raw.strip()
            if not pattern or pattern.startswith("#"):
                continue

            negated = pattern.startswith("!")
            if negated:
                pattern = pattern[1:]

            dir_only = pattern.endswith("/")
            pattern = pattern.rstrip("/")

            anchored = pattern.startswith("/") or "/" in pattern.rstrip("/")
            pattern = pattern.lstrip("/")
            if not pattern:
                continue

            self.rules.append((pattern, negated, dir_only, anchored))

    def match(self, rel_path, is_dir):
        """Return True if rel_path (posix, relative to repo root) is ignored."""
        ignored = False
        for pattern, negated, dir_only, anchored in self.rules:
            if (
                dir_only
                and not is_dir
                and not self._matches_parent_dir(rel_path, pattern, anchored)
            ):
                continue
            if self._matches(rel_path, pattern, anchored, dir_only, is_dir):
                ignored = not negated
        return ignored

    def _matches(self, rel_path, pattern, anchored, dir_only, is_dir):
        if dir_only and not is_dir:
            return self._matches_parent_dir(rel_path, pattern, anchored)
        if anchored:
            return fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(
                rel_path, pattern + "/*"
            )
        # Unanchored: match against the basename or any path segment.
        if fnmatch.fnmatch(os.path.basename(rel_path), pattern):
            return True
        return any(fnmatch.fnmatch(part, pattern) for part in rel_path.split("/"))

    def _matches_parent_dir(self, rel_path, pattern, anchored):
        """True when any ancestor directory of rel_path matches the pattern."""
        parts = rel_path.split("/")[:-1]
        for i in range(len(parts)):
            prefix = "/".join(parts[: i + 1])
            if anchored:
                if fnmatch.fnmatch(prefix, pattern):
                    return True
            elif fnmatch.fnmatch(parts[i], pattern):
                return True
        return False


def hash_file_content(path):
    """SHA-256 of file bytes; mirrors iris.file_system.file_utils."""
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        return "unreadable"


def find_cache_dir(repo_root, explicit=None):
    """Locate the IRIS cache directory for repo_root.

    Discovery is by glob, never by reconstructing the subdirectory name from the
    current folder: the subdirectory is named after the folder name at index
    time, which differs when the repo is cloned under another name.

    Only looks at repo_root/.iris_cache/. It deliberately does NOT search
    subdirectories: a cache one level down belongs to a *nested* repo, and
    hashing repo_root against it silently produces meaningless drift figures.
    Use --repo (or the registry) to point at the right repo instead.
    """
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        if (candidate / "codebase_overview.json").is_file():
            return candidate
        raise SystemExit(f"No codebase_overview.json in --cache dir: {candidate}")

    matches = sorted(repo_root.glob(".iris_cache/*/codebase_overview.json"))
    if not matches:
        return None
    # Most recently written cache wins when a repo carries several (e.g. an
    # older cache left behind under a previous folder name).
    newest = max(matches, key=lambda p: p.stat().st_mtime)
    return newest.parent


def registry_path():
    """Location of the indexed-repo registry.

    Lives outside any skill folder so reinstalling or upgrading the skill does
    not wipe it, and so Claude Code and Kiro installs share one registry.
    """
    base = os.environ.get("IRIS_HOME")
    if base:
        return Path(base).expanduser() / "indexed_repos.json"
    return Path.home() / ".iris" / "indexed_repos.json"


def load_registry():
    """Return registered repos that still exist on disk, newest first.

    Entries are validated on read rather than trusted: repos get deleted,
    renamed, and moved, and a stale entry must not send the agent to a path
    that is no longer there.
    """
    path = registry_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    entries = data.get("repos") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return []

    live = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        root = entry.get("root")
        if not root:
            continue
        root_path = Path(root)
        if not root_path.is_dir():
            continue
        # Re-derive the cache by glob instead of trusting the stored path: the
        # cache subdirectory name can change when a repo is re-indexed under a
        # different folder name.
        cache = find_cache_dir(root_path)
        if cache is None:
            continue
        live.append(
            {
                "root": str(root_path.resolve()),
                "cache": str(cache),
                "indexed_at": entry.get("indexed_at"),
            }
        )

    live.sort(key=lambda e: e.get("indexed_at") or "", reverse=True)
    return live


def save_registry_entry(repo_root, indexed_at=None):
    """Record repo_root as indexed. Idempotent; newest entry wins.

    Best-effort by design: a registry write failure must never fail an
    indexing run, since the registry is a convenience for discovery, not a
    source of truth.
    """
    repo_root = Path(repo_root).resolve()
    path = registry_path()
    existing = []
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            existing = data.get("repos") if isinstance(data, dict) else data
            if not isinstance(existing, list):
                existing = []
        except (OSError, json.JSONDecodeError):
            existing = []

    kept = [
        e
        for e in existing
        if isinstance(e, dict) and e.get("root") and Path(e["root"]) != repo_root
    ]
    kept.append({"root": str(repo_root), "indexed_at": indexed_at})

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": 1, "repos": kept}, indent=2), encoding="utf-8"
        )
        return True
    except OSError:
        return False


def find_cache_upward(start):
    """Walk up from start looking for a repo with an .iris_cache/.

    Handles the common case of the working directory being a subdirectory of an
    indexed repo (e.g. cwd is repo/backend/).
    """
    current = Path(start).resolve()
    for candidate in [current, *current.parents]:
        if find_cache_dir(candidate) is not None:
            return candidate
    return None


PROJECT_MARKERS = (
    ".git",
    "package.json",
    "pyproject.toml",
    "setup.py",
    "requirements.txt",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Gemfile",
    "composer.json",
    "CMakeLists.txt",
    "Makefile",
    "*.csproj",
    "*.sln",
)

SOURCE_SUFFIXES = (
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".kt",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".cs",
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".hpp",
    ".swift",
    ".scala",
    ".m",
)


def count_indexable_files(path):
    """Roughly how many files IRIS would summarize under `path`.

    Reuses the same walk and ignore rules as new-file detection, so the number
    shown to a user before they authorise indexing reflects what would actually
    be sent to Bedrock. Approximate by nature — IRIS's live config may differ
    slightly — so callers should present it as "~N".
    """
    path = Path(path)
    try:
        return len(collect_current_files(path, build_ignore_spec(path)))
    except OSError:
        return 0


def looks_like_a_codebase(path, max_probe=400):
    """Is `path` plausibly a code repository in its own right?

    Used to avoid a specific wrong answer: if the working directory is clearly
    its own project but has no IRIS cache, falling back to "the only registered
    repo" would answer confidently about a completely different codebase. In
    that situation the honest reply is "this repo is not indexed — want me to
    index it?", not a silent substitution.

    Deliberately cheap and shallow: a marker file, or any source file within two
    levels. Over-detecting is safe (it produces an offer to index); the
    dangerous direction is under-detecting.
    """
    path = Path(path)
    try:
        for marker in PROJECT_MARKERS:
            if "*" in marker:
                if any(path.glob(marker)):
                    return True
            elif (path / marker).exists():
                return True

        seen = 0
        for entry in path.iterdir():
            seen += 1
            if seen > max_probe:
                break
            if entry.is_file() and entry.suffix.lower() in SOURCE_SUFFIXES:
                return True
            if entry.is_dir() and not entry.name.startswith("."):
                try:
                    for child in entry.iterdir():
                        seen += 1
                        if seen > max_probe:
                            break
                        if child.is_file() and child.suffix.lower() in SOURCE_SUFFIXES:
                            return True
                except OSError:
                    continue
    except OSError:
        return False
    return False


class RepoResolution:
    """Outcome of resolving which indexed repo a question is about."""

    def __init__(
        self,
        repo_root=None,
        cache_dir=None,
        how="",
        candidates=None,
        unindexed_cwd=None,
    ):
        self.repo_root = repo_root
        self.cache_dir = cache_dir
        self.how = how
        self.candidates = candidates or []
        # Set when the working directory is itself an unindexed codebase — the
        # signal that the right move is to offer indexing, not to substitute
        # some other repo's cache.
        self.unindexed_cwd = unindexed_cwd

    @property
    def ok(self):
        return self.repo_root is not None and self.cache_dir is not None


def resolve_repo(explicit_repo=None, explicit_cache=None, cwd=None):
    """Decide which indexed repo to operate on.

    Escalating strategy, because the assistant's working directory is often
    unrelated to the indexed repo — the skill may be installed user-level while
    Claude Code sits in a different project entirely:

      1. --repo given            -> honour it exactly (error if not indexed)
      2. cwd or an ancestor      -> nearest enclosing indexed repo
      3. registry, cwd inside    -> the registered repo containing cwd
      4. registry, single entry  -> that one, stated explicitly
      5. registry, several       -> ambiguous; return candidates to choose from
      6. nothing               -> unresolved
    """
    cwd = Path(cwd or Path.cwd()).resolve()

    if explicit_repo:
        root = Path(explicit_repo).expanduser().resolve()
        cache = find_cache_dir(root, explicit_cache)
        return RepoResolution(repo_root=root, cache_dir=cache, how="explicit --repo")

    if explicit_cache:
        # A cache without a repo: assume cwd is the tree it describes.
        return RepoResolution(
            repo_root=cwd,
            cache_dir=find_cache_dir(cwd, explicit_cache),
            how="explicit --cache against cwd",
        )

    enclosing = find_cache_upward(cwd)
    if enclosing is not None:
        return RepoResolution(
            repo_root=enclosing,
            cache_dir=find_cache_dir(enclosing),
            how="cwd" if enclosing == cwd else f"ancestor of cwd ({enclosing.name})",
        )

    registry = load_registry()
    for entry in registry:
        root = Path(entry["root"])
        if cwd == root or root in cwd.parents:
            return RepoResolution(
                repo_root=root,
                cache_dir=Path(entry["cache"]),
                how="registry (cwd is inside a registered repo)",
            )

    # Before falling back to a registered repo, check whether the working
    # directory is a codebase in its own right. If it is, it simply has not been
    # indexed — and answering from an unrelated repo's cache would be worse than
    # any error, because it looks like a real answer.
    if looks_like_a_codebase(cwd):
        return RepoResolution(
            how="unindexed_cwd", candidates=registry, unindexed_cwd=cwd
        )

    if len(registry) == 1:
        entry = registry[0]
        return RepoResolution(
            repo_root=Path(entry["root"]),
            cache_dir=Path(entry["cache"]),
            how="registry (only one indexed repo known)",
        )

    if len(registry) > 1:
        return RepoResolution(how="ambiguous", candidates=registry)

    return RepoResolution(how="unresolved")


def find_nested_caches(repo_root, limit=12):
    """Find caches in immediate subdirectories, for a helpful 'no cache' message.

    When someone runs this from a directory that merely *contains* indexed
    repos, the answer is not "no index exists" — it is "you pointed at the
    wrong level". Surface the candidates so the agent can retarget.
    """
    found = []
    try:
        for entry in sorted(repo_root.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if any(entry.glob(".iris_cache/*/codebase_overview.json")):
                found.append(entry)
            if len(found) >= limit:
                break
    except OSError:
        pass
    return found


# Fraction of a cache's tracked paths that must exist under the target tree for
# the pairing to be plausible. Unrelated repos still share generic top-level
# names (README.md, config.yaml, .gitignore), so a >0 test is not enough:
# measured against IRIS's own cache, the correct repo scores ~0.85 while an
# unrelated sibling scores ~0.10. 0.25 sits in that gap with margin on both
# sides. A genuinely huge deletion is reported as drift, not a mismatch,
# because deleted paths still resolve against the right tree's directories.
CACHE_MATCH_MIN_OVERLAP = 0.25


def cache_belongs_to_repo(cached_hashes, repo_root, sample=60):
    """Sanity-check that a cache actually describes repo_root.

    Samples tracked paths and measures how many exist on disk. Near-zero overlap
    means the cache was built for a different tree, and every drift number
    derived from it would be noise. Cheap insurance against a mispointed
    --cache, a cache copied into the wrong repo, or a --repo aimed at a parent
    directory.
    """
    paths = list(cached_hashes)[:sample]
    if not paths:
        return True, 0.0
    present = sum(1 for rel in paths if (repo_root / rel).exists())
    overlap = present / len(paths)
    return overlap >= CACHE_MATCH_MIN_OVERLAP, overlap


def collect_current_files(repo_root, ignore_spec):
    """Walk the repo and return relative posix paths IRIS would index."""
    found = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        current = Path(dirpath)
        rel_dir = current.relative_to(repo_root).as_posix()

        # Prune ignored directories in place so os.walk skips descending them.
        kept = []
        for name in dirnames:
            rel = name if rel_dir == "." else f"{rel_dir}/{name}"
            if not ignore_spec.match(rel, is_dir=True):
                kept.append(name)
        dirnames[:] = kept

        for name in filenames:
            rel = name if rel_dir == "." else f"{rel_dir}/{name}"
            if ignore_spec.match(rel, is_dir=False):
                continue
            full = current / name
            try:
                size = full.stat().st_size
            except OSError:
                continue
            limit = MAX_NOTEBOOK_SIZE if name.endswith(".ipynb") else MAX_FILE_SIZE
            if size > limit:
                continue
            found.append(rel)
    return found


def load_json(path, label):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not read {label} at {path}: {exc}")


def build_ignore_spec(repo_root, use_gitignore=True):
    patterns = list(DEFAULT_IGNORE_PATTERNS)
    gitignore = repo_root / ".gitignore"
    if use_gitignore and gitignore.is_file():
        try:
            patterns.extend(gitignore.read_text(encoding="utf-8").splitlines())
        except OSError:
            pass
    return IgnoreSpec(patterns)


def analyze(repo_root, cache_dir, detect_new=True):
    cached_hashes = load_json(cache_dir / "file_hashes.json", "file_hashes.json")
    if not isinstance(cached_hashes, dict):
        raise SystemExit(f"file_hashes.json is not a JSON object: {cache_dir}")

    modified, deleted, unreadable = [], [], []
    for rel_path, cached_hash in sorted(cached_hashes.items()):
        full = repo_root / rel_path
        if not full.is_file():
            deleted.append(rel_path)
            continue
        current_hash = hash_file_content(full)
        if current_hash == "unreadable":
            unreadable.append(rel_path)
        elif current_hash != cached_hash:
            modified.append(rel_path)

    new = []
    if detect_new:
        spec = build_ignore_spec(repo_root)
        tracked = set(cached_hashes)
        new = sorted(
            p for p in collect_current_files(repo_root, spec) if p not in tracked
        )

    tracked_count = len(cached_hashes)
    drifted = len(modified) + len(deleted) + len(new)
    # An empty cache tracks nothing, so a ratio is meaningless. Report full
    # drift so the caller treats the index as unusable rather than "fresh".
    ratio = (drifted / tracked_count) if tracked_count else 1.0

    metadata = {}
    metadata_path = cache_dir / "codebase_metadata.json"
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}

    belongs, overlap = cache_belongs_to_repo(cached_hashes, repo_root)

    return {
        "cache_dir": str(cache_dir),
        "repo_root": str(repo_root),
        "indexed_at": metadata.get("evaluation_timestamp"),
        "cache_matches_repo": belongs,
        "path_overlap": round(overlap, 3),
        "tracked_files": tracked_count,
        "new_files": new,
        "modified_files": modified,
        "deleted_files": deleted,
        "unreadable_files": unreadable,
        "drifted_files": drifted,
        "drift_ratio": round(ratio, 4),
        "new_file_detection": detect_new,
    }


def render(result, threshold, limit):
    lines = []
    verdict = result["verdict"]
    lines.append(f"IRIS cache: {result['cache_dir']}")
    if result["indexed_at"]:
        lines.append(f"Indexed at: {result['indexed_at']}")
    lines.append(
        f"Tracked files: {result['tracked_files']} | "
        f"drifted: {result['drifted_files']} "
        f"({result['drift_ratio'] * 100:.1f}%, threshold {threshold * 100:.0f}%)"
    )
    lines.append(f"VERDICT: {verdict}")

    for label, key in (
        ("Modified", "modified_files"),
        ("New", "new_files"),
        ("Deleted", "deleted_files"),
        ("Unreadable", "unreadable_files"),
    ):
        paths = result[key]
        if not paths:
            continue
        lines.append(f"\n{label} ({len(paths)}):")
        for path in paths[:limit]:
            lines.append(f"  {path}")
        if len(paths) > limit:
            lines.append(f"  ... and {len(paths) - limit} more")

    if verdict == "empty_cache":
        lines.append(
            "\nThe cache tracks no files — it is unusable. Treat this as an "
            "unindexed repo: explore natively, and offer to build the index."
        )
    elif verdict == "cache_mismatch":
        lines.append(
            f"\nOnly {result['path_overlap'] * 100:.0f}% of this cache's tracked "
            "paths exist under the directory being checked, so it almost "
            "certainly describes a different tree. Do NOT report a drift figure "
            "from this pairing. Point --repo at the indexed repo root (or fix "
            "--cache), then re-run."
        )
    elif verdict == "fresh":
        lines.append(
            "\nCached summaries match the working tree. Answer from the index."
        )
    elif verdict == "small_drift":
        lines.append(
            "\nAnswer from the index, but read the files listed above live — do not "
            "trust their cached summaries. Note the slight staleness in your answer."
        )
    else:
        lines.append(
            "\nLarge drift. Tell the user, ask ONCE whether to run `iris prepare`, "
            "and answer this turn from live reads either way."
        )
    if not result["new_file_detection"]:
        lines.append(
            "(New-file detection was disabled; counts cover tracked files only.)"
        )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Detect drift between an IRIS cache and the working tree."
    )
    parser.add_argument(
        "--repo", default=".", help="Repository root to check (default: cwd)"
    )
    parser.add_argument(
        "--cache", help="Cache directory; discovered by glob when omitted"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.15,
        help="Drift ratio at or above which the verdict is large_drift (default: 0.15)",
    )
    parser.add_argument("--json", action="store_true", help="Emit raw JSON")
    parser.add_argument(
        "--quiet", action="store_true", help="Print only the verdict line"
    )
    parser.add_argument(
        "--no-new",
        action="store_true",
        help="Skip new-file detection (faster; tracked files only)",
    )
    parser.add_argument(
        "--limit", type=int, default=25, help="Max paths listed per category"
    )
    parser.add_argument(
        "--list-repos",
        action="store_true",
        help="List indexed repos known to the registry, then exit",
    )
    parser.add_argument(
        "--register",
        action="store_true",
        help="Record --repo in the registry (done automatically after indexing)",
    )
    args = parser.parse_args(argv)

    if args.list_repos:
        registry = load_registry()
        if args.json:
            print(json.dumps({"repos": registry}, indent=2))
        elif not registry:
            print(
                f"No indexed repos registered ({registry_path()} is absent or empty).\n"
                "Run the skill's setup task in a repo, or pass --repo explicitly."
            )
        else:
            print(f"Indexed repos ({registry_path()}):\n")
            for entry in registry:
                stamp = entry.get("indexed_at") or "unknown"
                print(
                    f"  {entry['root']}\n      cache: {entry['cache']}\n      indexed: {stamp}"
                )
        return 0

    if args.register:
        target = Path(args.repo).expanduser().resolve()
        if find_cache_dir(target) is None:
            print(f"Not an indexed repo (no .iris_cache/): {target}", file=sys.stderr)
            return 1
        if save_registry_entry(target):
            print(f"Registered: {target}")
            return 0
        print(f"Could not write {registry_path()}", file=sys.stderr)
        return 1

    # Resolve which repo to check. --repo defaults to "." but the working
    # directory is frequently unrelated to the indexed repo, so fall back to
    # ancestors and the registry before giving up.
    explicit_repo = args.repo if args.repo != "." else None
    resolution = resolve_repo(explicit_repo, args.cache, cwd=Path.cwd())

    if resolution.how == "ambiguous":
        message = (
            "Several indexed repos are registered and the working directory is "
            "not inside any of them. Ask the user which one, or pass --repo:\n"
        )
        for entry in resolution.candidates:
            message += f"\n  --repo {entry['root']}"
        if args.json:
            print(
                json.dumps(
                    {"verdict": "ambiguous_repo", "candidates": resolution.candidates},
                    indent=2,
                )
            )
        else:
            print(message)
        return 1

    if resolution.how == "unindexed_cwd":
        target = resolution.unindexed_cwd
        payload = {
            "verdict": "unindexed_repo",
            "repo_root": str(target),
            "file_count": count_indexable_files(target),
            "other_indexed_repos": [e["root"] for e in resolution.candidates],
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"This repo is NOT indexed: {target}\n"
                f"Indexable files: ~{payload['file_count']}\n\n"
                "Do not answer from another repo's cache. Offer to index this one "
                "(the skill's setup task), and ask whether the user wants to wait "
                "for the index or get an answer from a normal code read now."
            )
            if payload["other_indexed_repos"]:
                print(
                    "\nOther repos ARE indexed, but they are different codebases:\n  "
                    + "\n  ".join(payload["other_indexed_repos"])
                )
        return 1

    if resolution.repo_root is None:
        message = (
            f"No indexed repo found. The working directory ({Path.cwd()}) is not "
            "inside one, and no repos are registered.\n"
            "Pass --repo <indexed-repo>, or run the skill's setup task to index one."
        )
        print(
            json.dumps({"verdict": "no_cache", "message": message}, indent=2)
            if args.json
            else message
        )
        return 1

    repo_root = resolution.repo_root
    if not repo_root.is_dir():
        print(f"Not a directory: {repo_root}", file=sys.stderr)
        return 1
    if resolution.how not in ("explicit --repo", "cwd"):
        # Say out loud which repo was chosen and why, so a wrong inference is
        # visible to the user rather than silently shaping the answer.
        print(
            f"[resolved repo: {repo_root}  (via {resolution.how})]\n", file=sys.stderr
        )

    cache_dir = find_cache_dir(repo_root, args.cache)
    if cache_dir is None:
        # Distinguish "not indexed" from "you pointed one level too high" — the
        # latter is the common case when the assistant's working directory is a
        # folder that merely contains indexed repos.
        nested = find_nested_caches(repo_root)
        message = (
            f"No .iris_cache/*/codebase_overview.json directly under {repo_root}. "
            "This directory is not indexed by IRIS."
        )
        if nested:
            names = ", ".join(p.name for p in nested)
            message += (
                f"\n\nHowever, {len(nested)} indexed repo(s) exist in "
                f"subdirectories: {names}."
                "\nIf the question is about one of them, re-run with "
                "--repo <that-subdirectory>. Do not check the parent directory: "
                "hashing it against a nested repo's cache yields meaningless drift."
            )
        payload = {
            "verdict": "no_cache",
            "repo_root": str(repo_root),
            "nested_indexed_repos": [str(p) for p in nested],
            "message": message,
        }
        print(json.dumps(payload, indent=2) if args.json else message)
        return 1

    result = analyze(repo_root, cache_dir, detect_new=not args.no_new)

    if result["tracked_files"] == 0:
        # A cache that tracks no files cannot answer anything, even though
        # nothing "drifted" — treat it as unusable, not fresh.
        result["verdict"] = "empty_cache"
    elif not result["cache_matches_repo"]:
        # None of the cache's tracked paths exist here. Any ratio computed from
        # this pairing is noise, so refuse rather than report a number.
        result["verdict"] = "cache_mismatch"
    elif result["drifted_files"] == 0:
        result["verdict"] = "fresh"
    elif result["drift_ratio"] >= args.threshold:
        result["verdict"] = "large_drift"
    else:
        result["verdict"] = "small_drift"

    if args.json:
        print(json.dumps(result, indent=2))
    elif args.quiet:
        if result["verdict"] == "empty_cache":
            print("empty_cache (index tracks no files)")
        elif result["verdict"] == "cache_mismatch":
            print("cache_mismatch (cache does not describe this directory)")
        else:
            print(f"{result['verdict']} ({result['drift_ratio'] * 100:.1f}% drift)")
    else:
        print(render(result, args.threshold, args.limit))

    if result["verdict"] == "fresh":
        return 0
    if result["verdict"] in ("empty_cache", "cache_mismatch"):
        return 1  # unusable index, same class of problem as no cache at all
    return 2


if __name__ == "__main__":
    sys.exit(main())
