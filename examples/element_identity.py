#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Element identity: what UUIDs exist, which are stable, and how to get
persistent identity for parsed models.

A frequent question: "does a parse produce UUIDs for the Python data
structure?"  The answer has three parts, one per layer, and this
example demonstrates each — because the layers behave differently and
mixing them up causes subtle bugs:

1. **Parse layer — fresh uuid4, per parse, NOT persistent.**
   The `Model` root always carries a fresh uuid4 string as its `name`
   (definition.py).  *Anonymous* elements (declared without a name,
   e.g. `part : Engine;`) also get a fresh uuid4 as their `name`
   (usage.py).  Named elements carry only their declared name — there
   is no `.uuid` attribute on parsed objects.  Re-parsing the same
   source therefore yields DIFFERENT identifiers; any round-trip
   comparison must normalize the Model root name and anonymous names.

2. **Interchange layer — deterministic uuid5 `@id`s, stable forever.**
   `to_interchange(model)` assigns every element a JSON-LD `@id`:
   `uuid5` derived from the element's position in the model tree under
   a fixed namespace (INTERCHANGE_NAMESPACE).  Export the same model
   twice — same process or fresh process, same day or next year — and
   the JSON is byte-identical.  These are the identifiers to use when
   something downstream needs to reference an element across parses,
   builds, or tools.

3. **Round trip — identity preserved.**
   `from_interchange(to_interchange(model))` rebuilds a live `Model`
   through the same grammar-class path as a fresh parse, and
   re-exporting it reproduces the identical `@graph`, `@id`s included.

Caveat for multi-document identity: the uuid5 is *position-derived*, so
the same element declared inside a different parent (or a different
package ordering) hashes differently.  Position-derived ids are stable
for a given source text, which is what diff-friendly interchange wants;
they are not content-addressed.  For cross-document element identity,
declare elements with explicit names and match on resolved qualified
names — or extend the exporter to honor an explicit `@id` annotation
when the source carries one.

Run:  python examples/element_identity.py
"""

from __future__ import annotations

import json
import re

from sysmlpy import loads
from sysmlpy.interchange import (
    from_interchange,
    interchange_to_json_text,
    to_interchange,
)

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def banner(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def main() -> None:
    src = """package VehicleModel {
        part def Engine;
        part e : Engine;
        attribute power : ScalarValues::Real;
    }"""

    banner("1) PARSE LAYER: fresh uuid4 identity per parse (not persistent)")
    m1, m2 = loads(src), loads(src)
    print("Model.name after parse #1:", m1.name)
    print("Model.name after parse #2:", m2.name)
    print("same?", m1.name == m2.name, "— fresh uuid4 every parse")

    anon = loads("package P { part def Engine; part : Engine; }")

    def find_anonymous(el: object) -> None:
        n = str(getattr(el, "name", ""))
        if _UUID4_RE.match(n):
            print(f"anonymous {type(el).__name__} got uuid4 name: {n}")
        for child in getattr(el, "children", []):
            find_anonymous(child)

    print("\nunnamed declaration 'part : Engine;' →")
    find_anonymous(anon)
    print("named elements (Engine, e, power) carry no generated uuid —")

    banner("2) INTERCHANGE LAYER: deterministic uuid5 @id (stable identity)")
    d1, d2 = to_interchange(m1), to_interchange(m2)
    # Show the named elements; every element in the graph carries an @id.
    for e in d1["@graph"]:
        name = e.get("declaredName")
        if name:
            print(f'  {e["@id"]:56} {e["@type"]:18} {name}')
    identical = json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)
    print(f"\n  ({len(d1['@graph'])} elements in @graph, every one with an @id)")
    print("export of parse #1 == export of parse #2 (byte-identical):", identical)

    banner("3) ROUND TRIP: rebuild via @id graph — identity preserved")
    m3 = from_interchange(d1)
    d3 = to_interchange(m3)
    print("rebuild → re-export reproduces the identical @graph:",
          d3["@graph"] == d1["@graph"])
    print("\nJSON-LD excerpt:")
    print(interchange_to_json_text({"@graph": d1["@graph"][:2]}, indent=2))

    banner("4) stable_ids=True — content-addressed ids that survive edits")
    d_pos = to_interchange(m1)
    d_stb = to_interchange(m1, stable_ids=True)
    eng_pos = next(e["@id"] for e in d_pos["@graph"]
                   if e.get("declaredName") == "Engine")
    eng_stb = next(e["@id"] for e in d_stb["@graph"]
                   if e.get("declaredName") == "Engine")
    print("position id: ", eng_pos)
    print("stable id:   ", eng_stb)
    base = "package VehicleModel { part def Engine; }"
    edited = "package VehicleModel { part def Dummy; part def Engine; }"
    eng_before = next(e["@id"] for e in
                      to_interchange(base, stable_ids=True)["@graph"]
                      if e.get("declaredName") == "Engine")
    eng_after = next(e["@id"] for e in
                     to_interchange(edited, stable_ids=True)["@graph"]
                     if e.get("declaredName") == "Engine")
    print("after inserting an unrelated sibling BEFORE Engine —")
    print("  position ids: id", "unchanged" if
          next(e["@id"] for e in to_interchange(base)["@graph"]
               if e.get("declaredName") == "Engine")
          == next(e["@id"] for e in to_interchange(edited)["@graph"]
                  if e.get("declaredName") == "Engine") else "SHIFTED")
    print("  stable ids:   id", "unchanged" if eng_before == eng_after
          else "SHIFTED")
    print("\nCLI: sysmlpy export model.sysml --stable-ids")
    print("scope + L3 options: docs/stable-identities.md")


if __name__ == "__main__":
    main()