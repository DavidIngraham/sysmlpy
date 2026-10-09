"""Requirement-derivation library relationships, independent of diagram layout.

Resolve explicit library metadata and named inherited end roles. This is not a
general semantic-metadata evaluator: user-defined metadata specializations and
evaluation of the library's logical implication constraint remain out of scope.
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


def _member(scope, name, seen, exported=False):
    if isinstance(scope, str):
        return ('RequirementDerivation::' + _METADATA[name]) if scope == 'RequirementDerivation' and name in _METADATA else None
    key = (id(scope), name, exported)
    if key in seen:
        return None
    seen = seen | {key}
    matches = [c for c in getattr(scope, 'children', [])
               if name in (getattr(c, 'name', None), getattr(c, 'shortname', None))]
    if matches:
        return matches[0] if len(matches) == 1 else None
    for declaration in _imports(scope):
        if type(declaration).__name__ == 'AliasMember':
            if name in (declaration.memberName, declaration.memberShortName):
                return _resolve(scope, declaration.memberElement.names, seen)
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
            if hit is not None and all(hit is not c and hit != c for c in candidates):
                candidates.append(hit)
    return candidates[0] if len(candidates) == 1 else None


def _resolve(scope, names, seen=frozenset()):
    if not names:
        return None
    # Library symbols are symbolic identities, not fabricated model elements.
    while scope is not None:
        if isinstance(scope, str):
            break
        hit = _member(scope, names[0], seen)
        if hit is not None:
            for name in names[1:]:
                hit = _member(hit, name, seen, exported=True)
                if hit is None:
                    return None
            return hit
        scope = getattr(scope, 'parent', None)
    if names[0] == 'RequirementDerivation':
        if len(names) == 1:
            return 'RequirementDerivation'
        if len(names) == 2 and names[1] in _METADATA:
            return 'RequirementDerivation::' + _METADATA[names[1]]
    return None


def _tags(element, keywords):
    tags = set()
    for keyword in keywords:
        text = keyword if isinstance(keyword, str) else keyword.get('keyword', '')
        text = ''.join(text.split())
        if not text.startswith('#'):
            continue
        symbol = _resolve(element, text[1:].split('::'))
        if isinstance(symbol, str) and symbol.startswith('RequirementDerivation::'):
            tags.add(symbol.split('::')[-1])
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


def _roles(element, active=frozenset()):
    if id(element) in active:
        return False, {}
    active = active | {id(element)}
    grammar = element.grammar.get_definition()
    prefix = grammar.get('prefix') or {}
    is_derivation = 'derivation' in _tags(element, prefix.get('usageExtension', prefix.get('keyword', [])))
    roles = {}
    names = [getattr(element, 'typed_by_name', None)]
    names += list(getattr(element, '_specializes_names', []))
    for name in names:
        base = _resolve(getattr(element, 'parent', None), name.split('::')) if name else None
        if base is not None and getattr(base, 'sysml_type', None) == 'connection':
            inherited_derivation, inherited_roles = _roles(base, active)
            is_derivation |= inherited_derivation
            roles.update(inherited_roles)
    for end in _ends(element):
        declaration = end['usage']['declaration']['declaration']
        name = (declaration.get('identification') or {}).get('declaredName')
        tags = _tags(element, end.get('extensions', [])) & {'original', 'derive'}
        if tags:
            roles[name] = tags
        else:
            for redefined in _references(declaration, 'OwnedRedefinition'):
                if redefined and redefined[-1] in roles:
                    roles[name] = roles[redefined[-1]]
    return is_derivation, roles


@dataclass
class DerivationIssue:
    code: str
    message: str
    element: object


def extract_derivations(model):
    """Return (original/derived endpoint pairs, issues) for connection usages.

    Invalid or unresolved connections emit diagnostics and no misleading edges.
    Multiple derived roles bound to the same requirement produce one view edge.
    """
    edges, issues, visited = [], [], set()
    def scan(element):
        if id(element) in visited:
            return
        visited.add(id(element))
        if type(getattr(element, 'grammar', None)).__name__ == 'ConnectionUsage':
            derived, roles = _roles(element)
            if derived:
                start = len(issues)
                endpoints = {'original': [], 'derive': []}
                for end in _ends(element):
                    declaration = end['usage']['declaration']['declaration']
                    name = (declaration.get('identification') or {}).get('declaredName')
                    role = roles.get(name, set())
                    refs = list(_references(declaration, 'OwnedReferenceSubsetting'))
                    target = _resolve(element.parent, refs[0]) if len(refs) == 1 else None
                    if len(role) != 1:
                        issues.append(DerivationIssue('DERIVATION_END_ROLE', f'End {name!r} needs one original/derive role.', element))
                    elif target is None or getattr(target, 'sysml_type', '') != 'requirement' or getattr(target, 'is_definition', False):
                        issues.append(DerivationIssue('DERIVATION_END_TARGET', f'End {name!r} must reference a resolved requirement usage.', element))
                    else:
                        endpoints[next(iter(role))].append(target)
                if len(endpoints['original']) != 1 or not endpoints['derive']:
                    issues.append(DerivationIssue('DERIVATION_CARDINALITY', 'A derivation needs exactly one original end and at least one derived end.', element))
                elif any(endpoints['original'][0] is target for target in endpoints['derive']):
                    issues.append(DerivationIssue('DERIVATION_SELF', 'The original requirement cannot also be derived.', element))
                if len(issues) == start:
                    for target in endpoints['derive']:
                        pair = (endpoints['original'][0], target)
                        if not any(a is pair[0] and b is pair[1] for a, b in edges):
                            edges.append(pair)
        for child in getattr(element, 'children', []):
            scan(child)
    scan(model)
    return edges, issues
