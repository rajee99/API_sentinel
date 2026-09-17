"""
API Sentinel - OpenAPI Parser
==============================
Parses OpenAPI 3.x specifications, resolves $ref references, and provides
structured access to paths, operations, parameters, and schemas.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

import yaml


def load_openapi_spec(spec_path: str) -> dict:
    """
    Load and parse an OpenAPI specification file (YAML or JSON).

    Parameters
    ----------
    spec_path : str
        Filesystem path to the OpenAPI specification file.

    Returns
    -------
    dict
        The parsed OpenAPI specification as a Python dictionary.

    Raises
    ------
    FileNotFoundError
        If the spec file does not exist at the given path.
    """
    with open(spec_path, "r", encoding="utf-8") as f:
        if spec_path.endswith(".json"):
            return json.load(f)
        else:
            return yaml.safe_load(f)


def match_route(live_path: str, openapi_paths: List[str]) -> Optional[str]:
    """
    Match a concrete runtime URL path against OpenAPI path templates.

    Parameters
    ----------
    live_path : str
        The actual runtime URL path (e.g., '/api/v1/users/42').
    openapi_paths : list[str]
        OpenAPI path template strings (e.g., ['/api/v1/users/{id}']).

    Returns
    -------
    str | None
        The matching OpenAPI path template, or None if no match.
    """
    clean_path = live_path.rstrip("/") if len(live_path) > 1 else live_path

    if clean_path in openapi_paths:
        return clean_path

    sorted_templates = sorted(openapi_paths, key=lambda p: -len(p))

    for template in sorted_templates:
        if "{" not in template:
            continue
        regex_pattern = re.sub(r"\{[^}]+\}", r"[^/]+", template)
        regex = re.compile(f"^{regex_pattern}$")
        if regex.match(clean_path):
            return template

    return None


def extract_path_params(live_path: str, template: str) -> Dict[str, str]:
    """
    Extract path parameter values from a concrete path given a template.

    Parameters
    ----------
    live_path : str
        The actual runtime URL path (e.g., '/api/v1/users/42').
    template : str
        The OpenAPI path template (e.g., '/api/v1/users/{id}').

    Returns
    -------
    dict
        Mapping of parameter names to their runtime values.

    Examples
    --------
    >>> extract_path_params('/api/v1/users/42', '/api/v1/users/{id}')
    {'id': '42'}
    """
    params: Dict[str, str] = {}
    template_parts = template.split("/")
    path_parts = live_path.split("/")

    if len(template_parts) != len(path_parts):
        return params

    for t_part, p_part in zip(template_parts, path_parts):
        match = re.match(r"^\{(.+)\}$", t_part)
        if match:
            params[match.group(1)] = p_part

    return params


class OpenAPIParser:
    """
    Full-featured OpenAPI 3.x specification parser.

    Provides structured access to:
    - Path templates and operations
    - Parameter definitions (path, query, header, cookie)
    - Request/response body schemas
    - $ref resolution (including nested and circular references)
    - Content-type negotiation
    """

    def __init__(self, spec_data: Dict[str, Any]):
        self.spec = spec_data
        self.paths: Dict[str, Any] = spec_data.get("paths", {})
        self.components_schemas: Dict[str, Any] = (
            spec_data.get("components", {}).get("schemas", {})
        )
        self._path_templates: List[str] = list(self.paths.keys())

    @classmethod
    def from_file(cls, filepath: str) -> "OpenAPIParser":
        """Create parser from a spec file path."""
        data = load_openapi_spec(filepath)
        return cls(data)

    @classmethod
    def from_dict(cls, spec_data: Dict[str, Any]) -> "OpenAPIParser":
        """Create parser from an already-parsed spec dictionary."""
        return cls(spec_data)

    # ------------------------------------------------------------------
    # Route matching
    # ------------------------------------------------------------------

    def match_route(self, request_path: str) -> Optional[str]:
        """Match a runtime path to an OpenAPI template. Returns template or None."""
        return match_route(request_path, self._path_templates)

    def get_path_item(self, template: str) -> Optional[Dict[str, Any]]:
        """Get the path item object for a given template."""
        return self.paths.get(template)

    def get_operation(
        self, request_path: str, method: str
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Get the operation object for a path + method combination.

        Returns
        -------
        tuple[str, dict] | None
            (path_template, operation_object) or None if not found.
        """
        template = self.match_route(request_path)
        if template is None:
            return None

        path_item = self.paths[template]
        operation = path_item.get(method.lower())
        if operation is None:
            return None

        return template, operation

    def get_available_methods(self, request_path: str) -> List[str]:
        """Get all HTTP methods defined for a given path."""
        template = self.match_route(request_path)
        if template is None:
            return []

        path_item = self.paths[template]
        http_methods = {"get", "post", "put", "delete", "patch", "head", "options", "trace"}
        return [m.upper() for m in path_item.keys() if m.lower() in http_methods]

    # ------------------------------------------------------------------
    # Parameter extraction
    # ------------------------------------------------------------------

    def get_parameters(
        self, request_path: str, method: str, location: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get parameter definitions for an operation.

        Parameters
        ----------
        request_path : str
            Runtime path or template.
        method : str
            HTTP method.
        location : str, optional
            Filter by 'query', 'path', 'header', or 'cookie'.

        Returns
        -------
        list[dict]
            Parameter definition objects.
        """
        result = self.get_operation(request_path, method)
        if result is None:
            return []

        _, operation = result
        params = operation.get("parameters", [])

        # Also include path-level parameters
        template = self.match_route(request_path)
        if template:
            path_item = self.paths[template]
            path_level_params = path_item.get("parameters", [])
            # Merge: operation-level overrides path-level
            op_param_names = {(p.get("name"), p.get("in")) for p in params}
            for p in path_level_params:
                if (p.get("name"), p.get("in")) not in op_param_names:
                    params.append(p)

        # Resolve any $ref in parameters
        resolved_params = [self.resolve_ref(p) for p in params]

        if location:
            return [p for p in resolved_params if p.get("in") == location]

        return resolved_params

    def get_query_params(self, request_path: str, method: str) -> List[Dict[str, Any]]:
        """Get query parameter definitions."""
        return self.get_parameters(request_path, method, location="query")

    def get_path_params(self, request_path: str, method: str) -> List[Dict[str, Any]]:
        """Get path parameter definitions."""
        return self.get_parameters(request_path, method, location="path")

    # ------------------------------------------------------------------
    # Request/Response schema access
    # ------------------------------------------------------------------

    def get_request_body_schema(
        self, request_path: str, method: str, content_type: str = "application/json"
    ) -> Optional[Dict[str, Any]]:
        """
        Get the resolved request body schema for an operation.

        Parameters
        ----------
        request_path : str
            Runtime path.
        method : str
            HTTP method.
        content_type : str
            Media type to look up (default: application/json).

        Returns
        -------
        dict | None
            Resolved JSON Schema or None if not defined.
        """
        result = self.get_operation(request_path, method)
        if result is None:
            return None

        _, operation = result
        request_body = operation.get("requestBody", {})
        request_body = self.resolve_ref(request_body)
        content = request_body.get("content", {})
        media_type = content.get(content_type, {})
        schema = media_type.get("schema")

        if schema:
            return self.resolve_ref(schema)
        return None

    def get_response_schema(
        self,
        request_path: str,
        method: str,
        status_code: int,
        content_type: str = "application/json",
    ) -> Optional[Dict[str, Any]]:
        """
        Get the resolved response body schema for a specific status code.

        Tries exact status code match first, then wildcard (e.g., '2XX'),
        then 'default'.

        Parameters
        ----------
        request_path : str
            Runtime path.
        method : str
            HTTP method.
        status_code : int
            HTTP response status code.
        content_type : str
            Media type (default: application/json).

        Returns
        -------
        dict | None
            Resolved JSON Schema or None.
        """
        result = self.get_operation(request_path, method)
        if result is None:
            return None

        _, operation = result
        responses = operation.get("responses", {})

        # Try exact match, then wildcard, then default
        status_str = str(status_code)
        wildcard = f"{status_str[0]}XX"
        response_spec = (
            responses.get(status_str)
            or responses.get(wildcard)
            or responses.get("default")
        )

        if not response_spec:
            return None

        response_spec = self.resolve_ref(response_spec)
        content = response_spec.get("content", {})
        media_type = content.get(content_type, {})
        schema = media_type.get("schema")

        if schema:
            return self.resolve_ref(schema)
        return None

    def get_response_status_codes(self, request_path: str, method: str) -> List[str]:
        """Get all documented response status codes for an operation."""
        result = self.get_operation(request_path, method)
        if result is None:
            return []

        _, operation = result
        return list(operation.get("responses", {}).keys())

    def get_response_content_types(
        self, request_path: str, method: str, status_code: int
    ) -> List[str]:
        """Get all documented content types for a specific response."""
        result = self.get_operation(request_path, method)
        if result is None:
            return []

        _, operation = result
        responses = operation.get("responses", {})
        status_str = str(status_code)
        wildcard = f"{status_str[0]}XX"
        response_spec = (
            responses.get(status_str)
            or responses.get(wildcard)
            or responses.get("default")
        )

        if not response_spec:
            return []

        response_spec = self.resolve_ref(response_spec)
        return list(response_spec.get("content", {}).keys())

    # ------------------------------------------------------------------
    # $ref resolution
    # ------------------------------------------------------------------

    def resolve_ref(self, schema: Any, _seen: Optional[set] = None) -> Any:
        """
        Recursively resolve $ref references in a schema object.

        Handles:
        - #/components/schemas/... references
        - Nested $ref chains
        - Circular reference detection (returns {} on cycle)

        Parameters
        ----------
        schema : Any
            Schema object that may contain $ref.
        _seen : set, optional
            Internal tracking for circular reference detection.

        Returns
        -------
        Any
            The fully resolved schema.
        """
        if not isinstance(schema, dict):
            return schema

        if _seen is None:
            _seen = set()

        if "$ref" in schema:
            ref_path = schema["$ref"]

            # Circular reference guard
            if ref_path in _seen:
                return {}
            _seen = _seen | {ref_path}

            if ref_path.startswith("#/components/schemas/"):
                schema_name = ref_path[len("#/components/schemas/"):]
                resolved = self.components_schemas.get(schema_name, {})
                # Merge sibling keys (e.g., description alongside $ref)
                siblings = {k: v for k, v in schema.items() if k != "$ref"}
                merged = self.resolve_ref(resolved, _seen)
                if isinstance(merged, dict):
                    merged = {**merged, **siblings}
                return merged

        # Resolve nested schemas
        result = {}
        for key, value in schema.items():
            if key == "properties" and isinstance(value, dict):
                result[key] = {
                    prop_name: self.resolve_ref(prop_schema, _seen)
                    for prop_name, prop_schema in value.items()
                }
            elif key == "items" and isinstance(value, dict):
                result[key] = self.resolve_ref(value, _seen)
            elif key == "allOf" and isinstance(value, list):
                result[key] = [self.resolve_ref(item, _seen) for item in value]
            elif key == "oneOf" and isinstance(value, list):
                result[key] = [self.resolve_ref(item, _seen) for item in value]
            elif key == "anyOf" and isinstance(value, list):
                result[key] = [self.resolve_ref(item, _seen) for item in value]
            elif key == "additionalProperties" and isinstance(value, dict):
                result[key] = self.resolve_ref(value, _seen)
            else:
                result[key] = value

        return result

    # ------------------------------------------------------------------
    # Schema utilities
    # ------------------------------------------------------------------

    def is_request_body_required(self, request_path: str, method: str) -> bool:
        """Check if the request body is marked as required."""
        result = self.get_operation(request_path, method)
        if result is None:
            return False

        _, operation = result
        request_body = operation.get("requestBody", {})
        request_body = self.resolve_ref(request_body)
        return request_body.get("required", False)

    def get_schema_required_fields(self, schema: Dict[str, Any]) -> List[str]:
        """Extract the 'required' field list from a schema."""
        resolved = self.resolve_ref(schema)
        return resolved.get("required", [])

    def get_schema_properties(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Extract the 'properties' from a schema."""
        resolved = self.resolve_ref(schema)
        return resolved.get("properties", {})