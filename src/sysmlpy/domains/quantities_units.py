"""Adapter for existing ISQ/Pint dimensional validation.

Pint values and arithmetic remain shared interpreter infrastructure. This adapter
owns activation of library-specific diagnostic and typed-value policies, reusing
the existing checker and validator engines to preserve their behavior.
"""
from .registry import DomainAdapter, DomainDiagnostic


class QuantitiesUnitsAdapter(DomainAdapter):
    name = 'quantities-and-units'
    model_packages = ('ISQ', 'SI', 'USCustomaryUnits', 'Quantities')
    capabilities = frozenset({'analyze', 'validate_value'})

    def analyze(self, context):
        from ..semantic import ExpressionTypeChecker
        checker = ExpressionTypeChecker(context.analyzer, context.symbols,
                                        list(context.library_roots))
        # Use the same complete expression walk as before migration; the legacy
        # check_units() walk intentionally visits a narrower set of owners.
        dimensional = [i for i in checker.check(context.model)
                       if i.code == 'UNIT_DIMENSION_MISMATCH']
        dimensional.extend(checker.check_derivations(context.model))
        return [DomainDiagnostic(i.severity, i.code, i.message, i.element, i.reference)
                for i in dimensional]

    def validate_value(self, type_name, value):
        from ..validator import validate_unit_conformance
        if type_name is None or value.units.dimensionless:
            return ()
        # Preserve Attribute.set_value's existing type-name convention.
        conforms, message = validate_unit_conformance(type_name.capitalize() + 'Value', value)
        if conforms:
            return ()
        return (DomainDiagnostic('error', 'UNIT_VALUE_MISMATCH', message),)
