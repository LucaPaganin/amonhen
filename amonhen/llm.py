"""The one place a chat-completion request is built, sent and parsed.

Two features talk to a model — the proposals for unseen merchants (5.5) and the
reading of 5.9 — and they must do it the same way: one transport, one shape of
request, one set of failure modes. The endpoint is any OpenAI-compatible chat
completion gateway, configured in the environment (README, ``AMONHEN_LLM_*``).

Two protocol requirements live here because they belong to the protocol and not
to a prompt: ``response_format: json_object``, and the lowercase word "json" in
the prompt — DeepSeek and OpenAI both refuse the first without the second.
"""
import json
from dataclasses import dataclass

import requests

from amonhen.settings import LLM_API_KEY, LLM_MODEL, LLM_URL


class LlmOff(RuntimeError):
    """No endpoint or model is configured: the feature says so instead of failing."""


@dataclass(frozen=True)
class LlmConfig:
    url: str
    api_key: str
    model: str
    timeout: int = 60

    @property
    def configured(self) -> bool:
        return bool(self.url and self.model)


def llm_config() -> LlmConfig:
    return LlmConfig(url=LLM_URL, api_key=LLM_API_KEY, model=LLM_MODEL)


def chat_json(config: LlmConfig, system: str, payload: dict) -> dict:
    """Send one request and return the object the model answered with.

    Raises ``requests.RequestException`` when the call itself fails and
    ``ValueError`` when the answer is not a JSON object: the caller turns both
    into a message for the person, and nothing here retries.
    """
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    body = {
        "model": config.model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }
    response = requests.post(config.url, json=body, headers=headers, timeout=config.timeout)
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("the model did not answer with a json object")
    return parsed
