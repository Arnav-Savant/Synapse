from functools import lru_cache
from pathlib import Path

import kuzu

_SCHEMA_STATEMENTS = [
    "CREATE NODE TABLE IF NOT EXISTS Concept(id STRING PRIMARY KEY, title STRING, category STRING)",
    (
        "CREATE REL TABLE IF NOT EXISTS RELATES_TO(FROM Concept TO Concept, "
        "type STRING, note STRING, justification STRING, confidence DOUBLE, "
        "status STRING, job_id STRING, created_at TIMESTAMP)"
    ),
]

HIERARCHY_MAX_DEPTH = 10_000
# Kùzu's variable-length path queries silently cap at 30 hops otherwise,
# which would cause false-negative cycle detection in the hierarchical-type
# acyclicity check (see app/repositories/graph_repo.py, added in a later
# task). Confirmed empirically against the installed kuzu version.


@lru_cache
def get_kuzu_connection(db_path: Path | None = None) -> kuzu.Connection:
    from app.core.config import get_server_config

    path = db_path or get_server_config().kuzu_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    db = kuzu.Database(str(path))
    conn = kuzu.Connection(db)
    for statement in _SCHEMA_STATEMENTS:
        conn.execute(statement)
    conn.execute(f"CALL var_length_extend_max_depth={HIERARCHY_MAX_DEPTH}")
    return conn
