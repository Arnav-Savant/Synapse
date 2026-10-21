"""Domain CRUD plus the vault-folder side effect of saving a domain.

Deleting a domain removes only its settings and derived index rows; the
vault folder and notes on disk are never touched (spec §5.2, §20.7).
"""

import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import ServerConfig
from app.db.models import Domain
from app.repositories import domain_repo
from app.schemas.domains import DomainProfile

logger = logging.getLogger(__name__)


class InvalidDomainError(ValueError):
    """The domain name can't produce a usable slug."""


class VaultFolderError(RuntimeError):
    """The vault folder for a domain could not be created."""


class DomainInUseError(RuntimeError):
    """A queued, running or waiting job still references this domain."""


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise InvalidDomainError(f"domain name {name!r} has no letters or digits to build a folder name from")
    return slug


async def list_domains(session: AsyncSession) -> list[Domain]:
    return await domain_repo.list_domains(session)


async def create_domain(
    session: AsyncSession, config: ServerConfig, *, name: str, purpose: str, profile: DomainProfile
) -> Domain:
    """Creates `$VAULTS_ROOT/<slug>/` (reusing it if present). The returned
    row carries a transient `folder_existed` flag for the API response."""
    name = name.strip()
    slug = slugify(name)
    vault_dir = config.vaults_root / slug
    folder_existed = vault_dir.is_dir()
    try:
        vault_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("domain %r: could not create vault folder %s (%s)", slug, vault_dir, exc.strerror or exc)
        raise VaultFolderError(f"could not create vault folder {str(vault_dir)!r}: {exc.strerror or exc}") from exc

    domain = await domain_repo.create_domain(
        session,
        slug=slug,
        name=name,
        purpose=purpose.strip(),
        vault_path=str(vault_dir.resolve()),
        profile=profile.model_dump(),
    )
    domain.folder_existed = folder_existed
    logger.info(
        "domain %r created, vault %s (%s)",
        slug,
        vault_dir,
        "reused existing folder" if folder_existed else "new folder",
    )
    return domain


async def update_domain(
    session: AsyncSession, slug: str, *, name: str, purpose: str, profile: DomainProfile
) -> Domain:
    """Renaming never moves the folder or changes the slug."""
    domain = await domain_repo.update_domain(
        session, slug, name=name.strip(), purpose=purpose.strip(), profile=profile.model_dump()
    )
    logger.info("domain %r updated (folder unchanged: %s)", slug, domain.vault_path)
    return domain


async def delete_domain(session: AsyncSession, slug: str) -> None:
    await domain_repo.get_by_slug(session, slug)  # 404 before the in-use check
    if await domain_repo.has_active_job(session, slug):
        logger.warning("domain %r delete refused: an active job still uses it", slug)
        raise DomainInUseError(f"domain {slug!r} has an active job; cancel or wait for it first")
    await domain_repo.delete_domain(session, slug)
    logger.info("domain %r deleted; vault files left on disk", slug)
