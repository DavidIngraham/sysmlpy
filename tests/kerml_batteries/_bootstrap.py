#!/usr/bin/env python3
"""Shared bootstrap for the kerml battery scripts.

Batteries must run for ANY contributor from ANY clone location, so this
module replaces the old hardcoded machine paths:

- Source resolution: prefer an already-importable ``sysmlpy`` (pytest run
  against an installed/venv package, batteries run in-tree via uv/poetry),
  then the checkout's ``src/`` tree, then a project-local ``.venv``.
- OMG SysML-v2-Release corpus resolution: ``$SYSML2_RELEASE_DIR`` first,
  then well-known sibling locations, else a one-time shallow clone pinned
  to a fixed upstream commit (re-downloadable, cacheable, CI-friendly).

Call :func:`boot` at the top of a battery to fix up ``sys.path``; call
:func:`corpus_root` wherever the corpus is needed. Every battery prints a
``RESULT:`` line and exits 1 on failure, so the pytest wrapper
(``tests/kerml_test.py``) needs no knowledge of this module.
"""
import os
import subprocess
import sys
from pathlib import Path

# Pinned upstream commit of Systems-Modeling/SysML-v2-Release. The 2026-08
# release update (fb97b75); bump deliberately when the corpus must move.
CORPUS_PINNED_COMMIT = "fb97b754f29588b8e9c7a35f370880cd15eb29e7"
CORPUS_REPO_URL = "https://github.com/Systems-Modeling/SysML-v2-Release.git"


def count_elements(node: dict) -> int:
    """Total number of nodes in a parse_to_dict tree (incl. the root)."""
    n = 1
    for child in node.get("children", []):
        n += count_elements(child)
    return n


def _parse_to_dict_nonempty(text: str) -> dict:
    from sysmlpy.kerml.kerml_visitor import parse_to_dict

    dd = parse_to_dict(text)
    if count_elements(dd) == 0:
        raise ValueError("0 elements extracted")
    return dd


def _safe_call(fn, text: str) -> str | None:
    """Run fn(text); None on success, 'ExcType: msg' string on failure.

    Results cross the process-pool boundary, so failures are reported as
    plain strings — parser exception objects carry unpicklable streams.
    """
    try:
        fn(text)
    except Exception as e:  # noqa: BLE001 - stringified for pickling
        return f"{type(e).__name__}: {e}"
    return None


def parse_texts_parallel(
    items: list[tuple], fn,
) -> list[tuple]:
    """Run fn(text) over (label, text) items, preserving order.

    Returns list[(label, None_or_error_string)]. Uses a small process pool
    when several cores are available (the ANTLR runtime is GIL-bound, so
    threads would not help); falls back to serial otherwise.
    """
    workers = min(4, os.cpu_count() or 1)
    if workers <= 1 or len(items) < 8:
        out = []
        for label, text in items:
            out.append((label, _safe_call(fn, text)))
        return out
    from concurrent.futures import ProcessPoolExecutor

    results: list[tuple] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_safe_call, fn, text) for _, text in items]
        for (label, _), fut in zip(items, futs):
            results.append((label, fut.result()))
    return results


def repo_root() -> Path:
    """Checkout root: kerml_batteries/ -> tests/ -> repo root."""
    return Path(__file__).resolve().parent.parent.parent


def checkout_venv() -> Path | None:
    """The checkout's optional ``.venv/`` python (gitignored, opt-in)."""
    venv = repo_root() / ".venv"
    py = venv / "bin" / "python"
    return py if py.exists() else None


def _importable(interp: Path) -> bool:
    probe = subprocess.run(
        [str(interp), "-c", "import sysmlpy"],
        capture_output=True,
    )
    return probe.returncode == 0


def boot() -> None:
    """Make ``import sysmlpy`` work for the calling battery.

    In order: existing interpreter (no-op), checkout ``src/`` tree,
    checkout ``.venv``. Prints one line about what was done.
    """
    probe = subprocess.run([sys.executable, "-c", "import sysmlpy"],
                           capture_output=True)
    if probe.returncode == 0:
        return
    src = repo_root() / "src"
    if (src / "sysmlpy").is_dir():
        sys.path.insert(0, str(src))
        print(f"[bootstrap] sys.path.insert(0, {src})")
        return
    venv_py = checkout_venv()
    if venv_py is not None and _importable(venv_py):
        print(f"[bootstrap] re-exec under {venv_py}")
        os.execv(str(venv_py), [str(venv_py), *sys.argv])
    raise SystemExit(
        "[bootstrap] sysmlpy is not importable. Either install it "
        "(pip install -e .) or run the batteries with the project venv "
        "(source .venv/bin/activate or uv run pytest)."
    )


def corpus_root() -> Path | None:
    """Locate the OMG SysML-v2-Release checkout.

    Order: ``$SYSML2_RELEASE_DIR``, previous auto-clone cache, local
    well-known checkouts, a pinned shallow clone of the pinned commit.
    Returns None only when a clone is impossible (no network and no
    local copy), so batteries can skip corpus sections gracefully.
    """
    env = os.environ.get("SYSML2_RELEASE_DIR")
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p

    root = repo_root()
    cache = root / ".cache" / "SysML-v2-Release"

    def _is_corpus(p: Path) -> bool:
        return p.is_dir() and (p / "sysml.library").is_dir()

    if _is_corpus(cache):
        return cache
    for candidate in (
        Path("/mnt/TBFox/SysML-v2-Release"),
        Path.home() / "third_party" / "SysML-v2-Release",
        Path("/storage16/home/jfox/proj/third_party/SysML-v2-Release"),
    ):
        if _is_corpus(candidate):
            return candidate

    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        print(f"[bootstrap] cloning corpus from {CORPUS_REPO_URL} ...")
        subprocess.run(
            ["git", "clone", "--filter=blob:none", CORPUS_REPO_URL,
             str(cache)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(cache), "checkout", "--quiet",
             CORPUS_PINNED_COMMIT],
            check=True, capture_output=True,
        )
    except Exception as exc:  # noqa: BLE001 - offline CI/dev falls through
        print(f"[bootstrap] corpus clone unavailable: {exc}")
        return None
    return cache


_corpus_cache: Path | None = None
_corpus_resolved = False


def corpus_or_none() -> Path | None:
    """Cached corpus lookup; never raises (None = corpus unavailable)."""
    global _corpus_cache, _corpus_resolved
    if not _corpus_resolved:
        _corpus_cache = corpus_root()
        _corpus_resolved = True
    return _corpus_cache


def kernel_library_dir() -> Path:
    """sysmlpy's bundled kernel library (in-tree, always available)."""
    return repo_root() / "src" / "sysmlpy" / "library" / "kernel"