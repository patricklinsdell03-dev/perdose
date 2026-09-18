"""One structured AI call for a learn page, with a local answer cache and a cost tally.

Answers are saved under data/llm_cache/content/ (git-ignored), keyed by the prompt version,
model, effort and the exact message: re-assembling a page after a code change never pays
for the same answer twice.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

from pipeline.settings import LlmConfig

CACHE_DIR = Path("data/llm_cache/content")
MAX_TOKENS = 16000  # room for thinking plus a full page; responses are far shorter


class DraftingFailed(Exception):
    """The model did not return a complete answer."""


@dataclass
class Tally:
    calls: int = 0
    cached: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class ContentAI:
    def __init__(self, config: LlmConfig, prompt_version: str, client=None, cache_dir=CACHE_DIR):
        if config.content is None:
            raise ValueError("config/llm.yml has no `content` model")
        self.config = config
        self.choice = config.content
        self.prompt_version = prompt_version
        self.cache_dir = cache_dir
        self._client = client
        self.tally = Tally()

    @property
    def client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def cost_gbp(self) -> float | None:
        return self.config.cost_gbp(
            self.choice.id, self.tally.input_tokens, self.tally.output_tokens
        )

    def cache_path(self, name: str, compound_id: str, system: str, message: str) -> Path:
        key = json.dumps(
            [self.prompt_version, self.choice.id, self.choice.effort, name, system, message]
        )
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / compound_id / f"{name}-{digest}.json"

    def ask(self, name: str, compound_id: str, system: str, message: str, schema: type[BaseModel]):
        path = self.cache_path(name, compound_id, system, message)
        if path.exists():
            try:
                answer = schema.model_validate_json(path.read_text(encoding="utf-8"))
                self.tally.cached += 1
                return answer
            except ValidationError:
                pass  # saved under an older schema: ask again
        kwargs = {"output_config": {"effort": self.choice.effort}} if self.choice.effort else {}
        self.tally.calls += 1
        response = self.client.messages.parse(
            model=self.choice.id,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": message}],
            output_format=schema,
            **kwargs,
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.tally.input_tokens += usage.input_tokens
            self.tally.output_tokens += usage.output_tokens
        if response.stop_reason != "end_turn" or response.parsed_output is None:
            raise DraftingFailed(f"{name}: the model stopped early ({response.stop_reason})")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(response.parsed_output.model_dump_json(indent=1), encoding="utf-8")
        return response.parsed_output


def estimate_tokens(text: str) -> int:
    """A deliberately generous estimate (about 3.5 characters per token) for the spending
    cap; the real count comes back with each answer."""
    return int(len(text) / 3.5) + 1
