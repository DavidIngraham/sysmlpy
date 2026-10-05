# CI Integration Guide

Parse and semantics checks for SysML/KerML models in GitHub Actions,
GitLab CI, and pre-commit — one engine, one exit-code contract
everywhere:

| exit | meaning |
|------|---------|
| 0 | all files parse; no findings at/above the failure level |
| 1 | findings at/above the failure level (parse failures always block) |
| 2 | operational error (no files found, unreadable input) |

The engine is `sysmlpy ci` (`src/sysmlpy/ci_check.py`). The same code
runs in every integration below, so behavior can never drift between
them.

## Gate 1: parse (blocking, always on)

Every `.sysml` file must parse through the full pipeline
(`sysmlpy.loads` — ANTLR parse → visitor → grammar classes). Every
`.kerml` file must parse through the KerML grammar. A syntax error is a
finding with `file:line:col` position and fails the check in every
semantic mode. No rescue, no partial parse — exactly what `loads`
accepts.

Gate status (probed 2026-10-04, v0.96.4):

- OMG valid corpus (`tests/sysmlv2/validation/valid/`): **71/71** files
  that should parse, do (the 72nd, `Import_Visibility_Valid.sysml`,
  embeds a deliberate bare-import syntax error per its own XPECT
  comments — bare `import` without a visibility keyword is
  intentionally rejected; see AGENTS.md pitfall 7).
- Bundled standard library (`src/sysmlpy/library/`): all files parse —
  this repository's own CI gates them via the `sysml-check` workflow
  on every push.

## Gate 2: semantics (advisory by default, strict opt-in)

After parsing, each file is run through the semantic analyzer
(`sysmlpy.analyze`) with the same findings model. Three modes:

- `--semantic off` — skip semantic analysis entirely.
- `--semantic advisory` (**default**) — findings are printed and
  labeled, but never fail the check. Parse failures still block.
- `--semantic strict` — semantic **errors** fail the check (exit 1).
  Warnings still don't block, mirroring `sysmlpy analyze --fail-on
  error`.

Why advisory is the default — known analyzer limitations. The analyzer
is correct on the ~200 assertions pinned in `tests/semantic_test.py`,
but the bundled standard library is only symbol-indexed by name
(`LibrarySymbolIndex`), never loaded as a model. Consequences for
realistic units-heavy models:

- `import SI::*` flags `UNRESOLVED_IMPORT` — top-level package names
  (`SI`, `Quantities`) are not registered as namespaces by the index
  (only nested packages are).
- `ISQ::LengthValue` flags `UNDEFINED_SYMBOL` — the `ISQ` package is a
  re-export facade (`public import ISQBase::*`), and re-exports are not
  followed.
- Unit expressions (`kg`, `N`, `['m/s²']`) flag
  `UNRESOLVED_EXPRESSION_IDENTIFIER` — the analyzer does not resolve
  identifiers against imported unit symbols.

Probed on the OMG valid corpus: 28 of 71 cleanly-parsing files report
semantic errors, all in these classes. A strict default would reject
valid models — so advisory is the honest default, and the findings are
labeled `known analyzer limitation` in text and JSON output.

### Promoting to strict

1. Run `sysmlpy ci . --semantic advisory` and triage the findings:
   - real model bugs — fix them (this is the value of the check);
   - false positives — all in the known classes above.
2. When the findings are all known-class false positives, promote with
   `--semantic strict`. If a new false-positive class appears later,
   file it (the `known_limitation` label in JSON output identifies the
   class).

## GitHub Actions

This repository exposes a reusable workflow:
`.github/workflows/sysml-check.yml` (also triggered on its own pushes
and PRs, dogfooding the repo's library and fixtures). In your repo:

```yaml
jobs:
  sysml-check:
    uses: mycr0ft/sysmlpy/.github/workflows/sysml-check.yml@v0.96.4
    with:
      paths: models              # space-separated files/dirs
      semantic: advisory         # off | advisory | strict
      exclude: third_party/      # comma-separated substring patterns
      library: ''                # optional library root for semantics
      install: pypi              # pypi (released) | source (this repo)
      version: ''                # pin a version when install=pypi
      python-version: '3.12'
```

The workflow caches the ANTLR DFA cache (`~/.cache/sysmlpy`) keyed on
`pyproject.toml` — cold parses are dominated by DFA construction, so
repeat runs are substantially faster.

`install: source` installs sysmlpy from the calling repo's checkout —
that's wrong unless the calling repo *is* sysmlpy; it exists for this
repo's own dogfood runs (`sysml-dogfood.yml`).

This repo dogfoods the gate on every push/PR: `sysml-dogfood.yml`
calls the reusable workflow locally with
`paths: src/sysmlpy/library tests/fixtures`, `install: source` —
the bundled standard library and the runtime-showcase fixtures must
always parse. (The `tests/sysmlv2/validation/invalid/` corpus is
deliberately *not* gated — those files must fail to parse.)

## GitLab CI

Include the template from this repo and extend the base job:

```yaml
include:
  - project: mycr0ft/sysmlpy
    ref: v0.96.4
    file: .gitlab/sysml-check.gitlab-ci.yml

sysml-check:
  extends: .sysml-check
  variables:
    SYSML_PATHS: "models src"   # files/dirs to check
    SYSML_SEMANTIC: "advisory"  # off | advisory | strict
    SYSML_EXCLUDE: "third_party/,sandbox/"
    SYSMLPY_VERSION: "0.96.4"   # pin; empty = latest
```

The job caches pip and the DFA cache (`.cache/sysmlpy`) between runs.

## pre-commit

Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/mycr0ft/sysmlpy
    rev: v0.96.4
    hooks:
      - id: sysmlpy-ci           # parse gate + advisory semantics
        args: ['--semantic', 'strict']   # optional: promote
        exclude: ^third_party/
      # or the pure parse gate:
      - id: sysmlpy-parse
```

Hooks receive only the changed files (`pass_filenames: true`), so
commit-time checks are fast even on large trees. Note pre-commit
installs the hook environment from the *hook repo* (sysmlpy), so
`language: python` here means "install sysmlpy from this repo's tag".

## CI-friendly flags

- `--format json` — machine-readable output: per-finding
  `file`/`level`/`stage`/`code`/`message`/`known_limitation`, a
  `summary` block, and the `exit_code`. Useful for posting check
  results as PR comments or GitLab merge-request widgets.
- `--exclude PATTERN` — substring match on the path, repeatable.
  Skip vendored models, generated files, third-party trees.
- `-l/--library PATH` — library root for semantic analysis.
- `--no-semantic` — shorthand for `--semantic off`.

## Programmatic use

```python
from sysmlpy.ci_check import run_check

result = run_check(["models"], semantic="advisory")
if result.exit_code:
    for f in result.parse_failures:
        print(f.file, f.message)
```

`run_check` returns a `CheckResult` (`.parse_failures`,
`.semantic_errors`, `.semantic_warnings`, `.as_dict()`,
`.as_text()`).
