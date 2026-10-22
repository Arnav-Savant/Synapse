import type { Ancestor, OutlineNode, OverlapKind, Outline } from "../../api/jobs";

/** Pure edits to an outline. Each returns a new tree and never touches its input. */

function removedWith(tree: Outline, key: string): Set<string> {
  const removed = new Set([key]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const n of tree.nodes) {
      // A node goes with its parents only when every one of them is gone.
      if (!removed.has(n.key) && n.parent_keys.length > 0 && n.parent_keys.every((p) => removed.has(p))) {
        removed.add(n.key);
        grew = true;
      }
    }
  }
  return removed;
}

/** Removes a node and its subtree. The root cannot be dropped: that would be an empty outline. */
export function dropNode(tree: Outline, key: string): Outline {
  const target = tree.nodes.find((n) => n.key === key);
  if (!target || target.parent_keys.length === 0) return tree;
  const removed = removedWith(tree, key);
  return {
    ...tree,
    nodes: tree.nodes
      .filter((n) => !removed.has(n.key))
      .map((n) => ({ ...n, parent_keys: n.parent_keys.filter((p) => !removed.has(p)) })),
  };
}

function nextKey(tree: Outline): string {
  const taken = new Set(tree.nodes.map((n) => n.key));
  let i = 1;
  while (taken.has(`u${i}`)) i += 1;
  return `u${i}`;
}

/** A new subtopic under `parentKey`. It starts with the parent's domains and no overlap verdict. */
export function addChild(tree: Outline, parentKey: string, title: string): Outline {
  const parent = tree.nodes.find((n) => n.key === parentKey);
  const clean = title.trim();
  if (!parent || !clean) return tree;
  const node: OutlineNode = {
    key: nextKey(tree),
    title: clean,
    summary: "",
    parent_keys: [parentKey],
    domains: [...parent.domains],
    content_slice: null,
    verdicts: {},
    hub: false,
    reuse: false,
  };
  return { ...tree, nodes: [...tree.nodes, node] };
}

/** Turns a domain on or off for one node. A node always keeps at least one domain. */
export function toggleDomain(tree: Outline, key: string, slug: string): Outline {
  return {
    ...tree,
    nodes: tree.nodes.map((n) => {
      if (n.key !== key) return n;
      if (n.domains.includes(slug)) return n.domains.length > 1 ? { ...n, domains: n.domains.filter((d) => d !== slug) } : n;
      return { ...n, domains: [...n.domains, slug] };
    }),
  };
}

/** Overrides the overlap verdict for one node in one domain. The existing note it points at is kept, so the choice can be undone. */
export function setVerdict(tree: Outline, key: string, slug: string, kind: OverlapKind): Outline {
  return {
    ...tree,
    nodes: tree.nodes.map((n) => {
      if (n.key !== key) return n;
      const current = n.verdicts[slug];
      return {
        ...n,
        verdicts: { ...n.verdicts, [slug]: { kind, target_note_id: current?.target_note_id ?? null, reason: "Chosen by you" } },
      };
    }),
  };
}

/** Applies the owner's unticked nodes before the tree is sent. */
export function applyExclusions(tree: Outline, excluded: ReadonlySet<string>): Outline {
  return [...excluded].reduce((t, key) => dropNode(t, key), tree);
}

/** For display: children listed under the first parent, in outline order. */
export function childrenByParent(tree: Outline): Map<string | null, OutlineNode[]> {
  const map = new Map<string | null, OutlineNode[]>();
  for (const n of tree.nodes) {
    const parent = n.parent_keys[0] ?? null;
    map.set(parent, [...(map.get(parent) ?? []), n]);
  }
  return map;
}

/** Keys of a node and everything beneath it (by display parent), used to dim an unticked subtree. */
export function subtreeKeys(tree: Outline, key: string): Set<string> {
  const children = childrenByParent(tree);
  const out = new Set<string>();
  const walk = (k: string) => {
    out.add(k);
    for (const c of children.get(k) ?? []) walk(c.key);
  };
  walk(key);
  return out;
}

/** Replaces the hub path above the topic for one domain. Attached notes need a hub, so they are cleared with the last one. */
export function setAncestors(tree: Outline, slug: string, ancestors: Ancestor[]): Outline {
  return {
    ...tree,
    ancestors: { ...tree.ancestors, [slug]: ancestors },
    adopt: ancestors.length === 0 ? { ...tree.adopt, [slug]: [] } : tree.adopt,
  };
}

/** Ticks or unticks an existing top-level note to be attached under the innermost hub. */
export function toggleAdopt(tree: Outline, slug: string, noteId: string): Outline {
  const current = tree.adopt[slug] ?? [];
  const next = current.includes(noteId) ? current.filter((id) => id !== noteId) : [...current, noteId];
  return { ...tree, adopt: { ...tree.adopt, [slug]: next } };
}
