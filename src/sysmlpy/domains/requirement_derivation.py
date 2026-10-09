"""Requirement Derivation Domain Library adapter."""
from .registry import DomainAdapter, DomainDiagnostic, DomainRelation


class RequirementDerivationAdapter(DomainAdapter):
    name = 'requirement-derivation'
    model_packages = ('RequirementDerivation', 'DerivationConnections')
    capabilities = frozenset({'analyze', 'relations'})

    def analyze(self, context):
        from ..derivation import evaluate_derivations, qualified_name
        evaluations, issues = evaluate_derivations(
            context.model, context.options.get('requirement_results'))
        result = [DomainDiagnostic('error', i.code, i.message, i.element) for i in issues]
        for evaluation in evaluations:
            if evaluation.result is False:
                result.append(DomainDiagnostic(
                    'error', 'DERIVATION_IMPLICATION_VIOLATED',
                    f"{qualified_name(evaluation.original)!r} is true but "
                    f"derived requirement {qualified_name(evaluation.derived)!r} is false.",
                    evaluation.derived))
        return result

    def relations(self, model):
        from ..derivation import extract_derivations
        return [DomainRelation('derive', source, target, '«derive»')
                for source, target in extract_derivations(model)[0]]
