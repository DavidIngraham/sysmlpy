"""Model-only library descriptors, without invented execution capabilities."""
from dataclasses import dataclass
from .registry import DomainAdapter


@dataclass(frozen=True)
class ModelLibraryAdapter(DomainAdapter):
    name: str
    model_packages: tuple


def model_library_adapters():
    return (
        ModelLibraryAdapter('analysis', ('AnalysisTooling', 'SampledFunctions',
                                        'StateSpaceRepresentation', 'TradeStudies')),
        ModelLibraryAdapter('cause-and-effect', ('CauseAndEffect', 'CausationConnections')),
        ModelLibraryAdapter('geometry', ('ShapeItems',)),
        ModelLibraryAdapter('metadata', ('ImageMetadata', 'ModelingMetadata',
                                        'ParametersOfInterestMetadata', 'RiskMetadata')),
    )
