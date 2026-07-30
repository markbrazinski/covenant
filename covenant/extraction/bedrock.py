from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from src.obligations.candidate import SUPPORTED_USAGES


ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = Path(__file__).parent / "prompts" / "candidate_delta_v1.md"
SCHEMA_PATH = Path(__file__).parent / "schemas" / "candidate_delta_v1.json"


class ConverseClient(Protocol):
    def converse(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ModelExtraction:
    payload: dict[str, Any]
    model_id: str
    prompt_version: str
    input_token_count: int
    output_token_count: int
    attempts: int


class BedrockInvocationError(RuntimeError):
    def __init__(self, category: str, message: str, *, attempts: int) -> None:
        super().__init__(message)
        self.category = category
        self.safe_message = message
        self.attempts = attempts


class BedrockCandidateExtractor:
    """Invoke one authorized Bedrock model through the Converse API."""

    def __init__(
        self,
        *,
        model_id: str,
        region: str | None = None,
        client: ConverseClient | None = None,
        max_retries: int = 2,
    ) -> None:
        if not model_id.strip():
            raise ValueError("a Bedrock model ID is required")
        if max_retries < 0 or max_retries > 2:
            raise ValueError("max_retries must be between zero and two")
        self.model_id = model_id
        self.region = region
        self.max_retries = max_retries
        self._client = client

    def extract(self, prior_text: str, candidate_text: str) -> ModelExtraction:
        prompt, prompt_version = load_prompt()
        schema = load_bedrock_output_schema()
        request = {
            "modelId": self.model_id,
            "system": [
                {
                    "text": prompt.replace(
                        "{{USAGE_VOCABULARY}}",
                        ", ".join(sorted(SUPPORTED_USAGES)),
                    )
                }
            ],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "text": (
                                "<prior_version_evidence>\n"
                                f"{prior_text}\n"
                                "</prior_version_evidence>\n\n"
                                "<candidate_version_evidence>\n"
                                f"{candidate_text}\n"
                                "</candidate_version_evidence>"
                            )
                        }
                    ],
                }
            ],
            "inferenceConfig": {"maxTokens": 4096, "temperature": 0.0},
            "outputConfig": {
                "textFormat": {
                    "type": "json_schema",
                    "structure": {
                        "jsonSchema": {
                            "schema": json.dumps(schema, separators=(",", ":")),
                            "name": "covenant_candidate_delta_v1",
                            "description": (
                                "Evidence-bound semantic candidate delta. "
                                "No downstream assets or actions."
                            ),
                        }
                    },
                }
            },
        }
        client = self._client or self._make_client()
        response: dict[str, Any] | None = None
        attempts = 0
        for attempts in range(1, self.max_retries + 2):
            try:
                response = client.converse(**request)
                break
            except Exception as exc:
                if attempts > self.max_retries:
                    raise BedrockInvocationError(
                        invocation_failure_category(exc),
                        "Bedrock extraction failed; no candidate was produced",
                        attempts=attempts,
                    ) from exc
        if response is None:
            raise BedrockInvocationError(
                "INVOCATION_FAILED",
                "Bedrock extraction failed; no candidate was produced",
                attempts=attempts,
            )
        try:
            content = response["output"]["message"]["content"]
            text_blocks = [item["text"] for item in content if "text" in item]
            payload = json.loads("".join(text_blocks))
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise BedrockInvocationError(
                "MALFORMED_MODEL_OUTPUT",
                "Bedrock returned malformed structured output; no candidate was produced",
                attempts=attempts,
            ) from exc
        usage = response.get("usage", {})
        return ModelExtraction(
            payload=payload,
            model_id=self.model_id,
            prompt_version=prompt_version,
            input_token_count=int(usage.get("inputTokens", 0)),
            output_token_count=int(usage.get("outputTokens", 0)),
            attempts=attempts,
        )

    def _make_client(self) -> ConverseClient:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise BedrockInvocationError(
                "BEDROCK_DEPENDENCY_UNAVAILABLE",
                "The Bedrock runtime dependency is not installed",
                attempts=0,
            ) from exc
        return boto3.client(
            "bedrock-runtime",
            region_name=self.region
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION"),
            config=Config(
                connect_timeout=5,
                read_timeout=30,
                retries={"total_max_attempts": 1, "mode": "standard"},
            ),
        )


def load_prompt() -> tuple[str, str]:
    prompt = PROMPT_PATH.read_text()
    first_line, _, _ = prompt.partition("\n")
    marker = "PROMPT_VERSION:"
    if not first_line.startswith(marker):
        raise RuntimeError("candidate extraction prompt has no version marker")
    return prompt, first_line.removeprefix(marker).strip()


def load_schema() -> dict[str, Any]:
    schema = json.loads(SCHEMA_PATH.read_text())
    expected = sorted(SUPPORTED_USAGES)
    actual = sorted(
        schema["properties"]["rules"]["items"]["properties"]["usage_class"]["enum"]
    )
    if actual != expected:
        raise RuntimeError("model schema usage vocabulary diverges from the engine")
    return schema


def load_bedrock_output_schema() -> dict[str, Any]:
    """Project the canonical schema onto Bedrock's supported JSON Schema subset."""
    schema = deepcopy(load_schema())
    confidence = schema["properties"]["rules"]["items"]["properties"]["confidence"]
    confidence.pop("minimum", None)
    confidence.pop("maximum", None)
    return schema


def invocation_failure_category(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if "timeout" in name or "timeout" in message:
        return "TIMEOUT"
    if "credential" in name or "credential" in message or "expired" in message:
        return "AUTHENTICATION_FAILED"
    if "accessdenied" in name or "not authorized" in message:
        return "AUTHORIZATION_FAILED"
    return "INVOCATION_FAILED"
