# Initial support for the Requirement Derivation Domain Library

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

## Scope

- Resolves the standard `RequirementDerivation` metadata names through qualified
  names, membership imports, wildcard imports, and aliases.
- Retains annotated definition ends and ordinary usage-end `::>` bindings;
  resolves named roles from the typed connection definition.
- Requires exactly one original and at least one derived endpoint. Self-derivation,
  unresolved targets, and ambiguous end roles produce no diagram edges.
  `sysmlpy.derivation.extract_derivations(model)` returns `(edges, issues)`;
  these extraction diagnostics are not integrated with `analyze()`.
- Draws an edge only when both requirement nodes are selected. Repeated targets
  produce one edge.
- This is a focused standard-library projection, not a complete SysML resolver.
  Arbitrary semantic-metadata subclasses, all feature inheritance/redefinition
  rules, and logical implication evaluation are not implemented.

## Review scope and follow-up support

Suggested PR title: **Add initial support for the Requirement Derivation Domain Library**.
The domain library is specified in SysML v2 Part 1, section 9.6. This work does
not claim complete requirements-management or domain-library semantic conformance.

The commits separate general syntax preservation (ANTLR visitor, grammar objects,
and public model loading/dumping) from interpreting the domain library and
projecting it into a General View. The generic regression suite uses locally
defined metadata and parts, without importing the derivation library:
`tests/connection_roundtrip_test.py`. Domain-specific coverage and the pinned
OMG example remain in `tests/derivation_test.py`.

| Capability | This change | Work needed for broader support |
| --- | --- | --- |
| Connection bodies, metadata prefixes, and end reference subsetting | Preserved through model round trips | Independent of domain semantics |
| Standard metadata forms and named roles from a typed local definition | Supported for the tested forms | General semantic-metadata specialization and feature inheritance |
| Direct `DerivationConnections::Derivation` typing or `derivations` subsetting, without metadata | Not interpreted by the extractor | Resolve standard base types/features and original/derived role subsetting |
| Structural validity | Extraction checks endpoint kind, one original, derived endpoints, and self-derivation | Integrate diagnostics with `analyze()` and test malformed/ambiguous/inherited forms comprehensively |
| `originalImpliesDerived` | Not evaluated | Define evaluation for known/unknown requirement results; do not equate an edge with proof of logical implication |
| Diagram projection | Tested General View edges, explicitly a rendering convention | Broader graphical conformance and connection-definition presentation |
| Traceability and interchange consumers | No new derivation-specific integration | Decide and test how derivation appears in trace reports, matrices, and interchange |
| Official examples | One pinned example plus an explicitly modified variant | Add further official examples, including `VehicleRequirementDerivation.sysml`, and negative cases |

An unqualified claim of full domain-library support would require an explicit
coverage contract across the remaining rows, rather than just recognizing the
three metadata keywords. Domain library support is optional under specification
Clause 2; the library definitions themselves are normative.

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

Both regression suites run in normal pytest discovery (no conformance marker):
`poetry run pytest tests/connection_roundtrip_test.py tests/derivation_test.py -q`.
