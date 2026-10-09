"""Derivation defaults and explicit adapter activation across core consumers."""
from sysmlpy import loads, analyze, as_general_view
from sysmlpy.traceability import extract_traceability
from sysmlpy.domains import (DomainRegistry, DomainAdapter, DomainDiagnostic,
                            DomainRelation, get_registry, using_domains)
from sysmlpy.domains.requirement_derivation import RequirementDerivationAdapter

SOURCE = """package P {private import RequirementDerivation::*;
 requirement a; requirement b;
 #derivation connection d {end #original s ::> a;end #derive t ::> b;}
}"""


def test_default_and_optout_cover_all_consumers():
    model = loads(SOURCE)
    assert ': «derive»' in as_general_view(model)
    assert extract_traceability(model).by_name('a').derives == ['P::b']
    with using_domains(DomainRegistry()):
        assert ': «derive»' not in as_general_view(model)
        assert extract_traceability(model).by_name('a').derives == []
        assert not [i for i in analyze(model, requirement_results={'P::a': True, 'P::b': False})
                    if i.code.startswith('DERIVATION_')]
        assert '#derivation' in model.dump()  # disabling semantics never discards syntax
    assert ': «derive»' in as_general_view(model)


def test_explicit_adapter_invokes_diagnostics():
    with using_domains(DomainRegistry((RequirementDerivationAdapter(),))):
        issues = analyze(loads(SOURCE), requirement_results={'P::a': True, 'P::b': False})
    assert any(i.code == 'DERIVATION_IMPLICATION_VIOLATED' for i in issues)


def test_custom_domain_integrates_without_core_changes():
    class Custom(DomainAdapter):
        name = 'custom'
        capabilities = frozenset({'analyze', 'relations'})
        def analyze(self, context):
            return [DomainDiagnostic('warning', 'CUSTOM', 'custom check')]
        def relations(self, model):
            return [DomainRelation('custom', model.find('a')[0], model.find('b')[0], 'custom')]
    with using_domains(DomainRegistry((Custom(),))):
        model = loads(SOURCE)
        assert any(i.code == 'CUSTOM' for i in analyze(model))
        assert ': custom' in as_general_view(model)
        assert ': «derive»' not in as_general_view(model)
    assert any(d['name'] == 'requirement-derivation' for d in get_registry().describe())
