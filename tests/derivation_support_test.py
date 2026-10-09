"""Requirement Derivation Domain Library integration and semantic regressions."""
from pathlib import Path
import pytest
from sysmlpy import loads, analyze, as_general_view
from sysmlpy.derivation import extract_derivations, evaluate_derivations, qualified_name
from sysmlpy.interchange import to_interchange, from_interchange
from sysmlpy.traceability import extract_traceability, as_traceability_matrix_view

DIRECT = '''package P {
 private import DerivationConnections::*;
 requirement a; requirement b;
 connection d : Derivation {
  end s :> originalRequirement ::> a;
  end t :> derivedRequirements ::> b;
 }
}'''
INHERITED = '''package P {
 private import RequirementDerivation::*;
 requirement a; requirement b;
 #derivation connection def Base {end #original s; end #derive t;}
 connection def Child :> Base;
 connection d : Child {end s ::> a; end t ::> b;}
}'''


def names(model):
    edges, issues = extract_derivations(model)
    assert not issues, [(i.code, i.message) for i in issues]
    return [(qualified_name(a), qualified_name(b)) for a,b in edges]


@pytest.mark.parametrize('source', [DIRECT,
    DIRECT.replace(': Derivation', ':> derivations').replace(':> originalRequirement ', ':> originalRequirements '),
    DIRECT.replace('private import DerivationConnections::*;', 'private import RequirementDerivation::*;'),
    INHERITED,
    INHERITED.replace('end s ::>', 'end renamed :>> s ::>'),
    INHERITED.replace('connection def Child :> Base;', 'connection def Child :> Base { end :>> s; }'),
    INHERITED.replace('connection def Child :> Base;', 'connection def Intermediate :> Base; connection def Child :> Intermediate;'),
    INHERITED.replace('end #original s;', 'end #original s ::> a;').replace('end s ::> a;', ''),
])
def test_standard_forms_and_roundtrip(source):
    for _ in range(2):
        model = loads(source)
        assert names(model) == [('P::a', 'P::b')]
        assert as_general_view(model).count(': «derive»') == 1
        source = model.dump()


def test_custom_metadata_specializations_and_short_names():
    source = INHERITED.replace('requirement a;', '''metadata def Relation :> DerivationMetadata;
        metadata def <rel> SpecificRelation :> Relation;
        metadata def Start :> OriginalRequirementMetadata;
        metadata def Finish :> DerivedRequirementMetadata;
        requirement a;''').replace('#derivation', '#rel').replace('#original', '#Start').replace('#derive', '#Finish')
    assert names(loads(source)) == [('P::a', 'P::b')]
    assert names(loads(loads(source).dump())) == [('P::a', 'P::b')]


def test_official_vehicle_unnamed_ends_and_interchange():
    source = (Path(__file__).parent/'fixtures/derivation/VehicleRequirementDerivation.sysml').read_text()
    model = loads(source)
    expected = [('VehicleRequirementDerivation::vehicleMassRequirement',
                 'VehicleRequirementDerivation::'+target)
                for target in ('chassisMassRequirement','engineMassRequirement')]
    for candidate in (model, loads(model.dump()), from_interchange(to_interchange(model))):
        assert names(candidate) == expected
        assert as_general_view(candidate).count(': «derive»') == 2


@pytest.mark.parametrize('source,code', [
    (DIRECT.replace('requirement b;', 'part b;'), 'DERIVATION_END_TARGET'),
    (DIRECT.replace('::> b', '::> missing'), 'DERIVATION_END_TARGET'),
    (DIRECT.replace('::> b', '::> a'), 'DERIVATION_SELF'),
    (DIRECT.replace(':> derivedRequirements', ':> originalRequirement'), 'DERIVATION_CARDINALITY'),
    (DIRECT.replace('end t :> derivedRequirements ::> b;', ''), 'DERIVATION_CARDINALITY'),
    (DIRECT.replace(':> derivedRequirements', ''), 'DERIVATION_END_ROLE'),
    (INHERITED.replace('end t ::> b;', ''), 'DERIVATION_END_TARGET'),
    (INHERITED.replace('connection def Child :> Base;', 'connection def Child :> Base; connection def Base2 :> Child;').replace('connection def Base {', 'connection def Base :> Base2 {'), 'DERIVATION_INHERITANCE_CYCLE'),
])
def test_invalid_derivation_analyzer(source, code):
    model=loads(source)
    edges, issues=extract_derivations(model)
    assert not edges
    assert code in {i.code for i in issues}
    assert code in {i.code for i in analyze(model, style_checks=False)}


@pytest.mark.parametrize('a,b,expected', [
    (True,True,True),(True,False,False),(True,None,None),
    (False,True,True),(False,False,True),(False,None,True),
    (None,True,True),(None,False,None),(None,None,None),
])
def test_implication_truth_table(a,b,expected):
    evaluations,issues=evaluate_derivations(loads(DIRECT),{'P::a':a,'P::b':b})
    assert not issues
    assert len(evaluations)==1
    assert evaluations[0].result is expected


def test_implication_analyzer_and_unknown_policy():
    model=loads(DIRECT)
    assert evaluate_derivations(model)[0][0].result is None
    assert 'DERIVATION_IMPLICATION_VIOLATED' not in {i.code for i in analyze(model)}
    issues=analyze(model,requirement_results={'P::a':True,'P::b':False})
    assert 'DERIVATION_IMPLICATION_VIOLATED' in {i.code for i in issues}
    with pytest.raises(ValueError):
        evaluate_derivations(model,{'P::a':1})


def test_traceability_does_not_confuse_derivation_with_coverage():
    model=loads(DIRECT)
    report=extract_traceability(model)
    assert report.by_name('a').derives==['P::b']
    assert report.by_name('b').derived_from==['P::a']
    assert report.coverage()['covered']==0
    assert report.by_name('b').status=='uncovered'
    assert report.to_json()['requirements'][1]['derived_from']==['P::a']
    assert '| P::a' in report.to_markdown()
    assert 'derived from: P::a' in report.to_text()
    for format in ('markdown','html','plantuml'):
        output=as_traceability_matrix_view(model,show_derivation=True,output_format=format)
        assert ('Derived from' if format!='plantuml' else ': derive') in output


def test_direct_interchange_retains_roles():
    assert names(from_interchange(to_interchange(loads(DIRECT)))) == [('P::a','P::b')]


@pytest.mark.parametrize('connection', [
    'connection d : Child connect a to b;',
    'connection d : Child connect s references a to t references b;',
])
def test_typed_connector_shorthand(connection):
    source = INHERITED.replace('connection d : Child {end s ::> a; end t ::> b;}',connection)
    assert names(loads(source)) == [('P::a','P::b')]
    assert names(loads(loads(source).dump())) == [('P::a','P::b')]


def test_explicit_standard_connector_roles():
    source = DIRECT[:DIRECT.index(' connection d')] + 'connection d : Derivation connect originalRequirement references a to derivedRequirements references b; }'
    assert names(loads(source)) == [('P::a','P::b')]


def test_unlabelled_abstract_library_connector_does_not_guess_roles():
    source = DIRECT[:DIRECT.index(' connection d')] + 'connection d : Derivation connect a to b; }'
    edges,issues=extract_derivations(loads(source))
    assert not edges
    assert 'DERIVATION_END_ROLE' in {i.code for i in issues}


def test_import_ambiguity_does_not_choose_arbitrary_metadata():
    source = 'package Other {metadata def derivation;} ' + INHERITED.replace(
        'private import RequirementDerivation::*;',
        'private import RequirementDerivation::*; private import Other::*;')
    assert extract_derivations(loads(source))[0] == []


def test_inherited_role_conflict_is_diagnostic():
    source=INHERITED.replace('connection def Child :> Base;',
        '#derivation connection def Other {end #derive s; end #original t;} connection def Child :> Base, Other;')
    edges,issues=extract_derivations(loads(source))
    assert not edges
    assert 'DERIVATION_END_ROLE' in {i.code for i in issues}


def test_abstract_derivation_template_can_leave_roles_for_specializations():
    source = DIRECT.replace('connection d : Derivation',
        'abstract connection def Template :> Derivation; connection d : Template')
    assert names(loads(source)) == [('P::a','P::b')]


def test_qualified_role_subsetting_through_definition():
    source = INHERITED.replace('end s ::> a;', 'end renamed :> Base::s ::> a;')
    # Subsetting adds an end; redefinition replaces an inherited end. The
    # inherited original is still unbound, so this is not a valid derivation.
    edges,issues=extract_derivations(loads(source))
    assert not edges
    assert 'DERIVATION_END_TARGET' in {i.code for i in issues}


def test_alias_to_metadata_definition_without_children():
    source=INHERITED.replace('requirement a;',
        'metadata def Custom :> DerivationMetadata; alias D for Custom; requirement a;').replace('#derivation','#D')
    assert names(loads(source)) == [('P::a','P::b')]


def test_private_import_is_not_reexported_for_metadata():
    source='package Hidden {private import RequirementDerivation::*;} ' + INHERITED.replace(
        'private import RequirementDerivation::*;', 'private import Hidden::*;')
    assert extract_derivations(loads(source))[0] == []


def test_public_import_reexports_metadata():
    source='package Facade {public import RequirementDerivation::*;} ' + INHERITED.replace(
        'private import RequirementDerivation::*;', 'private import Facade::*;')
    assert names(loads(source)) == [('P::a','P::b')]


def test_inherited_binding_keeps_its_declaring_scope():
    source='package A { private import RequirementDerivation::*;\n       requirement a; requirement b;\n       #derivation connection def Base {end #original s ::> a; end #derive t ::> b;}\n    }\n    package B {private import A::Base; requirement a; requirement b; connection d : Base;}'
    assert names(loads(source)) == [('A::a','A::b')]
