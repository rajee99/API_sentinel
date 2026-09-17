"""
API Sentinel - OpenAPI Spec Parser & Diff Comparator Engine
Parses OpenAPI specifications and detects schema drift in runtime request/response data.
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Tuple, Union
import yaml


# ===========================================================================
# Standalone utility functions for spec loading and path matching
# ===========================================================================


def load_openapi_spec(spec_path: str) -> dict:
    """
    Load and parse an OpenAPI specification file (YAML or JSON).

    Parameters
    ----------
    spec_path : str
        Filesystem path to the OpenAPI specification file.
        Supports both YAML (.yaml, .yml) and JSON (.json) formats.

    Returns
    -------
    dict
        The parsed OpenAPI specification as a Python dictionary.

    Raises
    ------
    FileNotFoundError
        If the spec file does not exist at the given path.
    yaml.YAMLError
        If the YAML/JSON content is malformed.

    Examples
    --------
    >>> spec = load_openapi_spec("openapi.yaml")
    >>> spec["openapi"]
    '3.0.3'
    >>> list(spec["paths"].keys())
    ['/api/v1/users', '/api/v1/users/{id}', '/api/v1/auth/login']
    """
    with open(spec_path, "r", encoding="utf-8") as f:
        if spec_path.endswith(".json"):
            import json
            return json.load(f)
        else:
            return yaml.safe_load(f)


def match_route(live_path: str, openapi_paths: list) -> Optional[str]:
    """
    Match a concrete runtime URL path against a list of OpenAPI path templates.

    Converts dynamic path segments in OpenAPI templates (e.g., ``{id}``,
    ``{user_id}``) into regex patterns that match any non-slash characters.
    This allows concrete URLs like ``/api/v1/users/94a82f3c`` to be matched
    against parameterized templates like ``/api/v1/users/{id}``.

    The matching algorithm:
    1. First attempts an exact string match (for static paths).
    2. Then converts each OpenAPI template's ``{param}`` segments into
       regex groups matching ``[^/]+`` (one or more non-slash characters).
    3. Returns the first matching template, preferring more specific
       (longer) templates over shorter ones.

    Parameters
    ----------
    live_path : str
        The actual runtime URL path from an HTTP request
        (e.g., ``/api/v1/users/94a82f3c``, ``/api/v1/users``).
    openapi_paths : list[str]
        A list of OpenAPI path template strings
        (e.g., ``['/api/v1/users', '/api/v1/users/{id}']``).

    Returns
    -------
    str | None
        The matching OpenAPI path template string if found, otherwise ``None``.

    Examples
    --------
    >>> paths = ['/api/v1/users', '/api/v1/users/{id}', '/api/v1/auth/login']

    >>> match_route('/api/v1/users', paths)
    '/api/v1/users'

    >>> match_route('/api/v1/users/94a82f3c', paths)
    '/api/v1/users/{id}'

    >>> match_route('/api/v1/users/123', paths)
    '/api/v1/users/{id}'

    >>> match_route('/api/v1/auth/login', paths)
    '/api/v1/auth/login'

    >>> match_route('/api/v1/unknown/endpoint', paths) is None
    True
    """
    # Normalize: strip trailing slash (except for root "/")
    clean_path = live_path.rstrip("/") if len(live_path) > 1 else live_path

    # 1. Attempt exact match first (fastest path for static routes)
    if clean_path in openapi_paths:
        return clean_path

    # 2. Sort templates by specificity: longer templates first, so that
    #    /api/v1/users/{id}/posts/{post_id} is tried before /api/v1/users/{id}
    sorted_templates = sorted(openapi_paths, key=lambda p: -len(p))

    # 3. Regex-based matching for parameterized paths
    for template in sorted_templates:
        # Skip templates without parameters (already handled by exact match)
        if "{" not in template:
            continue

        # Convert {param_name} to a regex group matching one or more non-slash chars.
        # Supports various parameter patterns:
        #   - UUIDs:    94a82f3c-1234-5678-9abc-def012345678
        #   - Integers: 42, 9999
        #   - Slugs:    my-resource-name
        #   - Base64:   dXNlcjoxMjM=
        regex_pattern = re.sub(r"\{[^}]+\}", r"[^/]+", template)
        regex = re.compile(f"^{regex_pattern}$")

        if regex.match(clean_path):
            return template

    return None


# ===========================================================================
# Enums and data classes
# ===========================================================================


class DriftSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class DriftType(str, Enum):
    UNDOCUMENTED_ENDPOINT = "UNDOCUMENTED_ENDPOINT"
    UNDOCUMENTED_STATUS_CODE = "UNDOCUMENTED_STATUS_CODE"
    UNDOCUMENTED_QUERY_PARAM = "UNDOCUMENTED_QUERY_PARAM"
    MISSING_REQUIRED_QUERY_PARAM = "MISSING_REQUIRED_QUERY_PARAM"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    EXTRA_FIELD = "EXTRA_FIELD"
    TYPE_MISMATCH = "TYPE_MISMATCH"


@dataclass
class DriftIssue:
    issue_type: DriftType
    severity: DriftSeverity
    path: str
    method: str
    location: str  # 'request_query', 'request_body', 'response_body', 'status_code'
    message: str
    expected: Optional[Any] = None
    actual: Optional[Any] = None


# ===========================================================================
# OpenAPI Spec Parser class
# ===========================================================================


class OpenAPISpecParser:
    """Parses and resolves OpenAPI spec paths, methods, components, and schemas."""

    def __init__(self, spec_data: Dict[str, Any]):
        self.spec = spec_data
        self.paths = spec_data.get("paths", {})
        self.components = spec_data.get("components", {}).get("schemas", {})
        self._compiled_routes: List[Tuple[re.Pattern, str, Dict[str, Any]]] = []
        self._compile_routes()

    @classmethod
    def from_file(cls, filepath: str) -> "OpenAPISpecParser":
        """Create an OpenAPISpecParser from a spec file using load_openapi_spec."""
        data = load_openapi_spec(filepath)
        return cls(data)

    def _compile_routes(self):
        for path_pattern, path_item in self.paths.items():
            # Convert OpenAPI path parameters like /users/{id} to regex ^/users/[^/]+$
            regex_pattern = re.sub(r"\{[^}]+\}", r"[^/]+", path_pattern)
            regex = re.compile(f"^{regex_pattern}$")
            self._compiled_routes.append((regex, path_pattern, path_item))

    def resolve_ref(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Resolves $ref references within OpenAPI schemas."""
        if not isinstance(schema, dict):
            return schema

        if "$ref" in schema:
            ref_path = schema["$ref"]
            if ref_path.startswith("#/components/schemas/"):
                schema_name = ref_path.replace("#/components/schemas/", "")
                resolved = self.components.get(schema_name, {})
                # Merge any sibling keys
                merged = {k: v for k, v in schema.items() if k != "$ref"}
                merged_resolved = self.resolve_ref(resolved)
                merged.update(merged_resolved)
                return merged

        return schema

    def match_route(self, request_path: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Finds matching path template and path item for an incoming request path."""
        # Use the standalone match_route function for path matching
        matched_template = match_route(request_path, list(self.paths.keys()))
        if matched_template:
            return matched_template, self.paths[matched_template]
        return None

    def get_operation(self, request_path: str, method: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        match = self.match_route(request_path)
        if not match:
            return None
        path_template, path_item = match
        operation = path_item.get(method.lower())
        if operation is None:
            return None
        return path_template, operation


# ===========================================================================
# API Diff Engine class
# ===========================================================================


class APIDiffEngine:
    """Compares runtime request & response payloads against OpenAPI specification schemas."""

    def __init__(self, parser: OpenAPISpecParser):
        self.parser = parser

    def compare_request(
        self, path: str, method: str, query_params: Dict[str, Any], body: Any
    ) -> List[DriftIssue]:
        issues: List[DriftIssue] = []
        op_match = self.parser.get_operation(path, method)

        if not op_match:
            issues.append(
                DriftIssue(
                    issue_type=DriftType.UNDOCUMENTED_ENDPOINT,
                    severity=DriftSeverity.ERROR,
                    path=path,
                    method=method.upper(),
                    location="endpoint",
                    message=f"Endpoint '{method.upper()} {path}' is not defined in OpenAPI spec",
                )
            )
            return issues

        _, operation = op_match

        # 1. Query parameters check
        spec_params = operation.get("parameters", [])
        query_param_specs = {
            p["name"]: p for p in spec_params if isinstance(p, dict) and p.get("in") == "query"
        }

        for param_name, param_spec in query_param_specs.items():
            if param_spec.get("required", False) and param_name not in query_params:
                issues.append(
                    DriftIssue(
                        issue_type=DriftType.MISSING_REQUIRED_QUERY_PARAM,
                        severity=DriftSeverity.ERROR,
                        path=path,
                        method=method.upper(),
                        location="request_query",
                        message=f"Required query parameter '{param_name}' is missing from request",
                        expected=param_name,
                        actual=list(query_params.keys()),
                    )
                )

        for actual_param in query_params:
            if actual_param not in query_param_specs:
                issues.append(
                    DriftIssue(
                        issue_type=DriftType.UNDOCUMENTED_QUERY_PARAM,
                        severity=DriftSeverity.WARNING,
                        path=path,
                        method=method.upper(),
                        location="request_query",
                        message=f"Query parameter '{actual_param}' is not documented in OpenAPI spec",
                        actual=actual_param,
                    )
                )

        # 2. Request body check
        request_body_spec = operation.get("requestBody", {})
        content_spec = request_body_spec.get("content", {}).get("application/json", {})
        schema_spec = content_spec.get("schema")

        if schema_spec and body is not None:
            resolved_schema = self.parser.resolve_ref(schema_spec)
            body_issues = self._validate_schema(
                data=body,
                schema=resolved_schema,
                path=path,
                method=method,
                location="request_body",
            )
            issues.extend(body_issues)

        return issues

    def compare_response(
        self, path: str, method: str, status_code: int, body: Any
    ) -> List[DriftIssue]:
        issues: List[DriftIssue] = []
        op_match = self.parser.get_operation(path, method)

        if not op_match:
            # Already reported in request pass if endpoint missing
            return issues

        _, operation = op_match
        responses_spec = operation.get("responses", {})

        status_str = str(status_code)
        response_spec = responses_spec.get(status_str) or responses_spec.get(f"{status_str[0]}XX") or responses_spec.get("default")

        if not response_spec:
            issues.append(
                DriftIssue(
                    issue_type=DriftType.UNDOCUMENTED_STATUS_CODE,
                    severity=DriftSeverity.ERROR,
                    path=path,
                    method=method.upper(),
                    location="status_code",
                    message=f"Response status code {status_code} is not documented for '{method.upper()} {path}'",
                    expected=list(responses_spec.keys()),
                    actual=status_code,
                )
            )
            return issues

        content_spec = response_spec.get("content", {}).get("application/json", {})
        schema_spec = content_spec.get("schema")

        if schema_spec and body is not None:
            resolved_schema = self.parser.resolve_ref(schema_spec)
            body_issues = self._validate_schema(
                data=body,
                schema=resolved_schema,
                path=path,
                method=method,
                location="response_body",
            )
            issues.extend(body_issues)

        return issues

    def _validate_schema(
        self, data: Any, schema: Dict[str, Any], path: str, method: str, location: str, json_path: str = "$"
    ) -> List[DriftIssue]:
        issues: List[DriftIssue] = []
        schema = self.parser.resolve_ref(schema)

        expected_type = schema.get("type")
        if expected_type:
            actual_type = self._get_json_type(data)
            if not self._types_match(expected_type, actual_type):
                issues.append(
                    DriftIssue(
                        issue_type=DriftType.TYPE_MISMATCH,
                        severity=DriftSeverity.ERROR,
                        path=path,
                        method=method.upper(),
                        location=location,
                        message=f"Type mismatch at {json_path}: expected '{expected_type}', got '{actual_type}'",
                        expected=expected_type,
                        actual=actual_type,
                    )
                )
                return issues

        if isinstance(data, dict) and schema.get("type") == "object":
            properties = schema.get("properties", {})
            required_fields = schema.get("required", [])

            # Check missing required fields
            for req in required_fields:
                if req not in data:
                    issues.append(
                        DriftIssue(
                            issue_type=DriftType.MISSING_REQUIRED_FIELD,
                            severity=DriftSeverity.ERROR,
                            path=path,
                            method=method.upper(),
                            location=location,
                            message=f"Missing required field '{req}' at {json_path}",
                            expected=req,
                            actual=list(data.keys()),
                        )
                    )

            # Check extra fields & validate property types
            for key, val in data.items():
                child_path = f"{json_path}.{key}"
                if key not in properties:
                    issues.append(
                        DriftIssue(
                            issue_type=DriftType.EXTRA_FIELD,
                            severity=DriftSeverity.WARNING,
                            path=path,
                            method=method.upper(),
                            location=location,
                            message=f"Undocumented field '{key}' at {child_path}",
                            actual=key,
                        )
                    )
                else:
                    child_schema = properties[key]
                    issues.extend(
                        self._validate_schema(val, child_schema, path, method, location, child_path)
                    )

        elif isinstance(data, list) and schema.get("type") == "array":
            item_schema = schema.get("items")
            if item_schema and len(data) > 0:
                # Check sample of items or first item
                for idx, item in enumerate(data[:5]):  # limit inspection depth
                    child_path = f"{json_path}[{idx}]"
                    issues.extend(
                        self._validate_schema(item, item_schema, path, method, location, child_path)
                    )

        return issues

    @staticmethod
    def _get_json_type(val: Any) -> str:
        if val is None:
            return "null"
        if isinstance(val, bool):
            return "boolean"
        if isinstance(val, int):
            return "integer"
        if isinstance(val, float):
            return "number"
        if isinstance(val, str):
            return "string"
        if isinstance(val, list):
            return "array"
        if isinstance(val, dict):
            return "object"
        return "unknown"

    @staticmethod
    def _types_match(expected: str, actual: str) -> bool:
        if expected == actual:
            return True
        if expected == "number" and actual in ("integer", "number"):
            return True
        return False

    # ------------------------------------------------------------------
    # Async Fire-and-Forget entry point used by APISentinelMiddleware
    # ------------------------------------------------------------------

    async def analyze_payload_async(
        self,
        method: str,
        raw_path: str,
        matched_path: Optional[str],
        status_code: int,
        query_params: Dict[str, Any],
        request_body: Optional[Any],
        response_body: Optional[Any],
        reporter: Any,
        print_clean: bool = False,
    ) -> List[DriftIssue]:
        """
        Coroutine designed to run as a background ``asyncio`` task (fire-and-forget).

        Bundles both request and response drift analysis into a single async call
        so the middleware can schedule it *after* the response has already been
        streamed back to the client.

        The canonical path used for spec look-up is ``raw_path`` (the actual URL
        path string) because ``OpenAPISpecParser.get_operation`` handles regex
        matching internally.  ``matched_path`` is carried along only for
        diagnostic / logging purposes.

        All exceptions are swallowed so that monitoring failures **never** affect
        the target application.
        """
        try:
            # Run the synchronous diff logic inside the running event loop.
            request_issues = self.compare_request(
                path=raw_path,
                method=method,
                query_params=query_params,
                body=request_body,
            )
            response_issues = self.compare_response(
                path=raw_path,
                method=method,
                status_code=status_code,
                body=response_body,
            )

            all_issues = request_issues + response_issues

            if all_issues:
                reporter.report_drift(all_issues)
            elif print_clean:
                reporter.report_clean(method, raw_path, status_code)

            return all_issues

        except Exception:  # noqa: BLE001
            # Sentinel monitoring MUST NOT crash the host application.
            return []