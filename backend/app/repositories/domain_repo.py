"""Domain repository: async Postgres reads/writes for `domains` rows.

Stateless functions taking an explicit `AsyncSession`. Each write commits
immediately, matching the other repositories.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Domain, Job

logger = logging.getLogger(__name__)

ACTIVE_JOB_STATUSES = ("queued", "running", "awaiting_owner")


class DomainNotFoundError(LookupError):
    """No Domain row exists for the given slug."""


class DomainExistsError(ValueError):
    """A Domain with this slug already exists."""


async def get_by_slug(session: AsyncSession, slug: str) -> Domain:
    result = await session.execute(select(Domain).where(Domain.slug == slug))
    domain = result.scalars().first()
    if domain is None:
        raise DomainNotFoundError(f"no domain with slug {slug!r}")
    return domain


async def list_domains(session: AsyncSession) -> list[Domain]:
    result = await session.execute(select(Domain).order_by(Domain.name))
    return list(result.scalars().all())


async def count_domains(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(Domain))
    return result.scalar_one()


async def create_domain(
    session: AsyncSession, *, slug: str, name: str, purpose: str, vault_path: str, profile: dict
) -> Domain:
    existing = await session.execute(select(Domain.id).where(Domain.slug == slug))
    if existing.first() is not None:
        raise DomainExistsError(f"a domain with slug {slug!r} already exists")
    domain = Domain(slug=slug, name=name, purpose=purpose, vault_path=vault_path, profile=profile)
    session.add(domain)
    try:
        await session.commit()
    except IntegrityError as exc:  # lost a race with a concurrent create of the same slug
        await session.rollback()
        raise DomainExistsError(f"a domain with slug {slug!r} already exists") from exc
    logger.debug("domain row created: slug=%s", slug)
    return domain


async def update_domain(session: AsyncSession, slug: str, *, name: str, purpose: str, profile: dict) -> Domain:
    domain = await get_by_slug(session, slug)
    domain.name = name
    domain.purpose = purpose
    domain.profile = profile
    await session.commit()
    logger.debug("domain row updated: slug=%s", slug)
    return domain


async def has_active_job(session: AsyncSession, slug: str) -> bool:
    """True if any non-terminal job chose or resolved to this domain."""
    result = await session.execute(
        select(Job.id)
        .where(Job.status.in_(ACTIVE_JOB_STATUSES))
        .where((Job.domain_choice == slug) | Job.resolved_domains.contains([slug]))
        .limit(1)
    )
    return result.first() is not None


async def delete_domain(session: AsyncSession, slug: str) -> None:
    """Deletes the row. `notes`, `note_links` and `note_drafts` rows go with it
    through ON DELETE CASCADE; vault files are never touched."""
    domain = await get_by_slug(session, slug)
    await session.delete(domain)
    await session.commit()
    logger.debug("domain row deleted: slug=%s", slug)


async def get_by_id(session: AsyncSession, domain_id: str) -> Domain:
    domain = await session.get(Domain, domain_id)
    if domain is None:
        raise DomainNotFoundError(f"no domain with id {domain_id!r}")
    return domain
