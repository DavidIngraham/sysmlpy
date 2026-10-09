"""Domain-independent extension contracts; no library-specific imports or rules.

Registries are immutable collections. Activation is explicit and context-local;
plugins are never discovered or imported from the environment automatically.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True)
class DomainContext:
    model: object
    analyzer: object = None
    symbols: object = None
    library_roots: tuple = ()
    options: object = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, 'options', MappingProxyType(dict(self.options)))


@dataclass(frozen=True)
class DomainDiagnostic:
    severity: str
    code: str
    message: str
    element: object = None
    reference: str = ''


@dataclass(frozen=True)
class DomainRelation:
    kind: str
    source: object
    target: object
    label: str


class DomainAdapter:
    """Override only implemented hooks. Empty capabilities mean model-only.

    Adapters must be stateless/reentrant. Hook exceptions propagate; a broken
    plugin must not silently turn validation into success. Hooks must not invoke
    the same top-level operation recursively on the same model.
    """
    name = ''
    model_packages = ()
    capabilities = frozenset()

    def analyze(self, context):
        return ()

    def relations(self, model):
        return ()

    def validate_value(self, type_name, value):
        return ()


@dataclass(frozen=True)
class DomainRegistry:
    adapters: tuple = ()

    def __post_init__(self):
        adapters = tuple(self.adapters)
        names = [a.name for a in adapters]
        if any(not isinstance(name, str) or not name for name in names):
            raise ValueError('Adapters need nonempty string names.')
        if len(set(names)) != len(names):
            raise ValueError('Duplicate domain adapter name.')
        object.__setattr__(self, 'adapters', adapters)

    def with_adapters(self, *adapters):
        return DomainRegistry(self.adapters + tuple(adapters))

    def without(self, *names):
        unknown = set(names) - {a.name for a in self.adapters}
        if unknown:
            raise ValueError(f'Unknown domain adapters: {sorted(unknown)}')
        return DomainRegistry(tuple(a for a in self.adapters if a.name not in names))

    def describe(self):
        return tuple({'name': a.name, 'model_packages': tuple(a.model_packages),
                      'capabilities': tuple(sorted(a.capabilities))} for a in self.adapters)

    def analyze(self, context):
        return [issue for a in self.adapters if 'analyze' in a.capabilities
                for issue in a.analyze(context)]

    def relations(self, model):
        return [edge for a in self.adapters if 'relations' in a.capabilities
                for edge in a.relations(model)]

    def validate_value(self, type_name, value):
        return [issue for a in self.adapters if 'validate_value' in a.capabilities
                for issue in a.validate_value(type_name, value)]


_active = ContextVar('sysmlpy_domains', default=None)


def get_registry():
    registry = _active.get()
    if registry is None:
        from .builtin import builtin_registry
        return builtin_registry()
    return registry


@contextmanager
def using_domains(registry):
    """Use an explicit registry for nested analysis/render/report/value calls.

    An empty registry disables domain hooks, not parsing, imports, or numeric
    representation. ContextVar tokens restore the previous registry even after
    errors and keep concurrent async tasks isolated.
    """
    if not isinstance(registry, DomainRegistry):
        raise TypeError('Expected a DomainRegistry.')
    token = _active.set(registry)
    try:
        yield registry
    finally:
        _active.reset(token)
