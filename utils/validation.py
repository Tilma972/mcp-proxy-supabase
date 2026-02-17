"""
JSON Schema parameter validation for tool calls.

Validates incoming params against tool input_schema before dispatch,
avoiding unnecessary worker calls on invalid input.
"""

from typing import Dict, Any, List, Optional


def validate_params(params: Dict[str, Any], input_schema: Dict[str, Any]) -> Optional[List[str]]:
    """
    Validate params against a JSON Schema input_schema.

    Checks:
    - Required fields are present
    - Field types match (string, number, integer, boolean, object, array)
    - Enum values are valid

    Args:
        params: The parameters to validate
        input_schema: JSON Schema definition (from ToolSchema.input_schema)

    Returns:
        None if valid, list of error messages if invalid
    """
    errors = []

    properties = input_schema.get("properties", {})
    required = input_schema.get("required", [])

    # Check required fields
    for field in required:
        if field not in params:
            desc = properties.get(field, {}).get("description", "")
            errors.append(f"Missing required field: '{field}'" + (f" ({desc})" if desc else ""))

    # Validate provided fields
    for field, value in params.items():
        if field not in properties:
            # Unknown field - skip (don't reject, workers may accept extra fields)
            continue

        field_schema = properties[field]
        expected_type = field_schema.get("type")

        if value is None:
            # None is acceptable for optional fields
            continue

        # Type checking
        if expected_type == "string" and not isinstance(value, str):
            errors.append(f"Field '{field}' must be a string, got {type(value).__name__}")

        elif expected_type == "number" and not isinstance(value, (int, float)):
            errors.append(f"Field '{field}' must be a number, got {type(value).__name__}")

        elif expected_type == "integer" and not isinstance(value, int):
            errors.append(f"Field '{field}' must be an integer, got {type(value).__name__}")

        elif expected_type == "boolean" and not isinstance(value, bool):
            errors.append(f"Field '{field}' must be a boolean, got {type(value).__name__}")

        elif expected_type == "object" and not isinstance(value, dict):
            errors.append(f"Field '{field}' must be an object, got {type(value).__name__}")

        elif expected_type == "array" and not isinstance(value, list):
            errors.append(f"Field '{field}' must be an array, got {type(value).__name__}")

        # Enum checking
        enum_values = field_schema.get("enum")
        if enum_values and value not in enum_values:
            errors.append(
                f"Field '{field}' must be one of {enum_values}, got '{value}'"
            )

    return errors if errors else None
