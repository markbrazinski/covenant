#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from covenant.matching import BedrockAgreementMatcher, execute_match
from covenant.registry import DataHubAgreementRegistry
from src.api.matching import document_text_from_upload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Match one incoming agreement through Bedrock and DataHub."
    )
    parser.add_argument("candidate_document", type=Path)
    parser.add_argument(
        "--model-id",
        default=os.getenv("COVENANT_BEDROCK_MODEL_ID"),
        help="Authorized Bedrock model or inference-profile ID.",
    )
    parser.add_argument(
        "--region",
        default=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.model_id:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "receipt": {
                        "provider": "bedrock",
                        "failure_category": "MODEL_ID_REQUIRED",
                        "safe_message": (
                            "Select an authorized Bedrock model before matching"
                        ),
                    },
                },
                sort_keys=True,
            )
        )
        return 2
    document_text = document_text_from_upload(
        args.candidate_document.name,
        args.candidate_document.read_bytes(),
    )
    result = execute_match(
        document_text,
        matcher=BedrockAgreementMatcher(
            model_id=args.model_id,
            region=args.region,
        ),
        registry=DataHubAgreementRegistry(),
    )
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0 if result.status in {"MATCH_VERIFIED", "MATCH_NOT_FOUND"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
