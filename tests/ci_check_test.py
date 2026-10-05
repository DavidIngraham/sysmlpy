# -*- coding: utf-8 -*-
"""Tests for the CI check engine and ``sysmlpy ci`` subcommand.

Pins the exit-code contract shared by the CLI, the GitHub Action
(``.github/workflows/sysml-check.yml``), the GitLab template, and the
pre-commit hooks:

* parse failures always block (exit 1) in every semantic mode;
* advisory semantics report findings but keep exit 0;
* strict semantics promote semantic errors to blocking;
* operational errors (no files found) exit 2;
* JSON output carries a machine-readable summary.

The corpus-level gate (every bundled library file + the runtime-showcase
fixtures parse) is dogfooded by CI itself via the ``sysml-check``
workflow, not re-asserted here — these tests stay fast with tiny
in-memory models.
"""

import json

import pytest

from sysmlpy.ci_check import (
    CheckResult,
    discover_files,
    run_check,
    format_output,
)

CLEAN = """package Hello {
    part def Wheel {
        attribute diameter : ScalarValues::Real;
    }
    part bike {
        part frontWheel : Wheel;
    }
}
"""

SYNTAX_ERROR = """package Broken {
    part def Engine {
        attribute rpm : ScalarValues::Real
    }
}
"""

SEMANTIC_ERROR = """package BadRef {
    part def Vehicle {
        part engine : Engine;
    }
}
"""

SEMANTIC_WARNING = """package Hello {
    part def Wheel {
        attribute d : ScalarValues::Real;
    }
}
"""


def _write(tmp_path, name, text):
    p = tmp_path / name if isinstance(name, str) else tmp_path.joinpath(*name)
    p.write_text(text, encoding="utf-8")
    return p


class TestDiscoverFiles:
    def test_directory_recursive(self, tmp_path):
        (tmp_path / "models" / "nested").mkdir(parents=True)
        _write(tmp_path, ("models", "a.sysml"), CLEAN)
        _write(tmp_path, ("models", "nested", "b.sysml"), CLEAN)
        _write(tmp_path, ("models", "notes.txt"), "not a model")
        found = discover_files([tmp_path / "models"])
        assert sorted(f.name for f in found) == ["a.sysml", "b.sysml"]

    def test_single_file_and_kerml(self, tmp_path):
        f = _write(tmp_path, "k.kerml", "function f;\n")
        assert [f] == discover_files([f])

    def test_exclude_substring(self, tmp_path):
        (tmp_path / "models").mkdir()
        (tmp_path / "third_party").mkdir()
        _write(tmp_path, ("models", "a.sysml"), CLEAN)
        _write(tmp_path, ("third_party", "b.sysml"), CLEAN)
        found = discover_files([tmp_path], exclude=["third_party"])
        assert all("third_party" not in f.as_posix() for f in found)
        assert any(f.name == "a.sysml" for f in found)

    def test_dedupe_and_sorted(self, tmp_path):
        (tmp_path / "models").mkdir()
        a = _write(tmp_path, ("models", "a.sysml"), CLEAN)
        found = discover_files([tmp_path / "models", a])
        assert len(found) == 1


class TestRunCheckParseGate:
    def test_clean_parse_exit_0(self, tmp_path):
        _write(tmp_path, "hello.sysml", CLEAN)
        r = run_check([str(tmp_path)], semantic="off")
        assert r.exit_code == 0
        assert r.parse_failures == []
        assert r.files_checked == 1

    def test_syntax_error_blocks_in_every_mode(self, tmp_path):
        _write(tmp_path, "broken.sysml", SYNTAX_ERROR)
        for mode in ("off", "advisory", "strict"):
            r = run_check([str(tmp_path)], semantic=mode)
            assert r.exit_code == 1, mode
            assert len(r.parse_failures) == 1
            assert r.parse_failures[0].code == "PARSE"

    def test_no_files_exit_2(self, tmp_path):
        r = run_check([str(tmp_path / "empty-dir")])
        (tmp_path / "empty-dir").mkdir()
        r = run_check([str(tmp_path / "empty-dir")])
        assert r.exit_code == 2
        assert any(f.code == "NO_FILES" for f in r.findings)

    def test_invalid_semantic_mode_raises(self, tmp_path):
        _write(tmp_path, "hello.sysml", CLEAN)
        with pytest.raises(ValueError):
            run_check([str(tmp_path)], semantic="bogus")

    def test_kerml_parse_gate(self, tmp_path):
        _write(tmp_path, "good.kerml", "function f;\n")
        _write(tmp_path, "bad.kerml", "function ??? ;\n")
        r = run_check([str(tmp_path)], semantic="off")
        assert r.exit_code == 1
        assert len(r.parse_failures) == 1
        assert "bad.kerml" in r.parse_failures[0].file


class TestRunCheckSemanticModes:
    def test_advisory_reports_but_does_not_block(self, tmp_path):
        _write(tmp_path, "badref.sysml", SEMANTIC_ERROR)
        r = run_check([str(tmp_path)], semantic="advisory")
        assert r.semantic_errors, "semantic error expected in findings"
        assert r.exit_code == 0, "advisory must not block on semantic errors"

    def test_strict_blocks_on_semantic_error(self, tmp_path):
        _write(tmp_path, "badref.sysml", SEMANTIC_ERROR)
        r = run_check([str(tmp_path)], semantic="strict")
        assert r.exit_code == 1
        assert any(f.code == "UNDEFINED_SYMBOL" for f in r.findings)

    def test_strict_clean_exit_0(self, tmp_path):
        _write(tmp_path, "hello.sysml", CLEAN)
        r = run_check([str(tmp_path)], semantic="strict")
        assert r.exit_code == 0

    def test_strict_blocks_on_semantic_warning_only_fails_on_errors(self, tmp_path):
        # A warnings-only file passes even strict (strict fails on errors,
        # mirroring `sysmlpy analyze --fail-on error`).
        _write(tmp_path, "warn.sysml", SEMANTIC_WARNING)
        r = run_check([str(tmp_path)], semantic="strict")
        assert r.exit_code == 0
        assert r.semantic_warnings  # but the warning is still reported


class TestResultShapes:
    def test_json_round_trip(self, tmp_path):
        _write(tmp_path, "hello.sysml", CLEAN)
        r = run_check([str(tmp_path)], semantic="advisory")
        payload = json.loads(format_output(r, "json"))
        assert payload["files_checked"] == 1
        assert payload["semantic_mode"] == "advisory"
        assert payload["exit_code"] == 0
        assert payload["summary"]["parse_failures"] == 0

    def test_text_output_mentions_failures(self, tmp_path):
        _write(tmp_path, "broken.sysml", SYNTAX_ERROR)
        r = run_check([str(tmp_path)], semantic="off")
        text = format_output(r, "text")
        assert "broken.sysml" in text
        assert "result: FAIL" in text

    def test_known_limitation_flagging(self, tmp_path):
        # UNDEFINED_SYMBOL is a known-limited analyzer class (library
        # symbol index) — advisory mode labels it so CI logs can filter.
        _write(tmp_path, "badref.sysml", SEMANTIC_ERROR)
        r = run_check([str(tmp_path)], semantic="advisory")
        flagged = [f for f in r.findings if f.known_limitation]
        assert flagged, "known-limited classes must carry the flag"


class TestCliCiCommand:
    """Exit-code contract of `sysmlpy ci` (argparse wiring)."""

    @pytest.fixture
    def main(self):
        from sysmlpy.__main__ import main
        return main

    def test_clean_off_exit_0(self, tmp_path, main, capsys):
        f = _write(tmp_path, "hello.sysml", CLEAN)
        assert main(["ci", str(f), "--semantic", "off"]) == 0
        out = capsys.readouterr().out
        assert "result: PASS" in out

    def test_parse_failure_exit_1(self, tmp_path, main, capsys):
        f = _write(tmp_path, "broken.sysml", SYNTAX_ERROR)
        assert main(["ci", str(f)]) == 1
        out = capsys.readouterr().out
        assert "Syntax error" in out
        assert "result: FAIL" in out

    def test_advisory_semantic_errors_still_exit_0(self, tmp_path, main):
        f = _write(tmp_path, "badref.sysml", SEMANTIC_ERROR)
        assert main(["ci", str(f), "--semantic", "advisory"]) == 0

    def test_strict_semantic_errors_exit_1(self, tmp_path, main):
        f = _write(tmp_path, "badref.sysml", SEMANTIC_ERROR)
        assert main(["ci", str(f), "--semantic", "strict"]) == 1

    def test_no_semantic_shorthand(self, tmp_path, main):
        f = _write(tmp_path, "badref.sysml", SEMANTIC_ERROR)
        assert main(["ci", str(f), "--no-semantic"]) == 0

    def test_json_output(self, tmp_path, main, capsys):
        f = _write(tmp_path, "hello.sysml", CLEAN)
        assert main(["ci", str(f), "--semantic", "off", "--format", "json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert data["exit_code"] == 0
        assert data["files_checked"] == 1

    def test_exclude_flag(self, tmp_path, main):
        _write(tmp_path, "a.sysml", CLEAN)
        _write(tmp_path, "b.sysml", SYNTAX_ERROR)
        assert main(["ci", str(tmp_path), "--semantic", "off",
                     "--exclude", "b.sysml"]) == 0

    def test_missing_dir_exit_2(self, tmp_path, main):
        assert main(["ci", str(tmp_path / "nope"),
                     "--semantic", "off"]) == 2


class TestCheckResultDataclass:
    def test_properties_partition(self):
        r = CheckResult(semantic_mode="advisory")
        assert r.parse_failures == []
        assert r.semantic_errors == []
        assert r.semantic_warnings == []
