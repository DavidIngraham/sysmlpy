#!/usr/bin/env python3
"""kerml package __init__ + SysML coexistence checks."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _bootstrap import boot, kernel_library_dir  # noqa: E402

boot()

PASS, FAIL = [], []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  [{detail}]")


from sysmlpy.kerml import (  # noqa: E402
    KerMLSyntaxError,
    parse,
    parse_file,
    parse_to_dict,
)

check("public API import", True)

base_kerml = kernel_library_dir() / "Base.kerml"
tree = parse_file(str(base_kerml)) if base_kerml.exists() else None
check("parse_file on Base.kerml", tree is not None,
      f"missing: {base_kerml}")

d = parse_to_dict("class C { feature f: T; }")
check("parse_to_dict shape", d["children"][0]["children"][0]["declaredName"] == "f")

try:
    parse("class @;")
    check("KerMLSyntaxError raised", False)
except KerMLSyntaxError:
    check("KerMLSyntaxError raised", True)

from sysmlpy import antlr_parser  # noqa: E402
antlr_parser.parse("package P;")
check("SysML parser unaffected", True)

print()
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    sys.exit(1)