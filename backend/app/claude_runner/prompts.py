"""Task prompt templates for headless Claude Code invocations.

The knowledge repo's own `CLAUDE.md` carries the actual behavior contract
(dedup rules, frontmatter schema, hard rules); these prompts just point at
what changed for this specific run.
"""


def ingestion_prompt(source_relative_path: str) -> str:
    return (
        f"A new or updated source file was added at `source/{source_relative_path}`. "
        "Follow the instructions in CLAUDE.md to update the knowledge base: "
        "read that source file, read the relevant existing knowledge/*.md files, "
        "then create or update the appropriate knowledge/*.md concept files. "
        "When done, summarize which knowledge files you created or updated."
    )
