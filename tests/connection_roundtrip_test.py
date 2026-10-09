"""Connection syntax preservation independent of any domain-library semantics."""
import re
from sysmlpy import loads
from sysmlpy.formatting import classtree

INLINE = 'package Requirements {\n    metadata def relation; metadata def startRole; metadata def finishRole;\n    part def A;\n    part def B;\n    part a : A;\n    part b : B;\n    #relation connection d {\n        doc /* The mission requires this behavior. */\n        end #startRole source ::> a;\n        end #finishRole target ::> b;\n    }\n} '


def compact(text):
    return re.sub(r"\s+", "", text)


def test_inline_connection_roundtrip():
    model = loads(INLINE)
    for _ in range(2):
        text = classtree(model).dump()
        assert '#relationconnectiond' in compact(text)
        assert 'end#startRolesource::>a;' in compact(text)
        assert 'end#finishRoletarget::>b;' in compact(text)
        assert 'The mission requires this behavior.' in text
        model = loads(text)

def test_nested_connection_roundtrip():
    source = INLINE.replace('#relation connection d', 'part context { #relation connection d').replace('\n} ', '\n} } ')
    text = classtree(loads(source)).dump()
    assert 'end#startRolesource::>a;' in compact(text)
    assert 'end#finishRoletarget::>b;' in compact(text)

def test_public_model_dump_preserves_connection():
    model = loads(INLINE)
    for _ in range(2):
        text = model.dump()
        assert 'end#startRolesource::>a;' in compact(text)
        assert 'end#finishRoletarget::>b;' in compact(text)
        assert 'The mission requires this behavior.' in text
        model = loads(text)

def test_definition_roundtrip():
    source = INLINE.replace('connection d', 'connection def D').replace(
        'source ::> a', 'source : A').replace('target ::> b', 'target : B')
    model = loads(source)
    for _ in range(2):
        text = model.dump()
        assert '#relationconnectiondefD' in compact(text)
        assert 'end#startRolesource:A;' in compact(text)
        assert 'end#finishRoletarget:B;' in compact(text)
        model = loads(text)


def test_plain_connection_end_reference_roundtrip():
    source = 'package P { part a; part b; connection c { end source ::> a; end target ::> b; } }'
    for _ in range(2):
        model = loads(source)
        source = model.dump()
        assert 'endsource::>a;' in compact(source)
        assert 'endtarget::>b;' in compact(source)


def test_edit_connection_body_preserves_extended_ends():
    model = loads(INLINE.replace('doc /*', 'attribute confidence = 1; doc /*'))
    connection = model.find('d')[0]
    connection.doc = 'Updated description.'
    assert {c.name for c in connection.children} == {'confidence', 'source', 'target'}
    text = model.dump()
    assert 'Updated description.' in text
    assert 'end#startRolesource::>a;' in compact(text)
    assert 'attributeconfidence=1;' in compact(text)
    loads(text)


def test_extended_end_public_dump():
    end = loads(INLINE).find('d')[0].children[0]
    assert 'end#startRolesource::>a;' in compact(end.dump())


def test_anonymous_connection_keyword_roundtrip():
    source='package P { connection {end a; end b;} }'
    for _ in range(2):
        source=loads(source).dump()
        assert 'connection' in source
        assert 'end a' in source


def test_body_subsetting_and_binding_are_both_preserved():
    source = """package P {
        part a; part b; part sources; part targets;
        connection c {end s :> sources ::> a; end t :> targets ::> b;}
    }"""
    for _ in range(2):
        source = loads(source).dump()
        text = compact(source)
        assert 'ends:>sources::>a;' in text
        assert 'endt:>targets::>b;' in text
