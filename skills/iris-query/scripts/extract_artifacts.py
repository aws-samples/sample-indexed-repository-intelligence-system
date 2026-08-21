# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Targeted extraction from an IRIS artifact index (the optional second index).

The artifact counterpart to extract_overview.py. Where that script reads
codebase_overview.json, this one reads artifact_overview.json — LLM summaries of
project artifacts (pptx/docx/xlsx/pdf/md/txt/video) discovered under the
configured artifact_dir — plus the extracted text under extracted_artifacts/,
which is the primary retrieval source for artifact content.

Stdlib-only by design, like its sibling: it runs for consumers who cloned a repo
with a committed .iris_cache/ and have no venv, no iris package, and no AWS
access. Artifact indexing is optional, so a repo with no artifact_overview.json
is normal — this script says so and exits non-zero rather than treating it as an
error.

Subcommands:
    stats                     Index shape: counts by phase, type, and format
    tree                      phase → type rollup with one-line purposes
    list [--phase P] …        Compact path + one-line purpose listing
    search TERM [TERM ...]    Keyword search over summaries, topics, and paths
    files PATH [PATH ...]     Full summary entries for named artifacts
    content PATH [PATH ...]   Extracted TEXT of an artifact (the real content)

Usage:
    python3 extract_artifacts.py --repo . search "cost estimate"
    python3 extract_artifacts.py --repo . content during-project/meetings/Week1.docx
"""

import argparse
import json
import re
import sys
from pathlib import Path

# The skill is installed inside the user's repo, so writing __pycache__ next to
# these scripts would show up in their `git status`.
sys.dont_write_bytecode = True

# Reuse cache/repo discovery so all three scripts agree on which cache is
# authoritative and which repo a question is about.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from check_staleness import (
        ARTIFACT_OVERVIEW_FILE,
        find_cache_dir,
        resolve_artifact_dir,
        resolve_repo,
    )
except ImportError:  # pragma: no cover - defensive; scripts ship together
    ARTIFACT_OVERVIEW_FILE = "artifact_overview.json"

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

    def resolve_artifact_dir(repo_root, explicit=None):
        return {
            "artifact_dir": explicit,
            "artifact_dir_source": "--artifact-dir" if explicit else None,
            "artifact_dir_exists": bool(explicit and Path(explicit).is_dir()),
        }

    def resolve_repo(explicit_repo=None, explicit_cache=None, cwd=None):
        raise SystemExit(
            "check_staleness.py is missing from this skill install; "
            "pass --repo explicitly."
        )


EXTRACTED_DIR = "extracted_artifacts"


def find_artifact_cache(repo_root, explicit_cache=None):
    """Locate the cache directory holding artifact_overview.json.

    Normally the artifact index lives beside the codebase index, so the shared
    discovery in check_staleness.py finds it. The fallback covers a cache built
    with `iris prepare --artifact` alone, where no codebase_overview.json exists
    for the glob to latch onto.
    """
    if explicit_cache:
        candidate = Path(explicit_cache).expanduser().resolve()
        if (candidate / ARTIFACT_OVERVIEW_FILE).is_file():
            return candidate
        raise SystemExit(f"No {ARTIFACT_OVERVIEW_FILE} in --cache dir: {candidate}")

    cache_dir = find_cache_dir(repo_root)
    if cache_dir is not None and (cache_dir / ARTIFACT_OVERVIEW_FILE).is_file():
        return cache_dir

    matches = sorted(repo_root.glob(f".iris_cache/*/{ARTIFACT_OVERVIEW_FILE}"))
    if matches:
        return max(matches, key=lambda p: p.stat().st_mtime).parent
    return None


def load_artifact_overview(repo_root, explicit_cache=None):
    cache_dir = find_artifact_cache(repo_root, explicit_cache)
    if cache_dir is None:
        raise SystemExit(
            f"No .iris_cache/*/{ARTIFACT_OVERVIEW_FILE} under {repo_root}.\n"
            "This repo has no artifact index. Artifact indexing is optional: it "
            "only exists once artifact_dir is configured and indexed. Answer from "
            "the codebase index, and offer artifact indexing only if the user has "
            "an artifact directory."
        )
    path = cache_dir / ARTIFACT_OVERVIEW_FILE
    try:
        with open(path, "r", encoding="utf-8") as handle:
            overview = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not read {path}: {exc}")
    if not isinstance(overview, dict):
        raise SystemExit(f"{ARTIFACT_OVERVIEW_FILE} is not a JSON object: {path}")
    return cache_dir, overview


def entry_text(entry):
    """Flatten one artifact entry into searchable text."""
    if not isinstance(entry, dict):
        return ""
    parts = [
        str(entry.get("purpose") or ""),
        str(entry.get("summary") or ""),
        str(entry.get("project_phase") or ""),
        str(entry.get("source_material_type") or ""),
    ]
    for key in ("key_topics", "related_artifacts"):
        values = entry.get(key)
        if isinstance(values, list):
            parts.extend(str(v) for v in values)
    return "\n".join(parts)


def one_line(entry, width=160):
    """First sentence of an artifact's purpose, truncated."""
    if not isinstance(entry, dict):
        return "(no summary)"
    purpose = " ".join(str(entry.get("purpose") or entry.get("summary") or "").split())
    if not purpose:
        return "(no summary)"
    match = re.search(r"(?<=[.!?])\s", purpose)
    if match and match.start() < width:
        purpose = purpose[: match.start() + 1]
    if len(purpose) > width:
        purpose = purpose[: width - 1].rstrip() + "…"
    return purpose


def resolve_paths(overview, requested):
    """Map user-supplied paths to artifact_overview keys.

    Accepts exact keys, filename/suffix matches (so `Week1_Kickoff.docx` finds
    `during-project/meetings/Week1_Kickoff.docx`), directory prefixes (so
    `during-project/` returns everything beneath it), and — because artifact
    filenames are long and easily mistyped — a case-insensitive stem match.
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
        lowered = needle.lower()
        fuzzy = [k for k in keys if lowered in k.lower()]
        if fuzzy:
            resolved.extend(sorted(fuzzy))
            continue
        missing.append(raw)
    seen, ordered = set(), []
    for key in resolved:
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered, missing


def format_entry(path, entry, brief=False):
    lines = [f"### {path}"]
    if not isinstance(entry, dict):
        lines.append("(malformed cache entry)")
        return "\n".join(lines)

    tags = [
        str(entry.get("project_phase") or "unclassified"),
        str(entry.get("source_material_type") or "unclassified"),
        str(entry.get("file_format") or "?"),
    ]
    lines.append("[" + " | ".join(tags) + "]")
    lines.append(" ".join(str(entry.get("purpose") or "(no purpose recorded)").split()))

    topics = entry.get("key_topics")
    if isinstance(topics, list) and topics:
        lines.append("Key topics: " + ", ".join(str(t) for t in topics))

    related = entry.get("related_artifacts")
    if isinstance(related, list) and related:
        lines.append("Related artifacts: " + ", ".join(str(r) for r in related))

    if not brief:
        summary = " ".join(str(entry.get("summary") or "").split())
        if summary:
            lines.append("Summary: " + summary)

    return "\n".join(lines)


def extracted_text_path(cache_dir, artifact_path):
    """Where the extracted text for an artifact lives.

    Mirrors iris/artifacts/knowledge_base.py:_artifact_md_path — ``.md`` is
    appended to the full filename, extension included, so report.pdf and
    report.docx do not collide.
    """
    rel = Path(artifact_path)
    return Path(cache_dir) / EXTRACTED_DIR / rel.parent / (rel.name + ".md")


def cmd_stats(overview, cache_dir, args):
    phases, types, formats = {}, {}, {}
    for entry in overview.values():
        if not isinstance(entry, dict):
            continue
        for bucket, key in (
            (phases, "project_phase"),
            (types, "source_material_type"),
            (formats, "file_format"),
        ):
            label = str(entry.get(key) or "unclassified")
            bucket[label] = bucket.get(label, 0) + 1

    extracted = list((Path(cache_dir) / EXTRACTED_DIR).rglob("*.md"))
    kb = Path(cache_dir) / "knowledge_base.md"

    print(f"Cache: {cache_dir}")
    print(f"Indexed artifacts: {len(overview)}")
    for title, bucket in (
        ("Project phases", phases),
        ("Material types", types),
        ("Formats", formats),
    ):
        print(f"\n{title}:")
        for label, count in sorted(bucket.items(), key=lambda kv: -kv[1]):
            print(f"  {count:>4}  {label}")
    print(f"\nExtracted text files under {EXTRACTED_DIR}/: {len(extracted)}")
    if kb.is_file():
        print(
            f"knowledge_base.md present ({kb.stat().st_size} bytes) — assembled for "
            "human review, not the retrieval source; use `content` instead."
        )
    return 0


def cmd_tree(overview, cache_dir, args):
    grouped = {}
    for path, entry in overview.items():
        phase = (
            str(entry.get("project_phase") or "unclassified")
            if isinstance(entry, dict)
            else "unclassified"
        )
        mat_type = (
            str(entry.get("source_material_type") or "unclassified")
            if isinstance(entry, dict)
            else "unclassified"
        )
        grouped.setdefault(phase, {}).setdefault(mat_type, []).append(path)

    print(f"Artifact index rollup, {len(overview)} artifacts:\n")
    for phase in sorted(grouped):
        total = sum(len(v) for v in grouped[phase].values())
        print(f"{phase}/  ({total})")
        for mat_type in sorted(grouped[phase]):
            paths = sorted(grouped[phase][mat_type])
            print(f"  {mat_type}/  ({len(paths)})")
            for path in paths[: args.per_group]:
                print(
                    f"      {Path(path).name} — {one_line(overview[path], width=110)}"
                )
            if len(paths) > args.per_group:
                print(f"      ... and {len(paths) - args.per_group} more")
        print()
    return 0


def matches_filters(entry, args):
    if not isinstance(entry, dict):
        return not (args.phase or args.type or args.format)
    if (
        args.phase
        and str(entry.get("project_phase") or "").lower() != args.phase.lower()
    ):
        return False
    if (
        args.type
        and str(entry.get("source_material_type") or "").lower() != args.type.lower()
    ):
        return False
    if args.format and str(
        entry.get("file_format") or ""
    ).lower() != args.format.lower().lstrip("."):
        return False
    return True


def cmd_list(overview, cache_dir, args):
    paths = sorted(p for p, entry in overview.items() if matches_filters(entry, args))
    if not paths:
        print("No indexed artifacts match those filters.", file=sys.stderr)
        return 1
    shown = paths[: args.limit] if args.limit else paths
    for path in shown:
        print(f"{path} — {one_line(overview[path], width=120)}")
    if len(paths) > len(shown):
        print(f"... and {len(paths) - len(shown)} more (raise --limit)")
    return 0


def cmd_search(overview, cache_dir, args):
    terms = [t.lower() for term in args.terms for t in term.split() if t]
    if not terms:
        print("No search terms given.", file=sys.stderr)
        return 1

    scored = []
    for path, entry in overview.items():
        if not matches_filters(entry, args):
            continue
        haystack = entry_text(entry).lower()
        path_lower = path.lower()
        if args.match_all and not all(t in haystack or t in path_lower for t in terms):
            continue
        score = 0
        for term in terms:
            score += haystack.count(term)
            # Filenames carry a lot of meaning in artifact trees
            # ("Week3_Pipeline_Review.docx"), so weight path hits.
            score += 5 * path_lower.count(term)
        if not score:
            continue
        scored.append((score, path))

    if not scored:
        print(f"No artifact entries match: {', '.join(terms)}")
        print(
            "Widen the terms, or grep the extracted text directly:\n"
            f"  grep -ril '<term>' '{Path(cache_dir) / EXTRACTED_DIR}'"
        )
        return 1

    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    shown = scored[: args.limit]
    print(f"{len(scored)} matching artifact(s); showing top {len(shown)}:\n")
    for score, path in shown:
        if args.full:
            print(format_entry(path, overview[path]))
            print()
        else:
            print(f"{path}  [score {score:.0f}]")
            print(f"    {one_line(overview[path])}")
    if len(scored) > len(shown):
        print(f"\n... and {len(scored) - len(shown)} more (raise --limit)")
    print(
        "\nSummaries are for routing. Read the extracted text with "
        "`content <path>` before quoting figures, dates, or decisions."
    )
    return 0


def cmd_files(overview, cache_dir, args):
    resolved, missing = resolve_paths(overview, args.paths)
    if missing:
        print(f"Not in the artifact index: {', '.join(missing)}", file=sys.stderr)
        print(
            "Either the artifact was added after the last indexing run, or its "
            "format is unsupported. Check `list` for what is indexed.",
            file=sys.stderr,
        )
    if not resolved:
        return 1
    if args.limit and len(resolved) > args.limit:
        print(
            f"(matched {len(resolved)} artifacts; showing first {args.limit} — "
            f"narrow the path or raise --limit)\n"
        )
        resolved = resolved[: args.limit]
    for index, path in enumerate(resolved):
        if index:
            print()
        print(format_entry(path, overview[path], brief=args.brief))
    return 0


def cmd_content(overview, cache_dir, args):
    """Print the extracted text of an artifact — the actual content.

    This is the artifact equivalent of reading the live file on the codebase
    side: summaries route, extracted text answers. There is no "live" artifact
    to read (a .pptx or .mp4 is not readable as text), so this extracted copy is
    as close to source as the skill gets — which is exactly why the staleness
    check matters before quoting from it.
    """
    resolved, missing = resolve_paths(overview, args.paths)
    if missing:
        print(f"Not in the artifact index: {', '.join(missing)}", file=sys.stderr)
    if not resolved:
        return 1
    if len(resolved) > args.limit:
        print(
            f"(matched {len(resolved)} artifacts; showing first {args.limit})\n",
            file=sys.stderr,
        )
        resolved = resolved[: args.limit]

    printed = 0
    for path in resolved:
        text_path = extracted_text_path(cache_dir, path)
        print(f"### {path}")
        if not text_path.is_file():
            print(
                f"(no extracted text at {text_path} — extraction failed or was "
                "skipped; the summary in `files` is all the index has)\n"
            )
            continue
        try:
            content = text_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"(could not read {text_path}: {exc})\n")
            continue
        if args.max_chars and len(content) > args.max_chars:
            print(content[: args.max_chars])
            print(
                f"\n... truncated at {args.max_chars} of {len(content)} characters "
                f"(raise --max-chars, or read {text_path} directly)"
            )
        else:
            print(content)
        print()
        printed += 1
    return 0 if printed else 1


def build_parser():
    parser = argparse.ArgumentParser(
        description="Extract targeted slices of an IRIS artifact_overview.json."
    )
    parser.add_argument("--repo", default=".", help="Repository root (default: cwd)")
    parser.add_argument("--cache", help="Cache dir; discovered by glob when omitted")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_filters(sub):
        sub.add_argument("--phase", help="Filter by project_phase")
        sub.add_argument("--type", help="Filter by source_material_type")
        sub.add_argument("--format", help="Filter by file_format (pptx, docx, pdf, …)")

    p_stats = subparsers.add_parser("stats", help="Artifact index shape")
    p_stats.set_defaults(func=cmd_stats)

    p_tree = subparsers.add_parser("tree", help="phase → type rollup with purposes")
    p_tree.add_argument("--per-group", type=int, default=8)
    p_tree.set_defaults(func=cmd_tree)

    p_list = subparsers.add_parser("list", help="Compact path + one-line purpose")
    add_filters(p_list)
    p_list.add_argument("--limit", type=int, default=0, help="0 = no limit")
    p_list.set_defaults(func=cmd_list)

    p_search = subparsers.add_parser("search", help="Keyword search over summaries")
    p_search.add_argument("terms", nargs="+")
    add_filters(p_search)
    p_search.add_argument("--limit", type=int, default=12)
    p_search.add_argument(
        "--full", action="store_true", help="Print full entries, not one-liners"
    )
    p_search.add_argument(
        "--match-all",
        action="store_true",
        help="Require every term to appear (default: any term, ranked)",
    )
    p_search.set_defaults(func=cmd_search)

    p_files = subparsers.add_parser("files", help="Full entries for named artifacts")
    p_files.add_argument("paths", nargs="+")
    p_files.add_argument("--brief", action="store_true", help="Drop the long summary")
    p_files.add_argument("--limit", type=int, default=20)
    p_files.set_defaults(func=cmd_files)

    p_content = subparsers.add_parser(
        "content", help="Extracted text of an artifact (the actual content)"
    )
    p_content.add_argument("paths", nargs="+")
    p_content.add_argument(
        "--max-chars",
        type=int,
        default=20000,
        help="Truncate each artifact's text (0 = no limit; default 20000)",
    )
    p_content.add_argument("--limit", type=int, default=5)
    p_content.set_defaults(func=cmd_content)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    # Mirror the sibling scripts: the working directory is often unrelated to the
    # indexed repo, so resolve via cwd, ancestors, then the registry.
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
        print(
            f"This repo is NOT indexed: {resolution.unindexed_cwd}\n"
            "Offer to index it (the skill's setup task). Do not answer from "
            "another repo's cache.",
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

    cache_dir, overview = load_artifact_overview(repo_root, args.cache)
    if not overview:
        print(
            f"{ARTIFACT_OVERVIEW_FILE} is empty — artifact indexing ran but "
            "summarized nothing. Treat artifacts as unindexed.",
            file=sys.stderr,
        )
        return 1
    return args.func(overview, cache_dir, args)


if __name__ == "__main__":
    sys.exit(main())
