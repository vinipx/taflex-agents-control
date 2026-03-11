"""
schema_validator.py — JSON schema validation for MCP artifact payloads.

Implements Step 2.3 of Phase 2 (AGENT_AUTONOMOUS_IMPLEMENTATION_GUIDE.md).

Validates each artifact against a JSON Schema file stored in ``schemas/``.
Uses the ``jsonschema`` library when available; falls back to basic structural
validation when it is not installed.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Directory containing .schema.json files (relative to this file's package root)
_SCHEMAS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "schemas")

# Mapping from artifact stem name → schema file name
ARTIFACT_SCHEMA_MAP: dict[str, str] = {
    "test-plan": "test-plan.schema.json",
    "test-changes": "test-changes.schema.json",
    "execution-summary": "execution-summary.schema.json",
    "allure-summary": "allure-summary.schema.json",
    "maintenance-actions": "maintenance-actions.schema.json",
}


def validate_artifact(
    artifact_name: str, data: dict
) -> tuple[bool, list[str]]:
    """
    Validate *data* against the JSON Schema for *artifact_name*.

    Parameters
    ----------
    artifact_name:
        One of the keys in ``ARTIFACT_SCHEMA_MAP`` (e.g. ``"test-plan"``).
    data:
        The artifact dictionary to validate.

    Returns
    -------
    tuple[bool, list[str]]
        ``(is_valid, errors)`` — errors is an empty list when valid.
    """
    schema_filename = ARTIFACT_SCHEMA_MAP.get(artifact_name)
    if not schema_filename:
        return False, [f"Unknown artifact: '{artifact_name}'"]

    schema_path = os.path.join(_SCHEMAS_DIR, schema_filename)
    if not os.path.isfile(schema_path):
        return False, [f"Schema file not found: {schema_path}"]

    try:
        with open(schema_path, "r", encoding="utf-8") as fh:
            schema = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"Failed to load schema '{schema_path}': {exc}"]

    # Prefer jsonschema library when available
    try:
        import jsonschema  # type: ignore[import]

        validator = jsonschema.Draft7Validator(schema)
        errors = [str(e.message) for e in sorted(validator.iter_errors(data), key=str)]
        is_valid = len(errors) == 0
        if is_valid:
            logger.info("[SCHEMA] '%s' is valid.", artifact_name)
        else:
            logger.warning("[SCHEMA] '%s' has %d error(s).", artifact_name, len(errors))
        return is_valid, errors
    except ImportError:
        logger.warning(
            "[SCHEMA] jsonschema not installed — using basic structural validation."
        )
        return _basic_validate(artifact_name, data, schema)


def validate_all_artifacts(artifacts_dir: str) -> dict:
    """
    Validate all recognised artifacts found in *artifacts_dir*.

    Parameters
    ----------
    artifacts_dir:
        Directory containing ``*.json`` artifact files.

    Returns
    -------
    dict
        Summary dict with structure::

            {
                "all_valid": bool,
                "results": {
                    "<artifact_name>": {
                        "valid": bool,
                        "errors": ["..."]
                    },
                    ...
                }
            }
    """
    summary: dict[str, Any] = {"all_valid": True, "results": {}}

    if not os.path.isdir(artifacts_dir):
        logger.error("[SCHEMA] artifacts_dir not found: %s", artifacts_dir)
        summary["all_valid"] = False
        summary["error"] = f"Directory not found: {artifacts_dir}"
        return summary

    for stem in ARTIFACT_SCHEMA_MAP:
        json_path = os.path.join(artifacts_dir, f"{stem}.json")
        if not os.path.isfile(json_path):
            logger.warning("[SCHEMA] Artifact file not found: %s", json_path)
            summary["results"][stem] = {
                "valid": False,
                "errors": [f"File not found: {json_path}"],
            }
            summary["all_valid"] = False
            continue

        try:
            with open(json_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            summary["results"][stem] = {
                "valid": False,
                "errors": [f"Failed to read/parse: {exc}"],
            }
            summary["all_valid"] = False
            continue

        is_valid, errors = validate_artifact(stem, data)
        summary["results"][stem] = {"valid": is_valid, "errors": errors}
        if not is_valid:
            summary["all_valid"] = False

    return summary


# ---------------------------------------------------------------------------
# Basic structural validator (used when jsonschema is not installed)
# ---------------------------------------------------------------------------


def _basic_validate(
    artifact_name: str, data: dict, schema: dict
) -> tuple[bool, list[str]]:
    """Minimal schema validator that checks required fields and basic types."""
    errors: list[str] = []

    required = schema.get("required", [])
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: '{field}'")

    properties = schema.get("properties", {})
    for field, field_schema in properties.items():
        if field not in data:
            continue
        expected_type = field_schema.get("type")
        if expected_type:
            if not _check_type(data[field], expected_type):
                errors.append(
                    f"Field '{field}' expected type '{expected_type}', "
                    f"got '{type(data[field]).__name__}'"
                )

    is_valid = len(errors) == 0
    return is_valid, errors


_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


def _check_type(value: Any, json_type: str) -> bool:
    """Return True if *value* matches *json_type*."""
    expected = _TYPE_MAP.get(json_type)
    if expected is None:
        return True  # Unknown type — don't error
    return isinstance(value, expected)
