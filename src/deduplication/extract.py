#!/usr/bin/env python3
"""
Split a monolithic Markdown file produced by the fuzzer into individual findings.

Usage:
    python extract.py reported_issues_36.md
Outputs:
    reported_issues_36/00000.md
    reported_issues_36/00001.md
    …
Prints total non-empty findings kept.

“Empty stuff” = blocks whose *body* (everything after the header) is only
whitespace → they are silently discarded.
"""

import re, sys, pathlib

HDR = re.compile(r"^##\s+Reported Issue by Agent\b", re.I)


def split_findings(text: str) -> list[str]:
    """Return list of finding blocks (header included), skipping empty bodies."""
    blocks, cur = [], []
    for line in text.splitlines(keepends=True):
        if HDR.match(line):
            if cur and _body_has_content(cur):
                blocks.append("".join(cur))
            cur = [line]  # start new block with header
        else:
            cur.append(line)
    if cur and _body_has_content(cur):
        blocks.append("".join(cur))
    return blocks


def _body_has_content(lines: list[str]) -> bool:
    """True if block has non-blank text after the first line (the header)."""
    return any(s.strip() for s in lines[1:])  # ignore header


def main(md_path: str):
    src = pathlib.Path(md_path)
    out_dir = src.with_suffix("")  # e.g. reported_issues_36/
    out_dir.mkdir(exist_ok=True)

    findings = split_findings(src.read_text(encoding="utf-8"))

    for i, block in enumerate(findings):
        (out_dir / f"{i:05}.md").write_text(block, encoding="utf-8")

    print(f"non-empty findings written: {len(findings)} → {out_dir}/")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("provide exactly one .md path")
    main(sys.argv[1])
