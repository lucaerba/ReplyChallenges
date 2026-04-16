"""
LLM Factory — istanze ChatOpenAI (OpenRouter) con Langfuse v3 callback.

Usa Langfuse SDK v3 (langfuse>=3,<4) come da requisiti challenge.
"""

from __future__ import annotations

import os
from typing import Any

import ulid
from langchain_openai import ChatOpenAI
from langfuse import get_client, observe
from langfuse.langchain import CallbackHandler


def generate_session_id() -> str:
    """Genera un session ID univoco: {TEAM_NAME}-{ULID} senza spazi."""
    team = os.getenv("TEAM_NAME", "team").replace(" ", "-")
    return f"{team}-{ulid.new().str}"


def build_llm(
    session_id: str,
    agent_name: str = "agent",
    temperature: float = 0.0,
    max_tokens: int = 2048,
    model: str | None = None,
) -> ChatOpenAI:
    """
    Crea un ChatOpenAI che punta a OpenRouter con Langfuse CallbackHandler v3.

    Parameters
    ----------
    session_id  : session ID condiviso per la run (raggruppamento Langfuse)
    agent_name  : etichetta per debug (non usata dal modello)
    temperature : 0 = deterministico
    max_tokens  : token max risposta
    model       : override modello (default: OPENROUTER_MODEL da .env)
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENROUTER_API_KEY non impostata nel .env")

    # Langfuse v3: CallbackHandler legge PUBLIC_KEY, SECRET_KEY e HOST da env
    # Il session_id viene passato via metadata config durante l'invocazione
    langfuse_handler = CallbackHandler()

    selected_model = model or os.getenv(
        "OPENROUTER_MODEL", "google/gemini-2.0-flash-001"
    )

    return ChatOpenAI(
        api_key=api_key,
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        model=selected_model,
        temperature=temperature,
        max_tokens=max_tokens,
        default_headers={
            "HTTP-Referer": "https://github.com/reply-challenges/mirror-2026",
            "X-Title": "Reply Mirror 2026 - Fraud Detection",
        },
        timeout=int(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "90")),
        max_retries=int(os.getenv("OPENROUTER_MAX_RETRIES", "3")),
        callbacks=[langfuse_handler],
    )


@observe()
def invoke_with_langfuse(
    runnable: Any,
    payload: Any,
    session_id: str,
    extra_config: dict[str, Any] | None = None,
) -> Any:
    """Invoca un runnable LangChain tracciando token/costi e legando la chiamata alla sessione."""
    langfuse_handler = CallbackHandler()
    config: dict[str, Any] = {
        "callbacks": [langfuse_handler],
        "metadata": {"langfuse_session_id": session_id},
    }
    if extra_config:
        # Mantiene callbacks/metadata tracciate, ma consente parametri addizionali (es. recursion_limit).
        config.update(extra_config)
    return runnable.invoke(payload, config=config)


def flush_langfuse() -> None:
    """Flush del client Langfuse attivo usato dai callback."""
    get_client().flush()
