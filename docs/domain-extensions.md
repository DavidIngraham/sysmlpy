# Domain extensions

`sysmlpy.domains` separates domain policies from the consumers that run analysis,
render General Views, report requirement traceability, and set typed values.
Default adapters preserve existing behavior. Registration is explicit: there is
no entry-point scanning or automatic import of third-party plugins.

## Built-in catalog

| Adapter name | Implemented hooks |
| --- | --- |
| `requirement-derivation` | Analysis diagnostics and derivation relationships |
| `quantities-and-units` | Dimensional diagnostics and typed-value validation |
| `analysis` | Model-only |
| `cause-and-effect` | Model-only |
| `geometry` | Model-only |
| `metadata` | Model-only |

Call `get_registry().describe()` to inspect names, representative model packages,
and capabilities. Model-only entries describe bundled library content; they do
not claim complete executable semantics for those libraries.

## Selecting adapters

```python
from sysmlpy import analyze
from sysmlpy.domains import DomainRegistry, get_registry, using_domains

with using_domains(get_registry().without('quantities-and-units')):
    issues = analyze(model)

with using_domains(DomainRegistry()):
    core_issues = analyze(model)
```

An empty registry disables domain hooks. Parsing, imported library definitions,
ordinary type checks, and quantity representation/arithmetic remain available.
Library search paths still use the existing `analyze(library=...)` mechanism;
adapter selection does not load or unload model libraries.

Registries are immutable collections. `with_adapters()` returns a new registry;
duplicate names and unknown names passed to `without()` raise `ValueError`.
`using_domains()` restores the previous registry even after an exception. It uses
`ContextVar`: async tasks inherit their creation context and can override it
independently. Adapters themselves must be stateless and reentrant.

## Adding an adapter

```python
from sysmlpy.domains import (
    DomainAdapter, DomainDiagnostic, get_registry, using_domains,
)

class ProjectPolicy(DomainAdapter):
    name = 'project-policy'
    capabilities = frozenset({'analyze'})

    def analyze(self, context):
        if not context.model.children:
            return (DomainDiagnostic('warning', 'EMPTY_PROJECT',
                                     'The project has no elements.'),)
        return ()

with using_domains(get_registry().with_adapters(ProjectPolicy())):
    issues = analyze(model)
```

Advertise only hooks the adapter implements:

- `analyze(context)` returns `DomainDiagnostic` objects. `DomainContext` provides
  the model, analyzer, symbol table, library roots, and a shallow read-only options
  mapping. Referenced model objects are not frozen. Requirement derivation reads
  the existing `requirement_results` option for explicit implication evaluation.
- `relations(model)` returns `DomainRelation(kind, source, target, label)` objects
  with model-element endpoints. General Views render selected endpoints as
  labeled directed dashed edges. Requirement traceability consumes only the
  `derive` kind to preserve its existing report schema.
- `validate_value(type_name, value)` returns diagnostics for a normalized Pint
  quantity assigned through `Attribute.set_value()`. That consumer raises
  `ValueError` for error diagnostics; it currently ignores non-error diagnostics.

Hook exceptions propagate. A broken adapter must not silently turn validation
into success. Hooks must not recursively invoke the same top-level operation on
the same model.

## Migration boundaries

Requirement derivation keeps its interpretation engine in `derivation.py`; the
adapter supplies its diagnostics and edges through the shared contracts.

The units adapter reuses existing dimensional checking and ISQ conformance
helpers. Core expression checking can suppress dimensional diagnostics while
retaining operand-type checks. Direct users of `ExpressionTypeChecker` keep the
legacy default, including unit checks. The adapter currently reuses the complete
legacy expression traversal and selects its dimensional diagnostics, so analysis
does perform an additional traversal.

Pint's shared registry, quantity conversion, and evaluator arithmetic remain
shared infrastructure. This interface does not make Pint optional or support
swapping the numerical backend. Analysis, Cause and Effect, Geometry, and Metadata
continue to use generic model parsing/indexing and any existing generic evaluation;
their catalog adapters add no new executable behavior.

Core contracts, core expression-check selection, domain adapters, and catalog
changes are separate commits to make independent review practical.

## Validation (2026-10-09)

The combined required core, rendering, domain, evaluator, traceability, and related
integration run reported: **10 failed, 1130 passed, 15 skipped, 1 warning in 243.66s (0:04:03)**. The ten validator failures
match the previously reproduced upstream baseline exactly; there are no new
failing test names. Required core tests and adapter tests passed. SV Blue Dog
still round-trips with nine requirement usages and eight derivation edges, and
the pinned OMG example renders to SVG with PlantUML.
