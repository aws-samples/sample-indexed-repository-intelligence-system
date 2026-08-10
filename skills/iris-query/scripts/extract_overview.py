# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Targeted extraction from an IRIS codebase_overview.json.

Stdlib-only by design: runs for consumers with no venv, no iris package, and no
AWS access. Purpose is to keep the overview OUT of the agent's context — it is
~200 KB for a mid-sized repo. Pull only the entries a question needs.

Subcommands:
    stats                     Cache shape: file count, languages, flagged files
    files PATH [PATH ...]     Full entries for named files (exact or suffix match)
    search TERM [TERM ...]    Keyword search over purpose/class/function text
    symbol NAME               Find a class or function by name
    imports PATH              Direct imports of PATH, and files importing PATH
    tree [--depth N]          Directory rollup with per-directory file purposes
    list [--dir D]            Compact path + one-line purpose listing

Usage:
    python3 extract_overview.py --repo . search "websocket auth"
    python3 extract_overview.py --cache .iris_cache/foo files iris/cli.py
"""

import argparse
import json
import re
import sys
from pathlib import Path

# The skill is installed inside the user's repo, so writing __pycache__ next to
# these scripts would show up in their `git status`. Suppress it before the
# sibling import below.
sys.dont_write_bytecode = True

# Reuse cache discovery so both scripts agree on which cache is authoritative.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from check_staleness import (
        find_cache_dir,
        find_nested_caches,
        load_registry,
        resolve_repo,
    )
except ImportError:  # pragma: no cover - defensive; scripts ship together

    def find_cache_dir(repo_root, explicit=None):
        if explicit:
            candidate = Path(explicit).expanduser().resolve()
            if (candidate / "codebase_overview.json").is_file():
                return candidate
            raise SystemExit(f"No codebase_overview.json in --cache dir: {candidate}")
        matches = sorted(repo_root.glob(".iris_cache/*/codebase_overview.json"))
        if not matches:
            return None
        return max(matches, key=lambda p: p.stat().st_mtime).parent

    def find_nested_caches(repo_root, limit=12):
        found = []
        try:
            for entry in sorted(repo_root.iterdir()):
                if entry.is_dir() and not entry.name.startswith("."):
                    if any(entry.glob(".iris_cache/*/codebase_overview.json")):
                        found.append(entry)
                if len(found) >= limit:
                    break
        except OSError:
            pass
        return found

    def load_registry():
        return []

    def resolve_repo(explicit_repo=None, explicit_cache=None, cwd=None):
        raise SystemExit(
            "check_staleness.py is missing from this skill install; "
            "pass --repo explicitly."
        )


EXT_LANGUAGE = {
    ".py": "Python",
    ".ipynb": "Jupyter",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".kt": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".c": "C",
    ".h": "C/C++ header",
    ".cc": "C++",
    ".cpp": "C++",
    ".hpp": "C++ header",
    ".swift": "Swift",
    ".m": "Objective-C",
    ".scala": "Scala",
    ".sh": "Shell",
    ".bash": "Shell",
    ".ps1": "PowerShell",
    ".sql": "SQL",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".md": "Markdown",
    ".rst": "reStructuredText",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".tf": "Terraform",
    ".dockerfile": "Docker",
}


def load_overview(repo_root, explicit_cache):
    cache_dir = find_cache_dir(repo_root, explicit_cache)
    if cache_dir is None:
        message = (
            f"No .iris_cache/*/codebase_overview.json directly under {repo_root}. "
            "This directory is not indexed by IRIS."
        )
        # The usual cause is a working directory one level above the indexed
        # repo. Name the candidates rather than just reporting absence.
        nested = find_nested_caches(repo_root)
        if nested:
            names = ", ".join(p.name for p in nested)
            message += (
                f"\n\n{len(nested)} indexed repo(s) exist in subdirectories: "
                f"{names}.\nRe-run with --repo <that-subdirectory> to query one."
            )
        raise SystemExit(message)
    path = cache_dir / "codebase_overview.json"
    try:
        with open(path, "r", encoding="utf-8") as handle:
            overview = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not read {path}: {exc}")
    if not isinstance(overview, dict):
        raise SystemExit(f"codebase_overview.json is not a JSON object: {path}")
    return cache_dir, overview


def entry_text(entry):
    """Flatten one overview entry into searchable text."""
    if not isinstance(entry, dict):
        return ""
    parts = [str(entry.get("purpose") or "")]
    classes = entry.get("classes")
    if isinstance(classes, dict):
        for name, body in classes.items():
            parts.append(name)
            if isinstance(body, dict):
                parts.append(str(body.get("purpose") or ""))
                methods = body.get("methods")
                if isinstance(methods, dict):
                    for method_name, method_doc in methods.items():
                        parts.append(method_name)
                        parts.append(str(method_doc or ""))
            else:
                parts.append(str(body or ""))
    functions = entry.get("functions")
    if isinstance(functions, dict):
        for name, doc in functions.items():
            parts.append(name)
            parts.append(str(doc or ""))
    return "\n".join(parts)


TEST_DIR_NAMES = (
    "test",
    "tests",
    "__tests__",
    "spec",
    "specs",
    "docs",
    "doc",
    "fixtures",
)
DOC_SUFFIXES = (".md", ".rst", ".txt")
# Anchored on separators so 'latest.py' and 'contest.py' are not mistaken for
# tests. Matches test_x, x_test, test-x, spec.x, conftest, mock_y, and so on.
TEST_STEM_RE = re.compile(
    r"(^|[._\-])(tests?|specs?|fixtures?|mocks?|snapshots?)([._\-]|$)|^conftest$"
)


def is_test_or_doc(path_lower):
    """Heuristic: does this path look like a test or a document, not implementation?

    Used only to down-rank search hits. Deliberately conservative — a false
    positive costs a search-ranking position, not correctness.
    """
    segments = path_lower.split("/")
    filename = segments[-1]
    if any(seg in TEST_DIR_NAMES for seg in segments[:-1]):
        return True
    if filename.endswith(DOC_SUFFIXES):
        return True
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return bool(TEST_STEM_RE.search(stem))


def one_line(entry, width=160):
    """First sentence of an entry's purpose, truncated."""
    if not isinstance(entry, dict):
        return "(no summary)"
    purpose = " ".join(str(entry.get("purpose") or "").split())
    if not purpose:
        return "(no summary)"
    match = re.search(r"(?<=[.!?])\s", purpose)
    if match and match.start() < width:
        purpose = purpose[: match.start() + 1]
    if len(purpose) > width:
        purpose = purpose[: width - 1].rstrip() + "…"
    return purpose


def resolve_paths(overview, requested):
    """Map user-supplied paths to overview keys.

    Accepts exact keys, suffix matches (so `cli.py` finds `iris/cli.py`), and
    directory prefixes (so `backend/` returns everything beneath it).
    """
    resolved, missing = [], []
    keys = list(overview)
    for raw in requested:
        needle = raw.strip().lstrip("./").rstrip()
        if needle in overview:
            resolved.append(needle)
            continue
        if needle.endswith("/"):
            prefix = [k for k in keys if k.startswith(needle)]
            if prefix:
                resolved.extend(sorted(prefix))
                continue
        suffix = [k for k in keys if k == needle or k.endswith("/" + needle)]
        if suffix:
            resolved.extend(sorted(suffix))
            continue
        prefix = [k for k in keys if k.startswith(needle.rstrip("/") + "/")]
        if prefix:
            resolved.extend(sorted(prefix))
            continue
        missing.append(raw)
    # Preserve order, drop duplicates.
    seen, ordered = set(), []
    for key in resolved:
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered, missing


def format_entry(path, entry, include_members=True):
    lines = [f"### {path}"]
    if not isinstance(entry, dict):
        lines.append("(malformed cache entry)")
        return "\n".join(lines)

    purpose = " ".join(str(entry.get("purpose") or "").split())
    lines.append(purpose or "(no purpose recorded)")

    flags = []
    if entry.get("genai_system") == "Yes":
        flags.append("GenAI system: yes")
    bugs = entry.get("has_bugs")
    if bugs and bugs != "No bugs":
        flags.append(f"bug signal: {bugs}")
    if flags:
        lines.append("[" + "; ".join(flags) + "]")

    imports = entry.get("imported_files")
    if isinstance(imports, list) and imports:
        lines.append("Imports: " + ", ".join(str(i) for i in imports))

    if not include_members:
        return "\n".join(lines)

    classes = entry.get("classes")
    if isinstance(classes, dict) and classes:
        lines.append("Classes:")
        for name, body in classes.items():
            if isinstance(body, dict):
                lines.append(
                    f"  - {name}: {' '.join(str(body.get('purpose') or '').split())}"
                )
                methods = body.get("methods")
                if isinstance(methods, dict) and methods:
                    for method_name, method_doc in methods.items():
                        lines.append(
                            f"      .{method_name}: {' '.join(str(method_doc or '').split())}"
                        )
            else:
                lines.append(f"  - {name}: {' '.join(str(body or '').split())}")

    functions = entry.get("functions")
    if isinstance(functions, dict) and functions:
        lines.append("Functions:")
        for name, doc in functions.items():
            lines.append(f"  - {name}: {' '.join(str(doc or '').split())}")

    return "\n".join(lines)


def cmd_stats(overview, cache_dir, args):
    languages = {}
    genai, buggy, with_symbols = [], [], 0
    for path, entry in overview.items():
        suffix = Path(path).suffix.lower()
        label = EXT_LANGUAGE.get(suffix, suffix or "(no extension)")
        languages[label] = languages.get(label, 0) + 1
        if not isinstance(entry, dict):
            continue
        if entry.get("genai_system") == "Yes":
            genai.append(path)
        if entry.get("has_bugs") and entry["has_bugs"] != "No bugs":
            buggy.append(path)
        if entry.get("classes") or entry.get("functions"):
            with_symbols += 1

    top_dirs = {}
    for path in overview:
        head = path.split("/")[0] if "/" in path else "(root)"
        top_dirs[head] = top_dirs.get(head, 0) + 1

    print(f"Cache: {cache_dir}")
    print(f"Indexed files: {len(overview)} ({with_symbols} with class/function detail)")
    print("\nLanguages:")
    for label, count in sorted(languages.items(), key=lambda kv: -kv[1]):
        print(f"  {count:>4}  {label}")
    print("\nTop-level directories:")
    for label, count in sorted(top_dirs.items(), key=lambda kv: -kv[1]):
        print(f"  {count:>4}  {label}")
    print(f"\nFlagged as GenAI-related: {len(genai)}")
    print(f"Flagged with possible bugs: {len(buggy)}")
    if args.verbose and buggy:
        print("\nFiles with bug signals:")
        for path in sorted(buggy):
            print(f"  {path}")
    return 0


def cmd_files(overview, cache_dir, args):
    resolved, missing = resolve_paths(overview, args.paths)
    if missing:
        print(f"Not in the index: {', '.join(missing)}", file=sys.stderr)
        print(
            "These files are either unindexed (added after the last `iris prepare`) "
            "or excluded by ignore_patterns. Read them live.",
            file=sys.stderr,
        )
    if not resolved:
        # Nothing matched at all: a non-zero exit tells the caller to stop
        # relying on the index and switch to native tools.
        return 1
    if args.limit and len(resolved) > args.limit:
        print(
            f"(matched {len(resolved)} files; showing first {args.limit} — "
            f"narrow the path or raise --limit)\n"
        )
        resolved = resolved[: args.limit]
    for index, path in enumerate(resolved):
        if index:
            print()
        print(format_entry(path, overview[path], include_members=not args.brief))
    return 0


def cmd_search(overview, cache_dir, args):
    terms = [t.lower() for term in args.terms for t in term.split() if t]
    if not terms:
        print("No search terms given.", file=sys.stderr)
        return 1

    scored = []
    for path, entry in overview.items():
        haystack = entry_text(entry).lower()
        path_lower = path.lower()
        if args.match_all and not all(t in haystack or t in path_lower for t in terms):
            continue
        score = 0
        for term in terms:
            score += haystack.count(term)
            # Path hits are strong signal for "where is X" questions.
            score += 5 * path_lower.count(term)
        if not score:
            continue
        # Tests and docs mention a subject far more often than the code that
        # implements it, so raw term frequency ranks them above the thing the
        # user actually asked about. Down-weight rather than exclude them —
        # sometimes the test IS the answer.
        if not args.include_tests and is_test_or_doc(path_lower):
            score = score / 4.0
        scored.append((score, path))

    if not scored:
        joined = ", ".join(terms)
        print(f"No index entries match: {joined}")
        print("Fall back to native Grep over the live tree.")
        return 1

    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    shown = scored[: args.limit]
    print(f"{len(scored)} matching file(s); showing top {len(shown)}:\n")
    for score, path in shown:
        if args.full:
            print(format_entry(path, overview[path]))
            print()
        else:
            marker = " (test/doc)" if is_test_or_doc(path.lower()) else ""
            print(f"{path}  [score {score:.0f}]{marker}")
            print(f"    {one_line(overview[path])}")
    if len(scored) > len(shown):
        print(f"\n... and {len(scored) - len(shown)} more (raise --limit)")
    print("\nVerify by reading the live files before quoting code or line numbers.")
    return 0


def cmd_symbol(overview, cache_dir, args):
    needle = args.name
    exact = needle.lower()
    hits = []
    for path, entry in overview.items():
        if not isinstance(entry, dict):
            continue
        classes = entry.get("classes")
        if isinstance(classes, dict):
            for name, body in classes.items():
                if self_match(name, exact, args.exact):
                    purpose = (
                        body.get("purpose") if isinstance(body, dict) else str(body)
                    )
                    hits.append((path, "class", name, purpose or ""))
                if isinstance(body, dict) and isinstance(body.get("methods"), dict):
                    for method_name, method_doc in body["methods"].items():
                        if self_match(method_name, exact, args.exact):
                            hits.append(
                                (
                                    path,
                                    f"method of {name}",
                                    method_name,
                                    method_doc or "",
                                )
                            )
        functions = entry.get("functions")
        if isinstance(functions, dict):
            for name, doc in functions.items():
                if self_match(name, exact, args.exact):
                    hits.append((path, "function", name, doc or ""))

    if not hits:
        print(f"No class, method, or function named like '{needle}' in the index.")
        print("The symbol may be unindexed or defined in an ignored file — try Grep.")
        return 1

    print(f"{len(hits)} match(es) for '{needle}':\n")
    for path, kind, name, doc in hits[: args.limit]:
        print(f"{path}  —  {kind} `{name}`")
        summary = " ".join(str(doc).split())
        if summary:
            print(f"    {summary}")
    if len(hits) > args.limit:
        print(f"\n... and {len(hits) - args.limit} more (raise --limit)")
    print("\nRead the live file for the actual signature and body.")
    return 0


def self_match(name, needle, exact):
    lowered = name.lower()
    return lowered == needle if exact else needle in lowered


def cmd_imports(overview, cache_dir, args):
    resolved, missing = resolve_paths(overview, [args.path])
    if missing or not resolved:
        print(f"Not in the index: {args.path}", file=sys.stderr)
        return 1
    target = resolved[0]

    entry = overview[target]
    outgoing = entry.get("imported_files") if isinstance(entry, dict) else []
    outgoing = [str(i) for i in outgoing] if isinstance(outgoing, list) else []

    incoming = []
    for path, other in overview.items():
        if path == target or not isinstance(other, dict):
            continue
        imports = other.get("imported_files")
        if isinstance(imports, list) and any(str(i) == target for i in imports):
            incoming.append(path)

    print(f"### {target}\n")
    print(f"Imports ({len(outgoing)}):")
    for path in outgoing or ["  (none recorded)"]:
        print(f"  → {path}" if outgoing else path)
    print(f"\nImported by ({len(incoming)}):")
    for path in sorted(incoming) or ["  (none recorded)"]:
        print(f"  ← {path}" if incoming else path)
    print(
        "\nImport edges come from LLM summaries and may be incomplete. "
        "Confirm call sites with Grep when it matters."
    )
    return 0


def cmd_tree(overview, cache_dir, args):
    grouped = {}
    for path in overview:
        parts = path.split("/")
        key = (
            "/".join(parts[: args.depth])
            if len(parts) > args.depth
            else ("/".join(parts[:-1]) or "(root)")
        )
        grouped.setdefault(key, []).append(path)

    print(f"Index rollup by directory (depth {args.depth}), {len(overview)} files:\n")
    for key in sorted(grouped):
        paths = sorted(grouped[key])
        print(f"{key}/  ({len(paths)} files)")
        for path in paths[: args.per_dir]:
            print(f"    {path.split('/')[-1]} — {one_line(overview[path], width=110)}")
        if len(paths) > args.per_dir:
            print(f"    ... and {len(paths) - args.per_dir} more")
        print()
    return 0


def cmd_list(overview, cache_dir, args):
    paths = sorted(overview)
    if args.dir:
        prefix = args.dir.strip("/") + "/"
        paths = [p for p in paths if p.startswith(prefix)]
        if not paths:
            print(f"No indexed files under: {args.dir}", file=sys.stderr)
            return 1
    shown = paths[: args.limit] if args.limit else paths
    for path in shown:
        print(f"{path} — {one_line(overview[path], width=120)}")
    if len(paths) > len(shown):
        print(f"... and {len(paths) - len(shown)} more (raise --limit)")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        description="Extract targeted slices of an IRIS codebase_overview.json."
    )
    parser.add_argument("--repo", default=".", help="Repository root (default: cwd)")
    parser.add_argument("--cache", help="Cache dir; discovered by glob when omitted")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_stats = subparsers.add_parser("stats", help="Cache shape and coverage")
    p_stats.add_argument(
        "-v", "--verbose", action="store_true", help="List bug-flagged files"
    )
    p_stats.set_defaults(func=cmd_stats)

    p_files = subparsers.add_parser("files", help="Full entries for named files")
    p_files.add_argument("paths", nargs="+")
    p_files.add_argument(
        "--brief", action="store_true", help="Purpose and imports only, no members"
    )
    p_files.add_argument("--limit", type=int, default=20)
    p_files.set_defaults(func=cmd_files)

    p_search = subparsers.add_parser("search", help="Keyword search over summaries")
    p_search.add_argument("terms", nargs="+")
    p_search.add_argument("--limit", type=int, default=12)
    p_search.add_argument(
        "--full", action="store_true", help="Print full entries, not one-liners"
    )
    p_search.add_argument(
        "--match-all",
        action="store_true",
        help="Require every term to appear (default: any term, ranked)",
    )
    p_search.add_argument(
        "--include-tests",
        action="store_true",
        help="Rank tests and docs equally (default: down-weighted vs implementation)",
    )
    p_search.set_defaults(func=cmd_search)

    p_symbol = subparsers.add_parser("symbol", help="Locate a class/method/function")
    p_symbol.add_argument("name")
    p_symbol.add_argument("--exact", action="store_true", help="Exact name match only")
    p_symbol.add_argument("--limit", type=int, default=20)
    p_symbol.set_defaults(func=cmd_symbol)

    p_imports = subparsers.add_parser("imports", help="Import edges for one file")
    p_imports.add_argument("path")
    p_imports.set_defaults(func=cmd_imports)

    p_tree = subparsers.add_parser("tree", help="Directory rollup with purposes")
    p_tree.add_argument("--depth", type=int, default=1)
    p_tree.add_argument("--per-dir", type=int, default=8)
    p_tree.set_defaults(func=cmd_tree)

    p_list = subparsers.add_parser("list", help="Compact path + one-line purpose")
    p_list.add_argument("--dir", help="Restrict to a directory prefix")
    p_list.add_argument("--limit", type=int, default=0, help="0 = no limit")
    p_list.set_defaults(func=cmd_list)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    # Mirror check_staleness.py: the working directory is often unrelated to the
    # indexed repo (the skill may be installed user-level while the assistant
    # sits in another project), so resolve via cwd, ancestors, then registry.
    explicit_repo = args.repo if args.repo != "." else None
    resolution = resolve_repo(explicit_repo, args.cache, cwd=Path.cwd())

    if resolution.how == "ambiguous":
        print(
            "Several indexed repos are registered and the working directory is "
            "not inside any of them. Ask the user which one, or pass --repo:",
            file=sys.stderr,
        )
        for entry in resolution.candidates:
            print(f"  --repo {entry['root']}", file=sys.stderr)
        return 1

    if resolution.how == "unindexed_cwd":
        # Never substitute another repo's cache for an unindexed one — it would
        # read as a real answer about the wrong codebase.
        print(
            f"This repo is NOT indexed: {resolution.unindexed_cwd}\n"
            "Offer to index it (the skill's setup task), and ask whether the user "
            "wants to wait for indexing or get an answer from a normal code read "
            "now. Do not answer from another repo's cache.",
            file=sys.stderr,
        )
        if resolution.candidates:
            print(
                "\nOther repos are indexed, but they are different codebases:\n  "
                + "\n  ".join(e["root"] for e in resolution.candidates),
                file=sys.stderr,
            )
        return 1

    if resolution.repo_root is None:
        print(
            f"No indexed repo found. The working directory ({Path.cwd()}) is not "
            "inside one, and no repos are registered.\n"
            "Pass --repo <indexed-repo>, or run the skill's setup task to index one.",
            file=sys.stderr,
        )
        return 1

    repo_root = resolution.repo_root
    if not repo_root.is_dir():
        print(f"Not a directory: {repo_root}", file=sys.stderr)
        return 1
    if resolution.how not in ("explicit --repo", "cwd"):
        print(
            f"[resolved repo: {repo_root}  (via {resolution.how})]\n", file=sys.stderr
        )

    cache_dir, overview = load_overview(repo_root, args.cache)
    return args.func(overview, cache_dir, args)


if __name__ == "__main__":
    sys.exit(main())
