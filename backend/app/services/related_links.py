"""Rules that keep `## Related` sparse once the linker has chosen: link a cluster once, and write a pair on one note only.

Pure functions over title keys; the services do the reading and writing.
"""

from app.agents.linker import RelatedLink
from app.vault.hierarchy import ParentMap
from app.vault.titles import title_key


def collapse_to_parents(
    links: list[RelatedLink], tree: ParentMap, implied: set[str], own_key: str, titles: dict[str, str]
) -> list[RelatedLink]:
    """When two or more chosen notes share a parent that sits outside this note's own family, link that parent once
    instead of each of them. A parent with no known title is left out of this, and the links stay as they were."""
    by_parent: dict[str, list[RelatedLink]] = {}
    for link in links:
        for parent in sorted(tree.get(title_key(link.title), ())):
            if parent != own_key and parent not in implied and parent in titles:
                by_parent.setdefault(parent, []).append(link)
                break
    clusters = {p: members for p, members in by_parent.items() if len(members) >= 2}
    if not clusters:
        return links
    collapsed: set[int] = set()
    out: list[RelatedLink] = []
    for parent, members in clusters.items():
        collapsed.update(id(m) for m in members)
        kind = "prerequisite" if any(m.kind == "prerequisite" for m in members) else "contrast"
        names = ", ".join(m.title for m in members)
        out.append(RelatedLink(title=titles[parent], kind=kind, why=f"Several of its notes matter here ({names}), so read the group from its parent."))
    return [*[l for l in links if id(l) not in collapsed], *out]


def pair_losers(entries: dict[str, list[tuple[str, str]]]) -> dict[str, set[str]]:
    """`entries` maps a note's title key to its Related (target title, note) lines. When two notes list each other,
    the pair stays on one of them: the one whose entry is a prerequisite, else the alphabetically first title.
    Returns, per note, the target keys to remove."""
    listed = {note: {title_key(t): n for t, n in lines} for note, lines in entries.items()}
    losers: dict[str, set[str]] = {}
    for a, targets in listed.items():
        for b, note_a in targets.items():
            note_b = listed.get(b, {}).get(a)
            if note_b is None or a >= b:  # visit each pair once
                continue
            rank_a = 0 if note_a.lower().startswith("prerequisite") else 1
            rank_b = 0 if note_b.lower().startswith("prerequisite") else 1
            drop_on = b if (rank_a, a) <= (rank_b, b) else a
            keep_on = a if drop_on == b else b
            losers.setdefault(drop_on, set()).add(keep_on)
    return losers
