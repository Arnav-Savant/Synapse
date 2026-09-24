from collections.abc import AsyncIterator
from functools import cached_property

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import ServerConfig, get_server_config


class PostgresConnection:
    def __init__(self, config: ServerConfig) -> None:
        self._config = config

    @cached_property
    def _engine(self) -> AsyncEngine:
        return create_async_engine(self._config.database_url, echo=False)

    def get_engine(self) -> AsyncEngine:
        return self._engine

    async def get_session(self) -> AsyncIterator[AsyncSession]:
        session_factory = async_sessionmaker(bind=self.get_engine(), expire_on_commit=False)
        async with session_factory() as session:
            yield session


postgres_connection = PostgresConnection(get_server_config())
