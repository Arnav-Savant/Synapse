"""Domain routes. Thin: validate via schemas, call the service."""

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_server_config
from app.core.postgres_connection import postgres_connection
from app.agents.profile_builder import draft_profile
from app.engines.factory import build_engine
from app.schemas.domains import (
    CreateDomainRequest,
    DomainListResponse,
    DomainOut,
    DomainProfile,
    ProfileAnswers,
    UpdateDomainRequest,
)
from app.services import domain_service

router = APIRouter()


def _out(domain) -> DomainOut:
    return DomainOut.model_validate(domain, from_attributes=True)


@router.get("/domains", response_model=DomainListResponse)
async def list_domains(session: AsyncSession = Depends(postgres_connection.get_session)) -> DomainListResponse:
    domains = await domain_service.list_domains(session)
    return DomainListResponse(domains=[_out(d) for d in domains])


@router.post("/domains", response_model=DomainOut, status_code=201)
async def create_domain(
    body: CreateDomainRequest, session: AsyncSession = Depends(postgres_connection.get_session)
) -> DomainOut:
    domain = await domain_service.create_domain(
        session, get_server_config(), name=body.name, purpose=body.purpose, profile=body.profile
    )
    return _out(domain)


@router.post("/domains/draft-profile", response_model=DomainProfile)
async def draft_domain_profile(answers: ProfileAnswers) -> DomainProfile:
    """Asks Claude to fill in a profile from the form answers. Saves nothing."""
    result = await draft_profile(build_engine(), job_id=f"profile-{uuid.uuid4().hex[:8]}", answers=answers)
    return result.value


@router.put("/domains/{slug}", response_model=DomainOut)
async def update_domain(
    slug: str, body: UpdateDomainRequest, session: AsyncSession = Depends(postgres_connection.get_session)
) -> DomainOut:
    domain = await domain_service.update_domain(
        session, slug, name=body.name, purpose=body.purpose, profile=body.profile
    )
    return _out(domain)


@router.delete("/domains/{slug}", status_code=204)
async def delete_domain(slug: str, session: AsyncSession = Depends(postgres_connection.get_session)) -> Response:
    await domain_service.delete_domain(session, slug)
    return Response(status_code=204)
