# OMG requirement derivation regression fixture

`RequirementDerivationExample.sysml` is copied byte-for-byte from the
Systems Modeling SysML v2 Pilot Implementation example corpus.

- Revision: `32d42cdd4846576131e8ae6cf782d2880488adec`
- Source: https://raw.githubusercontent.com/Systems-Modeling/SysML-v2-Pilot-Implementation/32d42cdd4846576131e8ae6cf782d2880488adec/sysml/src/examples/Requirements%20Examples/RequirementDerivationExample.sysml
- SHA-256: `1575a8e09c008145ff619ef7d0ce7622d9e88c77811a6984578ef393d99e26c7`
- Retrieved: 2026-10-09. See the accompanying upstream LICENSE.

The original binds both `r1_1` and `r1_2` to `req1_1`. This is preserved;
the diagram must therefore contain one unique edge. A separate, explicitly
modified test variant binds the second derived end to `req1_2`.

The tests distinguish syntax acceptance, lossless public-model round trips,
and inherited-role visualization. Merely accepting the input is insufficient.

## Vehicle example

`VehicleRequirementDerivation.sysml` is also copied unchanged from the OMG Pilot
Implementation, revision `1852fda9820944b5b5f3f12f6953f0d31fcaa8c7`:
https://github.com/Systems-Modeling/SysML-v2-Pilot-Implementation/blob/1852fda9820944b5b5f3f12f6953f0d31fcaa8c7/sysml/src/examples/Requirements%20Examples/VehicleRequirementDerivation.sysml

SHA-256: `aa7dcf0498eb967f539fc81ef63c6f924c691edfe26c279a875c1a3a0729a8e8`. This example exercises three unnamed
connection ends. This revision uses EPL-2.0; see LICENSE-EPL-2.0. The earlier example retains its original LICENSE (LGPL-3.0).
