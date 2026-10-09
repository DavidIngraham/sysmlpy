# Requirement Derivation Domain Library support

The requirement-derivation domain library uses metadata-prefixed connections:

```sysml
package Mission {
    private import RequirementDerivation::*;
    requirement voyage;
    requirement navigation;
    requirement endurance;
    #derivation connection voyageDerivation {
        doc /* Proposed engineering rationale: the voyage needs both capabilities. */
        end #original source ::> voyage;
        end #derive navigationEnd ::> navigation;
        end #derive enduranceEnd ::> endurance;
    }
}
```

The ANTLR visitor now retains connection bodies and metadata extension prefixes.
`ExtendedUsage` stores the annotated ends as structured usages, including their
declarations, reference subsetting, and completion. Both grammar serialization
and public `Model.dump()` retain these details and the connection documentation.
Metadata prefixes on connection definitions are preserved too.

`as_general_view()` renders inline derivations and named roles inherited from a typed connection definition:

```python
from pathlib import Path
from sysmlpy import loads, as_general_view

model = loads(Path("requirements.sysml").read_text(encoding="utf-8"))

def walk(element):
    yield element
    for child in element.children:
        yield from walk(child)

requirements = [element for element in walk(model)
                if getattr(element, "sysml_type", "") == "requirement"
                and not element.is_definition]
Path("requirements.puml").write_text(
    as_general_view(model, elements=requirements, direction="LR"),
    encoding="utf-8",
)
```

Render the resulting PlantUML text with a local PlantUML installation, for example
`java -jar plantuml.jar -tsvg requirements.puml`, then embed the SVG in Markdown.
The renderer uses `original ..> derived : «derive»` as an explicit visualization
convention. This is not a claim of complete SysML v2 graphical conformance;
[OMG tracks an open issue about derivation graphical notation](https://issues.omg.org/issues/spec/SysML/2.0).

## Supported library forms

The library is SysML v2 Part 1 section 9.6: `DerivationConnections` supplies the
base connection and requirement roles; `RequirementDerivation` supplies semantic
metadata. The following forms are interpreted, with round-trip regressions:

- `#derivation`, `#original`, and `#derive`, including qualified names, imports,
  aliases, metadata short names, and user-defined metadata subclasses.
- Direct `: DerivationConnections::Derivation` typing and `:> derivations`
  subsetting, with original/derived role subsetting or redefinition on ends.
- Named and unnamed ends; multi-level local connection-definition specialization;
  inherited bindings; renamed and implicitly named redefined ends.
- Connector shorthand with explicit role names, or positional binding to the
  declared ends of a local connection definition. A bare abstract `Derivation`
  connector without role declarations is diagnosed rather than assigned an
  arbitrary original/derived direction.

`extract_derivations(model)` returns `(edges, issues)`. It checks end-role
ambiguity, requirement endpoint kind, missing bindings, original/derived
cardinality, self-derivation, connection inheritance cycles, and connector arity. Invalid
connections produce diagnostics instead of misleading edges. Repeated targets
produce one projected edge. `analyze()` includes these structural diagnostics.

General Views render usage-level edges when both endpoints are selected. A
connection definition establishes roles; it does not itself assert a relationship
between concrete requirement usages. The visualization convention described
above still applies; this change does not resolve OMG's open graphical-notation
issue or claim full graphical conformance.

## Implication evaluation

The library's `originalImpliesDerived` constraint is an implication, not evidence
that an engineering derivation is justified for all possible designs. Evaluate
it for **explicitly supplied requirement results**, keyed by qualified name:

```python
from sysmlpy import analyze
from sysmlpy.derivation import evaluate_derivations

values = {"Mission::voyage": True, "Mission::navigation": False}
evaluations, issues = evaluate_derivations(model, values)
issues = analyze(model, requirement_results=values)
```

Results are `True`, `False`, or `None` (unknown). A false original or a true derived
result makes an implication true; a true original with a false derived result
violates it; the other incomplete combinations remain unknown. Invalid value
types are rejected. The analyzer reports known violations as
`DERIVATION_IMPLICATION_VIOLATED`. Missing results do not become successful checks
or fabricated errors. `evaluate_derivations()` exposes their unknown status.
No result is inferred from an edge or a satisfy/verify relationship. Automatically
solving arbitrary requirement constraints and proving universal logical
implication are outside this evaluation contract.

## Traceability and interchange

`extract_traceability(model)` adds `derived_from` and `derives` qualified-name
lists to requirement records and JSON output. Text and Markdown reports expose
these relationships without counting them as satisfaction/verification coverage.
Use `as_traceability_matrix_view(model, show_derivation=True)` for additional
columns in Markdown/HTML or derivation edges in PlantUML; default coverage-matrix
output remains compatible. Existing interchange preserves the connection model;
no new interchange schema is introduced. Tests check extraction and rendering
after `from_interchange(to_interchange(model))`.

## Review scope and validation

Suggested PR title: **Add support for the Requirement Derivation Domain Library**.
This is a capability claim for the forms and evaluation contract above, not a
claim that every SysML language/semantic-metadata construct is implemented.
General metadata metaprogramming and full language conformance are not introduced.

The first commit contains general model-preservation fixes and domain-independent
regressions (`tests/connection_roundtrip_test.py`). The second adds initial
library interpretation and a pinned official example (`tests/derivation_test.py`).
A separate core follow-up fixes end subsetting and anonymous connection
serialization, with domain-independent tests. The domain follow-up extends library
forms, analyzer integration, three-valued implication checks, traceability outputs,
and interchange regressions (`tests/derivation_support_test.py`).
General parser/model-preservation changes must stay separate from domain behavior
and integration changes in the review history.

Both unchanged OMG examples are covered: `RequirementDerivationExample.sysml`
and `VehicleRequirementDerivation.sysml`, with separate source revisions and
checksums in the fixture README. The latter exercises unnamed ends and two
independent derived requirements. Tests also cover invalid and ambiguous forms.

## Official-model regression and before/after

Upstream `b0c827a39ab3713d0f98eb7fef56fa146a4c7ec2` has no requirement-derivation
fixture or assertions in its test tree. Its OMG conformance harness checks
`loads()` acceptance, which does not detect silently dropped model content.
The runtime-showcase fixtures cover other scenarios.

The new fixture is the unchanged OMG Pilot Implementation
`RequirementDerivationExample.sysml`. Its pinned source, checksum, license,
and the duplicate target present in the original are documented in
[`tests/fixtures/derivation/README.md`](../tests/fixtures/derivation/README.md).

The same four tests were executed against the upstream source and this branch:

| Assertion | Upstream | Fixed branch |
| --- | --- | --- |
| Official model parses | PASS | PASS |
| Metadata and end bindings survive two public round trips | FAIL | PASS |
| Inherited roles produce the official model's one unique edge | FAIL | PASS |
| Explicitly modified two-target variant produces two edges | FAIL | PASS |

The upstream dump reduces the connection usage to `connection : Req1_Derivation;`,
losing its end bindings. The fixed dump retains the metadata, body, and `::>`
references. The view resolves the roles on the connection definition.

Run the official regression with:

```sh
poetry run pytest tests/derivation_test.py -k official_example -q --tb=short
```

To reproduce the upstream comparison without changing the working tree, extract
`git archive b0c827a39ab3713d0f98eb7fef56fa146a4c7ec2` into a separate directory,
then run the same command with `PYTHONPATH=/absolute/path/to/extracted/src`.
Verify `poetry run python -c "import sysmlpy; print(sysmlpy.__file__)"` under
that environment points to the extracted source. Do not copy the old tests:
the comparison deliberately runs the new assertions against both implementations.

All three regression suites run in normal pytest discovery (no conformance marker):
`poetry run pytest tests/connection_roundtrip_test.py tests/derivation_test.py tests/derivation_support_test.py -q`.

## Expanded-support validation (2026-10-09)

The final combined run of required core tests and related reference, import,
traceability, interchange, validator, diff, CLI, and domain tests produced
**1,069 passed, 15 skipped, 10 failed**. All ten failures are in the existing
`validator_test.py` and were reproduced with identical test names on both
upstream `b0c827a` and the previous fork commit `9ae165d` (each baseline validator
run: 67 passed, 7 skipped, 10 failed). They concern trigger payloads and ordinary
connector diagnostics; they are not new derivation regressions. The required
core suites and the new support tests passed.

After separating the core regressions, the support-specific suite contains 42 tests; together with the earlier domain
and generic connection regressions there are 73 tests for this work. SV Blue Dog
still round-trips with 9 requirement usages and 8 derivation edges, and the OMG
example's PlantUML renders successfully to SVG.

## Current modularity

The repository bundles domain models separately under `library/domain`: Analysis,
Cause and Effect, Geometry, Metadata, Quantities and Units, and Requirement
Derivation. Generic library indexing is provided by `LibrarySymbolIndex` in
`semantic.py`; bundling/indexing models does not imply complete execution of their
semantics. Quantities and Units additionally has Python implementation in
`validator.py`, `evaluator.py`, `usage.py`, and `semantic.py`.

Derivation interpretation is isolated in `derivation.py`, but `semantic.py`,
`plantuml.py`, and `traceability.py` call it directly. There is no shared domain
adapter registration interface today. A future modularity change should introduce
a domain-independent hook contract in its own core commit, followed by domain
adapters in separate commits. It should preserve default behavior and reuse common
name resolution rather than grow multiple independent resolvers. No such framework
is claimed or introduced by this patch.
