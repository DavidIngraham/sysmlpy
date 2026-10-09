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
