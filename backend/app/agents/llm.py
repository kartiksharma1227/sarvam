"""Structured LLM calls: the model must return JSON matching a Pydantic model, or it is asked to fix it.

Agents only use `LLM.structured(...)`, so the provider can change without touching them.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol, TypeVar

import openai
from openai import AsyncOpenAI
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel, ValidationError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Tier = Literal["main", "fast"]
Check = Callable[[T], list[str]]

FIX_REQUEST = (
    "Your previous answer has these problems:\n{errors}\n\n"
    "Return the complete corrected JSON. Keep everything that was already correct."
)
# Keywords stripped from the wire schema if the API rejects them; Pydantic still enforces them locally.
LENGTH_KEYWORDS = ("minLength", "maxLength", "minItems", "maxItems")
TRANSIENT_ERRORS = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
)
# 429s that waiting won't fix: the account is out of credits.
PERMANENT_CODES = {"insufficient_quota"}


def is_transient(exc: BaseException) -> bool:
    """Worth retrying with backoff (network, rate limit, 5xx), but not an empty account."""
    return isinstance(exc, TRANSIENT_ERRORS) and (
        getattr(exc, "code", None) not in PERMANENT_CODES
    )


class AgentError(RuntimeError):
    def __init__(self, agent: str, errors: list[str]):
        self.agent = agent
        self.errors = errors
        super().__init__(
            f"{agent} could not produce valid output: " + "; ".join(errors)
        )


@dataclass
class Usage:
    """Token and call counts for one job, per model."""

    by_model: dict[str, dict[str, int]] = field(default_factory=dict)
    validation_retries: int = 0

    def add(self, model: str, input_tokens: int, output_tokens: int) -> None:
        entry = self.by_model.setdefault(
            model, {"calls": 0, "input_tokens": 0, "output_tokens": 0}
        )
        entry["calls"] += 1
        entry["input_tokens"] += input_tokens
        entry["output_tokens"] += output_tokens

    def as_dict(self) -> dict:
        return {
            "by_model": self.by_model,
            "validation_retries": self.validation_retries,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "Usage":
        data = data or {}
        by_model = {
            model: dict(counts) for model, counts in data.get("by_model", {}).items()
        }
        return cls(
            by_model=by_model, validation_retries=data.get("validation_retries", 0)
        )


class LLM(Protocol):
    usage: Usage

    async def structured(
        self,
        *,
        agent: str,
        tier: Tier,
        system: str,
        user: str,
        output_model: type[T],
        check: Check | None = None,
    ) -> T: ...


def format_validation_error(exc: ValidationError) -> list[str]:
    problems = []
    for err in exc.errors():
        where = ".".join(str(p) for p in err["loc"]) or "(root)"
        got = json.dumps(err.get("input"), default=str)
        if len(got) > 80:
            got = got[:77] + "..."
        problems.append(f"{where}: {err['msg']} (got {got})")
    return problems


def _strip_keywords(schema):
    if isinstance(schema, dict):
        return {
            k: _strip_keywords(v) for k, v in schema.items() if k not in LENGTH_KEYWORDS
        }
    if isinstance(schema, list):
        return [_strip_keywords(v) for v in schema]
    return schema


class OpenAILLM:
    def __init__(
        self, client: AsyncOpenAI | None = None, models: dict[str, str] | None = None
    ):
        self.client = client or AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,  # retries are handled below with backoff
        )
        self.models = models or {
            "main": settings.llm_model_main,
            "fast": settings.llm_model_fast,
        }
        self.validation_retries = settings.llm_validation_retries
        self.usage = Usage()
        self._strip_length_keywords = False

    def _schema(self, output_model: type[BaseModel]) -> dict:
        schema = to_strict_json_schema(output_model)
        return _strip_keywords(schema) if self._strip_length_keywords else schema

    async def structured(self, *, agent, tier, system, user, output_model, check=None):
        model = self.models[tier]
        if not model:
            raise AgentError(
                agent,
                [
                    f"no model configured for tier '{tier}'; set LLM_MODEL_{tier.upper()} in .env"
                ],
            )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        errors: list[str] = []
        for attempt in range(self.validation_retries + 1):
            content = await self._complete(model, messages, output_model)
            try:
                result = output_model.model_validate_json(content)
                errors = check(result) if check else []
            except ValidationError as exc:
                errors = format_validation_error(exc)
            if not errors:
                return result
            if attempt < self.validation_retries:
                self.usage.validation_retries += 1
                log.warning(
                    "%s: retrying after %d problem(s): %s",
                    agent,
                    len(errors),
                    "; ".join(errors)[:300],
                )
                messages += [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": FIX_REQUEST.format(
                            errors="\n".join(f"- {e}" for e in errors)
                        ),
                    },
                ]
        raise AgentError(agent, errors)

    async def _complete(
        self, model: str, messages: list[dict], output_model: type[BaseModel]
    ) -> str:
        try:
            return await self._request(model, messages, output_model)
        except openai.BadRequestError as exc:
            # Some models reject length keywords in strict schemas; fall back to enforcing them locally.
            if self._strip_length_keywords or not any(
                k in str(exc) for k in LENGTH_KEYWORDS
            ):
                raise
            log.warning(
                "Model rejected schema length keywords; enforcing them locally instead"
            )
            self._strip_length_keywords = True
            return await self._request(model, messages, output_model)

    @retry(
        retry=retry_if_exception(is_transient),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=20),
        reraise=True,
    )
    async def _request(
        self, model: str, messages: list[dict], output_model: type[BaseModel]
    ) -> str:
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": output_model.__name__,
                    "schema": self._schema(output_model),
                    "strict": True,
                },
            },
        )
        if response.usage:
            self.usage.add(
                model, response.usage.prompt_tokens, response.usage.completion_tokens
            )
        choice = response.choices[0]
        if getattr(choice.message, "refusal", None):
            raise AgentError(
                output_model.__name__, [f"model refused: {choice.message.refusal}"]
            )
        if choice.finish_reason == "length":
            raise AgentError(
                output_model.__name__, ["response was cut off (hit the token limit)"]
            )
        return choice.message.content or ""


def get_llm() -> LLM:
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise AgentError(
                "setup", ["OPENAI_API_KEY is empty; fill it in backend/.env"]
            )
        return OpenAILLM()
    raise AgentError(
        "setup",
        [f"unsupported LLM_PROVIDER {settings.llm_provider!r} (available: openai)"],
    )
