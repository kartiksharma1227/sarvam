"""Estimated cost of a job, from the token usage it recorded.

Prices are USD per million tokens (input, output), from OpenAI's pricing pages. They change over
time: override them without a code change by setting MODEL_PRICES in .env, e.g.
    MODEL_PRICES={"gpt-5.5": [5, 30], "gpt-5.4-mini": [0.75, 4.5]}
Models without a price are reported, never guessed. The Edge voice is free.
"""

import json
import logging

from app.config import settings

log = logging.getLogger(__name__)

DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "gpt-5.5": (5.00, 30.00),
    "gpt-5.4-mini": (0.75, 4.50),
    # Image model: text prompt tokens in, image tokens out.
    "gpt-image-1.5": (5.00, 32.00),
    "text-embedding-3-small": (0.02, 0.0),
}


def prices() -> dict[str, tuple[float, float]]:
    table = dict(DEFAULT_PRICES)
    if settings.model_prices:
        try:
            table.update(
                {
                    model: (float(p[0]), float(p[1]))
                    for model, p in json.loads(settings.model_prices).items()
                }
            )
        except (ValueError, TypeError, IndexError, KeyError):
            log.warning(
                'MODEL_PRICES is not valid JSON like {"model": [in, out]}; ignoring it'
            )
    return table


def job_cost(usage: dict | None) -> dict:
    """{"total_usd": float, "by_model": {model: usd}, "unpriced": [models]}."""
    table = prices()
    by_model: dict[str, float] = {}
    unpriced: list[str] = []
    for model, counts in (usage or {}).get("by_model", {}).items():
        price = table.get(model)
        if price is None:
            unpriced.append(model)
            continue
        usd = (
            counts.get("input_tokens", 0) / 1e6 * price[0]
            + counts.get("output_tokens", 0) / 1e6 * price[1]
        )
        by_model[model] = round(usd, 4)
    return {
        "total_usd": round(sum(by_model.values()), 4),
        "by_model": by_model,
        "unpriced": unpriced,
    }
