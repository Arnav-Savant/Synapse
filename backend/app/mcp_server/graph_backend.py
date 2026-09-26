"""Kùzu access abstraction for `SynapseMcpServer`.

Kùzu is single-process-exclusive: only one OS process may ever hold the
database file open. The main backend process holds one long-lived
connection for its whole life (`app.db.kuzu_db.get_kuzu_connection`), but
every real agent invocation runs the MCP server in a *separate* OS
subprocess (`app/mcp_server/entrypoint.py`) — a second `kuzu.Connection`
from that subprocess onto the same file crashes immediately.

`GraphBackend` is the seam that lets `SynapseMcpServer` stop caring which
process actually owns the Kùzu handle:

- `LocalGraphBackend` wraps an already-open `kuzu.Connection` (used by
  tests, which construct `SynapseMcpServer` in-process with an explicit
  `kuzu_conn`) and calls straight into `graph_repo`.
- `RemoteGraphBackend` is what the real subprocess uses instead: it never
  opens Kùzu itself, and instead calls the main backend process (which
  already holds the one legitimate connection) over loopback HTTP, via the
  six `/internal/graph/*` routes in `app/api/internal_graph.py`.

Exactly the six `graph_repo` operations `mcp_server/server.py`'s tool
builders touch are exposed here — see
`docs/superpowers/specs/2026-09-24-multi-agent-architecture-design.md`
§10.1 for why this is a small set of typed methods, not a generic
Cypher-proxy `Protocol`.
"""

from typing import Protocol

import httpx
import kuzu

from app.repositories import graph_repo
from app.repositories.graph_repo import GraphNeighborhood, RelationshipRecord

_ERROR_TYPES: tuple[type[Exception], ...] = (
    graph_repo.ConceptNotFoundInGraphError,
    graph_repo.CyclicRelationshipError,
    graph_repo.DuplicateRelationshipError,
    graph_repo.SymmetricRelationshipConflictError,
    graph_repo.RelationshipNotFoundError,
    graph_repo.InvalidGraphInputError,
)
_ERROR_TYPES_BY_NAME: dict[str, type[Exception]] = {exc.__name__: exc for exc in _ERROR_TYPES}


class GraphBackend(Protocol):
    """Same six-operation surface as `graph_repo`, minus the `conn`
    argument — implementations own how (or whether) they hold one."""

    def get_graph_neighborhood(
        self, concept_id: str, depth: int = 1, job_id: str | None = None
    ) -> GraphNeighborhood: ...

    def search_relationships(self, concept_id: str, job_id: str | None = None) -> list[RelationshipRecord]: ...

    def ensure_node(self, concept_id: str, title: str, category: str) -> None: ...

    def add_relationship(
        self,
        *,
        source_id: str,
        target_id: str,
        type: str,  # noqa: A002 — matches graph_repo's agent-facing parameter name
        justification: str,
        note: str = "",
        confidence: float | None = None,
        job_id: str,
    ) -> RelationshipRecord: ...

    def update_relationship(
        self,
        *,
        source_id: str,
        target_id: str,
        type: str,  # noqa: A002
        job_id: str,
        note: str | None = None,
        justification: str | None = None,
        confidence: float | None = None,
    ) -> RelationshipRecord: ...

    def remove_relationship(self, *, source_id: str, target_id: str, type: str, job_id: str) -> None: ...  # noqa: A002

    def close(self) -> None: ...


class LocalGraphBackend:
    """In-process delegation straight to `graph_repo`, over an already-open
    `kuzu.Connection` — exactly what `mcp_server/server.py`'s tool builders
    used to do inline. Used when a `kuzu_conn` is explicitly handed to
    `SynapseMcpServer` (today: only tests, which run in-process and don't
    hit the multi-process exclusivity problem at all)."""

    def __init__(self, kuzu_conn: kuzu.Connection) -> None:
        self._kuzu_conn = kuzu_conn

    def get_graph_neighborhood(
        self, concept_id: str, depth: int = 1, job_id: str | None = None
    ) -> GraphNeighborhood:
        return graph_repo.get_graph_neighborhood(self._kuzu_conn, concept_id, depth, job_id=job_id)

    def search_relationships(self, concept_id: str, job_id: str | None = None) -> list[RelationshipRecord]:
        return graph_repo.search_relationships(self._kuzu_conn, concept_id, job_id=job_id)

    def ensure_node(self, concept_id: str, title: str, category: str) -> None:
        graph_repo.ensure_node(self._kuzu_conn, concept_id, title, category)

    def add_relationship(
        self, *, source_id: str, target_id: str, type: str, justification: str,  # noqa: A002
        note: str = "", confidence: float | None = None, job_id: str,
    ) -> RelationshipRecord:
        return graph_repo.add_relationship(
            self._kuzu_conn, source_id=source_id, target_id=target_id, type=type,
            justification=justification, note=note, confidence=confidence, job_id=job_id,
        )

    def update_relationship(
        self, *, source_id: str, target_id: str, type: str, job_id: str,  # noqa: A002
        note: str | None = None, justification: str | None = None, confidence: float | None = None,
    ) -> RelationshipRecord:
        return graph_repo.update_relationship(
            self._kuzu_conn, source_id=source_id, target_id=target_id, type=type, job_id=job_id,
            note=note, justification=justification, confidence=confidence,
        )

    def remove_relationship(self, *, source_id: str, target_id: str, type: str, job_id: str) -> None:  # noqa: A002
        graph_repo.remove_relationship(
            self._kuzu_conn, source_id=source_id, target_id=target_id, type=type, job_id=job_id
        )

    def close(self) -> None:
        pass


def _node_from_json(data: dict) -> graph_repo.NeighborNode:
    return graph_repo.NeighborNode(id=data["id"], title=data["title"], category=data["category"])


def _relationship_from_json(data: dict) -> RelationshipRecord:
    return RelationshipRecord(
        source_id=data["source_id"],
        target_id=data["target_id"],
        type=data["type"],
        note=data["note"],
        justification=data["justification"],
        confidence=data["confidence"],
        status=data["status"],
        job_id=data["job_id"],
    )


def _raise_for_error_response(response: httpx.Response) -> None:
    """Reconstructs the exact same domain exception `graph_repo` would have
    raised in-process, from the `error`/`detail` body the six `main.py`
    exception handlers attach to a failed `/internal/graph/*` response (see
    `main.py`'s handlers for `_ERROR_TYPES`) — so nothing above this
    boundary can tell local from remote."""
    body = response.json()
    error_name = body.get("error")
    exc_type = _ERROR_TYPES_BY_NAME.get(error_name)
    if exc_type is None:
        response.raise_for_status()
        raise httpx.HTTPStatusError(
            f"unrecognized internal graph error response: {body!r}", request=response.request, response=response
        )
    raise exc_type(body.get("detail", ""))


class RemoteGraphBackend:
    """Loopback-HTTP delegation to the main backend's already-running
    process (see `app/api/internal_graph.py`), used by the real MCP server
    subprocess — the only process ever allowed to hold the actual Kùzu
    connection. Synchronous `httpx.Client`: every tool builder that touches
    these six operations is a plain (non-async) function."""

    def __init__(self, base_url: str) -> None:
        self._client = httpx.Client(base_url=base_url)

    def get_graph_neighborhood(
        self, concept_id: str, depth: int = 1, job_id: str | None = None
    ) -> GraphNeighborhood:
        # `job_id` is only included when not None: httpx serializes a `None`
        # dict value as an empty-string query param rather than omitting it,
        # which would reach FastAPI as job_id="" (a real, if harmless, value)
        # instead of the omitted-param default `graph_repo` expects to
        # trigger its committed-only NULL-comparison behavior.
        params: dict[str, str | int] = {"depth": depth}
        if job_id is not None:
            params["job_id"] = job_id
        response = self._client.get(f"/internal/graph/neighborhood/{concept_id}", params=params)
        if response.is_error:
            _raise_for_error_response(response)
        data = response.json()
        return GraphNeighborhood(
            center_id=data["center_id"],
            nodes=[_node_from_json(n) for n in data["nodes"]],
            edges=[_relationship_from_json(e) for e in data["edges"]],
        )

    def search_relationships(self, concept_id: str, job_id: str | None = None) -> list[RelationshipRecord]:
        params = {"job_id": job_id} if job_id is not None else {}
        response = self._client.get(f"/internal/graph/relationships/{concept_id}", params=params)
        if response.is_error:
            _raise_for_error_response(response)
        return [_relationship_from_json(r) for r in response.json()["relationships"]]

    def ensure_node(self, concept_id: str, title: str, category: str) -> None:
        response = self._client.post(
            "/internal/graph/nodes", json={"id": concept_id, "title": title, "category": category}
        )
        if response.is_error:
            _raise_for_error_response(response)

    def add_relationship(
        self, *, source_id: str, target_id: str, type: str, justification: str,  # noqa: A002
        note: str = "", confidence: float | None = None, job_id: str,
    ) -> RelationshipRecord:
        response = self._client.post(
            "/internal/graph/relationships",
            json={
                "source_id": source_id, "target_id": target_id, "type": type,
                "justification": justification, "note": note, "confidence": confidence, "job_id": job_id,
            },
        )
        if response.is_error:
            _raise_for_error_response(response)
        return _relationship_from_json(response.json())

    def update_relationship(
        self, *, source_id: str, target_id: str, type: str, job_id: str,  # noqa: A002
        note: str | None = None, justification: str | None = None, confidence: float | None = None,
    ) -> RelationshipRecord:
        response = self._client.patch(
            "/internal/graph/relationships",
            json={
                "source_id": source_id, "target_id": target_id, "type": type, "job_id": job_id,
                "note": note, "justification": justification, "confidence": confidence,
            },
        )
        if response.is_error:
            _raise_for_error_response(response)
        return _relationship_from_json(response.json())

    def remove_relationship(self, *, source_id: str, target_id: str, type: str, job_id: str) -> None:  # noqa: A002
        response = self._client.request(
            "DELETE",
            "/internal/graph/relationships",
            json={"source_id": source_id, "target_id": target_id, "type": type, "job_id": job_id},
        )
        if response.is_error:
            _raise_for_error_response(response)

    def close(self) -> None:
        self._client.close()
