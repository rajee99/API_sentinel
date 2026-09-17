"""
API Sentinel - Schema Inferencer
Generates and normalizes JSON Schemas from runtime payloads using genson.
"""

from typing import Any, Dict, Union
from genson import SchemaBuilder


def infer_json_schema(payload: Union[dict, list]) -> dict:
    """
    Infer a JSON Schema from a raw runtime JSON HTTP body (dict or list).

    Uses the genson library's SchemaBuilder to automatically convert
    arbitrary Python data structures into standard JSON Schema dictionaries.

    Parameters
    ----------
    payload : dict | list
        A Python dictionary or list representing a parsed JSON HTTP body.

    Returns
    -------
    dict
        A JSON Schema dictionary describing the structure of the input payload.
        The ``$schema`` meta-attribute is stripped for cleaner OpenAPI comparison.

    Examples
    --------
    >>> infer_json_schema({"name": "Alice", "age": 30, "active": True})
    {'type': 'object', 'properties': {'name': {'type': 'string'}, 'age': {'type': 'integer'}, 'active': {'type': 'boolean'}}, 'required': ['active', 'age', 'name']}

    >>> infer_json_schema([{"id": 1, "title": "Hello"}])
    {'type': 'array', 'items': {'type': 'object', 'properties': {'id': {'type': 'integer'}, 'title': {'type': 'string'}}, 'required': ['id', 'title']}}

    >>> infer_json_schema({"nested": {"key": "value"}})
    {'type': 'object', 'properties': {'nested': {'type': 'object', 'properties': {'key': {'type': 'string'}}, 'required': ['key']}}, 'required': ['nested']}
    """
    if payload is None:
        return {"type": "null"}

    builder = SchemaBuilder()
    builder.add_object(payload)
    schema = builder.to_schema()

    # Strip the $schema meta-attribute for cleaner comparison with OpenAPI schemas
    schema.pop("$schema", None)

    return schema


class SchemaInferencer:
    """Infers JSON Schema from raw request/response payload objects."""

    def __init__(self, schema_uri: str | None = None):
        self.schema_uri = schema_uri

    def infer_schema(self, data: Any) -> Dict[str, Any]:
        """
        Infer a JSON Schema from Python data structures (dict, list, etc.).
        """
        if data is None:
            return {"type": "null"}

        builder = SchemaBuilder(schema_uri=self.schema_uri)
        builder.add_object(data)
        schema = builder.to_schema()
        return self.normalize_schema(schema)

    @staticmethod
    def normalize_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clean up and normalize inferred schema for OpenAPI comparison.
        Strips meta attributes like $schema if present.
        """
        normalized = dict(schema)
        normalized.pop("$schema", None)
        return normalized