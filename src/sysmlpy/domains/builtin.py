"""Explicit built-in adapter composition; imports are lazy to avoid cycles."""
from functools import lru_cache
from .registry import DomainRegistry


@lru_cache(maxsize=1)
def builtin_registry():
    from .requirement_derivation import RequirementDerivationAdapter
    from .quantities_units import QuantitiesUnitsAdapter
    from .catalog import model_library_adapters
    return DomainRegistry((QuantitiesUnitsAdapter(), RequirementDerivationAdapter())
                          + model_library_adapters())
