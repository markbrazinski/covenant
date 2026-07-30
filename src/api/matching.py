from __future__ import annotations

import io
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from covenant.extraction import BedrockCandidateExtractor, extract_candidate
from covenant.extraction.progress import observe_extraction_progress
from covenant.matching import BedrockAgreementMatcher, execute_match
from covenant.matching.verifier import match_identity
from covenant.registry import DataHubAgreementRegistry
from covenant.registry.datahub import resolve_prior_document

from .service import APIStateError, CovenantService
from .store import RunStore


ROOT = Path(__file__).resolve().parents[2]
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
TERMINAL_PHASES = {"MATCH_VERIFIED", "MATCH_REJECTED", "MATCH_NOT_FOUND"}
EXTRACTION_TERMINAL_PHASES = {
    "CANDIDATE_READY",
    "EXTRACTION_REJECTED",
    "EXTRACTION_FAILED",
}


class MatchCoordinator:
    """Own asynchronous match runs without exposing source document content."""

    def __init__(
        self,
        store: RunStore,
        covenant_service: CovenantService,
        *,
        registry: DataHubAgreementRegistry | None = None,
        matcher_factory: Callable[[], BedrockAgreementMatcher] | None = None,
        extractor_factory: Callable[[], BedrockCandidateExtractor] | None = None,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self.store = store
        self.covenant_service = covenant_service
        self.registry = registry or DataHubAgreementRegistry()
        self.matcher_factory = matcher_factory or self._matcher
        self.extractor_factory = extractor_factory or self._extractor
        self.executor = executor or ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="covenant-match"
        )
        self._documents: dict[str, tuple[str, str]] = {}
        self._lock = RLock()

    def start(self, document_text: str, *, document_ref: str) -> dict[str, str]:
        match_id = match_identity({}, document_text)
        analysis = {
            "match_id": match_id,
            "phase": "MATCH_STARTED",
            "events": [],
            "result": None,
            "verification": None,
            "receipt": None,
            "change_id": None,
            "extraction_phase": None,
            "extraction_events": [],
        }
        self.store.put_analysis(match_id, analysis)
        with self._lock:
            self._documents[match_id] = (document_text, document_ref)
        self._event(match_id, "MATCH_STARTED", {})
        self.executor.submit(self._run_match, match_id)
        return {
            "match_id": match_id,
            "stream_url": f"/analyses/{match_id}/events",
        }

    def registered(self) -> list[dict[str, str]]:
        try:
            records = self.registry.list_registered()
        except Exception as exc:
            raise APIStateError(
                "REGISTRY_UNAVAILABLE",
                "the governed-agreement registry is unavailable",
                status_code=503,
                retryable=True,
            ) from exc
        return [record.as_dict() for record in records]

    def detail(self, match_id: str) -> dict[str, Any]:
        value = self.store.get_analysis(match_id)
        if value is None:
            raise APIStateError(
                "MATCH_NOT_FOUND",
                "agreement match analysis was not found",
                status_code=404,
            )
        return value

    def extract(self, match_id: str) -> dict[str, Any]:
        analysis = self.detail(match_id)
        if analysis["phase"] != "MATCH_VERIFIED":
            raise APIStateError(
                "VERIFIED_MATCH_REQUIRED",
                "candidate extraction requires a deterministically verified registry match",
            )
        analysis["extraction_phase"] = None
        analysis["extraction_events"] = []
        self.store.put_analysis(match_id, analysis)
        try:
            self._extraction_event(match_id, "PREPARING_SOURCES", {})
            with self._lock:
                source = self._documents.get(match_id)
            if source is None:
                raise APIStateError(
                    "MATCH_SOURCE_UNAVAILABLE",
                    "the matched source document is no longer available; run matching again",
                    status_code=410,
                )
            candidate_text, candidate_ref = source
            match = analysis["result"]["tool_call"]["tool_result_match"]
            prior_path = resolve_prior_document(match["prior_document_path"])
            prior_text = prior_path.read_text()
            with observe_extraction_progress(
                lambda phase, data: self._extraction_event(
                    match_id,
                    phase,
                    data,
                )
            ):
                result = extract_candidate(
                    prior_text,
                    candidate_text,
                    prior_ref=match["prior_document_path"],
                    candidate_ref=candidate_ref,
                    extractor=self.extractor_factory(),
                )
                if (
                    result.status != "EXTRACTED_UNVERIFIED"
                    or result.candidate is None
                ):
                    message = result.receipt.get(
                        "safe_message",
                        "Bedrock extraction did not produce a candidate",
                    )
                    self._extraction_event(
                        match_id,
                        "EXTRACTION_FAILED",
                        {
                            "message": message,
                            "failure_category": result.receipt.get(
                                "failure_category",
                                "INVOCATION_FAILED",
                            ),
                        },
                    )
                    raise APIStateError(
                        "EXTRACTION_FAILED",
                        message,
                        status_code=502,
                        retryable=True,
                    )
                record = self.covenant_service.record_verified_extraction(
                    result.candidate,
                    {
                        match["prior_document_path"]: prior_text,
                        candidate_ref: candidate_text,
                    },
                    result.receipt,
                    current_active_version=int(
                        match["current_version"].removeprefix("v")
                    ),
                    provider_name=match["vendor_name"],
                )
            if record["verification"]["status"] != "PASS":
                self._extraction_event(
                    match_id,
                    "EXTRACTION_REJECTED",
                    {"failures": record["verification"].get("failures", [])},
                )
            else:
                self._extraction_event(
                    match_id,
                    "CANDIDATE_READY",
                    {
                        "change_id": record.get("change_id"),
                        "rule_count": len(record["candidate"]["rules"]),
                        "citation_count": len(record["candidate"]["rules"]),
                    },
                )
            current = self.detail(match_id)
            current["change_id"] = record.get("change_id")
            self.store.put_analysis(match_id, current)
            return record
        except APIStateError:
            raise
        except Exception:
            self._extraction_event(
                match_id,
                "EXTRACTION_FAILED",
                {"message": "Extraction failed safely; no candidate was produced"},
            )
            raise

    def _run_match(self, match_id: str) -> None:
        with self._lock:
            document = self._documents.get(match_id)
        if document is None:
            self._event(
                match_id,
                "MATCH_REJECTED",
                {"reason": "source document is unavailable"},
            )
            return
        try:
            matcher = self.matcher_factory()
            execution = execute_match(
                document[0],
                matcher=matcher,
                registry=self.registry,
                on_event=lambda phase, data: self._event(match_id, phase, data),
            )
        except APIStateError as exc:
            self._event(
                match_id,
                "MATCH_REJECTED",
                {
                    "failures": [
                        {"check": exc.code, "message": str(exc)}
                    ]
                },
            )
            return
        except Exception:
            self._event(
                match_id,
                "MATCH_REJECTED",
                {
                    "failures": [
                        {
                            "check": "match_runtime",
                            "message": "agreement matching failed safely",
                        }
                    ]
                },
            )
            return
        analysis = self.detail(match_id)
        analysis["result"] = execution.result
        analysis["verification"] = execution.verification
        analysis["receipt"] = execution.receipt
        self.store.put_analysis(match_id, analysis)
        if execution.status == "MATCH_VERIFIED":
            self._event(match_id, "MATCH_VERIFIED", {})
        elif execution.status == "MATCH_NOT_FOUND":
            self._event(match_id, "MATCH_NOT_FOUND", {})
        else:
            failures = (
                execution.verification.get("failures", [])
                if execution.verification
                else [
                    {
                        "check": execution.receipt.get(
                            "failure_category", "match_invocation"
                        ),
                        "message": execution.receipt.get(
                            "safe_message", "agreement matching failed"
                        ),
                    }
                ]
            )
            self._event(match_id, "MATCH_REJECTED", {"failures": failures})

    def _event(self, match_id: str, phase: str, data: dict[str, Any]) -> None:
        analysis = self.detail(match_id)
        analysis["phase"] = phase
        analysis["events"].append(
            {
                "sequence": len(analysis["events"]) + 1,
                "phase": phase,
                **data,
            }
        )
        self.store.put_analysis(match_id, analysis)

    def _extraction_event(
        self,
        match_id: str,
        phase: str,
        data: dict[str, Any],
    ) -> None:
        analysis = self.detail(match_id)
        events = analysis.setdefault("extraction_events", [])
        analysis["extraction_phase"] = phase
        events.append(
            {
                "sequence": len(events) + 1,
                "phase": phase,
                **data,
            }
        )
        self.store.put_analysis(match_id, analysis)

    @staticmethod
    def _matcher() -> BedrockAgreementMatcher:
        model_id = os.getenv("COVENANT_BEDROCK_MODEL_ID", "").strip()
        if not model_id:
            raise APIStateError(
                "MODEL_ID_REQUIRED",
                "Select an authorized Bedrock model before agreement matching",
                status_code=503,
            )
        return BedrockAgreementMatcher(
            model_id=model_id,
            region=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
        )

    @staticmethod
    def _extractor() -> BedrockCandidateExtractor:
        model_id = os.getenv("COVENANT_BEDROCK_MODEL_ID", "").strip()
        if not model_id:
            raise APIStateError(
                "MODEL_ID_REQUIRED",
                "Select an authorized Bedrock model before extraction",
                status_code=503,
            )
        return BedrockCandidateExtractor(
            model_id=model_id,
            region=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
        )


def document_text_from_upload(filename: str, payload: bytes) -> str:
    if not payload or len(payload) > MAX_DOCUMENT_BYTES:
        raise APIStateError(
            "INVALID_DOCUMENT",
            "uploaded agreement must be between 1 byte and 5 MiB",
            status_code=422,
        )
    suffix = Path(filename).suffix.lower()
    if suffix in {".md", ".txt"}:
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise APIStateError(
                "INVALID_DOCUMENT",
                "text agreement must be UTF-8",
                status_code=422,
            ) from exc
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            pages = PdfReader(io.BytesIO(payload)).pages
            text = "\n".join(page.extract_text() or "" for page in pages)
        except Exception as exc:
            raise APIStateError(
                "INVALID_DOCUMENT",
                "PDF agreement text could not be extracted",
                status_code=422,
            ) from exc
        if not text.strip():
            raise APIStateError(
                "INVALID_DOCUMENT",
                "PDF agreement contains no extractable text",
                status_code=422,
            )
        return text
    raise APIStateError(
        "INVALID_DOCUMENT",
        "agreement must be a PDF, Markdown, or UTF-8 text file",
        status_code=422,
    )


def document_text_from_fixture(path: str) -> tuple[str, str]:
    candidate = (ROOT / path).resolve()
    fixtures = (ROOT / "fixtures").resolve()
    if (
        not candidate.is_relative_to(fixtures)
        or not candidate.is_file()
        or candidate.suffix.lower() not in {".md", ".txt", ".pdf"}
    ):
        raise APIStateError(
            "INVALID_FIXTURE_REFERENCE",
            "fixture reference must name a supported file under fixtures",
            status_code=422,
        )
    return document_text_from_upload(candidate.name, candidate.read_bytes()), path
