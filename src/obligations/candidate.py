from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


SUPPORTED_USAGES = {
    "internal_analytics",
    "ml_training",
    "customer_redistribution",
    "anonymized_derivative",
}
REQUIRED_USAGES = SUPPORTED_USAGES
LIFECYCLE_STATES = {
    "CANDIDATE",
    "AWAITING_REVIEW",
    "ACTIVE",
    "REJECTED",
    "SUPERSEDED",
}
SYNTHETIC_APPROVAL_LABEL = "SYNTHETIC TEST APPROVAL"

CANDIDATE_DELTA_SCHEMA = {
    "$id": "covenant.candidate_delta.v1",
    "required": [
        "candidate_delta_id",
        "obligation_id",
        "supersedes_version",
        "candidate_version",
        "effective_at",
        "usage_classes",
        "rules",
        "material_change",
        "evidence_status",
        "unresolved_gaps",
        "source_documents",
        "extractor",
        "lifecycle_state",
    ],
    "usage_class_enum": sorted(SUPPORTED_USAGES),
    "effect_enum": ["permitted", "prohibited", "review_required"],
    "lifecycle_state_enum": sorted(LIFECYCLE_STATES),
}

SUBJECT_ALIASES = (
    ("previously created anonymized derivatives", "anonymized_derivative"),
    ("creation of anonymized derivatives", "anonymized_derivative"),
    ("anonymized derivatives", "anonymized_derivative"),
    ("machine-learning training", "ml_training"),
    ("machine learning training", "ml_training"),
    ("customer redistribution", "customer_redistribution"),
    ("internal analytics", "internal_analytics"),
)
ACTION_PATTERNS = (
    (re.compile(r"\b(?:remains?|is|are) allowed\b", re.I), "permitted"),
    (re.compile(r"\b(?:is|are) prohibited\b", re.I), "prohibited"),
    (re.compile(r"\brequires? human review\b", re.I), "review_required"),
)
HEADER = re.compile(r"License\s+(?P<obligation>[A-Z0-9-]+)\s+—\s+Version\s+(?P<version>\d+)")
EFFECTIVE = re.compile(r"Effective\s+(?P<date>[A-Z][a-z]+\s+\d{1,2},\s+\d{4})")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def stable_json_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _header(text: str) -> tuple[str | None, int | None]:
    match = HEADER.search(text)
    if not match:
        return None, None
    return match.group("obligation"), int(match.group("version"))


def _effective_at(text: str) -> str | None:
    match = EFFECTIVE.search(text)
    if not match:
        return None
    value = datetime.strptime(match.group("date"), "%B %d, %Y")
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _subject(line: str) -> tuple[str | None, str | None]:
    lowered = line.lower()
    for phrase, usage in SUBJECT_ALIASES:
        if phrase in lowered:
            return usage, phrase
    if line.lstrip().startswith("-"):
        raw = line.lstrip()[1:].strip()
        subject = re.split(
            r"\s+(?:remains?|is|are|may|requires?)\b", raw, maxsplit=1, flags=re.I
        )[0]
        slug = re.sub(r"[^a-z0-9]+", "_", subject.lower()).strip("_")
        return slug or None, subject or None
    return None, None


def _effect(line: str) -> str | None:
    for pattern, effect in ACTION_PATTERNS:
        if pattern.search(line):
            return effect
    return None


def _citation(
    line: str, line_number: int, source_ref: str, source_hash: str
) -> dict[str, Any]:
    return {
        "source_ref": source_ref,
        "source_sha256": source_hash,
        "line_start": line_number,
        "line_end": line_number,
        "quote": line.strip(),
    }


def _extract_rules(text: str, source_ref: str) -> tuple[list[dict[str, Any]], list[str]]:
    rules: list[dict[str, Any]] = []
    gaps: list[str] = []
    source_hash = sha256_text(text)
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.lstrip().startswith("-"):
            continue
        usage, _ = _subject(line)
        if not usage:
            continue
        if re.search(r"\bmay\b|\bor\b", line, re.I):
            gaps.append(f"ambiguous_rule:{usage}")
            continue
        effect = _effect(line)
        if usage not in SUPPORTED_USAGES:
            gaps.append(f"unsupported_usage_class:{usage}")
        if effect is None:
            gaps.append(f"ambiguous_rule:{usage}")
            continue
        rules.append(
            {
                "usage_class": usage,
                "effect": effect,
                "evidence_status": "SUPPORTED"
                if usage in SUPPORTED_USAGES
                else "UNSUPPORTED",
                "citation": _citation(line, number, source_ref, source_hash),
            }
        )
    return rules, gaps


def _prior_effects(text: str, source_ref: str) -> dict[str, str]:
    rules, _ = _extract_rules(text, source_ref)
    if rules:
        return {rule["usage_class"]: rule["effect"] for rule in rules}
    lowered = text.lower()
    if "permits" not in lowered:
        return {}
    effects: dict[str, str] = {}
    for phrase, usage in SUBJECT_ALIASES:
        if phrase in lowered:
            effects[usage] = "permitted"
    return effects


def extract_candidate_text(
    old_text: str,
    new_text: str,
    *,
    old_ref: str,
    new_ref: str,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    now = now or (lambda: datetime.now(timezone.utc))
    old_obligation, old_version = _header(old_text)
    obligation, candidate_version = _header(new_text)
    rules, gaps = _extract_rules(new_text, new_ref)
    effective_at = _effective_at(new_text)
    if effective_at is None:
        gaps.append("missing_effective_date")
    if obligation is None:
        gaps.append("missing_obligation_id")
    if candidate_version is None:
        gaps.append("missing_candidate_version")
    if old_obligation and obligation and old_obligation != obligation:
        gaps.append("obligation_id_mismatch")

    by_usage: dict[str, set[str]] = {}
    for rule in rules:
        by_usage.setdefault(rule["usage_class"], set()).add(rule["effect"])
    for usage, effects in by_usage.items():
        if len(effects) > 1:
            gaps.append(f"contradictory_rule:{usage}")

    current_effects = {
        rule["usage_class"]: rule["effect"]
        for rule in rules
        if rule["usage_class"] in SUPPORTED_USAGES
    }
    prior_effects = _prior_effects(old_text, old_ref)
    material_change = any(
        prior_effects.get(usage) != current_effects.get(usage)
        for usage in SUPPORTED_USAGES
    )
    source_documents = [
        {
            "role": "superseded",
            "source_ref": old_ref,
            "version": old_version,
            "sha256": sha256_text(old_text),
        },
        {
            "role": "candidate",
            "source_ref": new_ref,
            "version": candidate_version,
            "sha256": sha256_text(new_text),
        },
    ]
    stable_identity = {
        "obligation_id": obligation,
        "supersedes_version": old_version,
        "candidate_version": candidate_version,
        "effective_at": effective_at,
        "rules": sorted(
            [
                {
                    "usage_class": item["usage_class"],
                    "effect": item["effect"],
                    "evidence_status": item["evidence_status"],
                    "citation": {
                        key: value
                        for key, value in item["citation"].items()
                        if key != "source_ref"
                    },
                }
                for item in rules
            ],
            key=lambda item: (item["usage_class"], item["effect"]),
        ),
        "source_documents": [
            {
                "role": item["role"],
                "version": item["version"],
                "sha256": item["sha256"],
            }
            for item in source_documents
        ],
    }
    warnings = []
    if re.search(r"ignore (?:all |any |prior )?instructions", new_text, re.I):
        warnings.append("instruction_like_source_text_ignored")
    return {
        "schema_version": "covenant.candidate_delta.v1",
        "candidate_delta_id": f"DELTA-{stable_json_hash(stable_identity)[:20]}",
        "obligation_id": obligation,
        "supersedes_version": old_version,
        "candidate_version": candidate_version,
        "effective_at": effective_at,
        "rules": rules,
        "usage_classes": {
            "permitted": sorted(
                item["usage_class"] for item in rules if item["effect"] == "permitted"
            ),
            "prohibited": sorted(
                item["usage_class"] for item in rules if item["effect"] == "prohibited"
            ),
            "review_required": sorted(
                item["usage_class"]
                for item in rules
                if item["effect"] == "review_required"
            ),
        },
        "material_change": material_change,
        "evidence_status": "SUPPORTED" if not gaps else "GAPS_PRESENT",
        "unresolved_gaps": sorted(set(gaps)),
        "source_warnings": warnings,
        "source_documents": source_documents,
        "extractor": {
            "identity": "covenant.deterministic_literal_extractor.v1",
            "extracted_at": now().astimezone(timezone.utc).isoformat(),
        },
        "lifecycle_state": "CANDIDATE",
    }


def extract_candidate(
    old_path: Path,
    new_path: Path,
    *,
    now: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    old_text = old_path.read_text()
    new_text = new_path.read_text()
    cwd = Path.cwd().resolve()

    def stable_ref(path: Path) -> str:
        resolved = path.resolve()
        try:
            return resolved.relative_to(cwd).as_posix()
        except ValueError:
            return path.name

    old_ref = stable_ref(old_path)
    new_ref = stable_ref(new_path)
    candidate = extract_candidate_text(
        old_text,
        new_text,
        old_ref=old_ref,
        new_ref=new_ref,
        now=now,
    )
    return candidate, {old_ref: old_text, new_ref: new_text}


def validate_candidate(
    candidate: dict[str, Any],
    documents: dict[str, str],
    *,
    current_active_version: int,
) -> dict[str, Any]:
    errors = list(candidate.get("unresolved_gaps", []))
    required_fields = set(CANDIDATE_DELTA_SCHEMA["required"])
    for field in sorted(required_fields - candidate.keys()):
        errors.append(f"missing_schema_field:{field}")
    if candidate.get("lifecycle_state") not in LIFECYCLE_STATES:
        errors.append("invalid_lifecycle_state")
    if candidate.get("evidence_status") not in {"SUPPORTED", "GAPS_PRESENT"}:
        errors.append("invalid_evidence_status")
    candidate_version = candidate.get("candidate_version")
    if not isinstance(candidate_version, int) or candidate_version <= current_active_version:
        errors.append("stale_candidate_version")

    for source in candidate.get("source_documents", []):
        ref = source.get("source_ref")
        text = documents.get(ref)
        if text is None:
            errors.append(f"missing_source_document:{ref}")
        elif sha256_text(text) != source.get("sha256"):
            errors.append(f"source_hash_mismatch:{ref}")

    seen: dict[str, set[str]] = {}
    for rule in candidate.get("rules", []):
        usage = rule.get("usage_class")
        effect = rule.get("effect")
        if usage not in SUPPORTED_USAGES:
            errors.append(f"unsupported_usage_class:{usage}")
        seen.setdefault(usage, set()).add(effect)
        citation = rule.get("citation") or {}
        ref = citation.get("source_ref")
        text = documents.get(ref, "")
        lines = text.splitlines()
        start = citation.get("line_start")
        end = citation.get("line_end")
        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
            errors.append(f"invalid_citation_location:{usage}")
            continue
        actual = "\n".join(lines[start - 1 : end]).strip()
        if actual != citation.get("quote"):
            errors.append(f"citation_text_mismatch:{usage}")
            continue
        cited_usage, _ = _subject(actual)
        cited_effect = _effect(actual)
        if cited_usage != usage or cited_effect != effect:
            errors.append(f"citation_claim_mismatch:{usage}")
        if citation.get("source_sha256") != sha256_text(text):
            errors.append(f"citation_source_hash_mismatch:{usage}")

    for usage, effects in seen.items():
        if len(effects) > 1:
            errors.append(f"contradictory_rule:{usage}")
    for usage in sorted(REQUIRED_USAGES - seen.keys()):
        errors.append(f"missing_required_rule:{usage}")
    expected_usage_classes = {
        effect: sorted(usage for usage, effects in seen.items() if effect in effects)
        for effect in CANDIDATE_DELTA_SCHEMA["effect_enum"]
    }
    if candidate.get("usage_classes") != expected_usage_classes:
        errors.append("usage_class_summary_mismatch")
    errors = sorted(set(errors))
    return {
        "valid": not errors,
        "errors": errors,
        "candidate_delta_id": candidate.get("candidate_delta_id"),
    }


def submit_for_review(
    candidate: dict[str, Any], validation: dict[str, Any], *, now: Callable[[], datetime] | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not validation.get("valid"):
        raise ValueError("candidate validation failed; review transition refused")
    if not candidate.get("material_change"):
        raise ValueError("candidate contains no material change; review transition refused")
    if candidate.get("lifecycle_state") != "CANDIDATE":
        raise ValueError("only a CANDIDATE may enter review")
    now = now or (lambda: datetime.now(timezone.utc))
    updated = deepcopy(candidate)
    updated["lifecycle_state"] = "AWAITING_REVIEW"
    event = {
        "transition_id": f"TRANSITION-{stable_json_hash([candidate['candidate_delta_id'], 'AWAITING_REVIEW'])[:20]}",
        "candidate_delta_id": candidate["candidate_delta_id"],
        "prior_state": "CANDIDATE",
        "new_state": "AWAITING_REVIEW",
        "actor_class": "agent_system_submission",
        "recorded_at": now().astimezone(timezone.utc).isoformat(),
        "rationale": "evidence-bound candidate passed deterministic validation",
    }
    return updated, event


def activate_synthetic_test(
    candidate: dict[str, Any],
    *,
    label: str,
    actor: str,
    rationale: str,
    now: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if label != SYNTHETIC_APPROVAL_LABEL:
        raise ValueError("activation requires the literal SYNTHETIC TEST APPROVAL label")
    if candidate.get("lifecycle_state") != "AWAITING_REVIEW":
        raise ValueError("only an AWAITING_REVIEW candidate may be activated")
    if not actor.startswith("synthetic_"):
        raise ValueError("synthetic activation actor must be visibly synthetic")
    now = now or (lambda: datetime.now(timezone.utc))
    updated = deepcopy(candidate)
    updated["lifecycle_state"] = "ACTIVE"
    activation_id = f"ACTIVATION-{stable_json_hash([candidate['candidate_delta_id'], label, actor])[:20]}"
    event = {
        "activation_id": activation_id,
        "candidate_delta_id": candidate["candidate_delta_id"],
        "prior_state": "AWAITING_REVIEW",
        "new_state": "ACTIVE",
        "label": label,
        "actor": actor,
        "actor_class": "synthetic_test_reviewer",
        "recorded_at": now().astimezone(timezone.utc).isoformat(),
        "rationale": rationale,
    }
    updated["activation"] = event
    return updated, event


def active_candidate_policy(candidate: dict[str, Any]) -> dict[str, Any]:
    if candidate.get("lifecycle_state") != "ACTIVE":
        raise ValueError("candidate is not ACTIVE")
    rules: dict[str, dict[str, str]] = {}
    for rule in candidate["rules"]:
        usage = rule["usage_class"]
        effect = rule["effect"]
        if effect == "permitted":
            disposition, state, suffix = "allowed", "recommendation_recorded", "allowed"
        elif effect == "review_required":
            disposition, state, suffix = "human_review", "awaiting_human_review", "review"
        elif effect == "prohibited" and usage == "ml_training":
            disposition, state, suffix = "remediate", "awaiting_human_approval", "prohibited_rebuild_or_deprecate"
        elif effect == "prohibited" and usage == "customer_redistribution":
            disposition, state, suffix = "stop_proposed", "awaiting_human_approval", "prohibited"
        else:
            disposition, state, suffix = "human_review", "awaiting_human_review", "unsupported_effect_review"
        rules[usage] = {
            "disposition": disposition,
            "decision_state": state,
            "rule": f"v{candidate['candidate_version']}.{usage}.{suffix}",
        }
    return {
        "obligation_id": candidate["obligation_id"],
        "supersedes_version": candidate["supersedes_version"],
        "active_version": candidate["candidate_version"],
        "effective_at": candidate["effective_at"],
        "candidate_delta_id": candidate["candidate_delta_id"],
        "activation_id": candidate["activation"]["activation_id"],
        "source_documents": candidate["source_documents"],
        "rules": rules,
        "default": {
            "disposition": "human_review",
            "decision_state": "awaiting_evidence",
            "rule": f"v{candidate['candidate_version']}.missing_or_unknown_usage.review",
        },
    }
