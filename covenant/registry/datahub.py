from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from time import perf_counter, sleep
from typing import Any, Callable, Protocol

from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.metadata.schema_classes import DomainPropertiesClass

from src.datahub_client.core import emitter, graph
from src.datahub_client.mcp import call_mcp


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_KIND = "covenant.governed_agreement.v1"
REGISTRY_PREFIX = "covenant.registry."
ATLAS_DOMAIN_URN = "urn:li:domain:covenant-agreement-atlas-signals-atlas-lic-004"
ATLAS_VENDOR_ID = "urn:li:covenantVendor:atlas-signals"
ATLAS_PRIOR_PATH = "fixtures/atlas_license_v3.md"


class RegistrySearch(Protocol):
    def __call__(self, calls: list[tuple[str, dict[str, Any]]]) -> list[Any]: ...


@dataclass(frozen=True)
class AgreementRecord:
    registry_urn: str
    vendor_id: str
    vendor_name: str
    obligation_id: str
    current_version: str
    effective_date: str
    prior_document_hash: str
    prior_document_path: str
    registered_at: str
    description: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)

    def as_lookup_dict(self) -> dict[str, str]:
        return {
            "vendor_id": self.vendor_id,
            "vendor_name": self.vendor_name,
            "obligation_id": self.obligation_id,
            "current_version": self.current_version,
            "effective_date": self.effective_date,
            "prior_document_hash": self.prior_document_hash,
            "prior_document_path": self.prior_document_path,
            "registered_at": self.registered_at,
        }


@dataclass(frozen=True)
class LookupResult:
    status: str
    match: AgreementRecord | None
    lookup_latency_ms: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "match": self.match.as_lookup_dict() if self.match else None,
            "lookup_latency_ms": self.lookup_latency_ms,
        }


def atlas_agreement_record(
    *,
    registered_at: str | None = None,
    source_path: str = ATLAS_PRIOR_PATH,
) -> AgreementRecord:
    resolved = resolve_prior_document(source_path)
    return AgreementRecord(
        registry_urn=ATLAS_DOMAIN_URN,
        vendor_id=ATLAS_VENDOR_ID,
        vendor_name="Atlas Signals",
        obligation_id="ATLAS-LIC-004",
        current_version="v3",
        effective_date="2025-07-01T00:00:00Z",
        prior_document_hash=sha256(resolved.read_bytes()).hexdigest(),
        prior_document_path=source_path,
        registered_at=registered_at
        or datetime.now(timezone.utc).isoformat(),
        description=(
            "Synthetic Atlas Signals v3 agreement governing internal analytics, "
            "machine-learning training, customer redistribution, and anonymized "
            "derivatives for fictional Northstar Commerce."
        ),
    )


def resolve_prior_document(path: str) -> Path:
    candidate = Path(path)
    resolved = (candidate if candidate.is_absolute() else ROOT / candidate).resolve()
    if not resolved.is_relative_to(ROOT) or not resolved.is_file():
        raise ValueError("registered prior document must be a file inside the repository")
    return resolved


class DataHubAgreementRegistry:
    """Registry whose records are native DataHub Domain property aspects."""

    def __init__(
        self,
        *,
        search_fn: RegistrySearch = call_mcp,
        graph_fn: Callable[[], Any] = graph,
        emitter_fn: Callable[[], Any] = emitter,
    ) -> None:
        self.search_fn = search_fn
        self.graph_fn = graph_fn
        self.emitter_fn = emitter_fn

    def seed(self, record: AgreementRecord) -> AgreementRecord:
        resolve_prior_document(record.prior_document_path)
        existing = self._read(record.registry_urn)
        if existing and existing == record:
            return existing
        if existing and existing.registered_at != record.registered_at:
            record = AgreementRecord(
                **{
                    **record.as_dict(),
                    "registered_at": existing.registered_at,
                }
            )
        properties = {
            REGISTRY_PREFIX + "kind": REGISTRY_KIND,
            REGISTRY_PREFIX + "vendor_id": record.vendor_id,
            REGISTRY_PREFIX + "vendor_name": record.vendor_name,
            REGISTRY_PREFIX + "obligation_id": record.obligation_id,
            REGISTRY_PREFIX + "current_version": record.current_version,
            REGISTRY_PREFIX + "effective_date": record.effective_date,
            REGISTRY_PREFIX + "prior_document_hash": record.prior_document_hash,
            REGISTRY_PREFIX + "prior_document_path": record.prior_document_path,
            REGISTRY_PREFIX + "registered_at": record.registered_at,
        }
        self.emitter_fn().emit(
            MetadataChangeProposalWrapper(
                entityType="domain",
                entityUrn=record.registry_urn,
                aspect=DomainPropertiesClass(
                    name=f"{record.vendor_name} · {record.obligation_id} · {record.current_version}",
                    description=record.description,
                    customProperties=properties,
                ),
            )
        )
        seeded = self._read(record.registry_urn)
        if seeded != record:
            raise RuntimeError("DataHub registry write did not read back exactly")
        return seeded

    def seed_and_wait(
        self,
        record: AgreementRecord,
        *,
        timeout_seconds: float = 15.0,
    ) -> AgreementRecord:
        seeded = self.seed(record)
        deadline = perf_counter() + timeout_seconds
        while perf_counter() < deadline:
            if self.lookup(record.vendor_name, record.obligation_id).status == "MATCH":
                return seeded
            sleep(0.25)
        raise RuntimeError("DataHub MCP registry search did not converge")

    def lookup_governed_agreement(
        self, vendor_name: str, obligation_id: str
    ) -> LookupResult:
        return self.lookup(vendor_name, obligation_id)

    def lookup(self, vendor_name: str, obligation_id: str) -> LookupResult:
        started = perf_counter()
        raw = self.search_fn(
            [
                (
                    "search",
                    {
                        "query": f"{vendor_name} {obligation_id}",
                        "num_results": 50,
                    },
                )
            ]
        )[0]
        matches: list[AgreementRecord] = []
        for urn in sorted(_collect_urns(raw)):
            record = self._read(urn)
            if (
                record is not None
                and (
                    record.vendor_name == vendor_name
                    or record.vendor_id == vendor_name
                )
                and record.obligation_id == obligation_id
            ):
                matches.append(record)
        if len(matches) > 1:
            raise RuntimeError("DataHub registry contains duplicate exact agreement keys")
        elapsed = max(0, round((perf_counter() - started) * 1000))
        return LookupResult(
            status="MATCH" if matches else "NOT_FOUND",
            match=matches[0] if matches else None,
            lookup_latency_ms=elapsed,
        )

    def list_registered(self) -> list[AgreementRecord]:
        raw = self.search_fn(
            [
                (
                    "search",
                    {
                        "query": "covenant governed agreement",
                        "num_results": 100,
                    },
                )
            ]
        )[0]
        records = {
            record.registry_urn: record
            for urn in _collect_urns(raw)
            if (record := self._read(urn)) is not None
        }
        return sorted(
            records.values(),
            key=lambda item: (item.vendor_name, item.obligation_id),
        )

    def _read(self, urn: str) -> AgreementRecord | None:
        if not urn.startswith("urn:li:domain:"):
            return None
        aspect = self.graph_fn().get_aspect(urn, DomainPropertiesClass)
        if aspect is None:
            return None
        properties = dict(aspect.customProperties or {})
        if properties.get(REGISTRY_PREFIX + "kind") != REGISTRY_KIND:
            return None
        try:
            path = properties[REGISTRY_PREFIX + "prior_document_path"]
            expected_hash = properties[REGISTRY_PREFIX + "prior_document_hash"]
            actual_hash = sha256(resolve_prior_document(path).read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                raise RuntimeError("registered prior document hash does not match DataHub")
            return AgreementRecord(
                registry_urn=urn,
                vendor_id=properties[REGISTRY_PREFIX + "vendor_id"],
                vendor_name=properties[REGISTRY_PREFIX + "vendor_name"],
                obligation_id=properties[REGISTRY_PREFIX + "obligation_id"],
                current_version=properties[REGISTRY_PREFIX + "current_version"],
                effective_date=properties[REGISTRY_PREFIX + "effective_date"],
                prior_document_hash=expected_hash,
                prior_document_path=path,
                registered_at=properties[REGISTRY_PREFIX + "registered_at"],
                description=aspect.description or "",
            )
        except KeyError as exc:
            raise RuntimeError("DataHub registry record is missing a required property") from exc


def _collect_urns(value: Any) -> set[str]:
    urns: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "urn" and isinstance(item, str):
                urns.add(item)
            else:
                urns.update(_collect_urns(item))
    elif isinstance(value, list):
        for item in value:
            urns.update(_collect_urns(item))
    return urns
