import { useState } from "react";

import type { TopicTreeNode } from "./topicTree";

interface TopicTreeProps {
  nodes: TopicTreeNode[];
  selectedSlug: string | null;
  onSelect: (slug: string) => void;
  depth?: number;
}

export function TopicTree({ nodes, selectedSlug, onSelect, depth = 0 }: TopicTreeProps) {
  return (
    <ul className={depth > 0 ? "ml-2.5 border-l border-ink-line pl-2.5" : "space-y-0.5"}>
      {nodes.map((node) => (
        <TopicTreeItem key={node.id} node={node} selectedSlug={selectedSlug} onSelect={onSelect} depth={depth} />
      ))}
    </ul>
  );
}

function TopicTreeItem({
  node,
  selectedSlug,
  onSelect,
  depth,
}: {
  node: TopicTreeNode;
  selectedSlug: string | null;
  onSelect: (slug: string) => void;
  depth: number;
}) {
  const [expanded, setExpanded] = useState(depth < 1);
  const hasChildren = node.children.length > 0;

  return (
    <li>
      <div className="flex items-center gap-1">
        {hasChildren ? (
          <button
            onClick={() => setExpanded((e) => !e)}
            className="w-3 shrink-0 text-graphite hover:text-paper"
            aria-label={expanded ? "collapse" : "expand"}
          >
            {expanded ? "−" : "+"}
          </button>
        ) : (
          <span className="w-3 shrink-0" />
        )}
        <button
          onClick={() => onSelect(node.id)}
          className={`truncate py-1 text-left ${
            selectedSlug === node.id ? "text-spark" : "text-graphite hover:text-paper"
          }`}
        >
          {node.title}
        </button>
      </div>
      {hasChildren && expanded && (
        <TopicTree nodes={node.children} selectedSlug={selectedSlug} onSelect={onSelect} depth={depth + 1} />
      )}
    </li>
  );
}
