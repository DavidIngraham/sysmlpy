"""Requirements derivations must survive model conversion and visualization."""
import re
from pathlib import Path

from sysmlpy import loads, as_general_view

OFFICIAL = (Path(__file__).parent / 'fixtures/derivation/RequirementDerivationExample.sysml').read_text()


def test_official_example_parses():
    assert loads(OFFICIAL) is not None


def test_official_example_public_roundtrip():
    model = loads(OFFICIAL)
    for _ in range(2):
        text = model.dump()
        for end in ('r1::>req1;', 'r1_1::>req1_1;', 'r1_2::>req1_1;'):
            assert end in compact(text)
        assert '#derivationconnectiondefReq1_Derivation' in compact(text)
        assert 'end#originalr1:Req1;' in compact(text)
        assert 'end#deriver1_1:Req1_1;' in compact(text)
        assert 'end#deriver1_2:Req1_2;' in compact(text)
        assert 'satisfyrequirementreq1:Req1bysystem' in compact(text)
        model = loads(text)


def test_official_example_inherited_roles():
    # The upstream example binds both derived ends to req1_1. Preserve it
    # verbatim: its projection has one unique edge, not an invented req1_2 edge.
    assert as_general_view(loads(OFFICIAL)).count(': «derive»') == 1


INLINE = """package Requirements {
    private import RequirementDerivation::*;
    requirement def A;
    requirement def B;
    requirement a : A;
    requirement b : B;
    #derivation connection d {
        doc /* The mission requires this behavior. */
        end #original source ::> a;
        end #derive target ::> b;
    }
} """


def compact(text):
    return re.sub(r'\s+', '', text)


def test_general_view_has_derivation_edge():
    text = as_general_view(loads(INLINE))
    a = re.search(r'rectangle "a" as (\w+)', text).group(1)
    b = re.search(r'rectangle "b" as (\w+)', text).group(1)
    assert f'{a} ..> {b} : «derive»' in text


def test_multiple_derived_ends():
    source = INLINE.replace('requirement b : B;', 'requirement b : B; requirement c : B;').replace('end #derive target ::> b;', 'end #derive target ::> b; end #derive another ::> c;')
    text = as_general_view(loads(source))
    assert text.count(': «derive»') == 2


def test_selection_omits_edges_to_hidden_requirements():
    model = loads(INLINE)
    text = as_general_view(model, elements=model.find('a'))
    assert ': «derive»' not in text


def test_unresolved_end_does_not_match_partial_path():
    source = INLINE.replace('target ::> b', 'target ::> b.missing')
    assert ': «derive»' not in as_general_view(loads(source))


def test_regular_connection_is_not_derivation():
    assert ': «derive»' not in as_general_view(loads(INLINE.replace('#derivation ', '')))


def test_qualified_metadata_and_references():
    source = INLINE.replace('#derivation', '#RequirementDerivation::derivation').replace(
        '#original', '#RequirementDerivation::original').replace(
        '#derive ', '#RequirementDerivation::derive ').replace(
        '::> a', '::> Requirements::a').replace('::> b', '::> Requirements::b')
    assert as_general_view(loads(source)).count(': «derive»') == 1


def test_same_names_in_other_package_do_not_steal_endpoints():
    source = 'package Other { requirement a; requirement b; } ' + INLINE
    model = loads(source)
    selected = model.find('Requirements')[0]
    assert as_general_view(model, focus=selected).count(': «derive»') == 1


def test_nested_public_dump_and_view():
    source = INLINE.replace('#derivation connection d', 'part context { #derivation connection d').replace('\n} ', '\n} } ')
    model = loads(source)
    for _ in range(2):
        assert as_general_view(model).count(': «derive»') == 1
        text = model.dump()
        assert 'end#originalsource::>a;' in compact(text)
        assert 'The mission requires this behavior.' in text
        model = loads(text)


def test_connection_body_edit_retains_roles():
    model = loads(INLINE.replace('doc /*', 'attribute confidence = 1; doc /*'))
    connection = model.find('d')[0]
    connection.doc = 'Revised rationale.'
    assert {c.name for c in connection.children} == {'confidence', 'source', 'target'}
    text = model.dump()
    assert 'Revised rationale.' in text
    assert 'end#originalsource::>a;' in compact(text)
    assert 'attributeconfidence=1;' in compact(text)
    assert as_general_view(loads(text)).count(': «derive»') == 1


def test_extended_end_dump_and_no_phantom_nodes():
    model = loads(INLINE)
    end = model.find('d')[0].children[0]
    assert 'end#originalsource::>a;' in compact(end.dump())
    text = as_general_view(model)
    assert 'source' not in text
    assert 'target' not in text


def test_whitespace_in_metadata_prefixes():
    source = INLINE.replace('#', '# ')
    assert as_general_view(loads(source)).count(': «derive»') == 1


def test_official_example_distinct_derived_variant():
    source = OFFICIAL.replace('end r1_2 ::> req1_1;', 'end r1_2 ::> req1_2;')
    assert as_general_view(loads(source)).count(': «derive»') == 2


def test_invalid_original_cardinality():
    from sysmlpy.derivation import extract_derivations
    source = INLINE.replace('end #derive target', 'end #original target')
    edges, issues = extract_derivations(loads(source))
    assert not edges
    assert 'DERIVATION_CARDINALITY' in {i.code for i in issues}


def test_original_cannot_also_be_derived():
    from sysmlpy.derivation import extract_derivations
    edges, issues = extract_derivations(loads(INLINE.replace('target ::> b', 'target ::> a')))
    assert not edges
    assert 'DERIVATION_SELF' in {i.code for i in issues}


def test_metadata_membership_imports():
    source = INLINE.replace('private import RequirementDerivation::*;',
        'private import RequirementDerivation::derivation; private import RequirementDerivation::original; private import RequirementDerivation::derive;')
    assert as_general_view(loads(source)).count(': «derive»') == 1


def test_metadata_alias():
    source = INLINE.replace('requirement def A;', 'alias D for RequirementDerivation::derivation; requirement def A;').replace('#derivation', '#D')
    assert as_general_view(loads(source)).count(': «derive»') == 1


def test_unrelated_metadata_is_not_derivation():
    source = INLINE.replace('private import RequirementDerivation::*;', 'metadata def derivation; metadata def original; metadata def derive;')
    assert ': «derive»' not in as_general_view(loads(source))


def test_typed_usage_inherits_derivation_metadata():
    source = OFFICIAL.replace('#derivation connection :', 'connection :')
    assert as_general_view(loads(source)).count(': «derive»') == 1


def test_official_ends_are_not_phantom_view_nodes():
    text = as_general_view(loads(OFFICIAL))
    assert not re.search(r'rectangle "r1(?:_1|_2)?"', text)
