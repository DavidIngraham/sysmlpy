"""Requirement-derivation library relationships, independent of diagram layout.

Resolve standard library typing, subsetting, and semantic metadata, with
inherited end roles. Implication evaluation uses explicitly supplied results;
unknown requirement results are never treated as established facts.
"""
from dataclasses import dataclass


_METADATA = {
    'original': 'original', 'OriginalRequirementMetadata': 'original',
    'derive': 'derive', 'DerivedRequirementMetadata': 'derive',
    'derivation': 'derivation', 'DerivationMetadata': 'derivation',
}


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _imports(scope):
    return getattr(scope, 'imports', []) or []


_AMBIGUOUS = object()
_STANDARD = {
    'Derivation': 'derivation', 'derivations': 'derivation',
    'originalRequirement': 'original', 'originalRequirements': 'original',
    'derivedRequirements': 'derive',
}


def _standard_member(scope, name):
    if scope == 'RequirementDerivation' and name in _METADATA:
        return 'RequirementDerivation::' + _METADATA[name]
    if scope in ('RequirementDerivation', 'DerivationConnections') and name in _STANDARD:
        return 'DerivationConnections::' + name
    if scope == 'DerivationConnections::Derivation' and name in _STANDARD:
        return 'DerivationConnections::' + name
    return None


def _declaration(element):
    grammar = getattr(element, 'grammar', None)
    if grammar is None:
        return {}
    node = grammar.get_definition()
    if 'definition' in node:
        return node['definition'].get('declaration', {})
    return node.get('declaration', {})


def _bases(element):
    declaration = _declaration(element)
    for kind in ('OwnedSubclassification', 'OwnedFeatureTyping', 'OwnedSubsetting', 'OwnedRedefinition'):
        yield from _references(declaration, kind)


def _names(element):
    names = {getattr(element, 'name', None), getattr(element, 'shortname', None)}
    for node in _walk(_declaration(element)):
        if node.get('name') == 'Identification':
            names.update((node.get('declaredName'), node.get('declaredShortName')))
    return {name.strip('<>') if isinstance(name, str) else name for name in names}


def _unique(candidates):
    distinct = []
    for hit in candidates:
        if hit is not None and not any(hit is c or (isinstance(hit, str) and hit == c) for c in distinct):
            distinct.append(hit)
    return distinct[0] if len(distinct) == 1 else (_AMBIGUOUS if distinct else None)


def _member(scope, name, seen, exported=False):
    if isinstance(scope, str):
        return _standard_member(scope, name)
    key = (id(scope), name, exported)
    if key in seen:
        return None
    seen = seen | {key}
    local = [c for c in getattr(scope, 'children', []) if name in _names(c)]
    if local:
        return _unique(local)
    for declaration in _imports(scope):
        if type(declaration).__name__ == 'AliasMember':
            if name in (declaration.memberName, declaration.memberShortName):
                visibility = getattr(declaration.prefix, 'visibility', None)
                if exported and visibility is not None and visibility.dump().strip() == 'private':
                    return None
                target = _resolve(scope, declaration.memberElement.names, seen)
                return target if target is not None else _AMBIGUOUS
    candidates = []
    for declaration in _imports(scope):
        if type(declaration).__name__ != 'Import':
            continue
        for imp in declaration.children:
            visibility = getattr(imp.prefix, 'visibility', None)
            if exported and (visibility is None or visibility.dump().strip() != 'public'):
                continue
            if type(imp).__name__ == 'MembershipImport':
                names = imp.membership.name.names
                hit = _resolve(scope, names, seen) if names[-1] == name else None
            else:
                namespace = _resolve(scope, imp.namespace.namespaces.names, seen)
                hit = _member(namespace, name, seen, exported=True) if namespace is not None else None
            candidates.append(hit)
    if candidates and _unique(candidates) is not None:
        return _unique(candidates)
    # Inherited features are visible inside typed usages and specialized definitions.
    for names in _bases(scope):
        base = _resolve(getattr(scope, 'parent', None), names, seen)
        if base is not None:
            candidates.append(_member(base, name, seen, exported=True))
    return _unique(candidates)


def _resolve(scope, names, seen=frozenset()):
    if not names:
        return None
    while scope is not None and not isinstance(scope, str):
        hit = _member(scope, names[0], seen)
        if hit is not None:
            for name in names[1:]:
                hit = _member(hit, name, seen, exported=True)
                if hit is None:
                    return None
            return hit
        scope = getattr(scope, 'parent', None)
    if names[0] in ('RequirementDerivation', 'DerivationConnections'):
        hit = names[0]
        for name in names[1:]:
            hit = _standard_member(hit, name)
            if hit is None:
                return None
        return hit
    return None


def _metadata_roles(symbol, active=frozenset()):
    if isinstance(symbol, str):
        return {symbol.split('::')[-1]} if symbol.startswith('RequirementDerivation::') else set()
    if id(symbol) in active or getattr(symbol, 'sysml_type', None) != 'metadata':
        return set()
    roles = set()
    for names in _bases(symbol):
        roles.update(_metadata_roles(_resolve(symbol.parent, names), active | {id(symbol)}))
    return roles


def _tags(element, keywords):
    tags = set()
    for keyword in keywords:
        text = keyword if isinstance(keyword, str) else keyword.get('keyword', '')
        text = ''.join(text.split())
        if not text.startswith('#'):
            continue
        symbol = _resolve(element, text[1:].split('::'))
        tags.update(_metadata_roles(symbol))
    return tags


def _ends(element):
    grammar = element.grammar.get_definition()
    if grammar['name'] == 'ConnectionDefinition':
        body = grammar['definition']['body']
    else:
        body = (grammar.get('body') or {}).get('body', {})
    for item in body.get('ownedRelatedElement', []):
        for member in item.get('ownedRelationship', []):
            if member.get('name') == 'NonOccurrenceUsageMember':
                for wrapper in member.get('ownedRelatedElement', []):
                    node = wrapper.get('ownedRelatedElement', {})
                    if node.get('name') == 'EndFeatureUsage' or (node.get('name') == 'ExtendedUsage' and 'end' in node.get('prefix', '').split()):
                        yield node


def _references(declaration, kind):
    for node in _walk(declaration):
        if node.get('name') == kind:
            yield [name for qn in _walk(node) if qn.get('name') == 'QualifiedName'
                   for name in qn.get('names', [])]


def _end_name(end):
    declaration = end['usage']['declaration']['declaration']
    name = (declaration.get('identification') or {}).get('declaredName')
    if name is None:
        redefined = list(_references(declaration, 'OwnedRedefinition'))
        if len(redefined) == 1 and redefined[0]:
            name = redefined[0][-1]
    return name


def _standard_role(symbol):
    if isinstance(symbol, str) and symbol.startswith('DerivationConnections::'):
        return _STANDARD.get(symbol.split('::')[-1])
    return None


def _connection_info(element, active=frozenset()):
    """Return classification, named roles, effective ends, and inheritance issues."""
    if id(element) in active:
        return False, {}, [], [DerivationIssue('DERIVATION_INHERITANCE_CYCLE',
            'Cyclic connection specialization prevents derivation resolution.', element)]
    active = active | {id(element)}
    grammar = element.grammar.get_definition()
    prefix = grammar.get('prefix') or {}
    derived = 'derivation' in _tags(element, prefix.get('usageExtension', prefix.get('keyword', [])))
    roles, ends, issues = {}, [], []
    for names in _bases(element):
        base = _resolve(getattr(element, 'parent', None), names)
        if _standard_role(base) == 'derivation':
            derived = True
            roles.update({'originalRequirement': {'original'},
                          'originalRequirements': {'original'}, 'derivedRequirements': {'derive'}})
        elif getattr(base, 'sysml_type', None) == 'connection':
            is_derivation, inherited, inherited_ends, inherited_issues = _connection_info(base, active)
            derived |= is_derivation
            issues.extend(inherited_issues)
            for name, values in inherited.items():
                roles.setdefault(name, set()).update(values)
            for record in inherited_ends:
                if not any(record[0] is old[0] and record[1] == old[1] for old in ends):
                    ends.append(record)
    for end in _ends(element):
        declaration = end['usage']['declaration']['declaration']
        name = _end_name(end)
        tags = _tags(element, end.get('extensions', [])) & {'original', 'derive'}
        redefinitions = list(_references(declaration, 'OwnedRedefinition'))
        for kind in ('OwnedSubsetting', 'OwnedRedefinition'):
            for reference in _references(declaration, kind):
                if not reference:
                    continue
                role = _standard_role(_resolve(element, reference))
                if role in ('original', 'derive'):
                    tags.add(role)
                elif len(reference) == 1:
                    tags.update(roles.get(reference[0], set()))
                else:
                    base = _resolve(element, reference[:-1])
                    if getattr(base, 'sysml_type', None) == 'connection' and id(base) not in active:
                        tags.update(_connection_info(base, active)[1].get(reference[-1], set()))
        if not tags and name is not None:
            tags = set(roles.get(name, set()))
        replaced = {r[-1] for r in redefinitions if r}
        if name is not None:
            replaced.add(name)
            roles[name] = tags
        ends = [record for record in ends if _end_name(record[1]) not in replaced]
        # Keep unnamed ends separately. None is not a shared role identity.
        ends.append((element, end, tags))
    # Connector shorthand binds declared end roles. An unnamed connector end
    # uses the corresponding inherited end's position, never an invented
    # original/derived direction for the bare abstract library connection.
    connector = grammar.get('part') or {}
    connector_ends = [node for node in _walk(connector) if node.get('name') == 'ConnectorEnd']
    if connector_ends:
        inherited = list(ends)
        ends = []
        for index, connector_end in enumerate(connector_ends):
            name = connector_end.get('declaredName')
            role = set(roles.get(name, set())) if name else set()
            if name is None and index < len(inherited):
                name = _end_name(inherited[index][1])
                role = inherited[index][2]
            node = {'name': 'EndFeatureUsage', 'usage': {'declaration': {'declaration': {
                'identification': {'declaredName': name},
                'specialization': connector_end,
            }}}}
            ends.append((element, node, role))
        if inherited and len(connector_ends) != len(inherited):
            issues.append(DerivationIssue('DERIVATION_CONNECTOR_ARITY',
                'Connector bindings do not match the inherited end count.', element))
    return derived, roles, ends, issues


@dataclass
class DerivationIssue:
    code: str
    message: str
    element: object


def extract_derivations(model):
    """Return (original/derived endpoint pairs, structural issues).

    Connections use either standard semantic metadata (including user-defined
    specializations) or explicit standard base typing/subsetting. Invalid and
    ambiguous connections have diagnostics and no projected edges. Definitions
    establish roles; only usages bind requirement endpoints.
    """
    edges, issues, visited = [], [], set()

    def scan(element):
        if id(element) in visited:
            return
        visited.add(id(element))
        grammar = getattr(element, 'grammar', None)
        if type(grammar).__name__ in ('ConnectionUsage', 'ConnectionDefinition'):
            derived, roles, ends, inheritance_issues = _connection_info(element)
            if derived:
                start = len(issues)
                issues.extend(inheritance_issues)
                endpoints = {'original': [], 'derive': []}
                role_counts = {'original': 0, 'derive': 0}
                for owner, end, role in ends:
                    declaration = end['usage']['declaration']['declaration']
                    name = _end_name(end)
                    if len(role) != 1:
                        issues.append(DerivationIssue('DERIVATION_END_ROLE',
                            f'End {name!r} needs one unambiguous original/derive role.', element))
                        continue
                    role_name = next(iter(role))
                    role_counts[role_name] += 1
                    if type(grammar).__name__ == 'ConnectionDefinition':
                        continue
                    refs = list(_references(declaration, 'OwnedReferenceSubsetting'))
                    target = _resolve(owner, refs[0]) if len(refs) == 1 else None
                    if target is None or getattr(target, 'sysml_type', '') != 'requirement' or getattr(target, 'is_definition', False):
                        issues.append(DerivationIssue('DERIVATION_END_TARGET',
                            f'End {name!r} must reference a resolved requirement usage.', element))
                    else:
                        endpoints[role_name].append(target)
                if type(grammar).__name__ == 'ConnectionUsage' and (role_counts['original'] != 1 or not role_counts['derive']):
                    issues.append(DerivationIssue('DERIVATION_CARDINALITY',
                        'A derivation needs exactly one original end and at least one derived end.', element))
                if endpoints['original'] and any(endpoints['original'][0] is target for target in endpoints['derive']):
                    issues.append(DerivationIssue('DERIVATION_SELF',
                        'The original requirement cannot also be derived.', element))
                if len(issues) == start and type(grammar).__name__ == 'ConnectionUsage':
                    for target in endpoints['derive']:
                        pair = (endpoints['original'][0], target)
                        if not any(a is pair[0] and b is pair[1] for a, b in edges):
                            edges.append(pair)
        for child in getattr(element, 'children', []):
            scan(child)
    scan(model)
    return edges, issues


def qualified_name(element):
    parts = []
    while element is not None and type(element).__name__ != 'Model':
        name = getattr(element, 'name', None)
        if name:
            parts.append(name)
        element = getattr(element, 'parent', None)
    return '::'.join(reversed(parts))


@dataclass
class DerivationEvaluation:
    original: object
    derived: object
    result: object  # True / False / None (unknown)


def evaluate_derivations(model, requirement_results=None):
    """Evaluate each implication for supplied requirement results, not a proof.

    Keys are fully qualified requirement names; values must be bool or None.
    Missing values remain unknown. False antecedent or true consequent satisfies
    the implication; true antecedent with false consequent violates it.
    Returns (evaluations, structural issues). No requirement result is inferred
    from satisfy/verify links, an edge, or an unevaluated constraint expression.
    """
    results = requirement_results or {}
    if any(value is not None and type(value) is not bool for value in results.values()):
        raise ValueError('Requirement results must be bool or None.')
    edges, issues = extract_derivations(model)
    evaluations = []
    for original, derived in edges:
        a = results.get(qualified_name(original))
        b = results.get(qualified_name(derived))
        result = True if a is False or b is True else (False if a is True and b is False else None)
        evaluations.append(DerivationEvaluation(original, derived, result))
    return evaluations, issues
