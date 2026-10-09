"""Bundled definitions and executable domain capabilities are distinct."""
from sysmlpy.domains import DomainContext, DomainRegistry, get_registry
from sysmlpy.domains.catalog import model_library_adapters


def test_all_bundled_domains_are_described_honestly():
    catalog = {item['name']: item for item in get_registry().describe()}
    assert set(catalog) == {'analysis', 'cause-and-effect', 'geometry', 'metadata',
                            'quantities-and-units', 'requirement-derivation'}
    for name in ('analysis', 'cause-and-effect', 'geometry', 'metadata'):
        assert catalog[name]['capabilities'] == ()
        assert catalog[name]['model_packages']
    assert 'analyze' in catalog['quantities-and-units']['capabilities']
    assert 'relations' in catalog['requirement-derivation']['capabilities']


def test_model_only_catalog_has_no_runtime_side_effects():
    registry = DomainRegistry(model_library_adapters())
    assert registry.analyze(DomainContext(None)) == []
    assert registry.relations(None) == []
    assert registry.validate_value('Unknown', object()) == []
