"""Ancestors and descendants of a note, from a map of title key -> the title keys of its parents."""

ParentMap = dict[str, set[str]]


def ancestors(key: str, parents: ParentMap) -> set[str]:
    """Every note above `key`, at any depth. Safe on a malformed map that contains a cycle."""
    found: set[str] = set()
    pending = list(parents.get(key, ()))
    while pending:
        current = pending.pop()
        if current in found or current == key:
            continue
        found.add(current)
        pending.extend(parents.get(current, ()))
    return found


def descendants(key: str, parents: ParentMap) -> set[str]:
    """Every note below `key`, at any depth."""
    children: dict[str, set[str]] = {}
    for child, above in parents.items():
        for p in above:
            children.setdefault(p, set()).add(child)
    found: set[str] = set()
    pending = list(children.get(key, ()))
    while pending:
        current = pending.pop()
        if current in found or current == key:
            continue
        found.add(current)
        pending.extend(children.get(current, ()))
    return found


def family(key: str, parents: ParentMap) -> set[str]:
    """What the hierarchy already links `key` to: its ancestors and its descendants."""
    return ancestors(key, parents) | descendants(key, parents)
