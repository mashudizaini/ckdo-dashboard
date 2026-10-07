#!/usr/bin/env python3
"""Verify every aliased named import points at something the target really exports.

Why this exists: on 2026-10-07 the whole production dashboard rendered blank
because one component imported `ebsBackupApi` from `@/api/dashboard` when it
lives in `@/api/ebsBackup`. In ESM a named import that does not exist is a hard
error, and because the failing module sat under the router, one wrong path took
the entire app down rather than one page.

It was not caught because the checks used proved the wrong things: esbuild
parses a single file, so it validates syntax and never resolves `@/` or looks at
another module's exports; and "the file is served with HTTP 200" only proves the
file exists, not that the app mounts.

    python scripts/check_imports.py      # exit 1 if anything is wrong
"""
import glob
import io
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..", "frontend", "src")
IMPORT_RE = re.compile(r'import\s*\{([^}]+)\}\s*from\s*"@/([^"]+)"')


def resolve(target: str):
    for cand in (target, target + ".js", target + ".jsx",
                 os.path.join(target, "index.js"), os.path.join(target, "index.jsx")):
        full = os.path.join(ROOT, cand)
        if os.path.isfile(full):
            return full
    return None


def exports(src: str, name: str) -> bool:
    return bool(
        re.search(rf'export\s+(const|function|class|let|var)\s+{re.escape(name)}\b', src)
        or re.search(rf'export\s*\{{[^}}]*\b{re.escape(name)}\b', src)
        or f"export default {name}" in src
    )


def main() -> int:
    problems = []
    files = (glob.glob(os.path.join(ROOT, "**", "*.jsx"), recursive=True)
             + glob.glob(os.path.join(ROOT, "**", "*.js"), recursive=True))
    for path in files:
        src = io.open(path, encoding="utf-8").read()
        for names, target in IMPORT_RE.findall(src):
            full = resolve(target)
            rel = os.path.relpath(path, ROOT)
            if not full:
                problems.append(f"{rel} -> @/{target} : module not found")
                continue
            tgt = io.open(full, encoding="utf-8").read()
            for raw in names.split(","):
                name = raw.strip().split(" as ")[0].strip()
                if name and not exports(tgt, name):
                    problems.append(f"{rel} -> @/{target} : '{name}' is not exported")

    for p in problems:
        print(f"  {p}")
    print(f"{len(problems)} problem(s)" if problems
          else f"OK — {len(files)} files, every aliased named import resolves.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
