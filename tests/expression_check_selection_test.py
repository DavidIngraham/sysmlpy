"""Expression type checks can run independently of dimensional diagnostics."""
from sysmlpy import loads
from sysmlpy.semantic import SemanticAnalyzer, SymbolTable, ExpressionTypeChecker


def test_type_checks_survive_disabling_unit_checks():
    model = loads("""package P { private import ISQ::*;
        attribute mass : MassValue; attribute length : LengthValue;
        constraint c {mass + length > 0}
        part def V {attribute flag : Boolean; attribute n : Integer; constraint d {flag and n}}
    }""")
    analyzer = SemanticAnalyzer()
    roots = analyzer._normalize_library_paths(None)
    symbols = SymbolTable()
    symbols.build_from_model(model, roots)
    full = ExpressionTypeChecker(analyzer, symbols, roots).check(model)
    types = ExpressionTypeChecker(analyzer, symbols, roots, include_units=False).check(model)
    assert any(i.code == 'UNIT_DIMENSION_MISMATCH' for i in full)
    assert not any(i.code == 'UNIT_DIMENSION_MISMATCH' for i in types)
    assert any(i.code == 'OPERAND_TYPE_MISMATCH' for i in types)
    assert [(i.code,i.message) for i in types] == [(i.code,i.message) for i in full if i.code != 'UNIT_DIMENSION_MISMATCH']

