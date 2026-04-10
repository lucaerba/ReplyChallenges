from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import ulid
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langfuse import Langfuse, observe, propagate_attributes
from langfuse.langchain import CallbackHandler


class OpenRouterClient:
    """Client OpenRouter con tracciamento Langfuse per chiamate LLM."""

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY non impostata nel file .env")

        self.base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.request_timeout = int(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "60"))
        self.max_retries = int(os.getenv("OPENROUTER_MAX_RETRIES", "2"))
        self.headers = {
            "HTTP-Referer": "https://github.com/lucaerba/ReplyChallenges",
            "X-Title": "Reply Mirror Challenge",
        }

        self.team_name = os.getenv("TEAM_NAME", "reply")
        self.session_id = self.generate_session_id()

        langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        if not langfuse_public_key or not langfuse_secret_key:
            raise ValueError(
                "LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY non impostate nel file .env"
            )

        self.langfuse_client = Langfuse(
            public_key=langfuse_public_key,
            secret_key=langfuse_secret_key,
            host=os.getenv("LANGFUSE_HOST", "https://challenges.reply.com/langfuse"),
        )

        self.primary_model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        self.fallback_model = os.getenv(
            "OPENROUTER_FALLBACK_MODEL", "openai/gpt-4o-mini"
        )

        self.available_models = {
            "qwen3": "qwen/qwen3-coder:free",
            "gemma-4": "google/gemma-4-31b-it:free",
            "gpt4-turbo": "openai/gpt-4-turbo-preview",
            "gpt4": "openai/gpt-4",
            "gpt35": "openai/gpt-3.5-turbo",
            "mistral7b": "mistralai/mistral-7b-instruct",
            "nous-hermes": "nousresearch/nous-hermes-2-mistral-7b-dpo",
            "llama2": "meta-llama/llama-2-70b-chat",
            "claude": "anthropic/claude-2",
        }

    def list_models(self) -> List[str]:
        return list(self.available_models.keys())

    def get_model_id(self, model_name: str) -> str:
        return self.available_models.get(model_name, model_name)

    def _model_candidates(self, model: str) -> List[str]:
        primary_model = self.get_model_id(model)
        fallback_model = self.get_model_id(self.fallback_model)
        candidates = [primary_model]
        if fallback_model not in candidates:
            candidates.append(fallback_model)
        return candidates

    def generate_session_id(self) -> str:
        return f"{self.team_name}-{ulid.new().str}"

    def get_session_id(self) -> str:
        return self.session_id

    def flush(self) -> None:
        self.langfuse_client.flush()

    @observe()
    def _invoke_with_langfuse(
        self,
        session_id: str,
        model: ChatOpenAI,
        messages: list[Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        trace_metadata: Dict[str, Any] = {
            "provider": "openrouter",
            "client": "OpenRouterClient",
        }
        if metadata:
            trace_metadata.update(metadata)

        with propagate_attributes(session_id=session_id, metadata=trace_metadata):
            langfuse_handler = CallbackHandler()
            return model.invoke(messages, config={"callbacks": [langfuse_handler]})

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt35",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        top_p: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Esegue una chiamata OpenRouter tracciata su Langfuse."""
        lc_messages: list[Any] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))

        last_error: Optional[Exception] = None
        for attempt, model_id in enumerate(self._model_candidates(model), start=1):
            llm = ChatOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                model=model_id,
                temperature=temperature,
                max_tokens=max_tokens,
                default_headers=self.headers,
                top_p=top_p,
                timeout=self.request_timeout,
                max_retries=self.max_retries,
            )

            try:
                start_time = time.time()
                response = self._invoke_with_langfuse(
                    session_id=self.session_id,
                    model=llm,
                    messages=lc_messages,
                    metadata={
                        **(metadata or {}),
                        "model_attempt": str(attempt),
                        "model_id": model_id,
                    },
                )
                end_time = time.time()

                content = (
                    response.content if hasattr(response, "content") else str(response)
                )

                usage = getattr(response, "usage_metadata", {}) or {}
                prompt_tokens = usage.get("input_tokens", 0)
                completion_tokens = usage.get("output_tokens", 0)
                total_tokens = usage.get(
                    "total_tokens", prompt_tokens + completion_tokens
                )

                response_metadata = getattr(response, "response_metadata", {}) or {}
                token_usage = response_metadata.get("token_usage", {})
                if not prompt_tokens:
                    prompt_tokens = token_usage.get("prompt_tokens", 0)
                if not completion_tokens:
                    completion_tokens = token_usage.get("completion_tokens", 0)
                if not total_tokens:
                    total_tokens = token_usage.get(
                        "total_tokens", prompt_tokens + completion_tokens
                    )

                return {
                    "content": content,
                    "model": model_id,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "cost": 0,
                    "latency_seconds": end_time - start_time,
                    "metadata": metadata or {},
                    "session_id": self.session_id,
                }
            except Exception as e:
                last_error = e
                error_text = str(e)
                if "429" not in error_text and "rate-limit" not in error_text.lower():
                    break

        return {
            "error": str(last_error) if last_error else "Unknown OpenRouter error",
            "model": self.get_model_id(model),
            "content": None,
            "metadata": metadata or {},
            "session_id": self.session_id,
        }
