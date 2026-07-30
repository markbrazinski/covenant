"""Model-backed candidate extraction boundaries."""

from .bedrock import BedrockCandidateExtractor
from .service import ExtractionResult, extract_candidate

__all__ = ["BedrockCandidateExtractor", "ExtractionResult", "extract_candidate"]
