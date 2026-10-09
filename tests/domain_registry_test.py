"""Generic extension mechanics, with no standard-library domain dependency."""
import asyncio
import pytest
from sysmlpy.domains import (DomainAdapter, DomainContext, DomainDiagnostic,
                            DomainRelation, DomainRegistry, get_registry, using_domains)


class Example(DomainAdapter):
    name = 'example'
    capabilities = frozenset({'analyze', 'relations', 'validate_value'})

    def analyze(self, context):
        return [DomainDiagnostic('warning', 'EXAMPLE', context.options['message'])]

    def relations(self, model):
        return [DomainRelation('example', model, model, 'example')]

    def validate_value(self, type_name, value):
        return [DomainDiagnostic('error', 'VALUE', type_name)]


def test_dispatch_and_explicit_registration():
    empty = DomainRegistry()
    registry = empty.with_adapters(Example())
    assert empty.adapters == ()
    assert registry.analyze(DomainContext(None, options={'message': 'hello'}))[0].message == 'hello'
    assert registry.relations(None)[0].kind == 'example'
    assert registry.validate_value('T', 1)[0].code == 'VALUE'
    assert registry.without('example') == empty
    assert registry.describe()[0]['capabilities'] == ('analyze', 'relations', 'validate_value')


def test_duplicate_and_unknown_names_fail():
    with pytest.raises(ValueError):
        DomainRegistry((Example(), Example()))
    with pytest.raises(ValueError):
        DomainRegistry((DomainAdapter(),))
    with pytest.raises(ValueError):
        DomainRegistry().without('typo')


def test_nested_activation_and_exception_restoration():
    previous = get_registry()
    registry = DomainRegistry((Example(),))
    with pytest.raises(RuntimeError):
        with using_domains(registry):
            with using_domains(DomainRegistry()):
                assert get_registry().adapters == ()
            assert get_registry() is registry
            raise RuntimeError('test')
    assert get_registry() == previous


def test_model_only_adapter_is_not_executed():
    class ModelOnly(Example):
        capabilities = frozenset()
    registry = DomainRegistry((ModelOnly(),))
    assert registry.analyze(DomainContext(None)) == []
    assert registry.relations(None) == []
    assert registry.validate_value('T', 1) == []


def test_plugin_errors_are_not_swallowed():
    with pytest.raises(KeyError):
        DomainRegistry((Example(),)).analyze(DomainContext(None))


def test_options_mapping_is_not_mutable():
    context = DomainContext(None, options={'a': 1})
    with pytest.raises(TypeError):
        context.options['a'] = 2


def test_concurrent_contexts_are_isolated():
    async def run():
        async def task(registry):
            with using_domains(registry):
                await asyncio.sleep(0)
                assert get_registry() is registry
        await asyncio.gather(task(DomainRegistry()), task(DomainRegistry((Example(),))))
    asyncio.run(run())
