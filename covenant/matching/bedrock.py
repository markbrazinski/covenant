from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from botocore.config import Config

from covenant.extraction.bedrock import ConverseClient, invocation_failure_category
from covenant.registry.datahub import LookupResult


PROMPT_PATH = Path(__file__).parent / "prompts" / "match_v1.md"
MODEL_SCHEMA_PATH = Path(__file__).parent / "schemas" / "match_model_output_v1.json"
TOOL_NAME = "lookup_governed_agreement"


@dataclass(frozen=True)
class ModelMatch:
    payload: dict[str, Any]
    tool_input: dict[str, str]
    tool_result: LookupResult
    tool_call_count: int
    model_id: str
    prompt_version: str
    input_token_count: int
    output_token_count: int
    attempts: int


class BedrockMatchError(RuntimeError):
    def __init__(self, category: str, message: str, *, attempts: int) -> None:
        super().__init__(message)
        self.category = category
        self.safe_message = message
        self.attempts = attempts


class BedrockAgreementMatcher:
    """Use Bedrock Converse tool use to identify one governed agreement."""

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

    def match(
        self,
        document_text: str,
        *,
        lookup: Callable[[str, str], LookupResult],
        on_tool_called: Callable[[dict[str, str]], None] | None = None,
        on_tool_returned: Callable[[LookupResult], None] | None = None,
    ) -> ModelMatch:
        prompt, prompt_version = load_prompt()
        user_message = {
            "role": "user",
            "content": [
                {
                    "text": (
                        "<incoming_agreement_evidence>\n"
                        f"{document_text}\n"
                        "</incoming_agreement_evidence>"
                    )
                }
            ],
        }
        first_request = {
            "modelId": self.model_id,
            "system": [{"text": prompt}],
            "messages": [user_message],
            "inferenceConfig": {"maxTokens": 2048, "temperature": 0.0},
            "toolConfig": {"tools": [lookup_tool_spec()]},
        }
        client = self._client or self._make_client()
        first, first_attempts = self._converse(client, first_request)
        try:
            assistant_message = first["output"]["message"]
            tool_blocks = [
                item["toolUse"]
                for item in assistant_message["content"]
                if isinstance(item, dict) and "toolUse" in item
            ]
        except (KeyError, TypeError) as exc:
            raise BedrockMatchError(
                "MALFORMED_MODEL_OUTPUT",
                "Bedrock returned an invalid match tool-use response",
                attempts=first_attempts,
            ) from exc
        if len(tool_blocks) != 1:
            raise BedrockMatchError(
                "INVALID_TOOL_CALL_COUNT",
                "Bedrock must call the governed-agreement lookup exactly once",
                attempts=first_attempts,
            )
        tool_use = tool_blocks[0]
        raw_input = tool_use.get("input")
        if (
            tool_use.get("name") != TOOL_NAME
            or not isinstance(raw_input, dict)
            or set(raw_input) != {"vendor_name", "obligation_id"}
            or not all(isinstance(raw_input.get(key), str) for key in raw_input)
        ):
            raise BedrockMatchError(
                "INVALID_TOOL_INPUT",
                "Bedrock called the agreement lookup with invalid identifiers",
                attempts=first_attempts,
            )
        tool_input = {
            "vendor_name": raw_input["vendor_name"],
            "obligation_id": raw_input["obligation_id"],
        }
        if on_tool_called:
            on_tool_called(tool_input)
        try:
            tool_result = lookup(
                tool_input["vendor_name"], tool_input["obligation_id"]
            )
        except Exception as exc:
            raise BedrockMatchError(
                "REGISTRY_UNAVAILABLE",
                "The governed-agreement registry could not be queried",
                attempts=first_attempts,
            ) from exc
        if on_tool_returned:
            on_tool_returned(tool_result)
        tool_result_message = {
            "role": "user",
            "content": [
                {
                    "toolResult": {
                        "toolUseId": tool_use["toolUseId"],
                        "content": [{"json": tool_result.as_dict()}],
                        "status": "success",
                    }
                }
            ],
        }
        final_request = {
            "modelId": self.model_id,
            "system": [{"text": prompt}],
            "messages": [user_message, assistant_message, tool_result_message],
            "inferenceConfig": {"maxTokens": 2048, "temperature": 0.0},
            "toolConfig": {"tools": [lookup_tool_spec()]},
            "outputConfig": {
                "textFormat": {
                    "type": "json_schema",
                    "structure": {
                        "jsonSchema": {
                            "schema": json.dumps(
                                load_model_schema(), separators=(",", ":")
                            ),
                            "name": "covenant_match_model_output_v1",
                            "description": (
                                "Identifier evidence and exact authoritative lookup echo."
                            ),
                        }
                    },
                }
            },
        }
        final, final_attempts = self._converse(client, final_request)
        try:
            content = final["output"]["message"]["content"]
            if any("toolUse" in item for item in content if isinstance(item, dict)):
                raise BedrockMatchError(
                    "INVALID_TOOL_CALL_COUNT",
                    "Bedrock attempted more than one governed-agreement lookup",
                    attempts=first_attempts + final_attempts,
                )
            text_blocks = [item["text"] for item in content if "text" in item]
            payload = json.loads("".join(text_blocks))
        except BedrockMatchError:
            raise
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise BedrockMatchError(
                "MALFORMED_MODEL_OUTPUT",
                "Bedrock returned malformed structured match output",
                attempts=first_attempts + final_attempts,
            ) from exc
        first_usage = first.get("usage", {})
        final_usage = final.get("usage", {})
        return ModelMatch(
            payload=payload,
            tool_input=tool_input,
            tool_result=tool_result,
            tool_call_count=1,
            model_id=self.model_id,
            prompt_version=prompt_version,
            input_token_count=int(first_usage.get("inputTokens", 0))
            + int(final_usage.get("inputTokens", 0)),
            output_token_count=int(first_usage.get("outputTokens", 0))
            + int(final_usage.get("outputTokens", 0)),
            attempts=first_attempts + final_attempts,
        )

    def _converse(
        self, client: ConverseClient, request: dict[str, Any]
    ) -> tuple[dict[str, Any], int]:
        for attempts in range(1, self.max_retries + 2):
            try:
                return client.converse(**request), attempts
            except Exception as exc:
                if attempts > self.max_retries:
                    raise BedrockMatchError(
                        invocation_failure_category(exc),
                        "Bedrock agreement matching failed",
                        attempts=attempts,
                    ) from exc
        raise BedrockMatchError(
            "INVOCATION_FAILED",
            "Bedrock agreement matching failed",
            attempts=self.max_retries + 1,
        )

    def _make_client(self) -> ConverseClient:
        try:
            import boto3
        except ImportError as exc:
            raise BedrockMatchError(
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
        raise RuntimeError("agreement match prompt has no version marker")
    return prompt, first_line.removeprefix(marker).strip()


def load_model_schema() -> dict[str, Any]:
    return json.loads(MODEL_SCHEMA_PATH.read_text())


def lookup_tool_spec() -> dict[str, Any]:
    return {
        "toolSpec": {
            "name": TOOL_NAME,
            "description": (
                "Look up a data-use agreement Covenant already governs. Given a "
                "vendor name and obligation identifier extracted from a document, "
                "this returns the current in-effect prior version if it exists in "
                "Covenant's registry, or reports that no matching agreement is "
                "under management."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "vendor_name": {
                            "type": "string",
                            "description": (
                                "Vendor or data provider name exactly as it appears "
                                "in the document."
                            ),
                        },
                        "obligation_id": {
                            "type": "string",
                            "description": (
                                "Obligation, license, or agreement identifier "
                                "exactly as it appears in the document."
                            ),
                        },
                    },
                    "required": ["vendor_name", "obligation_id"],
                }
            },
        }
    }
