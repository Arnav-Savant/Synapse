"""Task prompt templates for headless Claude Code invocations.

The knowledge repo's own `CLAUDE.md` carries the actual behavior contract
(dedup rules, frontmatter schema, hard rules); these prompts just point at
what changed for this specific run.
"""


def ingestion_prompt(source_relative_path: str) -> str:
    return (
        f"A new or updated source file was added at `source/{source_relative_path}`. "
        "It may be raw and unstructured. Follow CLAUDE.md's process in full: read "
        "the source, survey the existing knowledge base broadly (not just the "
        "obviously-related files), create or update the appropriate knowledge/*.md "
        "concept files with real synthesized study notes, and — this is often the "
        "step that gets shortchanged — add every relationship to another concept "
        "that's actually justified by this material, for both new and existing "
        "concepts you touch. When done, summarize which knowledge files you created "
        "or updated and which relationships you added."
    )


def chat_prompt(message: str, concept_slug: str | None) -> str:
    context = f" The user is currently looking at the '{concept_slug}' concept." if concept_slug else ""
    return (
        "Answer the following question using only the knowledge base in this "
        f"repository (knowledge/*.md) as your source of truth. Be concise.{context} "
        f"Question: {message}"
    )
