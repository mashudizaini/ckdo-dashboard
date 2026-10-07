#!/usr/bin/env python3
"""Catch the two import mistakes that have each blanked the production dashboard.

Both were one missing name, and both took the WHOLE app down rather than one
page, because the failing module sits under the router:

  1. 2026-10-07 — a component imported `ebsBackupApi` from `@/api/dashboard`
     when it lives in `@/api/ebsBackup`. In ESM a named import that does not
     exist is a hard error.
  2. 2026-10-07 — `<Pencil />` was used without being added to the lucide
     import, throwing ReferenceError on render.

Neither was caught by what was being used to verify:

  * `esbuild <file>` parses ONE file, so it validates syntax and never resolves
    `@/` or reads another module's exports.
  * "the file is served with HTTP 200" only proves the file exists, not that
    the app mounts.
  * eslint's `no-undef`, run with --no-eslintrc, reported nothing for the
    missing `Pencil` — verified directly against the broken file.

So this checks bindings itself: every capitalised identifier a file uses must
be imported into that file, declared in it, or destructured in it.

    python scripts/check_imports.py      # exit 1 if anything is wrong
"""
import glob
import io
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..", "frontend", "src")

ALIAS_IMPORT_RE = re.compile(r'import\s*\{([^}]+)\}\s*from\s*"@/([^"]+)"')
# Any import form: named, default, namespace.
IMPORT_BLOCK_RE = re.compile(r'import\s+([^;]+?)\s+from\s*["\']', re.S)
JSX_TAG_RE = re.compile(r"<([A-Z][A-Za-z0-9_]*)\b")
# A component passed as a JSX attribute value: icon={Pencil}.
#
# Scanning for capitalised identifiers generally does not work in JSX files:
# the prose BETWEEN tags is ordinary text, so "This", "Today" and "What" all
# look like identifiers, and so do object keys like `Authorization:`. An
# earlier version reported 2627 of those. These two shapes — a tag and an
# attribute value — are unambiguous, and between them they cover both real
# incidents: <Pencil /> and icon={Pencil}.
ATTR_USE_RE = re.compile(r"=\{([A-Z][A-Za-z0-9_]*)\}")

DECL_RE = re.compile(r"\b(?:function|class|const|let|var)\s+([A-Z][A-Za-z0-9_]*)")
# Destructured bindings, including renames: { icon: Icon }, { Foo }
DESTRUCTURE_RE = re.compile(r"[{,]\s*(?:[\w$]+\s*:\s*)?([A-Z][A-Za-z0-9_]*)\s*(?=[,}=])")
# Array destructuring binds too: const [RC, setRC] = useState(),
# .map(([id, label, Icon]) => ...). Without this the checker reported both as
# undefined — and five standing false alarms is how a tool stops being read.
ARRAY_DESTRUCTURE_RE = re.compile(r"[\[,]\s*([A-Z][A-Za-z0-9_]*)\s*(?=[,\]])")

# Globals that need no import. Not exhaustive — only what this codebase uses.
GLOBALS = {
    "React", "Math", "JSON", "Object", "Array", "String", "Number", "Boolean",
    "Date", "Promise", "Map", "Set", "WeakMap", "RegExp", "Error", "TypeError",
    "Intl", "URL", "URLSearchParams", "WebSocket", "Blob", "File", "FileReader",
    "FormData", "Image", "Infinity", "NaN", "AbortController", "Notification",
    "Audio", "Worker", "DOMParser", "TextDecoder", "TextEncoder", "Uint8Array",
    "ArrayBuffer", "BigInt", "Symbol", "Proxy", "Reflect", "Function",
}


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


def strip_noise(src: str) -> str:
    """Remove comments and string literals before looking for identifiers.

    Without this the scan reads prose: the first version reported 5918
    "problems", almost all of them Indonesian comment words that happen to be
    capitalised. A checker that cries wolf that loudly is worse than none,
    because nobody reads its output twice.

    JSX text between tags is left alone — it is matched only by the JSX tag
    pattern, which requires a '<' immediately before the name.
    """
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)      # /* block */
    src = re.sub(r"(?m)//.*$", " ", src)                    # // line
    src = re.sub(r"`[^`]*`", " ", src)                      # `template`
    src = re.sub(r"'[^'\n]*'", " ", src)                    # 'single'
    src = re.sub(r'"[^"\n]*"', " ", src)                    # "double"
    return src


def bound_names(src: str) -> set:
    """Every capitalised name this file actually brings into scope."""
    names = set(GLOBALS)
    for clause in IMPORT_BLOCK_RE.findall(src):
        # `Default, { a, b as c }` / `* as NS` / `{ x }`
        clause = clause.replace("*", " ")
        for part in re.split(r"[{},]", clause):
            part = part.strip()
            if not part:
                continue
            # `b as c` binds c; `as NS` binds NS
            if " as " in part:
                part = part.split(" as ")[-1]
            part = part.strip()
            if re.fullmatch(r"[A-Za-z0-9_$]+", part):
                names.add(part)
    names.update(DECL_RE.findall(src))
    names.update(DESTRUCTURE_RE.findall(src))
    names.update(ARRAY_DESTRUCTURE_RE.findall(src))
    return names


def undefined_capitalised(src: str) -> list:
    # Bindings are read from the original (imports live in strings-free code
    # anyway); uses are read from the stripped copy so comments and string
    # contents cannot masquerade as identifiers.
    bound = bound_names(src)
    clean = strip_noise(src)
    used = set(JSX_TAG_RE.findall(clean)) | set(ATTR_USE_RE.findall(clean))
    return sorted(n for n in used if n not in bound)


def main() -> int:
    problems = []
    files = (glob.glob(os.path.join(ROOT, "**", "*.jsx"), recursive=True)
             + glob.glob(os.path.join(ROOT, "**", "*.js"), recursive=True))
    for path in files:
        src = io.open(path, encoding="utf-8").read()
        rel = os.path.relpath(path, ROOT)

        for names, target in ALIAS_IMPORT_RE.findall(src):
            full = resolve(target)
            if not full:
                problems.append(f"{rel} -> @/{target} : module not found")
                continue
            tgt = io.open(full, encoding="utf-8").read()
            for raw in names.split(","):
                name = raw.strip().split(" as ")[0].strip()
                if name and not exports(tgt, name):
                    problems.append(f"{rel} -> @/{target} : '{name}' is not exported")

        for name in undefined_capitalised(src):
            problems.append(f"{rel} : '{name}' used but never imported or declared")

    for p in problems:
        print(f"  {p}")
    print(f"{len(problems)} problem(s)" if problems
          else f"OK - {len(files)} files, every import and capitalised name resolves.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
