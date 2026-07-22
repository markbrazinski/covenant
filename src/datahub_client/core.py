from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

import yaml
from datahub.emitter.mce_builder import (
    make_dashboard_urn,
    make_data_flow_urn,
    make_data_job_urn_with_flow,
    make_data_process_instance_urn,
    make_dataset_urn,
    make_ml_model_urn,
)
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.ingestion.graph.client import DataHubGraph
from datahub.ingestion.graph.config import DatahubClientConfig
from datahub.metadata.schema_classes import (
    AuditStampClass,
    AzkabanJobTypeClass,
    ChangeAuditStampsClass,
    CorpGroupInfoClass,
    DashboardInfoClass,
    DataFlowInfoClass,
    DataJobInfoClass,
    DataJobInputOutputClass,
    DataProcessInstanceInputClass,
    DataProcessInstanceOutputClass,
    DataProcessInstancePropertiesClass,
    DataProcessTypeClass,
    DatasetPropertiesClass,
    DomainPropertiesClass,
    DomainsClass,
    EdgeClass,
    GlobalTagsClass,
    GlossaryTermAssociationClass,
    GlossaryTermInfoClass,
    GlossaryTermsClass,
    MLModelPropertiesClass,
    OwnerClass,
    OwnershipClass,
    OwnershipTypeClass,
    StatusClass,
    TagAssociationClass,
    UpstreamClass,
    UpstreamLineageClass,
    VersionTagClass,
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


def entity_definition(entity_id: str, fixture: dict[str, Any] | None = None) -> dict[str, Any]:
    fixture = fixture or load_fixture()
    return next(entity for entity in fixture["entities"] if entity["id"] == entity_id)


def entity_urn(entity_id: str, fixture: dict[str, Any] | None = None) -> str:
    fixture = fixture or load_fixture()
    entity_type = entity_definition(entity_id, fixture).get("entity_type", "dataset")
    if entity_type == "dataset":
        return dataset_urn(entity_id, fixture)
    if entity_type == "dashboard":
        return make_dashboard_urn(fixture["platform"], f"northstar.{entity_id}")
    if entity_type == "mlModel":
        return make_ml_model_urn(
            fixture["platform"], f"northstar.{entity_id}", fixture["environment"]
        )
    if entity_type == "dataFlow":
        return make_data_flow_urn(
            fixture["platform"], f"northstar.{entity_id}", fixture["environment"]
        )
    if entity_type == "dataJob":
        flow_id = fixture["native_lineage"]["delivery"]["flow"]
        return make_data_job_urn_with_flow(
            entity_urn(flow_id, fixture), f"northstar.{entity_id}"
        )
    if entity_type == "dataProcessInstance":
        return make_data_process_instance_urn(f"northstar.{entity_id}")
    raise ValueError(f"unsupported fixture entity type: {entity_type}")


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


def property_contract(urn: str) -> tuple[type[Any], str]:
    """Return the native property aspect and entity type for a supported URN."""
    contracts: tuple[tuple[str, type[Any], str], ...] = (
        ("urn:li:dataset:", DatasetPropertiesClass, "dataset"),
        ("urn:li:dashboard:", DashboardInfoClass, "dashboard"),
        ("urn:li:mlModel:", MLModelPropertiesClass, "mlModel"),
        ("urn:li:dataFlow:", DataFlowInfoClass, "dataFlow"),
        ("urn:li:dataJob:", DataJobInfoClass, "dataJob"),
        (
            "urn:li:dataProcessInstance:",
            DataProcessInstancePropertiesClass,
            "dataProcessInstance",
        ),
    )
    for prefix, aspect_type, entity_type in contracts:
        if urn.startswith(prefix):
            return aspect_type, entity_type
    raise ValueError(f"unsupported Covenant entity type: {urn}")


def native_custom_properties(urn: str) -> dict[str, str]:
    """Read custom properties from the entity's native DataHub property aspect."""
    aspect_type, _ = property_contract(urn)
    aspect = graph().get_aspect(urn, aspect_type)
    if aspect is None:
        raise RuntimeError(f"missing native DataHub property aspect: {urn}")
    return dict(getattr(aspect, "customProperties", None) or {})


def native_name(urn: str) -> str:
    """Read the human-facing name from a native property aspect."""
    aspect_type, _ = property_contract(urn)
    aspect = graph().get_aspect(urn, aspect_type)
    if aspect is None:
        raise RuntimeError(f"missing native DataHub property aspect: {urn}")
    for field in ("name", "title"):
        value = getattr(aspect, field, None)
        if value:
            return value
    return urn


def seed_fixture(
    fixture: dict[str, Any] | None = None, *, preserve_decisions: bool = True
) -> dict[str, int]:
    fixture = fixture or load_fixture()
    out = emitter()
    hub = graph()
    out.test_connection()

    def base_properties(entity: dict[str, Any]) -> dict[str, str]:
        return {
            "covenant.synthetic": "true",
            "covenant.entity_id": entity["id"],
            "covenant.kind": entity["kind"],
            "covenant.terminal": str(entity["terminal"]).lower(),
            "covenant.usage_class": entity["usage_class"],
            "covenant.obligation_id": fixture["obligation"]["id"]
            if entity["id"] == "vendor_demographics_raw"
            else "",
            "covenant.active_obligation_version": str(
                fixture["obligation"]["active_version"]
            ),
            "covenant.effective_at": fixture["obligation"]["effective_at"],
        }

    def merge_receipt(
        urn: str, aspect_type: type[Any], properties: dict[str, str]
    ) -> dict[str, str]:
        current = hub.get_aspect(urn, aspect_type)
        current_props = getattr(current, "customProperties", None)
        if preserve_decisions and current_props:
            properties.update(
                {
                    key: value
                    for key, value in current_props.items()
                    if key.startswith("covenant.decision.")
                }
            )
        return properties

    def emit_common(urn: str, entity_type: str, entity: dict[str, Any]) -> None:
        is_control = entity["id"] == "unrelated_control"
        tags = set() if is_control else {tag_urn("CovenantSynthetic")}
        current_tags = hub.get_aspect(urn, GlobalTagsClass)
        if preserve_decisions and current_tags and not is_control:
            tags.update(
                association.tag
                for association in current_tags.tags
                if association.tag.startswith(
                    (
                        "urn:li:tag:CovenantDisposition_",
                        "urn:li:tag:CovenantDecisionState_",
                    )
                )
            )
        for aspect in (
            OwnershipClass(
                owners=[
                    OwnerClass(
                        owner=owner_urn(entity["owner"]),
                        type=OwnershipTypeClass.TECHNICAL_OWNER,
                    )
                ]
            ),
            DomainsClass(domains=[durn]),
            GlobalTagsClass(
                tags=[TagAssociationClass(tag=value) for value in sorted(tags)]
            ),
            StatusClass(removed=False),
        ):
            out.emit(
                MetadataChangeProposalWrapper(
                    entityType=entity_type, entityUrn=urn, aspect=aspect
                )
            )

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

    dataset_entities = [
        entity
        for entity in fixture["entities"]
        if entity.get("entity_type", "dataset") == "dataset"
    ]
    incoming: dict[str, list[str]] = {entity["id"]: [] for entity in dataset_entities}
    for upstream, downstream in fixture["edges"]:
        incoming[downstream].append(upstream)

    for entity in dataset_entities:
        urn = dataset_urn(entity["id"], fixture)
        props = (
            {}
            if entity["id"] == "unrelated_control"
            else merge_receipt(urn, DatasetPropertiesClass, base_properties(entity))
        )
        aspects: Iterable[Any] = (
            DatasetPropertiesClass(
                name=entity["name"],
                description=(
                    f"SYNTHETIC Covenant {entity['kind']} for fictional Northstar Commerce."
                ),
                customProperties=props,
            ),
        )
        for aspect in aspects:
            out.emit(
                MetadataChangeProposalWrapper(
                    entityType="dataset", entityUrn=urn, aspect=aspect
                )
            )
        emit_common(urn, "dataset", entity)
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

    # Remove the Gate 0 dataset equivalents from active search and lineage.
    for legacy_id in (
        "executive_dashboard",
        "churn_model_a",
        "propensity_model_b",
        "customer_delivery_job",
    ):
        out.emit(
            MetadataChangeProposalWrapper(
                entityType="dataset",
                entityUrn=dataset_urn(legacy_id, fixture),
                aspect=StatusClass(removed=True),
            )
        )

    actor = "urn:li:corpuser:covenant_gate0_agent"
    audit = AuditStampClass(time=1784678400000, actor=actor)

    # Native ML training processes bridge dataset features to native ML models.
    for model_id, training in fixture["native_lineage"]["model_training"].items():
        process = entity_definition(training["process"], fixture)
        process_urn = entity_urn(process["id"], fixture)
        input_urn = entity_urn(training["input"], fixture)
        model_urn = entity_urn(model_id, fixture)
        for aspect in (
            DataProcessInstancePropertiesClass(
                name=process["name"],
                created=audit,
                type=DataProcessTypeClass.BATCH_AD_HOC,
                customProperties=base_properties(process),
            ),
            DataProcessInstanceInputClass(
                inputs=[input_urn],
                inputEdges=[EdgeClass(destinationUrn=input_urn, created=audit)],
            ),
            DataProcessInstanceOutputClass(outputs=[model_urn]),
            StatusClass(removed=False),
        ):
            out.emit(
                MetadataChangeProposalWrapper(
                    entityType="dataProcessInstance",
                    entityUrn=process_urn,
                    aspect=aspect,
                )
            )

    dashboard = entity_definition("executive_dashboard", fixture)
    dashboard_urn = entity_urn(dashboard["id"], fixture)
    dashboard_input = entity_urn(
        fixture["native_lineage"]["dashboard_inputs"][dashboard["id"]], fixture
    )
    out.emit(
        MetadataChangeProposalWrapper(
            entityType="dashboard",
            entityUrn=dashboard_urn,
            aspect=DashboardInfoClass(
                title=dashboard["name"],
                description="SYNTHETIC native DataHub Dashboard for fictional Northstar Commerce.",
                lastModified=ChangeAuditStampsClass(lastModified=audit),
                customProperties=merge_receipt(
                    dashboard_urn, DashboardInfoClass, base_properties(dashboard)
                ),
                datasets=[],
                datasetEdges=[EdgeClass(destinationUrn=dashboard_input, created=audit)],
            ),
        )
    )
    emit_common(dashboard_urn, "dashboard", dashboard)

    for model_id, training in fixture["native_lineage"]["model_training"].items():
        model = entity_definition(model_id, fixture)
        model_urn = entity_urn(model_id, fixture)
        out.emit(
            MetadataChangeProposalWrapper(
                entityType="mlModel",
                entityUrn=model_urn,
                aspect=MLModelPropertiesClass(
                    name=model["name"],
                    description="SYNTHETIC native DataHub MLModel for fictional Northstar Commerce.",
                    version=VersionTagClass(versionTag="4"),
                    trainingJobs=[entity_urn(training["process"], fixture)],
                    customProperties=merge_receipt(
                        model_urn, MLModelPropertiesClass, base_properties(model)
                    ),
                ),
            )
        )
        emit_common(model_urn, "mlModel", model)

    delivery = fixture["native_lineage"]["delivery"]
    flow = entity_definition(delivery["flow"], fixture)
    flow_urn = entity_urn(flow["id"], fixture)
    out.emit(
        MetadataChangeProposalWrapper(
            entityType="dataFlow",
            entityUrn=flow_urn,
            aspect=DataFlowInfoClass(
                name=flow["name"],
                description="SYNTHETIC native DataHub DataFlow for fictional Northstar Commerce.",
                env=fixture["environment"],
                customProperties=base_properties(flow),
            ),
        )
    )
    emit_common(flow_urn, "dataFlow", flow)

    job = entity_definition(delivery["job"], fixture)
    job_urn = entity_urn(job["id"], fixture)
    job_input = entity_urn(delivery["input"], fixture)
    out.emit(
        MetadataChangeProposalWrapper(
            entityType="dataJob",
            entityUrn=job_urn,
            aspect=DataJobInfoClass(
                name=job["name"],
                type=AzkabanJobTypeClass.COMMAND,
                description="SYNTHETIC native DataHub DataJob for fictional Northstar Commerce.",
                flowUrn=flow_urn,
                env=fixture["environment"],
                customProperties=merge_receipt(
                    job_urn, DataJobInfoClass, base_properties(job)
                ),
            ),
        )
    )
    out.emit(
        MetadataChangeProposalWrapper(
            entityType="dataJob",
            entityUrn=job_urn,
            aspect=DataJobInputOutputClass(
                inputDatasets=[],
                outputDatasets=[],
                inputDatasetEdges=[EdgeClass(destinationUrn=job_input, created=audit)],
            ),
        )
    )
    emit_common(job_urn, "dataJob", job)

    native_entities = [
        entity
        for entity in fixture["entities"]
        if entity.get("entity_type", "dataset") != "dataset"
    ]
    return {
        "datasets": len(dataset_entities),
        "native_entities": len(native_entities),
        "dataset_edges": len(fixture["edges"]),
        "owners": len(fixture["owners"]),
        "domains": 1,
    }


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
