"""Existing dimensional policies remain compatible and independently selectable."""
import pytest
from sysmlpy import loads, analyze, Attribute
from sysmlpy.usage import ureg
from sysmlpy.evaluator import collect_values
from sysmlpy.domains import DomainRegistry, get_registry, using_domains
from sysmlpy.domains.quantities_units import QuantitiesUnitsAdapter
from sysmlpy.semantic import SemanticAnalyzer, SymbolTable, ExpressionTypeChecker

SOURCE = """package P {private import ISQ::*;
 part def V {attribute mass : MassValue; attribute length : LengthValue;
 constraint bad {mass + length > 0}
 attribute flag : Boolean; attribute n : Integer;
 constraint wrong {flag and n}}
}"""


def test_units_optout_keeps_core_type_diagnostics():
    model = loads(SOURCE)
    enabled = analyze(model)
    with using_domains(get_registry().without('quantities-and-units')):
        disabled = analyze(model)
    assert any(i.code == 'UNIT_DIMENSION_MISMATCH' for i in enabled)
    assert not any(i.code.startswith('UNIT_DIMENSION') for i in disabled)
    assert any(i.code == 'OPERAND_TYPE_MISMATCH' for i in disabled)
    assert sum(i.code == 'UNIT_DIMENSION_MISMATCH' for i in enabled) == 1


def test_adapter_matches_legacy_engine_diagnostics():
    model = loads(SOURCE)
    analyzer = SemanticAnalyzer()
    roots = analyzer._normalize_library_paths(None)
    symbols = SymbolTable()
    symbols.build_from_model(model, roots)
    checker = ExpressionTypeChecker(analyzer, symbols, roots)
    old = [i for i in checker.check(model) if i.code == 'UNIT_DIMENSION_MISMATCH']
    old += checker.check_derivations(model)
    new = [i for i in analyze(model) if i.code.startswith('UNIT_DIMENSION')]
    assert [(i.code,i.message,i.reference) for i in new] == [(i.code,i.message,i.reference) for i in old]


def test_typed_value_validation_is_selectable():
    class Type:
        name = 'mass'
    value = Attribute(name='value')
    value.typedby = Type()
    with pytest.raises(ValueError):
        value.set_value(2 * ureg.metre)
    with using_domains(DomainRegistry()):
        value.set_value(2 * ureg.metre)
    with using_domains(DomainRegistry((QuantitiesUnitsAdapter(),))):
        value.set_value(2 * ureg.kilogram)


def test_quantity_evaluation_is_shared_not_disabled_with_policy():
    model = loads('package P {attribute mass = 2 [kg];}')
    before = collect_values(model)['P::mass']
    with using_domains(DomainRegistry()):
        after = collect_values(model)['P::mass']
    assert before == after
    assert after.to('kg').magnitude == 2
