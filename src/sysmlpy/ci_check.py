# -*- coding: utf-8 -*-
"""CI check engine: parse gate + advisory semantics for SysML/KerML files.

Shared engine behind the ``sysmlpy ci`` subcommand, the GitHub Action
(``.github/workflows/sysml-check.yml``), the GitLab template, and the
pre-commit hooks — one exit-code contract everywhere:

=====  =========================================================
code   meaning
=====  =========================================================
0      all files parse; no findings at/above the failure level
1      findings at/above the failure level (parse failures always
       count; semantic errors only when ``semantic`` is ``strict``)
2      operational error (no files found, unreadable directory)
=====  =========================================================

Why semantics is advisory by default
-----------------------------------
The semantic analyzer is correct on the ~200 assertions pinned in
``tests/semantic_test.py``, but the bundled standard library is only
symbol-indexed by name (``LibrarySymbolIndex``), never loaded as a
model — so re-export facades (``ISQ`` re-exporting ``ISQBase::*``) and
unit usages (``SI::metre``) surface as false ``UNRESOLVED_IMPORT`` /
``UNDEFINED_SYMBOL`` errors on units-heavy models.  Probed on the valid
corpus (``tests/sysmlv2/validation/valid``): 28 of 71 files that parse
cleanly still report semantic errors, all in these known classes.
Until the library is model-loaded, a strict semantic gate would reject
valid models — so ``advisory`` is the honest default and ``strict``
promotes the check once a codebase is analyzer-clean.

Usage (library consumers)
-------------------------
>>> from sysmlpy.ci_check import run_check
>>> result = run_check(["model.sysml"])           # parse gate only
>>> result = run_check(["model.sysml"], semantic="advisory")
>>> result.exit_code, result.parse_failures        # (0, [])

The same engine runs from the CLI:

    sysmlpy ci .                    # parse gate, advisory semantics
    sysmlpy ci models --semantic strict   # promote to blocking
    sysmlpy ci . --format json     # machine-readable findings
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

SOURCE_EXTENSIONS = (".sysml", ".kerml")

# Known false-positive classes (see module docstring).  Advisory mode
# reports these but never blocks; strict mode treats every error as
# blocking.  Kept as a list so the JSON report can label them.
KNOWN_LIMITED_CLASSES = (
    "UNRESOLVED_IMPORT",
    "UNDEFINED_SYMBOL",
    "UNRESOLVED_EXPRESSION_IDENTIFIER",
    "INCOMPATIBLE_FEATURE_CHAIN",
    "INCOMPATIBLE_SUBSETTING",
    "DUPLICATE_NAME",
    "INCOMPATIBLE_PART_DEFINITION",
)


@dataclass
class CheckFinding:
    """One finding from the parse or semantic gate."""

    file: str
    level: str          # "error" | "warning"
    stage: str          # "parse" | "semantic"
    code: str           # e.g. "PARSE", "UNDEFINED_SYMBOL"
    message: str
    known_limitation: bool = False

    def as_dict(self) -> dict:
        return {
            "file": self.file,
            "level": self.level,
            "stage": self.stage,
            "code": self.code,
            "message": self.message,
            "known_limitation": self.known_limitation,
        }


@dataclass
class CheckResult:
    """Aggregate result over all checked files."""

    files_checked: int = 0
    findings: List[CheckFinding] = field(default_factory=list)
    duration_s: float = 0.0
    semantic_mode: str = "off"       # "off" | "advisory" | "strict"
    exit_code: int = 0

    @property
    def parse_failures(self) -> List[CheckFinding]:
        return [f for f in self.findings if f.stage == "parse" and f.level == "error"]

    @property
    def semantic_errors(self) -> List[CheckFinding]:
        return [f for f in self.findings if f.stage == "semantic" and f.level == "error"]

    @property
    def semantic_warnings(self) -> List[CheckFinding]:
        return [f for f in self.findings if f.stage == "semantic" and f.level == "warning"]

    def as_dict(self) -> dict:
        return {
            "files_checked": self.files_checked,
            "semantic_mode": self.semantic_mode,
            "duration_s": round(self.duration_s, 2),
            "exit_code": self.exit_code,
            "summary": {
                "parse_failures": len(self.parse_failures),
                "semantic_errors": len(self.semantic_errors),
                "semantic_warnings": len(self.semantic_warnings),
            },
            "findings": [f.as_dict() for f in self.findings],
        }

    def as_text(self) -> str:
        """Human-readable report (stdout for the CLI/Action)."""
        lines: List[str] = []
        mode = {"off": "off", "advisory": "advisory (non-blocking)",
                "strict": "strict (blocking)"}[self.semantic_mode]
        lines.append(f"sysmlpy ci: {self.files_checked} file(s), "
                     f"semantics {mode}")
        for f in self.findings:
            flag = "  [known analyzer limitation]" if f.known_limitation else ""
            lines.append(f"{f.file}: {f.level}: {f.stage}: {f.code}: "
                         f"{f.message}{flag}")
        lines.append("")
        lines.append(f"summary: {len(self.parse_failures)} parse failure(s), "
                     f"{len(self.semantic_errors)} semantic error(s), "
                     f"{len(self.semantic_warnings)} semantic warning(s)")
        verdict = {0: "PASS", 1: "FAIL", 2: "ERROR"}[self.exit_code]
        lines.append(f"result: {verdict}")
        return "\n".join(lines)


def discover_files(
    paths: Sequence[str | Path],
    *,
    extensions: Sequence[str] = SOURCE_EXTENSIONS,
    exclude: Sequence[str] = (),
) -> List[Path]:
    """Collect .sysml/.kerml files from files/directories (recursive).

    Exclusions match if any given pattern is a substring of the file's
    path — simple, portable across GitHub/GitLab/pre-commit contexts.
    """
    found: List[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            if p.suffix in extensions and not _excluded(p, exclude):
                if p not in seen:
                    seen.add(p)
                    found.append(p)
        elif p.is_dir():
            for ext in extensions:
                for fp in sorted(p.rglob(f"*{ext}")):
                    if fp.is_file() and not _excluded(fp, exclude) and fp not in seen:
                        seen.add(fp)
                        found.append(fp)
    return found


def _excluded(path: Path, exclude: Sequence[str]) -> bool:
    posix = path.as_posix()
    return any(pat in posix for pat in exclude)


def _parse_one(path: Path) -> Optional[str]:
    """Parse a file; return an error message or None on success.

    KerML files parse through the KerML grammar; SysML files through
    the full pipeline (loads).  The parse gate must be exactly as
    strict as ``sysmlpy.loads`` — no rescue, no partial parse.
    """
    if path.suffix == ".kerml":
        from sysmlpy.kerml import parse_file
        try:
            parse_file(str(path))
            return None
        except Exception as e:  # KerMLSyntaxError and any parse failure
            return str(e)
    import sysmlpy
    try:
        sysmlpy.loads(path.read_text(encoding="utf-8"))
        return None
    except Exception as e:  # SysMLSyntaxError and any parse-time failure
        return str(e)


def _analyze_one(path: Path, library: Optional[str]) -> List[CheckFinding]:
    """Run semantic analysis on one file; convert issues to findings."""
    import sysmlpy
    from sysmlpy import analyze

    findings: List[CheckFinding] = []
    try:
        if path.suffix == ".kerml":
            from sysmlpy.kerml import parse_to_dict
            model = parse_to_dict(path.read_text(encoding="utf-8"))
            # KerML symbol resolution is out of scope for the semantic
            # gate: the analyzer's checks are SysML-model-shaped.
            return findings
        kw: dict = {"filename": str(path)}
        if library:
            kw["library"] = library
        model = sysmlpy.loads(path.read_text(encoding="utf-8"))
        result = analyze(model, **kw)
        for issue in result:
            known = issue.code in KNOWN_LIMITED_CLASSES
            findings.append(CheckFinding(
                file=str(path),
                level=issue.severity,
                stage="semantic",
                code=issue.code,
                message=issue.message,
                known_limitation=known,
            ))
    except Exception as e:  # analysis crashed: report, don't kill the run
        findings.append(CheckFinding(
            file=str(path), level="error", stage="semantic",
            code="ANALYZER_CRASH", message=str(e)[:300],
        ))
    return findings


def run_check(
    paths: Sequence[str | Path],
    *,
    semantic: str = "advisory",
    library: Optional[str] = None,
    exclude: Sequence[str] = (),
    max_files: int = 2000,
) -> CheckResult:
    """Run the CI check over files/directories.

    Parameters
    ----------
    paths : files or directories (searched recursively)
    semantic : "off" | "advisory" (default) | "strict"
    library : optional path to a library root for semantic analysis
    exclude : substring patterns to skip (e.g. "third_party/")
    max_files : safety cap on discovered files

    Returns
    -------
    CheckResult with a decided exit_code (0/1/2) — the CLI, GitHub
    Action, GitLab template, and pre-commit all propagate it.
    """
    if semantic not in ("off", "advisory", "strict"):
        raise ValueError(f"semantic must be off/advisory/strict, got {semantic!r}")

    started = time.time()
    result = CheckResult(semantic_mode=semantic)

    files = discover_files(paths, exclude=exclude)
    if not files:
        result.exit_code = 2
        result.findings.append(CheckFinding(
            file="-", level="error", stage="parse", code="NO_FILES",
            message=f"No SysML/KerML files found under "
                    f"{', '.join(str(p) for p in paths)}",
        ))
        result.duration_s = time.time() - started
        return result
    if len(files) > max_files:
        result.exit_code = 2
        result.findings.append(CheckFinding(
            file="-", level="error", stage="parse", code="TOO_MANY_FILES",
            message=f"{len(files)} files exceeds max_files={max_files}",
        ))
        result.duration_s = time.time() - started
        return result

    for path in files:
        # ---- parse gate (always blocking) ----
        err = _parse_one(path)
        result.files_checked += 1
        if err is not None:
            result.findings.append(CheckFinding(
                file=str(path), level="error", stage="parse",
                code="PARSE", message=err,
            ))
            continue  # no point analyzing an unparseable file
        # ---- semantic gate ----
        if semantic == "off":
            continue
        result.findings.extend(_analyze_one(path, library))

    blocking = list(result.parse_failures)
    if semantic == "strict":
        blocking += result.semantic_errors

    result.exit_code = 1 if blocking else 0
    result.duration_s = time.time() - started
    return result


def format_output(result: CheckResult, fmt: str = "text") -> str:
    """Render a CheckResult as text or JSON (CLI ``--format``)."""
    if fmt == "json":
        return json.dumps(result.as_dict(), indent=2)
    return result.as_text()
