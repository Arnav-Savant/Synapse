"""Chat routes. Thin: validate via schemas, call the service."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.postgres_connection import postgres_connection
from app.schemas.chats import (
    AskRequest,
    ChatDetailOut,
    ChatListResponse,
    ChatSummaryOut,
    CreateChatRequest,
    MessageOut,
)
from app.services import chat_service

router = APIRouter()


@router.get("/chats", response_model=ChatListResponse)
async def list_chats(session: AsyncSession = Depends(postgres_connection.get_session)) -> ChatListResponse:
    return ChatListResponse(chats=await chat_service.list_chats(session))


@router.post("/chats", response_model=ChatSummaryOut, status_code=201)
async def create_chat(
    body: CreateChatRequest, session: AsyncSession = Depends(postgres_connection.get_session)
) -> ChatSummaryOut:
    return await chat_service.create_chat(session, body.domain_slugs)


@router.get("/chats/{chat_id}", response_model=ChatDetailOut)
async def get_chat(chat_id: str, session: AsyncSession = Depends(postgres_connection.get_session)) -> ChatDetailOut:
    return await chat_service.get_chat(session, chat_id)


@router.delete("/chats/{chat_id}", status_code=204)
async def delete_chat(chat_id: str, session: AsyncSession = Depends(postgres_connection.get_session)) -> Response:
    await chat_service.delete_chat(session, chat_id)
    return Response(status_code=204)


@router.post("/chats/{chat_id}/messages", response_model=MessageOut, status_code=202)
async def ask(
    chat_id: str, body: AskRequest, session: AsyncSession = Depends(postgres_connection.get_session)
) -> MessageOut:
    return await chat_service.ask(session, chat_id, body.text)
