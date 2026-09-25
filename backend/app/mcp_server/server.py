"""MCP server: role-scoped tool surface for the Text/Graph/Validation
agents, one `SynapseMcpServer` instance per Claude Code CLI invocation.

See `docs/superpowers/specs/2026-09-24-multi-agent-architecture-design.md`
§6.2/§9.3 for the design this implements (per-role tool sets, the
Postgres/Kùzu information-asymmetry, the pending/committed staging model).
Domain exceptions from `concept_repo`/`graph_repo`/`source_record_repo` are
translated to `mcp...exceptions.ToolError` at this layer — that is the only
way their message reaches the calling agent (mcp 2.2.0, confirmed
empirically: a bare exception's message is discarded, the client only sees
"Error executing tool <name>").
"""

import contextlib
import logging
from enum import Enum
from typing import Callable

import kuzu
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from app.core.postgres_connection import postgres_connection
from app.db.kuzu_db import get_kuzu_connection
from app.repositories import concept_repo, graph_repo, source_record_repo

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    TEXT_AGENT = "text_agent"
    GRAPH_AGENT = "graph_agent"
    VALIDATION_AGENT = "validation_agent"


# Exact, closed enumeration — deliberately not a blanket `except ValueError`/
# `except LookupError` (a real bug's ValueError could otherwise get silently
# relabeled as if it were a deliberate business-rule rejection). Anything
# outside this set is a real bug and should stay an uncaught crash (logged
# with a traceback, generic message to the client), not be translated.
_TRANSLATED_EXCEPTIONS = (
    concept_repo.ConceptNotFoundError,
    graph_repo.ConceptNotFoundInGraphError,
    graph_repo.CyclicRelationshipError,
    graph_repo.DuplicateRelationshipError,
    graph_repo.SymmetricRelationshipConflictError,
    graph_repo.RelationshipNotFoundError,
    graph_repo.InvalidGraphInputError,
    source_record_repo.SourceRecordNotFoundError,
)


def _translate(exc: Exception) -> None:
    """Re-raise a known domain exception as ToolError so its message
    reaches the calling agent (only ToolError preserves the message through
    MCPServer's protocol dispatch — confirmed empirically). Never call this
    on an exception outside _TRANSLATED_EXCEPTIONS; let anything else
    propagate as a real crash (logged with traceback server-side)."""
    raise ToolError(str(exc)) from exc


def _concept_to_dict(concept) -> dict:
    return {
        "id": concept.id,
        "title": concept.title,
        "category": concept.category,
        "body": concept.body,
        "metadata": concept.metadata_,
        "status": concept.status,
        "job_id": concept.job_id,
    }


def _concept_metadata_to_dict(metadata: concept_repo.ConceptMetadata) -> dict:
    return {"id": metadata.id, "title": metadata.title, "category": metadata.category}


def _node_to_dict(node: graph_repo.NeighborNode) -> dict:
    return {"id": node.id, "title": node.title, "category": node.category}


def _relationship_to_dict(record: graph_repo.RelationshipRecord) -> dict:
    return {
        "source_id": record.source_id,
        "target_id": record.target_id,
        "type": record.type,
        "note": record.note,
        "justification": record.justification,
        "confidence": record.confidence,
        "status": record.status,
        "job_id": record.job_id,
    }


TOOL_REGISTRY: dict[AgentRole, tuple[str, ...]] = {
    AgentRole.TEXT_AGENT: ("read_source", "search_concepts", "get_concept", "create_concept", "update_concept"),
    AgentRole.GRAPH_AGENT: (
        "get_graph_neighborhood", "search_relationships", "get_concept_metadata",
        "add_relationship", "update_relationship", "remove_relationship",
    ),
    AgentRole.VALIDATION_AGENT: ("get_concept", "get_graph_neighborhood", "search_concepts"),  # no writes, ever
}


class SynapseMcpServer:
    """Owns one MCP server subprocess's lifecycle and its role-scoped tool
    registration. One instance per Claude Code CLI invocation (one per
    agent role per job round) — never shared or reused across rounds."""

    def __init__(self, role: AgentRole, job_id: str, kuzu_conn: kuzu.Connection | None = None) -> None:
        self._role = role
        self._job_id = job_id
        self._kuzu_conn = kuzu_conn or get_kuzu_connection()
        # Wraps the FastAPI-Depends-shaped async-generator dependency as a
        # real async context manager for non-FastAPI callers.
        self._session_factory = contextlib.asynccontextmanager(postgres_connection.get_session)
        self._server = MCPServer(f"synapse-{role.value}")
        self._register_tools()

    def _register_tools(self) -> None:
        for name in TOOL_REGISTRY[self._role]:
            self._server.add_tool(_BUILDERS[name](self), name=name)

    def run_stdio(self) -> None:
        logger.info("MCP server starting: role=%s job=%s", self._role.value, self._job_id)
        try:
            self._server.run(transport="stdio")
        finally:
            self._kuzu_conn.close()
            logger.info("MCP server stopped: role=%s job=%s", self._role.value, self._job_id)


def _build_read_source_tool(server: "SynapseMcpServer") -> Callable:
    async def read_source(source_id: str) -> dict:
        try:
            async with server._session_factory() as session:
                source = await source_record_repo.read_source(session, source_id)
        except _TRANSLATED_EXCEPTIONS as exc:
            _translate(exc)
        return {
            "id": source.id,
            "content": source.content,
            "topic_hint": source.topic_hint,
            "uploaded_at": source.uploaded_at.isoformat(),
        }
    read_source.__name__ = "read_source"
    return read_source


def _build_search_concepts_tool(server: "SynapseMcpServer") -> Callable:
    async def search_concepts(query: str, limit: int = 10) -> dict:
        try:
            async with server._session_factory() as session:
                matches = await concept_repo.search_concepts(session, query, job_id=server._job_id, limit=limit)
        except _TRANSLATED_EXCEPTIONS as exc:
            _translate(exc)
        return {"concepts": [_concept_metadata_to_dict(m) for m in matches]}
    search_concepts.__name__ = "search_concepts"
    return search_concepts


def _build_get_concept_tool(server: "SynapseMcpServer") -> Callable:
    async def get_concept(concept_id: str) -> dict:
        try:
            async with server._session_factory() as session:
                concept = await concept_repo.get_concept(session, concept_id)
        except _TRANSLATED_EXCEPTIONS as exc:
            _translate(exc)
        return _concept_to_dict(concept)
    get_concept.__name__ = "get_concept"
    return get_concept


def _build_create_concept_tool(server: "SynapseMcpServer") -> Callable:
    async def create_concept(title: str, category: str, body: str, metadata: dict) -> dict:
        # job_id is closed over, never an LLM-visible parameter.
        try:
            async with server._session_factory() as session:
                concept = await concept_repo.create_concept(
                    session, title=title, category=category, body=body, metadata=metadata, job_id=server._job_id
                )
        except _TRANSLATED_EXCEPTIONS as exc:
            _translate(exc)
        return _concept_to_dict(concept)
    create_concept.__name__ = "create_concept"
    return create_concept


def _build_update_concept_tool(server: "SynapseMcpServer") -> Callable:
    async def update_concept(concept_id: str, body: str | None = None, metadata: dict | None = None) -> dict:
        try:
            async with server._session_factory() as session:
                concept = await concept_repo.update_concept(
                    session, concept_id=concept_id, job_id=server._job_id, body=body, metadata=metadata
                )
        except _TRANSLATED_EXCEPTIONS as exc:
            _translate(exc)
        return _concept_to_dict(concept)
    update_concept.__name__ = "update_concept"
    return update_concept


def _build_get_graph_neighborhood_tool(server: "SynapseMcpServer") -> Callable:
    def get_graph_neighborhood(concept_id: str, depth: int = 1) -> dict:
        try:
            neighborhood = graph_repo.get_graph_neighborhood(server._kuzu_conn, concept_id, depth)
        except _TRANSLATED_EXCEPTIONS as exc:
            _translate(exc)
        return {
            "center_id": neighborhood.center_id,
            "nodes": [_node_to_dict(n) for n in neighborhood.nodes],
            "edges": [_relationship_to_dict(e) for e in neighborhood.edges],
        }
    get_graph_neighborhood.__name__ = "get_graph_neighborhood"
    return get_graph_neighborhood


def _build_search_relationships_tool(server: "SynapseMcpServer") -> Callable:
    def search_relationships(concept_id: str) -> dict:
        try:
            relationships = graph_repo.search_relationships(server._kuzu_conn, concept_id)
        except _TRANSLATED_EXCEPTIONS as exc:
            _translate(exc)
        return {"relationships": [_relationship_to_dict(r) for r in relationships]}
    search_relationships.__name__ = "search_relationships"
    return search_relationships


def _build_get_concept_metadata_tool(server: "SynapseMcpServer") -> Callable:
    # Cross-store composition point (spec §9.3: Kùzu nodes are "kept in sync
    # only via get_concept_metadata reads") — Postgres read via concept_repo,
    # then a Kùzu upsert via graph_repo.ensure_node, composed here because
    # this is the one layer that legitimately knows about both stores.
    async def get_concept_metadata(concept_id: str) -> dict:
        try:
            async with server._session_factory() as session:
                metadata = await concept_repo.get_concept_metadata(session, concept_id)
        except _TRANSLATED_EXCEPTIONS as exc:
            _translate(exc)
        graph_repo.ensure_node(server._kuzu_conn, metadata.id, metadata.title, metadata.category)
        return {"id": metadata.id, "title": metadata.title, "category": metadata.category}
    get_concept_metadata.__name__ = "get_concept_metadata"
    return get_concept_metadata


def _build_add_relationship_tool(server: "SynapseMcpServer") -> Callable:
    def add_relationship(
        source_id: str, target_id: str, type: str, justification: str,
        note: str = "", confidence: float | None = None,
    ) -> dict:
        # job_id is closed over, never an LLM-visible parameter — confirmed
        # empirically that a closure variable does not appear in the
        # generated tool schema.
        try:
            record = graph_repo.add_relationship(
                server._kuzu_conn, source_id=source_id, target_id=target_id, type=type,
                justification=justification, note=note, confidence=confidence, job_id=server._job_id,
            )
        except _TRANSLATED_EXCEPTIONS as exc:
            _translate(exc)
        return _relationship_to_dict(record)
    add_relationship.__name__ = "add_relationship"
    return add_relationship


def _build_update_relationship_tool(server: "SynapseMcpServer") -> Callable:
    def update_relationship(
        source_id: str, target_id: str, type: str,
        note: str | None = None, justification: str | None = None, confidence: float | None = None,
    ) -> dict:
        try:
            record = graph_repo.update_relationship(
                server._kuzu_conn, source_id=source_id, target_id=target_id, type=type, job_id=server._job_id,
                note=note, justification=justification, confidence=confidence,
            )
        except _TRANSLATED_EXCEPTIONS as exc:
            _translate(exc)
        return _relationship_to_dict(record)
    update_relationship.__name__ = "update_relationship"
    return update_relationship


def _build_remove_relationship_tool(server: "SynapseMcpServer") -> Callable:
    def remove_relationship(source_id: str, target_id: str, type: str) -> dict:
        try:
            graph_repo.remove_relationship(
                server._kuzu_conn, source_id=source_id, target_id=target_id, type=type, job_id=server._job_id
            )
        except _TRANSLATED_EXCEPTIONS as exc:
            _translate(exc)
        return {"source_id": source_id, "target_id": target_id, "type": type, "removed": True}
    remove_relationship.__name__ = "remove_relationship"
    return remove_relationship


_BUILDERS: dict[str, Callable[["SynapseMcpServer"], Callable]] = {
    "read_source": _build_read_source_tool,
    "search_concepts": _build_search_concepts_tool,
    "get_concept": _build_get_concept_tool,
    "create_concept": _build_create_concept_tool,
    "update_concept": _build_update_concept_tool,
    "get_graph_neighborhood": _build_get_graph_neighborhood_tool,
    "search_relationships": _build_search_relationships_tool,
    "get_concept_metadata": _build_get_concept_metadata_tool,
    "add_relationship": _build_add_relationship_tool,
    "update_relationship": _build_update_relationship_tool,
    "remove_relationship": _build_remove_relationship_tool,
}
