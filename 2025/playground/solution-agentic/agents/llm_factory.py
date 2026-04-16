"""
LLM Factory — crea istanze ChatOpenAI (OpenRouter) con Langfuse callback integrato.

Differenza rispetto a OpenRouterClient:
- Restituisce un ChatOpenAI nativo LangChain, compatibile con bind_tools() e create_react_agent()
- Il Langfuse tracking avviene tramite CallbackHandler passato direttamente al modello
- Supporta model overriding per agent specializzati
"""

from __future__ import annotations

import os

import ulid
from langchain_openai import ChatOpenAI
from langfuse.langchain import CallbackHandler


def generate_session_id() -> str:
    """Genera un session ID univoco nel formato team-ULID."""
    team = os.getenv("TEAM_NAME", "reply")
    return f"{team}-{ulid.new().str}"


def build_llm(
    session_id: str,
    agent_name: str = "agent",
    temperature: float = 0.0,
    max_tokens: int = 1024,
    model: str | None = None,
) -> ChatOpenAI:
    """
    Crea un ChatOpenAI che punta a OpenRouter, con Langfuse CallbackHandler attivo.

    Parameters
    ----------
    session_id  : session ID condiviso da tutti gli agenti della stessa run
    agent_name  : etichetta per il tracciamento Langfuse (es. "citizen_analyst", "supervisor")
    temperature : 0 = deterministico, >0 = creativo
    max_tokens  : token massimi per la risposta
    model       : override del modello (default: usa OPENROUTER_MODEL da .env)
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENROUTER_API_KEY non impostata nel file .env")

    langfuse_pk = os.getenv("LANGFUSE_PUBLIC_KEY")
    langfuse_sk = os.getenv("LANGFUSE_SECRET_KEY")
    if not langfuse_pk or not langfuse_sk:
        raise EnvironmentError(
            "LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY non impostate nel file .env"
        )

    # Langfuse v4 CallbackHandler accetta solo public_key e trace_context.
    # Secret key/host vengono letti dalla configurazione ambiente (LANGFUSE_*).
    langfuse_handler = CallbackHandler(
        public_key=langfuse_pk,
    )

    selected_model = model or os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

    return ChatOpenAI(
        api_key=api_key,
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        model=selected_model,
        temperature=temperature,
        max_tokens=max_tokens,
        default_headers={
            "HTTP-Referer": "https://github.com/lucaerba/ReplyChallenges",
            "X-Title": "Reply Mirror Challenge - Agentic",
        },
        timeout=int(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "60")),
        max_retries=int(os.getenv("OPENROUTER_MAX_RETRIES", "2")),
        callbacks=[langfuse_handler],
    )
