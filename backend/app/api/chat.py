"""Chat route. Thin: validate via schemas, call the service."""

import contextlib

from fastapi import APIRouter

from app.core.postgres_connection import postgres_connection
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import chat_service

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    session_factory = contextlib.asynccontextmanager(postgres_connection.get_session)
    reply = await chat_service.ask(session_factory, body.message, body.concept_id)
    return ChatResponse(reply=reply)
