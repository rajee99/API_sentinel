"""Tests for api_sentinel.validator module — Runtime Contract Validation Engine."""

import os
import pytest
from api_sentinel.openapi_parser import OpenAPIParser
from api_sentinel.validator import ContractValidator, RuntimeData
from api_sentinel.validation_report import (
    DifferenceType,
    ValidationSeverity,
    ValidationStatus,
)


SPEC_PATH = os.path.join(os.path.dirname(__file__), "..", "openapi.yaml")


@pytest.fixture
def validator():
    return ContractValidator.from_file(SPEC_PATH)


# ===========================================================================
# Endpoint validation
# ===========================================================================


class TestEndpointValidation:
    """Test endpoint existence validation."""

    def test_valid_endpoint(self, validator):
        data = RuntimeData(
            method="GET",
            path="/api/v1/users",
            status_code=200,
            response_body=[{"id": 1, "name": "Alice", "email": "a@b.com"}],
        )
        report = validator.validate(data)
        undocumented = [
            d for d in report.differences
            if d.diff_type == DifferenceType.UNDOCUMENTED_ENDPOINT
        ]
        assert len(undocumented) == 0

    def test_undocumented_endpoint(self, validator):
        data = RuntimeData(
            method="GET",
            path="/api/v1/unknown",
            status_code=200,
            response_body={},
        )
        report = validator.validate(data)
        assert report.status == ValidationStatus.FAILED
        undocumented = [
            d for d in report.differences
            if d.diff_type == DifferenceType.UNDOCUMENTED_ENDPOINT
        ]
        assert len(undocumented) == 1


# ===========================================================================
# HTTP Method validation
# ===========================================================================


class TestMethodValidation:
    """Test HTTP method validation."""

    def test_valid_method(self, validator):
        data = RuntimeData(
            method="GET",
            path="/api/v1/users",
            status_code=200,
            response_body=[],
        )
        report = validator.validate(data)
        method_issues = [
            d for d in report.differences
            if d.diff_type == DifferenceType.METHOD_NOT_ALLOWED
        ]
        assert len(method_issues) == 0

    def test_method_not_allowed(self, validator):
        data = RuntimeData(
            method="DELETE",
            path="/api/v1/users",
            status_code=200,
            response_body={},
        )
        report = validator.validate(data)
        method_issues = [
            d for d in report.differences
            if d.diff_type == DifferenceType.METHOD_NOT_ALLOWED
        ]
        assert len(method_issues) == 1
        assert report.status == ValidationStatus.FAILED


# ===========================================================================
# Path parameter validation
# ===========================================================================


class TestPathParamValidation:
    """Test path parameter validation."""

    def test_valid_integer_path_param(self, validator):
        data = RuntimeData(
            method="GET",
            path="/api/v1/users/42",
            status_code=200,
            response_body={"id": 42, "name": "Alice", "email": "a@b.com"},
        )
        report = validator.validate(data)
        path_issues = [
            d for d in report.differences
            if d.diff_type == DifferenceType.PATH_PARAM_TYPE_MISMATCH
        ]
        assert len(path_issues) == 0

    def test_invalid_path_param_type(self, validator):
        data = RuntimeData(
            method="GET",
            path="/api/v1/users/not-a-number",
            status_code=200,
            response_body={"id": 1, "name": "Alice", "email": "a@b.com"},
        )
        report = validator.validate(data)
        path_issues = [
            d for d in report.differences
            if d.diff_type == DifferenceType.PATH_PARAM_TYPE_MISMATCH
        ]
        assert len(path_issues) == 1
        assert path_issues[0].severity == ValidationSeverity.WARNING


# ===========================================================================
# Query parameter validation
# ===========================================================================


class TestQueryParamValidation:
    """Test query parameter validation."""

    def test_valid_query_params(self, validator):
        data = RuntimeData(
            method="GET",
            path="/api/v1/users",
            status_code=200,
            query_params={"role": "admin", "limit": "10"},
            response_body=[],
        )
        report = validator.validate(data)
        query_issues = [
            d for d in report.differences
            if d.location == "query_params"
        ]
        assert len(query_issues) == 0

    def test_undocumented_query_param(self, validator):
        data = RuntimeData(
            method="GET",
            path="/api/v1/users",
            status_code=200,
            query_params={"role": "admin", "unknown_param": "value"},
            response_body=[],
        )
        report = validator.validate(data)
        undocumented = [
            d for d in report.differences
            if d.diff_type == DifferenceType.UNDOCUMENTED_QUERY_PARAM
        ]
        assert len(undocumented) == 1
        assert undocumented[0].json_path == "$.unknown_param"


# ===========================================================================
# Request body validation
# ===========================================================================


class TestRequestBodyValidation:
    """Test request body validation."""

    def test_valid_request_body(self, validator):
        data = RuntimeData(
            method="POST",
            path="/api/v1/users",
            status_code=201,
            request_body={"name": "Jane", "email": "jane@example.com"},
            response_body={"id": 1, "name": "Jane", "email": "jane@example.com"},
        )
        report = validator.validate(data)
        body_issues = [
            d for d in report.differences
            if d.location == "request_body"
        ]
        assert len(body_issues) == 0

    def test_missing_required_field_in_request(self, validator):
        data = RuntimeData(
            method="POST",
            path="/api/v1/users",
            status_code=201,
            request_body={"name": "Jane"},  # missing 'email'
            response_body={"id": 1, "name": "Jane", "email": "jane@example.com"},
        )
        report = validator.validate(data)
        missing = [
            d for d in report.differences
            if d.diff_type == DifferenceType.REQUIRED_FIELD_VIOLATION
            and d.location == "request_body"
        ]
        assert len(missing) == 1
        assert "email" in missing[0].message

    def test_extra_field_in_request(self, validator):
        data = RuntimeData(
            method="POST",
            path="/api/v1/users",
            status_code=201,
            request_body={
                "name": "Jane",
                "email": "jane@example.com",
                "secret_field": "hidden",
            },
            response_body={"id": 1, "name": "Jane", "email": "jane@example.com"},
        )
        report = validator.validate(data)
        extra = [
            d for d in report.differences
            if d.diff_type == DifferenceType.EXTRA_FIELD
            and d.location == "request_body"
        ]
        assert len(extra) == 1
        assert "secret_field" in extra[0].message

    def test_type_mismatch_in_request(self, validator):
        data = RuntimeData(
            method="POST",
            path="/api/v1/users",
            status_code=201,
            request_body={"name": 12345, "email": "jane@example.com"},  # name should be string
            response_body={"id": 1, "name": "Jane", "email": "jane@example.com"},
        )
        report = validator.validate(data)
        type_issues = [
            d for d in report.differences
            if d.diff_type == DifferenceType.TYPE_MISMATCH
            and d.location == "request_body"
        ]
        assert len(type_issues) == 1
        assert "name" in type_issues[0].json_path


# ===========================================================================
# Response body validation
# ===========================================================================


class TestResponseBodyValidation:
    """Test response body validation."""

    def test_valid_response_body(self, validator):
        data = RuntimeData(
            method="GET",
            path="/api/v1/users",
            status_code=200,
            response_body=[
                {"id": 1, "name": "Alice", "email": "alice@example.com"}
            ],
        )
        report = validator.validate(data)
        body_issues = [
            d for d in report.differences
            if d.location == "response_body"
            and d.diff_type == DifferenceType.TYPE_MISMATCH
        ]
        assert len(body_issues) == 0

    def test_missing_required_field_in_response(self, validator):
        data = RuntimeData(
            method="GET",
            path="/api/v1/users/1",
            status_code=200,
            response_body={"id": 1, "name": "Alice"},  # missing 'email'
        )
        report = validator.validate(data)
        missing = [
            d for d in report.differences
            if d.diff_type == DifferenceType.REQUIRED_FIELD_VIOLATION
            and d.location == "response_body"
        ]
        assert len(missing) == 1
        assert "email" in missing[0].message

    def test_extra_field_in_response(self, validator):
        data = RuntimeData(
            method="GET",
            path="/api/v1/users/1",
            status_code=200,
            response_body={
                "id": 1,
                "name": "Alice",
                "email": "alice@example.com",
                "debug_info": "should not be here",
            },
        )
        report = validator.validate(data)
        extra = [
            d for d in report.differences
            if d.diff_type == DifferenceType.EXTRA_FIELD
            and d.location == "response_body"
        ]
        assert len(extra) == 1
        assert "debug_info" in extra[0].message

    def test_type_mismatch_in_response(self, validator):
        data = RuntimeData(
            method="GET",
            path="/api/v1/users/1",
            status_code=200,
            response_body={
                "id": "not-an-integer",  # should be integer
                "name": "Alice",
                "email": "alice@example.com",
            },
        )
        report = validator.validate(data)
        type_issues = [
            d for d in report.differences
            if d.diff_type == DifferenceType.TYPE_MISMATCH
            and d.location == "response_body"
        ]
        assert len(type_issues) == 1
        assert type_issues[0].expected == "integer"
        assert type_issues[0].actual == "string"

    def test_nested_object_validation(self, validator):
        """Test that nested objects are validated recursively."""
        # Use login endpoint which has nested structure
        data = RuntimeData(
            method="POST",
            path="/api/v1/auth/login",
            status_code=200,
            request_body={"username": "alice", "password": "secret"},
            response_body={
                "access_token": "eyJhbGciOiJIUzI1NiJ9.test",
                "token_type": "bearer",
            },
        )
        report = validator.validate(data)
        # Should pass cleanly
        body_errors = [
            d for d in report.differences
            if d.location == "response_body"
            and d.severity == ValidationSeverity.ERROR
        ]
        assert len(body_errors) == 0

    def test_missing_token_type_in_login_response(self, validator):
        """Test detection of missing required field in login response."""
        data = RuntimeData(
            method="POST",
            path="/api/v1/auth/login",
            status_code=200,
            request_body={"username": "alice", "password": "secret"},
            response_body={
                "access_token": "eyJhbGciOiJIUzI1NiJ9.test",
                # Missing 'token_type' which is required
            },
        )
        report = validator.validate(data)
        missing = [
            d for d in report.differences
            if d.diff_type == DifferenceType.REQUIRED_FIELD_VIOLATION
            and d.location == "response_body"
        ]
        assert len(missing) == 1
        assert "token_type" in missing[0].message

    def test_array_item_validation(self, validator):
        """Test that array items are validated against the items schema."""
        data = RuntimeData(
            method="GET",
            path="/api/v1/users",
            status_code=200,
            response_body=[
                {"id": 1, "name": "Alice", "email": "alice@example.com"},
                {"id": "bad-id", "name": "Bob", "email": "bob@example.com"},  # id should be int
            ],
        )
        report = validator.validate(data)
        type_issues = [
            d for d in report.differences
            if d.diff_type == DifferenceType.TYPE_MISMATCH
            and "[1]" in d.json_path
        ]
        assert len(type_issues) == 1


# ===========================================================================
# Status code validation
# ===========================================================================


class TestStatusCodeValidation:
    """Test HTTP status code validation."""

    def test_documented_status_code(self, validator):
        data = RuntimeData(
            method="GET",
            path="/api/v1/users",
            status_code=200,
            response_body=[],
        )
        report = validator.validate(data)
        status_issues = [
            d for d in report.differences
            if d.diff_type == DifferenceType.UNDOCUMENTED_STATUS_CODE
        ]
        assert len(status_issues) == 0

    def test_undocumented_status_code(self, validator):
        data = RuntimeData(
            method="GET",
            path="/api/v1/users",
            status_code=500,
            response_body={"error": "Internal Server Error"},
        )
        report = validator.validate(data)
        status_issues = [
            d for d in report.differences
            if d.diff_type == DifferenceType.UNDOCUMENTED_STATUS_CODE
        ]
        assert len(status_issues) == 1

    def test_404_status_code_for_user_by_id(self, validator):
        """404 is documented for /api/v1/users/{id}."""
        data = RuntimeData(
            method="GET",
            path="/api/v1/users/999",
            status_code=404,
            response_body={"detail": "User not found"},
        )
        report = validator.validate(data)
        status_issues = [
            d for d in report.differences
            if d.diff_type == DifferenceType.UNDOCUMENTED_STATUS_CODE
        ]
        assert len(status_issues) == 0


# ===========================================================================
# Content-Type validation
# ===========================================================================


class TestContentTypeValidation:
    """Test Content-Type validation."""

    def test_valid_content_type(self, validator):
        data = RuntimeData(
            method="GET",
            path="/api/v1/users",
            status_code=200,
            response_content_type="application/json",
            response_body=[],
        )
        report = validator.validate(data)
        ct_issues = [
            d for d in report.differences
            if d.diff_type == DifferenceType.CONTENT_TYPE_MISMATCH
        ]
        assert len(ct_issues) == 0

    def test_mismatched_content_type(self, validator):
        data = RuntimeData(
            method="GET",
            path="/api/v1/users",
            status_code=200,
            response_content_type="text/html",
            response_body=[],
        )
        report = validator.validate(data)
        ct_issues = [
            d for d in report.differences
            if d.diff_type == DifferenceType.CONTENT_TYPE_MISMATCH
        ]
        assert len(ct_issues) == 1


# ===========================================================================
# Nullable validation
# ===========================================================================


class TestNullableValidation:
    """Test nullable value handling."""

    def test_nullable_field_with_null_value(self):
        """A nullable field should accept null without error."""
        spec_data = {
            "openapi": "3.0.3",
            "paths": {
                "/test": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "required": ["name"],
                                            "properties": {
                                                "name": {"type": "string"},
                                                "bio": {"type": "string", "nullable": True},
                                            },
                                        }
                                    }
                                },
                            }
                        }
                    }
                }
            },
            "components": {"schemas": {}},
        }
        validator = ContractValidator.from_dict(spec_data)
        data = RuntimeData(
            method="GET",
            path="/test",
            status_code=200,
            response_body={"name": "Alice", "bio": None},
        )
        report = validator.validate(data)
        nullable_issues = [
            d for d in report.differences
            if d.diff_type == DifferenceType.NULLABLE_VIOLATION
        ]
        assert len(nullable_issues) == 0

    def test_non_nullable_field_with_null_value(self):
        """A non-nullable field should raise error when null."""
        spec_data = {
            "openapi": "3.0.3",
            "paths": {
                "/test": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "required": ["name"],
                                            "properties": {
                                                "name": {"type": "string"},
                                            },
                                        }
                                    }
                                },
                            }
                        }
                    }
                }
            },
            "components": {"schemas": {}},
        }
        validator = ContractValidator.from_dict(spec_data)
        data = RuntimeData(
            method="GET",
            path="/test",
            status_code=200,
            response_body={"name": None},
        )
        report = validator.validate(data)
        nullable_issues = [
            d for d in report.differences
            if d.diff_type == DifferenceType.NULLABLE_VIOLATION
        ]
        assert len(nullable_issues) == 1


# ===========================================================================
# Enum validation
# ===========================================================================


class TestEnumValidation:
    """Test enum constraint validation."""

    def test_valid_enum_value(self):
        spec_data = {
            "openapi": "3.0.3",
            "paths": {
                "/test": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "status": {
                                                    "type": "string",
                                                    "enum": ["active", "inactive", "pending"],
                                                }
                                            },
                                        }
                                    }
                                },
                            }
                        }
                    }
                }
            },
            "components": {"schemas": {}},
        }
        validator = ContractValidator.from_dict(spec_data)
        data = RuntimeData(
            method="GET",
            path="/test",
            status_code=200,
            response_body={"status": "active"},
        )
        report = validator.validate(data)
        enum_issues = [
            d for d in report.differences
            if d.diff_type == DifferenceType.ENUM_VIOLATION
        ]
        assert len(enum_issues) == 0

    def test_invalid_enum_value(self):
        spec_data = {
            "openapi": "3.0.3",
            "paths": {
                "/test": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "status": {
                                                    "type": "string",
                                                    "enum": ["active", "inactive", "pending"],
                                                }
                                            },
                                        }
                                    }
                                },
                            }
                        }
                    }
                }
            },
            "components": {"schemas": {}},
        }
        validator = ContractValidator.from_dict(spec_data)
        data = RuntimeData(
            method="GET",
            path="/test",
            status_code=200,
            response_body={"status": "deleted"},  # not in enum
        )
        report = validator.validate(data)
        enum_issues = [
            d for d in report.differences
            if d.diff_type == DifferenceType.ENUM_VIOLATION
        ]
        assert len(enum_issues) == 1
        assert "deleted" in enum_issues[0].message


# ===========================================================================
# Integration tests
# ===========================================================================


class TestIntegration:
    """Full integration tests combining multiple validations."""

    def test_fully_valid_request_response(self, validator):
        """A completely valid request/response should produce PASSED."""
        data = RuntimeData(
            method="POST",
            path="/api/v1/users",
            status_code=201,
            request_body={"name": "Jane", "email": "jane@example.com", "role": "user"},
            response_body={
                "id": 1,
                "name": "Jane",
                "email": "jane@example.com",
                "role": "user",
                "created_at": "2026-08-01T00:00:00Z",
            },
        )
        report = validator.validate(data)
        assert report.status == ValidationStatus.PASSED
        assert report.is_valid is True
        assert report.error_count == 0

    def test_multiple_issues_detected(self, validator):
        """Multiple issues should all be captured in one report."""
        data = RuntimeData(
            method="POST",
            path="/api/v1/auth/login",
            status_code=200,
            request_body={"username": "alice"},  # missing 'password'
            response_body={
                "access_token": 12345,  # should be string
                # missing 'token_type'
                "extra": "field",
            },
        )
        report = validator.validate(data)
        assert report.status == ValidationStatus.FAILED
        assert report.error_count >= 2  # missing password + type mismatch or missing token_type
        assert len(report.differences) >= 3

    def test_report_serialization(self, validator):
        """Validate that reports serialize correctly."""
        data = RuntimeData(
            method="GET",
            path="/api/v1/users",
            status_code=200,
            response_body=[{"id": 1, "name": "Alice", "email": "a@b.com"}],
        )
        report = validator.validate(data)
        report_dict = report.to_dict()
        assert "endpoint" in report_dict
        assert "method" in report_dict
        assert "status" in report_dict
        assert "differences" in report_dict
        assert "timestamp" in report_dict

    def test_from_file_factory(self):
        """Test ContractValidator.from_file factory method."""
        validator = ContractValidator.from_file(SPEC_PATH)
        data = RuntimeData(
            method="GET",
            path="/api/v1/users",
            status_code=200,
            response_body=[],
        )
        report = validator.validate(data)
        assert report.endpoint == "/api/v1/users"