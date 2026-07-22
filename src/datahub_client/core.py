from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

import yaml
from datahub.emitter.mce_builder import make_dataset_urn
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.ingestion.graph.client import DataHubGraph
from datahub.ingestion.graph.config import DatahubClientConfig
from datahub.metadata.schema_classes import (
    CorpGroupInfoClass,
    DatasetPropertiesClass,
    DomainPropertiesClass,
    DomainsClass,
    GlobalTagsClass,
    GlossaryTermAssociationClass,
    GlossaryTermInfoClass,
    GlossaryTermsClass,
    OwnerClass,
    OwnershipClass,
    OwnershipTypeClass,
    StatusClass,
    TagAssociationClass,
    UpstreamClass,
    UpstreamLineageClass,
    AuditStampClass,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "fixtures" / "covenant_graph.yaml"


def load_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def gms_url() -> str:
    return os.getenv("DATAHUB_GMS_URL", "http://localhost:8080")


def emitter() -> DatahubRestEmitter:
    return DatahubRestEmitter(gms_url(), token=os.getenv("DATAHUB_TOKEN") or None)


def graph() -> DataHubGraph:
    return DataHubGraph(DatahubClientConfig(server=gms_url(), token=os.getenv("DATAHUB_TOKEN") or None))


def dataset_urn(entity_id: str, fixture: dict[str, Any] | None = None) -> str:
    fixture = fixture or load_fixture()
    return make_dataset_urn(
        fixture["platform"], f"northstar.{entity_id}", fixture["environment"]
    )


def owner_urn(owner_id: str) -> str:
    return f"urn:li:corpGroup:northstar_{owner_id}"


def domain_urn(domain_id: str) -> str:
    return f"urn:li:domain:{domain_id}"


def tag_urn(tag: str) -> str:
    return f"urn:li:tag:{tag}"


def obligation_urn(obligation_id: str) -> str:
    return f"urn:li:glossaryTerm:{obligation_id}"


def emit_aspect(urn: str, aspect: Any, *, entity_type: str = "dataset") -> None:
    emitter().emit(
        MetadataChangeProposalWrapper(
            entityType=entity_type, entityUrn=urn, aspect=aspect
        )
    )


def seed_fixture(
    fixture: dict[str, Any] | None = None, *, preserve_decisions: bool = True
) -> dict[str, int]:
    fixture = fixture or load_fixture()
    out = emitter()
    hub = graph()
    out.test_connection()

    durn = domain_urn(fixture["domain"]["id"])
    out.emit(
        MetadataChangeProposalWrapper(
            entityType="domain",
            entityUrn=durn,
            aspect=DomainPropertiesClass(
                name=fixture["domain"]["name"],
                description="Synthetic Gate 0 domain for Northstar Commerce.",
            ),
        )
    )
    for owner_id, display_name in fixture["owners"].items():
        out.emit(
            MetadataChangeProposalWrapper(
                entityType="corpGroup",
                entityUrn=owner_urn(owner_id),
                aspect=CorpGroupInfoClass(
                    admins=[], members=[], groups=[], displayName=display_name,
                    description="Synthetic Gate 0 ownership group.",
                ),
            )
        )

    ourn = obligation_urn(fixture["obligation"]["id"])
    if hub.get_aspect(ourn, GlossaryTermInfoClass) is None:
        for version, definition in (
            (3, "Synthetic Atlas license v3: analytics, ML training, redistribution, and anonymized derivatives permitted."),
            (4, "Synthetic Atlas license v4 effective 2026-08-01: analytics allowed; ML training and redistribution prohibited; preexisting anonymized derivatives require review."),
        ):
            out.emit(
                MetadataChangeProposalWrapper(
                    entityType="glossaryTerm",
                    entityUrn=ourn,
                    aspect=GlossaryTermInfoClass(
                        id=fixture["obligation"]["id"],
                        name=f"Atlas License {fixture['obligation']['id']}",
                        definition=definition,
                        termSource="INTERNAL",
                        sourceRef=f"fixtures/atlas_license_v{version}.md",
                        customProperties={
                            "covenant.synthetic": "true",
                            "covenant.obligation_version": str(version),
                            "covenant.effective_at": "2026-08-01T00:00:00Z" if version == 4 else "superseded",
                        },
                    ),
                )
            )

    incoming: dict[str, list[str]] = {e["id"]: [] for e in fixture["entities"]}
    for upstream, downstream in fixture["edges"]:
        incoming[downstream].append(upstream)

    for entity in fixture["entities"]:
        urn = dataset_urn(entity["id"], fixture)
        props = {
            "covenant.synthetic": "true",
            "covenant.entity_id": entity["id"],
            "covenant.kind": entity["kind"],
            "covenant.terminal": str(entity["terminal"]).lower(),
            "covenant.usage_class": entity["usage_class"],
            "covenant.obligation_id": fixture["obligation"]["id"]
            if entity["id"] == "vendor_demographics_raw"
            else "",
            "covenant.active_obligation_version": str(fixture["obligation"]["active_version"]),
            "covenant.effective_at": fixture["obligation"]["effective_at"],
        }
        current = hub.get_aspect(urn, DatasetPropertiesClass)
        if preserve_decisions and current and current.customProperties:
            props.update(
                {
                    key: value
                    for key, value in current.customProperties.items()
                    if key.startswith("covenant.decision.")
                }
            )
        aspects: Iterable[Any] = (
            DatasetPropertiesClass(
                name=entity["name"],
                description=(
                    f"SYNTHETIC Gate 0 {entity['kind']} for fictional Northstar Commerce. "
                    "Terminal type is represented as a DataHub dataset equivalent where noted."
                ),
                customProperties=props,
            ),
            OwnershipClass(
                owners=[
                    OwnerClass(
                        owner=owner_urn(entity["owner"]),
                        type=OwnershipTypeClass.TECHNICAL_OWNER,
                    )
                ]
            ),
            DomainsClass(domains=[durn]),
            GlobalTagsClass(tags=[TagAssociationClass(tag=tag_urn("CovenantSynthetic"))]),
            StatusClass(removed=False),
        )
        for aspect in aspects:
            out.emit(MetadataChangeProposalWrapper(entityType="dataset", entityUrn=urn, aspect=aspect))
        if entity["id"] == "vendor_demographics_raw":
            out.emit(
                MetadataChangeProposalWrapper(
                    entityType="dataset",
                    entityUrn=urn,
                    aspect=GlossaryTermsClass(
                        terms=[GlossaryTermAssociationClass(urn=ourn)],
                        auditStamp=AuditStampClass(
                            time=1784678400000,
                            actor="urn:li:corpuser:covenant_gate0_agent",
                            message="SYNTHETIC Gate 0 obligation association",
                        ),
                    ),
                )
            )
        if incoming[entity["id"]]:
            out.emit(
                MetadataChangeProposalWrapper(
                    entityType="dataset",
                    entityUrn=urn,
                    aspect=UpstreamLineageClass(
                        upstreams=[
                            UpstreamClass(
                                dataset=dataset_urn(upstream, fixture),
                                type="TRANSFORMED",
                            )
                            for upstream in sorted(incoming[entity["id"]])
                        ]
                    ),
                )
            )
        else:
            out.emit(
                MetadataChangeProposalWrapper(
                    entityType="dataset", entityUrn=urn,
                    aspect=UpstreamLineageClass(upstreams=[]),
                )
            )
    return {"entities": len(fixture["entities"]), "edges": len(fixture["edges"]), "owners": len(fixture["owners"]), "domains": 1}


def soft_delete_entities(entity_ids: Iterable[str]) -> None:
    out = emitter()
    fixture = load_fixture()
    for entity_id in entity_ids:
        out.emit(
            MetadataChangeProposalWrapper(
                entityType="dataset",
                entityUrn=dataset_urn(entity_id, fixture),
                aspect=StatusClass(removed=True),
            )
        )
