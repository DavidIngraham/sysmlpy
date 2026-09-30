# Stable Element Identities — Scoping for Idempotent Interchange

> **Status:** scope / not yet implemented
> **For:** projects that need the same SysML v2 model to produce the
> *same element identifiers* across parses, tools, and incremental
> edits — not just across round-trips.
> **Companion demo:** `examples/element_identity.py` (what exists today)

---

## 1. Problem statement

sysmlpy's interchange layer already assigns every element a
deterministic `@id` (uuid5 under a fixed namespace). That satisfies the
"parse the same text twice, get identical JSON" level of idempotency.
It does **not** survive edits that change structure before the element
in question. Verified behaviour (probes, 2026-09-28):

| Edit before `part def Engine` | Engine's `@id` |
|---|---|
| none (same text) | `sysml:d1959147…` — stable |
| ancestor package renamed `P` → `Q` | **stable** (wrapper nodes are unnamed; the hash chain runs through them) |
| sibling declared *after* it | **stable** (its own index is unchanged) |
| sibling declared *before* it | **shifts** — new uuid5 |
| element moved one nesting level deeper | **shifts** — new uuid5 |

So the current id encodes *structural position* (depth + sibling
index), not *what the element is*. Diff-friendly for unchanged text,
fragile for evolving models — the exact case a persistent store
(kuzu/networkx/cayley backend) or a cross-tool traceability pipeline
cares about.

## 2. Idempotency levels

| Level | Guarantee | Today |
|---|---|---|
| L0 | dump → parse → dump is fixed-point | ✅ |
| L1 | same text re-parsed → identical `@graph` | ✅ (uuid5 position ids) |
| L2 | insertion/reordering elsewhere in the document keeps ids of untouched elements | ❌ |
| L3 | same element across independently maintained documents (renamed parents, split packages) resolves to one identity | ❌ |

The store layer (`store.py`) is already keyed by element UUID and is
the natural consumer of L2; multi-repo/ ReqIF traceability wants L3.

## 3. Options

### A. Content-addressed uuid5 (recommended for L2)

Replace `_child_id(parent_id, key, index)` with a hash over the
element's *identity path*: resolved qualified name + `@type`
(+ occurrence index among content-identical siblings as tie-breaker).

- Pros: pure-python change localized to `interchange.py`; ids stable
  under insertion/reorder elsewhere; no source changes needed; the
  namespace/`sysml:` prefix machinery stays.
- Cons (measured): name collisions are real — two sibling
  `part def Engine` declarations hash to the same key. Tie-breaker
  (occurrence index among same-key siblings) reintroduces position
  sensitivity *only within the colliding group*, which is an acceptable
  degradation: untouched elements outside the group keep their ids.
- Needs the resolver: qualified names require `semantic.py`'s
  SymbolTable walk during export (already importable; export currently
  stays resolver-free).

### B. Canonical-subtree hashing (L2 robust, heavier)

Hash a canonical serialization of the element's *subtree* (sorted keys,
ids replaced by recursion). Collision-tolerant and rename-resistant
within the subtree; survives re-parenting only if the parent name is
part of the QN anyway. More implementation and spec work (canonical
form must be pinned by tests, like JSON canonicalization); use only if
A's tie-breaker behaviour is unacceptable.

### C. Source-carried explicit ids (L3, spec-aligned)

SysML v2's interchange `@id` is tool-assigned; the textual syntax has no
standard id slot. For cross-document identity, carry ids explicitly:

- doc-comment convention: `doc /* @id: sysml:… */` (already parsed as
  `.doc` on every element since v0.96.1);
- or a sidecar mapping file (text → id) maintained by the project.

Exporter honors an explicit id when present, mints per option A
otherwise. This is the only scheme that survives arbitrary re-factoring
and is honest about identity being *assigned*, not derived. Cost: a
convention the other project must adopt and preserve.

### D. Do nothing for L3

Match on resolved qualified names at query time (semantic.py already
resolves across imports). No id stability needed if consumers can key
on `P::Sub::Engine`. Often sufficient; cheapest.

## 4. Recommended scope

Phase 1 (L2) — **IMPLEMENTED (unreleased; on main)**:

1. ✅ `interchange.py`: `to_interchange(..., stable_ids=False)` — when
   True, ids are uuid5 over the **declared** qualified-name path
   (syntax-derived, no resolver: `P.Engine.power` style chains of
   `Identification.declaredName` from root) + `@type`; anonymous /
   unresolved elements hash the nearest named anchor plus the
   structural path from it (option-A resolved-QN variant deliberately
   deferred — declared path keeps export resolver-free and
   machine-independent).
2. ✅ Anonymous elements keep anchor-relative keys — documented that
   anonymous identity follows the nearest declared ancestor.
3. ✅ Tests (`tests/interchange_test.py::TestStableIds`): L1
   byte-identity, the §1 edit matrix as parametrized cases
   (sibling before/after, inner-feature insertion), ancestor-rename
   and re-nesting identity-follows-content semantics, collision-group
   uniqueness, graph-wide uniqueness on the rich model, round trip,
   and default-path invariance (`stable_ids=False` byte-identical to
   the v0.63.0 behaviour).
4. ✅ `store.py` upsert verified on the memory backend: same stable id
   updates the stored element in place (stores are UUID-keyed by
   design).  networkx/kuzu/cayley backends are optional-dependency
   gated in this environment (their test failures are pre-existing,
   unrelated to ids).
5. ✅ CLI: `sysmlpy export --stable-ids`.

Phase 2 (L3) — **IMPLEMENTED (unreleased; on main, registry variant)**:

- `reconcile_ids(document, registry)` — adopt ids from a previous
  export (dict, JSON text, or a filesystem `Path`/path str).
  Injective matching: (declaredName, @type) must be unique on BOTH
  sides, each registry id adopted at most once; ambiguous keys keep
  derived ids.
- `to_interchange(..., reconcile_with=...)` convenience — implies
  `stable_ids=True`.
- **Nested-ref remap:** adoption rewrites not just the element's
  top-level `@id` but every nested `{"@id": <derived>}` reference
  pointing at it (typed-by references, member chains) — without the
  remap, documents whose *identity* was reconciled dangle on import
  (found by `test_reconcile_result_round_trips` during this build).
- CLI: `sysmlpy export --reconcile-with model.json -o model.json` —
  idempotent fixed point after the first export.
- Tests (10): rename+insert motivating case, JSON-text registry,
  graph-wide uniqueness after reconcile (the spike's dupes pitfall),
  no-adoption for renamed/ambiguous elements, three-round file
  workflow, injectivity on same-name groups, error guards,
  `reconcile_with=` convenience flag, reconciled round trip.
- Registry-file str/Path disambiguation: a str is treated as a path
  only when it is < 4097 chars, single-line, and exists — otherwise
  it parses as JSON text (a JSON *body* pasted inline must not be
  `open()`ed as a filename).

Remaining gap to full L3: elements renamed so thoroughly that no
declared name matches stay unmatched (fresh derived ids; they become
registry entries on the next write).  The doc-comment `@id:`
convention (option C below) removes even that.

### Design decision recorded: declared-path, not resolved-QN

Option A as scoped mentioned hashing the *resolved* qualified name via
`semantic.py`.  Implementation uses the **declared** path instead
(chain of `Identification.declaredName` from root): resolution depends
on library availability and import resolution, which would make ids
machine-dependent — defeating idempotency.  Consequence: ids follow
declared identity, so renaming an ancestor re-mints descendant ids
(verified in `test_qn_follows_declared_identity`).  The position scheme
accidentally survived ancestor renames; the content scheme intentionally
does not.  Trade-off documented here rather than hidden.

## 5. Risks / open questions

- Resolved-QN depends on import resolution settings; a model whose
  imports resolve differently on another machine gets different ids.
  Mitigation: hash the *declared* QN path (pure syntax) rather than the
  resolved one, and document the difference.
- Changing the default id scheme breaks byte-comparisons against
  previously exported JSON — hence the opt-in flag and a CHANGELOG
  note; consider a `--stable-ids` CLI flag on `sysmlpy export`.
- Same-name sibling collision groups grow/shrink on edit; ids inside
  the group shift by design (tie-breaker index). Acceptable if
  documented; option C removes it entirely.