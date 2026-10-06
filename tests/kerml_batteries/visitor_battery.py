#!/usr/bin/env python3
"""kerml_visitor battery: structure-extraction cases + full corpus
through parse_to_dict."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _bootstrap import _parse_to_dict_nonempty, boot, corpus_or_none, \
    kernel_library_dir, parse_texts_parallel  # noqa: E402

boot()

from sysmlpy.kerml.kerml_visitor import parse_to_dict  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  [{detail}]")


print("== visitor: structural extraction ==")
d = parse_to_dict("standard library package Base { abstract classifier Anything {"
                  " feature self: Anything[1] subsets things; } }")
base = d["children"][0]
check("library package name", base.get("declaredName") == "Base", str(base)[:80])
check("package kind", base.get("name") == "library package")
anything = base["children"][0]
check("classifier Anything", anything.get("declaredName") == "Anything"
      and anything.get("name") == "classifier")
self_f = anything["children"][0]
check("feature self typed_by/subsets",
      self_f["typed_by"] == ["Anything"] and self_f["subsets"] == ["things"],
      str(self_f)[:160])

d = parse_to_dict("abstract datatype DataValue specializes Anything { }")
check("datatype specializes", d["children"][0].get("specializes") == ["Anything"])

d = parse_to_dict("class C specializes B, D { }")
check("multi specializes", d["children"][0].get("specializes") == ["B", "D"])

d = parse_to_dict("feature f: T[1] subsets s redefines r references rf { }")
f = d["children"][0]
check("feature all reference kinds",
      f["typed_by"] == ["T"] and f["subsets"] == ["s"]
      and f["redefines"] == ["r"] and f["references"] == ["rf"]
      and f["multiplicity"] == "[1]", str(f)[:160])

d = parse_to_dict("class C { public feature g : T; private feature h; }")
c = d["children"][0]
check("visibility on members",
      c["children"][0].get("visibility") == "public"
      and c["children"][1].get("visibility") == "private",
      str([(k.get("declaredName"), k.get("visibility")) for k in c["children"]]))

d = parse_to_dict("function f { in x: T1; out y: T2; return r : T3; }")
f = d["children"][0]
dirs = [(k.get("declaredName"), k.get("direction"), k.get("is_return"))
        for k in f["children"]]
check("function parameters + return",
      dirs == [("x", "in", None), ("y", "out", None), ("r", None, True)],
      str(dirs))

d = parse_to_dict("assoc A { end x: T1[1]; end y[0..*] : T2; }")
a = d["children"][0]
names = [k.get("declaredName") for k in a["children"]]
check("association ends", names == ["x", "y"], str(names))
check("association end typing",
      [k.get("typed_by") for k in a["children"]] == [["T1"], ["T2"]],
      str([k.get("typed_by") for k in a["children"]]))

d = parse_to_dict("standard library package P { doc /* hi */ class K; }")
p = d["children"][0]
check("doc captured on package", p.get("documentation") == [" hi "],
      str(p.get("documentation")))

print()
print("== corpus: parse_to_dict over the OMG .kerml tree ==")
REPO = corpus_or_none()
if REPO is None:
    print("  SKIP  OMG corpus unavailable; set SYSML2_RELEASE_DIR")
    CORPUS_EXPECTED = False
else:
    CORPUS_EXPECTED = True
roots = [] if REPO is None else [
    REPO / "kerml/src/examples", REPO / "sysml.library/Kernel Libraries",
    kernel_library_dir(),
]
ok = total = 0
if roots:
    items = []
    for root in roots:
        for fp in sorted(root.rglob("*.kerml")):
            items.append((str(fp),
                          fp.read_text(encoding="utf-8", errors="replace")))
    total = len(items)
    for fp_str, res in parse_texts_parallel(items, _parse_to_dict_nonempty):
        if res is not None:
            FAIL.append(fp_str)
            print(f"  FAIL {Path(fp_str).name}: {str(res)[:90]}")
        else:
            ok += 1
check(f"corpus parse_to_dict non-empty ({ok}/{total})", ok == total,
      f"{ok}/{total}")
if CORPUS_EXPECTED:
    check("OMG corpus root discovered (.kerml files found)", total > 100,
          f"{total} files")

print()
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    sys.exit(1)