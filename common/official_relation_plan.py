from typing import Any, Callable

from runtime_manifest import (
    _require_enum_value,
    _require_list,
    _require_mapping,
    resolve_artifact_by_role,
)

_RELATION_CARDINALITIES = {"single", "many"}
_RELATION_AGGREGATIONS = {"single", "mean", "min", "max", "all_or_nothing"}
_RELATION_KINDS = {
    "tabular_alignment",
    "exact_match",
    "execute_against",
    "structured_validation",
}
_VALIDATOR_KINDS = {
    "none",
    "csv_columns",
    "json_document",
    "json_schema",
    "archive_layout",
}


def _require_relation_artifact_rules(
    template: dict[str, Any],
    lane: str,
    *,
    fail_runtime: Callable[[str], None],
) -> list[dict[str, Any]]:
    rules = _require_list(template, lane, fail_runtime=fail_runtime)
    if len(rules) == 0:
        fail_runtime(f"Runtime manifest relation_plan template {lane} must not be empty.")

    normalized_rules: list[dict[str, Any]] = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            fail_runtime(
                f"Runtime manifest relation_plan template {lane}[{index}] must be an object."
            )
        accepted_validator_kinds = rule.get("acceptedValidatorKinds")
        if (
            not isinstance(accepted_validator_kinds, list)
            or len(accepted_validator_kinds) == 0
            or not all(
                isinstance(kind, str) and kind in _VALIDATOR_KINDS
                for kind in accepted_validator_kinds
            )
        ):
            fail_runtime(
                f"Runtime manifest relation_plan template {lane}[{index}] must declare acceptedValidatorKinds using supported validator kinds."
            )

        required_file = rule.get("requiredFile")
        if required_file is not None and not isinstance(required_file, dict):
            fail_runtime(
                f"Runtime manifest relation_plan template {lane}[{index}].requiredFile must be an object when present."
            )

        normalized_rules.append(
            {
                "acceptedValidatorKinds": list(accepted_validator_kinds),
                "requiredFile": required_file,
            }
        )

    return normalized_rules


def _require_relation_plan(
    runtime_manifest: dict[str, Any],
    *,
    fail_runtime: Callable[[str], None],
) -> dict[str, Any]:
    scorer = runtime_manifest.get("scorer")
    if not isinstance(scorer, dict) or scorer.get("kind") != "official":
        fail_runtime(
            "Official scorer relation_plan helpers require scorer.kind=official. Next step: use the generic runtime_manifest helpers for external scorers and retry."
        )

    relation_plan = runtime_manifest.get("relation_plan")
    if not isinstance(relation_plan, dict):
        fail_runtime(
            "Runtime manifest relation_plan is required for official scorers. Next step: republish the challenge with a scorer relation plan and retry."
        )

    templates = _require_list(relation_plan, "templates", fail_runtime=fail_runtime)
    if len(templates) == 0:
        fail_runtime("Runtime manifest relation_plan.templates must not be empty.")

    normalized_templates: list[dict[str, Any]] = []
    for index, template in enumerate(templates):
        if not isinstance(template, dict):
            fail_runtime(
                f"Runtime manifest relation_plan.templates[{index}] must be an object."
            )
        kind = _require_enum_value(
            template,
            "kind",
            allowed_values=_RELATION_KINDS,
            fail_runtime=fail_runtime,
        )
        cardinality = _require_enum_value(
            template,
            "cardinality",
            allowed_values=_RELATION_CARDINALITIES,
            fail_runtime=fail_runtime,
        )
        aggregation = _require_enum_value(
            template,
            "aggregation",
            allowed_values=_RELATION_AGGREGATIONS,
            fail_runtime=fail_runtime,
        )
        normalized_templates.append(
            {
                "kind": kind,
                "cardinality": cardinality,
                "aggregation": aggregation,
                "evaluation": _require_relation_artifact_rules(
                    template,
                    "evaluation",
                    fail_runtime=fail_runtime,
                ),
                "submission": _require_relation_artifact_rules(
                    template,
                    "submission",
                    fail_runtime=fail_runtime,
                ),
            }
        )

    return {"templates": normalized_templates}


def list_relation_evaluation_roles(relation: dict[str, Any]) -> list[str]:
    kind = relation.get("kind")
    if kind in {"tabular_alignment", "exact_match", "structured_validation"}:
        value = relation.get("evaluation_role")
        return [value] if isinstance(value, str) else []
    if kind == "execute_against":
        value = relation.get("harness_role")
        return [value] if isinstance(value, str) else []
    return []


def list_relation_submission_roles(relation: dict[str, Any]) -> list[str]:
    kind = relation.get("kind")
    if kind in {"tabular_alignment", "exact_match", "structured_validation"}:
        value = relation.get("submission_role")
        return [value] if isinstance(value, str) else []
    if kind == "execute_against":
        value = relation.get("solution_role")
        return [value] if isinstance(value, str) else []
    return []


def describe_relation(relation: dict[str, Any]) -> str:
    kind = relation.get("kind", "unknown")
    evaluation_roles = ",".join(list_relation_evaluation_roles(relation))
    submission_roles = ",".join(list_relation_submission_roles(relation))
    return f"{kind}:{evaluation_roles}->{submission_roles}"


def match_relation_to_template(
    relation: dict[str, Any],
    template: dict[str, Any],
) -> bool:
    return (
        relation.get("kind") == template.get("kind")
        and len(list_relation_evaluation_roles(relation))
        == len(template["evaluation"])
        and len(list_relation_submission_roles(relation))
        == len(template["submission"])
    )


def require_relation_plan_template(
    runtime_manifest: dict[str, Any],
    *,
    kind: str,
    fail_runtime: Callable[[str], None],
) -> dict[str, Any]:
    templates = _require_relation_plan(
        runtime_manifest,
        fail_runtime=fail_runtime,
    )["templates"]
    matches = [template for template in templates if template["kind"] == kind]
    if len(matches) != 1:
        fail_runtime(
            f"Runtime manifest relation_plan must contain exactly one template for relation kind {kind}."
        )
    return matches[0]


def _validate_relation_artifact(
    *,
    lane: str,
    role: str,
    rule: dict[str, Any],
    artifact: dict[str, Any],
    fail_runtime: Callable[[str], None],
) -> None:
    validator_kind = artifact["slot"].get("validator", {}).get("kind")
    if validator_kind not in rule["acceptedValidatorKinds"]:
        fail_runtime(
            f"Runtime manifest relation_plan rejects {lane} role {role} with validator.kind={validator_kind}."
        )

    required_file = rule.get("requiredFile")
    if not isinstance(required_file, dict):
        return

    required_extension = required_file.get("extension")
    if required_extension and artifact["slot"].get("file", {}).get("extension") != required_extension:
        fail_runtime(
            f"Runtime manifest relation_plan requires {lane} role {role} to use extension {required_extension}."
        )

    required_mime_type = required_file.get("mimeType")
    if required_mime_type and artifact["slot"].get("file", {}).get("mime_type") != required_mime_type:
        fail_runtime(
            f"Runtime manifest relation_plan requires {lane} role {role} to use mime_type {required_mime_type}."
        )


def list_matching_relations(
    runtime_manifest: dict[str, Any],
    *,
    template: dict[str, Any],
    fail_runtime: Callable[[str], None],
) -> list[dict[str, Any]]:
    relations = runtime_manifest["artifact_contract"].get("relations", [])
    matches = [
        relation
        for relation in relations
        if isinstance(relation, dict) and match_relation_to_template(relation, template)
    ]

    if len(matches) == 0:
        fail_runtime(
            f"Runtime manifest must contain at least one relation matching template kind={template['kind']}."
        )

    cardinality = template["cardinality"]
    if cardinality == "single" and len(matches) != 1:
        fail_runtime(
            f"Runtime manifest relation_plan requires exactly one {template['kind']} relation."
        )

    return matches


def resolve_relation_artifact_set(
    runtime_manifest: dict[str, Any],
    *,
    relation: dict[str, Any],
    template: dict[str, Any],
    fail_runtime: Callable[[str], None],
) -> dict[str, Any]:
    evaluation_roles = list_relation_evaluation_roles(relation)
    submission_roles = list_relation_submission_roles(relation)

    evaluation_artifacts = []
    for index, role in enumerate(evaluation_roles):
        artifact = resolve_artifact_by_role(
            runtime_manifest,
            lane="evaluation",
            role=role,
            fail_runtime=fail_runtime,
        )
        _validate_relation_artifact(
            lane="evaluation",
            role=role,
            rule=template["evaluation"][index],
            artifact=artifact,
            fail_runtime=fail_runtime,
        )
        evaluation_artifacts.append(artifact)

    submission_artifacts = []
    for index, role in enumerate(submission_roles):
        artifact = resolve_artifact_by_role(
            runtime_manifest,
            lane="submission",
            role=role,
            fail_runtime=fail_runtime,
        )
        _validate_relation_artifact(
            lane="submission",
            role=role,
            rule=template["submission"][index],
            artifact=artifact,
            fail_runtime=fail_runtime,
        )
        submission_artifacts.append(artifact)

    return {
        "relation": relation,
        "evaluation": evaluation_artifacts,
        "submission": submission_artifacts,
    }


def resolve_relation_artifact_sets(
    runtime_manifest: dict[str, Any],
    *,
    template: dict[str, Any],
    fail_runtime: Callable[[str], None],
) -> list[dict[str, Any]]:
    return [
        resolve_relation_artifact_set(
            runtime_manifest,
            relation=relation,
            template=template,
            fail_runtime=fail_runtime,
        )
        for relation in list_matching_relations(
            runtime_manifest,
            template=template,
            fail_runtime=fail_runtime,
        )
    ]


def aggregate_relation_scores(
    relation_scores: list[float],
    *,
    aggregation: str,
    fail_runtime: Callable[[str], None],
) -> float:
    if len(relation_scores) == 0:
        fail_runtime("Cannot aggregate an empty relation score set.")

    if aggregation == "single":
        if len(relation_scores) != 1:
            fail_runtime(
                "relation_plan aggregation=single requires exactly one relation score."
            )
        return relation_scores[0]

    if aggregation == "mean":
        return sum(relation_scores) / len(relation_scores)

    if aggregation == "min":
        return min(relation_scores)

    if aggregation == "max":
        return max(relation_scores)

    if aggregation == "all_or_nothing":
        return 1.0 if all(score == 1.0 for score in relation_scores) else 0.0

    fail_runtime(
        f"Unsupported relation_plan aggregation {aggregation}. Next step: use one of {','.join(sorted(_RELATION_AGGREGATIONS))}."
    )
