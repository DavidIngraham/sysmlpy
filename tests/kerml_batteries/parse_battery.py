#!/usr/bin/env python3
"""kerml.py parser battery: parse() over syntax cases + the full
.kerml corpus."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _bootstrap import boot, corpus_or_none, kernel_library_dir, \
    parse_texts_parallel  # noqa: E402

boot()

from sysmlpy.kerml.kerml import parse, KerMLSyntaxError  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  [{detail}]")


print("== kerml.parse: syntax ==")
cases_ok = [
    "package P;",
    "class C;",
    "abstract classifier Anything;",
    "datatype D specializes Anything;",
    "feature f: T[1] subsets s redefines r;",
    "assoc A { end x: T1; }",
    "behavior B { step s1; succession s first s1 then s2; }",
    "function f { in x: T1; return r : T2; }",
    "standard library package P { private import Q::*; }",
    "private import Base::Anything;",
    "doc /* note */",
    "comment /* regular */",
    "type T conjugates C;",
    "metadata m about t;",
]
for src in cases_ok:
    try:
        parse(src)
        check(f"parse: {src[:44]}", True)
    except KerMLSyntaxError as e:
        check(f"parse: {src[:44]}", False, str(e)[:100])

print()
print("== corpus: parse() over the OMG + bundled .kerml tree ==")
REPO = corpus_or_none()
roots = [] if REPO is None else [
    REPO / "kerml/src/examples", REPO / "sysml.library/Kernel Libraries",
    kernel_library_dir(),
]
if not roots:
    print("  SKIP  OMG corpus unavailable (no local copy, clone failed); "
          "set SYSML2_RELEASE_DIR or clone "
          "Systems-Modeling/SysML-v2-Release")
ok = total = 0
if roots:
    items = []
    for root in roots:
        for fp in sorted(root.rglob("*.kerml")):
            items.append((str(fp),
                          fp.read_text(encoding="utf-8", errors="replace")))
    total = len(items)
    for fp_str, res in parse_texts_parallel(items, parse):
        if res is not None:
            FAIL.append(fp_str)
            print(f"  FAIL {Path(fp_str).name}: {str(res)[:90]}")
        else:
            ok += 1
check(f"corpus parse ({ok}/{total})", ok == total, f"{ok}/{total}")
if total:
    check("bundled kernel library included in corpus sweep", total > 100,
          f"{total} files")

print()
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    sys.exit(1)