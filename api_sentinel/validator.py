"""
API Sentinel - Runtime Contract Validation Engine
==================================================
Compares runtime request/response data against the OpenAPI specification
and produces detailed ValidationReports.

Validates:
- HTTP Method
- Endpoint existence
- Path Parameters
- Query Parameters
- Request Body
- Response Body
- HTTP Status Code
- Content-Type

Detects:
- Missing Fields
- Extra Fields
- Type Mismatches
- Nested Object violations
- Array item violations
- Nullable value handling
- Enum violations
- Required field violations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from api_sentinel.inferencer import infer_json_schema
from api_sentinel.openapi_parser import OpenAPIParser, extract_path_params
from api_sentinel.validation_report import (
    Difference,
    DifferenceType,
    ValidationReport,
    ValidationSeverity,
    ValidationStatus,
)


@dataclass
class RuntimeData:
    """
    Encapsulates all runtime HTTP data for a single request/response cycle.

    Attributes
    ----------
    method : str
        HTTP method (GET, POST, PUT, DELETE, etc.).
    path : str
        The actual runtime URL path (e.g., '/api/v1/users/42').
    status_code : int
        HTTP response status code.
    query_params : dict
        Query parameters from the URL.
    request_body : Any
        Parsed request body (dict, list, or None).
    response_body : Any
        Parsed response body (dict, list, or None).
    request_content_type : str
        Content-Type of the request.
    response_content_type : str
        Content-Type of the response.
    path_params : dict
        Extracted path parameters (auto-populated during validation).
    """
    method: str
    path: str
    status_code: int
    query_params: Dict[str, Any] = field(default_factory=dict)
    request_body: Any = None
    response_body: Any = None
    request_content_type: str = "application/json"
    response_content_type: str = "application/json"
    path_params: Dict[str, str] = field(default_factory=dict)


class ContractValidator:
    """
    Runtime Contract Validation Engine.

    Compares RuntimeData against an OpenAPI specification and produces
    a comprehensive ValidationReport detailing all schema differences.

    Usage
    -----
    >>> parser = OpenAPIParser.from_file("openapi.yaml")
    >>> validator = ContractValidator(parser)
    >>> data = RuntimeData(
    ...     method="GET",
    ...     path="/api/v1/users/42",
    ...     status_code=200,
    ...     response_body={"id": 42, "name": "Alice", "email": "alice@example.com"}
    ... )
    >>> report = validator.validate(data)
    >>> print(report.summary())
    """

    def __init__(self, parser: OpenAPIParser):
        self.parser = parser

    @classmethod
    def from_file(cls, spec_path: str) -> "ContractValidator":
        """Create a validator from an OpenAPI spec file."""
        parser = OpenAPIParser.from_file(spec_path)
        return cls(parser)

    @classmethod
    def from_dict(cls, spec_data: Dict[str, Any]) -> "ContractValidator":
        """Create a validator from a parsed spec dictionary."""
        parser = OpenAPIParser.from_dict(spec_data)
        return cls(parser)

    # ------------------------------------------------------------------
    # Main validation entry point
    # ------------------------------------------------------------------

    def validate(self, runtime_data: RuntimeData) -> ValidationReport:
        """
        Validate a complete request/response cycle against the OpenAPI spec.

        Parameters
        ----------
        runtime_data : RuntimeData
            The runtime HTTP data to validate.

        Returns
        -------
        ValidationReport
            Complete validation report with all differences found.
        """
        differences: List[Difference] = []

        # Step 1: Validate endpoint exists
        template = self.parser.match_route(runtime_data.path)
        if template is None:
            differences.append(Difference(
                diff_type=DifferenceType.UNDOCUMENTED_ENDPOINT,
                severity=ValidationSeverity.ERROR,
                location="endpoint",
                json_path="$",
                message=f"Endpoint '{runtime_data.method} {runtime_data.path}' is not defined in OpenAPI spec",
                expected=self.parser._path_templates,
                actual=runtime_data.path,
            ))
            return self._build_report(
                runtime_data, template or runtime_data.path, differences
            )

        # Step 2: Validate HTTP method
        method_diffs = self._validate_method(runtime_data, template)
        differences.extend(method_diffs)
        if method_diffs:
            return self._build_report(runtime_data, template, differences)

        # Step 3: Validate path parameters
        runtime_data.path_params = extract_path_params(runtime_data.path, template)
        differences.extend(self._validate_path_params(runtime_data, template))

        # Step 4: Validate query parameters
        differences.extend(self._validate_query_params(runtime_data))

        # Step 5: Validate request body
        differences.extend(self._validate_request_body(runtime_data))

        # Step 6: Validate status code
        differences.extend(self._validate_status_code(runtime_data))

        # Step 7: Validate response content type
        differences.extend(self._validate_response_content_type(runtime_data))

        # Step 8: Validate response body
        differences.extend(self._validate_response_body(runtime_data))

        return self._build_report(runtime_data, template, differences)

    # ------------------------------------------------------------------
    # Individual validators
    # ------------------------------------------------------------------

    def _validate_method(
        self, runtime_data: RuntimeData, template: str
    ) -> List[Difference]:
        """Validate that the HTTP method is defined for the endpoint."""
        available = self.parser.get_available_methods(runtime_data.path)
        if runtime_data.method.upper() not in available:
            return [Difference(
                diff_type=DifferenceType.METHOD_NOT_ALLOWED,
                severity=ValidationSeverity.ERROR,
                location="method",
                json_path="$",
                message=(
                    f"Method '{runtime_data.method.upper()}' is not defined for "
                    f"'{template}'. Available: {available}"
                ),
                expected=available,
                actual=runtime_data.method.upper(),
            )]
        return []

    def _validate_path_params(
        self, runtime_data: RuntimeData, template: str
    ) -> List[Difference]:
        """Validate path parameters against their schema definitions."""
        differences: List[Difference] = []
        param_specs = self.parser.get_path_params(runtime_data.path, runtime_data.method)

        for param_spec in param_specs:
            param_name = param_spec.get("name", "")
            param_schema = param_spec.get("schema", {})
            param_value = runtime_data.path_params.get(param_name)

            if param_value is None:
                continue

            # Validate type of path parameter
            expected_type = param_schema.get("type")
            if expected_type:
                if not self._path_param_type_matches(param_value, expected_type):
                    differences.append(Difference(
                        diff_type=DifferenceType.PATH_PARAM_TYPE_MISMATCH,
                        severity=ValidationSeverity.WARNING,
                        location="path_params",
                        json_path=f"$.{param_name}",
                        message=(
                            f"Path parameter '{param_name}' expected type "
                            f"'{expected_type}', got value '{param_value}'"
                        ),
                        expected=expected_type,
                        actual=param_value,
                    ))

        return differences

    def _validate_query_params(self, runtime_data: RuntimeData) -> List[Difference]:
        """Validate query parameters against spec definitions."""
        differences: List[Difference] = []
        param_specs = self.parser.get_query_params(runtime_data.path, runtime_data.method)

        spec_params: Dict[str, Dict[str, Any]] = {
            p.get("name", ""): p for p in param_specs
        }

        # Check for missing required query params
        for param_name, param_spec in spec_params.items():
            if param_spec.get("required", False) and param_name not in runtime_data.query_params:
                differences.append(Difference(
                    diff_type=DifferenceType.MISSING_REQUIRED_QUERY_PARAM,
                    severity=ValidationSeverity.ERROR,
                    location="query_params",
                    json_path=f"$.{param_name}",
                    message=f"Required query parameter '{param_name}' is missing",
                    expected=param_name,
                    actual=list(runtime_data.query_params.keys()),
                ))

        # Check for undocumented query params
        for actual_param in runtime_data.query_params:
            if actual_param not in spec_params:
                differences.append(Difference(
                    diff_type=DifferenceType.UNDOCUMENTED_QUERY_PARAM,
                    severity=ValidationSeverity.WARNING,
                    location="query_params",
                    json_path=f"$.{actual_param}",
                    message=f"Query parameter '{actual_param}' is not documented in OpenAPI spec",
                    expected=list(spec_params.keys()),
                    actual=actual_param,
                ))

        # Validate enum constraints on query params
        for param_name, param_value in runtime_data.query_params.items():
            if param_name in spec_params:
                param_schema = spec_params[param_name].get("schema", {})
                enum_values = param_schema.get("enum")
                if enum_values and param_value not in enum_values:
                    differences.append(Difference(
                        diff_type=DifferenceType.ENUM_VIOLATION,
                        severity=ValidationSeverity.ERROR,
                        location="query_params",
                        json_path=f"$.{param_name}",
                        message=(
                            f"Query parameter '{param_name}' value '{param_value}' "
                            f"is not in allowed enum values: {enum_values}"
                        ),
                        expected=enum_values,
                        actual=param_value,
                    ))

        return differences

    def _validate_request_body(self, runtime_data: RuntimeData) -> List[Difference]:
        """Validate the request body against the spec schema."""
        differences: List[Difference] = []

        expected_schema = self.parser.get_request_body_schema(
            runtime_data.path, runtime_data.method, runtime_data.request_content_type
        )

        if expected_schema is None:
            # No request body defined in spec
            if runtime_data.request_body is not None:
                # Sending a body when none is expected is informational
                differences.append(Difference(
                    diff_type=DifferenceType.EXTRA_FIELD,
                    severity=ValidationSeverity.INFO,
                    location="request_body",
                    json_path="$",
                    message="Request body sent but none defined in OpenAPI spec",
                    expected=None,
                    actual=type(runtime_data.request_body).__name__,
                ))
            return differences

        # Check if body is required but missing
        is_required = self.parser.is_request_body_required(
            runtime_data.path, runtime_data.method
        )
        if is_required and runtime_data.request_body is None:
            differences.append(Difference(
                diff_type=DifferenceType.REQUIRED_FIELD_VIOLATION,
                severity=ValidationSeverity.ERROR,
                location="request_body",
                json_path="$",
                message="Request body is required but was not provided",
                expected=expected_schema,
                actual=None,
            ))
            return differences

        # Validate body against schema
        if runtime_data.request_body is not None:
            body_diffs = self._validate_schema(
                data=runtime_data.request_body,
                schema=expected_schema,
                location="request_body",
                json_path="$",
            )
            differences.extend(body_diffs)

        return differences

    def _validate_status_code(self, runtime_data: RuntimeData) -> List[Difference]:
        """Validate that the response status code is documented."""
        differences: List[Difference] = []

        documented_codes = self.parser.get_response_status_codes(
            runtime_data.path, runtime_data.method
        )

        status_str = str(runtime_data.status_code)
        wildcard = f"{status_str[0]}XX"

        if (
            status_str not in documented_codes
            and wildcard not in documented_codes
            and "default" not in documented_codes
        ):
            differences.append(Difference(
                diff_type=DifferenceType.UNDOCUMENTED_STATUS_CODE,
                severity=ValidationSeverity.ERROR,
                location="status_code",
                json_path="$",
                message=(
                    f"Response status code {runtime_data.status_code} is not "
                    f"documented for '{runtime_data.method.upper()} {runtime_data.path}'"
                ),
                expected=documented_codes,
                actual=runtime_data.status_code,
            ))

        return differences

    def _validate_response_content_type(
        self, runtime_data: RuntimeData
    ) -> List[Difference]:
        """Validate that the response content type is documented."""
        differences: List[Difference] = []

        documented_types = self.parser.get_response_content_types(
            runtime_data.path, runtime_data.method, runtime_data.status_code
        )

        if documented_types and runtime_data.response_content_type not in documented_types:
            differences.append(Difference(
                diff_type=DifferenceType.CONTENT_TYPE_MISMATCH,
                severity=ValidationSeverity.WARNING,
                location="content_type",
                json_path="$",
                message=(
                    f"Response Content-Type '{runtime_data.response_content_type}' "
                    f"is not documented. Expected one of: {documented_types}"
                ),
                expected=documented_types,
                actual=runtime_data.response_content_type,
            ))

        return differences

    def _validate_response_body(self, runtime_data: RuntimeData) -> List[Difference]:
        """Validate the response body against the spec schema for the given status code."""
        differences: List[Difference] = []

        expected_schema = self.parser.get_response_schema(
            runtime_data.path,
            runtime_data.method,
            runtime_data.status_code,
            runtime_data.response_content_type,
        )

        if expected_schema is None:
            return differences

        if runtime_data.response_body is None:
            return differences

        body_diffs = self._validate_schema(
            data=runtime_data.response_body,
            schema=expected_schema,
            location="response_body",
            json_path="$",
        )
        differences.extend(body_diffs)

        return differences

    # ------------------------------------------------------------------
    # Schema validation (recursive)
    # ------------------------------------------------------------------

    def _validate_schema(
        self,
        data: Any,
        schema: Dict[str, Any],
        location: str,
        json_path: str,
    ) -> List[Difference]:
        """
        Recursively validate data against a JSON Schema.

        Handles:
        - Type checking (including nullable)
        - Required fields
        - Extra fields
        - Nested objects
        - Arrays (item validation)
        - Enum constraints
        - Nullable values
        """
        differences: List[Difference] = []
        schema = self.parser.resolve_ref(schema)

        # Handle nullable
        nullable = schema.get("nullable", False)
        if data is None:
            if not nullable:
                expected_type = schema.get("type", "unknown")
                differences.append(Difference(
                    diff_type=DifferenceType.NULLABLE_VIOLATION,
                    severity=ValidationSeverity.ERROR,
                    location=location,
                    json_path=json_path,
                    message=f"Value is null at {json_path} but field is not nullable",
                    expected=expected_type,
                    actual="null",
                ))
            return differences

        # Type validation
        expected_type = schema.get("type")
        if expected_type:
            actual_type = self._get_json_type(data)
            if not self._types_match(expected_type, actual_type):
                differences.append(Difference(
                    diff_type=DifferenceType.TYPE_MISMATCH,
                    severity=ValidationSeverity.ERROR,
                    location=location,
                    json_path=json_path,
                    message=(
                        f"Type mismatch at {json_path}: "
                        f"expected '{expected_type}', got '{actual_type}'"
                    ),
                    expected=expected_type,
                    actual=actual_type,
                ))
                return differences  # Stop deeper validation on type mismatch

        # Enum validation
        enum_values = schema.get("enum")
        if enum_values is not None and data not in enum_values:
            differences.append(Difference(
                diff_type=DifferenceType.ENUM_VIOLATION,
                severity=ValidationSeverity.ERROR,
                location=location,
                json_path=json_path,
                message=(
                    f"Value '{data}' at {json_path} is not in allowed "
                    f"enum values: {enum_values}"
                ),
                expected=enum_values,
                actual=data,
            ))

        # Object validation
        if isinstance(data, dict) and schema.get("type") == "object":
            differences.extend(
                self._validate_object(data, schema, location, json_path)
            )

        # Array validation
        elif isinstance(data, list) and schema.get("type") == "array":
            differences.extend(
                self._validate_array(data, schema, location, json_path)
            )

        return differences

    def _validate_object(
        self,
        data: Dict[str, Any],
        schema: Dict[str, Any],
        location: str,
        json_path: str,
    ) -> List[Difference]:
        """Validate an object against its schema properties."""
        differences: List[Difference] = []
        properties = schema.get("properties", {})
        required_fields = schema.get("required", [])

        # Check missing required fields
        for req_field in required_fields:
            if req_field not in data:
                differences.append(Difference(
                    diff_type=DifferenceType.REQUIRED_FIELD_VIOLATION,
                    severity=ValidationSeverity.ERROR,
                    location=location,
                    json_path=f"{json_path}.{req_field}",
                    message=f"Missing required field '{req_field}' at {json_path}",
                    expected=req_field,
                    actual=list(data.keys()),
                ))

        # Check extra fields (not in properties and no additionalProperties)
        additional_props = schema.get("additionalProperties", None)
        for key in data:
            if key not in properties:
                # If additionalProperties is explicitly False, it's an error
                # If not specified or True, it's a warning
                if additional_props is False:
                    severity = ValidationSeverity.ERROR
                else:
                    severity = ValidationSeverity.WARNING

                differences.append(Difference(
                    diff_type=DifferenceType.EXTRA_FIELD,
                    severity=severity,
                    location=location,
                    json_path=f"{json_path}.{key}",
                    message=f"Undocumented field '{key}' at {json_path}",
                    expected=list(properties.keys()),
                    actual=key,
                ))

        # Recursively validate each known property
        for key, value in data.items():
            if key in properties:
                child_schema = self.parser.resolve_ref(properties[key])
                child_path = f"{json_path}.{key}"
                differences.extend(
                    self._validate_schema(value, child_schema, location, child_path)
                )

        return differences

    def _validate_array(
        self,
        data: List[Any],
        schema: Dict[str, Any],
        location: str,
        json_path: str,
    ) -> List[Difference]:
        """Validate array items against the items schema."""
        differences: List[Difference] = []
        items_schema = schema.get("items")

        if not items_schema or len(data) == 0:
            return differences

        items_schema = self.parser.resolve_ref(items_schema)

        # Validate a sample of items (limit to first 10 for performance)
        for idx, item in enumerate(data[:10]):
            child_path = f"{json_path}[{idx}]"
            differences.extend(
                self._validate_schema(item, items_schema, location, child_path)
            )

        return differences

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    @staticmethod
    def _get_json_type(val: Any) -> str:
        """Map a Python value to its JSON Schema type name."""
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
        """Check if runtime type matches expected schema type."""
        if expected == actual:
            return True
        # 'number' accepts both integer and float
        if expected == "number" and actual in ("integer", "number"):
            return True
        return False

    @staticmethod
    def _path_param_type_matches(value: str, expected_type: str) -> bool:
        """Check if a path parameter string value matches the expected type."""
        if expected_type == "string":
            return True
        if expected_type == "integer":
            try:
                int(value)
                return True
            except ValueError:
                return False
        if expected_type == "number":
            try:
                float(value)
                return True
            except ValueError:
                return False
        if expected_type == "boolean":
            return value.lower() in ("true", "false", "0", "1")
        return True

    def _build_report(
        self,
        runtime_data: RuntimeData,
        template: str,
        differences: List[Difference],
    ) -> ValidationReport:
        """Build a ValidationReport from collected differences."""
        # Determine overall status
        has_errors = any(d.severity == ValidationSeverity.ERROR for d in differences)
        has_warnings = any(d.severity == ValidationSeverity.WARNING for d in differences)

        if has_errors:
            status = ValidationStatus.FAILED
            severity = ValidationSeverity.ERROR
        elif has_warnings:
            status = ValidationStatus.WARNING
            severity = ValidationSeverity.WARNING
        else:
            status = ValidationStatus.PASSED
            severity = ValidationSeverity.INFO

        # Build expected schema (from spec)
        expected_schema = self.parser.get_response_schema(
            runtime_data.path,
            runtime_data.method,
            runtime_data.status_code,
            runtime_data.response_content_type,
        ) or {}

        # Build actual schema (inferred from runtime data)
        actual_schema = {}
        if runtime_data.response_body is not None:
            actual_schema = infer_json_schema(runtime_data.response_body)

        return ValidationReport(
            endpoint=template,
            method=runtime_data.method.upper(),
            status=status,
            severity=severity,
            status_code=runtime_data.status_code,
            expected_schema=expected_schema,
            actual_schema=actual_schema,
            differences=differences,
        )