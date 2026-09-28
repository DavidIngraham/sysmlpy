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

Phase 1 (L2, ~1-2 sessions):
1. `interchange.py`: `to_interchange(..., stable_ids=False)` — when
   True, id = uuid5(NAMESPACE, resolved-QN + "|" + @type +
   optional "|#" + occurrence); resolver run via `semantic` (errors
   fall back to position ids for anonymous/unresolved elements).
2. Anonymous elements keep uuid4-style content keys (they *have* no
   QN) — document that anonymous identity is per-parse by nature.
3. Tests: L1 byte-identity still holds; L2 scenario table from §1 as
   parametrized cases; collision group behaves per A.
4. `store.py` consumers get id-preserving upsert: `put` with the same
   stable id updates in place (already keyed this way — verify with
   kuzu/networkx backends).

Phase 2 (L3, opt-in): doc-comment `@id:` convention (option C) layered
on Phase 1; exporter/importer round-trip the explicit id and never
re-mint over it.

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