#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from covenant.extraction import BedrockCandidateExtractor, extract_candidate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract an unverified Covenant candidate through AWS Bedrock."
    )
    parser.add_argument("prior_document", type=Path)
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
                    "candidate": None,
                    "receipt": {
                        "provider": "bedrock",
                        "status": "FAILED",
                        "failure_category": "MODEL_ID_REQUIRED",
                        "safe_message": (
                            "Select an authorized Bedrock model before extraction"
                        ),
                    },
                },
                sort_keys=True,
            )
        )
        return 2
    prior_text = args.prior_document.read_text()
    candidate_text = args.candidate_document.read_text()
    result = extract_candidate(
        prior_text,
        candidate_text,
        prior_ref=args.prior_document.as_posix(),
        candidate_ref=args.candidate_document.as_posix(),
        extractor=BedrockCandidateExtractor(
            model_id=args.model_id,
            region=args.region,
        ),
    )
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0 if result.status == "EXTRACTED_UNVERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
