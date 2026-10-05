# The Vee Link: SysML ↔ STEP (stepper + pyoslc)

sysmlpy + [stepper](https://github.com/mycr0ft/stepper) +
[pyoslc](https://github.com/mycr0ft/pyoslc) form a Systems-Engineering
Vee toolchain: this page documents the SysML side of the joins.

```
     requirements & design              geometry & PMI
     (left/middle of Vee)               (right of Vee)
     .sysml  —  sysmlpy  —  OSLC  —  stepper  —  .stp
              parse/analyze   ^  parse/structure
                              │
                    pyoslc serves BOTH sides
                    as one OSLC catalog
                              │
                 released configuration = baseline
                 (hash-pinned, verifiable)
```

## qn_registry() — the SysML identity you expose

Every `to_interchange(stable_ids=True)` export carries a side table
mapping each *named* element's declared qualified-name path to its
stable interchange `@id`:

```python
import sysmlpy
from sysmlpy import to_interchange, qn_registry

m = sysmlpy.loads("""
package NistModel {
    part def 'NIST Test Case 1' {
        attribute thrust : Real;
    }
}
""")
doc = to_interchange(m, stable_ids=True)
print(qn_registry(doc)["NistModel.'NIST Test Case 1'"])
# sysml:45305c0c-…  (content-addressed; survives unrelated edits)
```

Facts pinned by tests (`tests/qn_registry_test.py`):

- keys are **deduped** declared QN paths (the visitor dict's wrapper
  nesting must not leak);
- values equal the corresponding graph element's `@id`;
- the registry is stable across export → import → export;
- explicit ids (`doc /* @id: … */` comments) surface verbatim;
- position-id exports yield `{}` (no identity to expose);
- after `reconcile_ids` adoption the registry is remapped with the
  graph, so it never dangles.

Quoted short names KEEP their quotes in the keys — downstream
matchers strip `'` before comparing against other tools' titles.

## What consumes it

- **pyoslc `/oslc/step/vee`** posts `{"registry": qn_registry(doc)}`
  to auto-link SysML elements to STEP AP242 products by leaf name —
  the identity edge is then queryable from both directions through
  the OSLC API.
- **pyoslc baselines** snapshot the link table into every released
  configuration — a baseline is therefore *also* a record of which
  SysML elements realized which geometry at release time.

## Serving SysML as OSLC

The Saturn V example (`pyoslc/examples/saturn_v/`) already serves
this repo's parsed models as OSLC SysML resources; see that repo's
`docs/DOMAIN_DEVELOPMENT.md`. The STEP domain tutorial (stepper's
mkdocs site, "Serving as OSLC") covers the geometry side.

## Baselines on this side

A pyoslc baseline pins the `.sysml` **source bytes** (hash) AND the
derived interchange payload (this repo's stable-ids export) — so a
released configuration is verifiable from either side:

- re-hash the pinned `.sysml` and compare with the baseline,
- or re-run `to_interchange` and compare with the pinned payload
  (they must agree byte-for-byte thanks to stable ids).

The SysML-side guarantee that makes this work: **stable ids are
content-addressed** — `docs/stable-identities.md` carries the full
identity analysis.