# -*- coding: utf-8 -*-
"""qn_registry — qualified-name -> stable @id side table (P3 Vee-join).

The registry is the join key between the SysML world and downstream
consumers (pyoslc STEP domain, P3): a caller exports with
``stable_ids=True``, reads ``qn_registry(document)``, and every named
element's declared qualified name resolves to its stable ``@id``
without re-walking tree containment or re-deriving hash chains.

Pinned here:
- keys are DEDUPED declared QN paths (the repeat-tail wrapper
  nesting must not leak into keys);
- values equal the corresponding graph element ``@id``;
- the registry is stable across export -> import -> export;
- position-id exports yield an EMPTY registry (no identity to expose);
- doc-id (Phase 2b) exports surface the explicit id in the registry;
- round-trip JSON keeps the side table; ``from_interchange`` ignores it.
"""

import json

import pytest

import sysmlpy
from sysmlpy import (
    loads, load_files, to_interchange, from_interchange, qn_registry,
    reconcile_ids, interchange_to_json_text,
)

MODEL = """
package SaturnV {
    part def Engine {
        attribute thrust : ScalarValues::Real;
    }
    part f1 : Engine;
}
"""


class TestQnRegistry:
    def test_entries_and_graph_agreement(self):
        doc = to_interchange(loads(MODEL), stable_ids=True)
        reg = qn_registry(doc)
        assert reg == {
            "SaturnV": doc["@graph"][0]["@id"],
            "SaturnV.Engine": next(e["@id"] for e in doc["@graph"]
                                   if e.get("declaredName") == "Engine"),
            "SaturnV.Engine.thrust": next(e["@id"] for e in doc["@graph"]
                                          if e.get("declaredName") == "thrust"),
            "SaturnV.f1": next(e["@id"] for e in doc["@graph"]
                               if e.get("declaredName") == "f1"),
        }

    def test_keys_are_deduped_paths(self):
        doc = to_interchange(loads(MODEL), stable_ids=True)
        reg = qn_registry(doc)
        for key in reg:
            segs = key.split(".")
            # no consecutive repeats leaked from wrapper nesting
            for a, b in zip(segs, segs[1:]):
                assert a != b, f"repeat tail in {key}"

    def test_position_ids_yield_empty_registry(self):
        doc = to_interchange(loads(MODEL), stable_ids=False)
        assert qn_registry(doc) == {}

    def test_stable_across_round_trip(self):
        m1 = loads(MODEL)
        reg1 = qn_registry(to_interchange(m1, stable_ids=True))
        m2 = from_interchange(to_interchange(m1, stable_ids=True))
        reg2 = qn_registry(to_interchange(m2, stable_ids=True))
        assert reg1 == reg2

    def test_survives_json_text_round_trip(self):
        doc = to_interchange(loads(MODEL), stable_ids=True)
        text = interchange_to_json_text(doc)
        assert qn_registry(json.loads(text)) == qn_registry(doc)

    def test_from_interchange_ignores_side_table(self):
        doc = to_interchange(loads(MODEL), stable_ids=True)
        assert qn_registry(doc)  # non-empty precondition
        m2 = from_interchange(doc)   # must not choke on "#qn_registry"
        assert m2.children

    def test_doc_ids_surface_in_registry(self):
        # INSIDE-braces doc comments attach to the element (the pinned
        # placement contract); sibling-level docs bubble to the
        # package — both surface in the registry under their owner.
        src = """
        package P {
            part def Tracker {
                doc /* @id: TR */;
            }
        }
        """
        m = loads(src)
        doc = to_interchange(m, doc_ids=True)
        reg = qn_registry(doc)
        assert reg.get("P.Tracker") == "TR"

    def test_reconcile_chain_keeps_registry_accurate(self):
        """Edit scenario: ancestor rename + reconcile. Members whose
        (declaredName, @type) survives the rename keep their OLD ids
        (injected adoption); the renamed element re-mints (name-keyed
        matching is injective — a rename is a different key). The
        registry must agree with the graph at every step."""
        m = loads(MODEL)
        doc1 = to_interchange(m, stable_ids=True)
        reg1 = qn_registry(doc1)
        m2 = loads(MODEL.replace("SaturnV", "Ares"))
        doc2 = to_interchange(m2, stable_ids=True)
        doc2 = reconcile_ids(doc2, doc1)
        reg2 = qn_registry(doc2)
        # children adopt doc1's ids (name survived the rename)
        assert reg2["Ares.Engine"] == reg1["SaturnV.Engine"]
        assert reg2["Ares.Engine.thrust"] == reg1["SaturnV.Engine.thrust"]
        assert reg2["Ares.f1"] == reg1["SaturnV.f1"]
        # the renamed root re-mints (different declared name — nothing
        # to match on at the injective reconcile layer)
        assert reg2["Ares"] != reg1["SaturnV"]
        # registry agrees with the graph after adoption
        by_name = {e["declaredName"]: e["@id"] for e in doc2["@graph"]
                   if e.get("declaredName")}
        for qn, rid in reg2.items():
            leaf = qn.rsplit(".", 1)[-1]
            assert by_name.get(leaf) == rid, f"{qn} disagrees with graph"

    def test_doc_ids_rename_survives_via_registry(self):
        """The doc-id identity guarantee: rename an ancestor WITH an
        explicit id and the renamed element keeps its id (explicit
        ids override derivation) — registry shows it.  The doc-id on
        a package is a sibling-level statement inside the braces
        (grammar shape: bare `doc /* @id: … */;` is not a valid
        package-member prefix form... it IS valid as a member-level
        doc: `doc /* … */;` right inside the braces)."""
        src1 = """
        package SaturnV {
            doc /* @id: ROOT */;
            part def Engine {
                doc /* @id: EN */;
            }
        }
        """
        m1 = loads(src1)
        reg1 = qn_registry(to_interchange(m1, doc_ids=True))
        src2 = src1.replace("SaturnV", "Ares")
        reg2 = qn_registry(to_interchange(loads(src2), doc_ids=True))
        assert any(v == "EN" for v in reg2.values()), \
            f"doc-id EN must survive rename: {reg2}"
        # The package-level ROOT claim (sibling-level doc inside the
        # braces) attaches to the package itself: reg1 keys it by
        # 'SaturnV', reg2 by 'Ares' — the KEY follows the declared
        # name (identity is carried by the SOURCE comment, not the
        # registry key). Both models carry the value under their own
        # package key.
        assert "ROOT" in set(reg1.values())
        assert "ROOT" in set(reg2.values())
        assert reg2.get("Ares") == "ROOT"

    def test_multi_file_model_registry(self, tmp_path):
        f1 = tmp_path / "p1.sysml"
        f2 = tmp_path / "p2.sysml"
        f1.write_text("package P {\n part def Wheel;\n}")
        f2.write_text("package P {\n part bike { part w : Wheel; }\n}")
        m = load_files([str(f1), str(f2)])
        reg = qn_registry(to_interchange(m, stable_ids=True))
        assert "P.Wheel" in reg and "P.bike" in reg

    def test_helper_in_public_api(self):
        assert sysmlpy.qn_registry is qn_registry