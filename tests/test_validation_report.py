"""Tests for api_sentinel.validation_report module."""

import pytest
from api_sentinel.validation_report import (
    Difference,
    DifferenceType,
    ValidationReport,
    ValidationSeverity,
    ValidationStatus,
)


class TestDifference:
    """Tests for the Difference dataclass."""

    def test_create_difference(self):
        diff = Difference(
            diff_type=DifferenceType.TYPE_MISMATCH,
            severity=ValidationSeverity.ERROR,
            location="response_body",
            json_path="$.user.age",
            message="Type mismatch: expected 'integer', got 'string'",
            expected="integer",
            actual="string",
        )
        assert diff.diff_type == DifferenceType.TYPE_MISMATCH
        assert diff.severity == ValidationSeverity.ERROR
        assert diff.location == "response_body"
        assert diff.json_path == "$.user.age"

    def test_to_dict(self):
        diff = Difference(
            diff_type=DifferenceType.MISSING_FIELD,
            severity=ValidationSeverity.ERROR,
            location="response_body",
            json_path="$.name",
            message="Missing required field 'name'",
            expected="name",
            actual=["id", "email"],
        )
        result = diff.to_dict()
        assert result["diff_type"] == "MISSING_FIELD"
        assert result["severity"] == "ERROR"
        assert result["expected"] == "name"
        assert result["actual"] == ["id", "email"]


class TestValidationReport:
    """Tests for the ValidationReport dataclass."""

    def test_create_passed_report(self):
        report = ValidationReport.create_passed(
            endpoint="/api/v1/users",
            method="GET",
            status_code=200,
        )
        assert report.status == ValidationStatus.PASSED
        assert report.is_valid is True
        assert report.error_count == 0
        assert report.warning_count == 0

    def test_failed_report(self):
        diffs = [
            Difference(
                diff_type=DifferenceType.TYPE_MISMATCH,
                severity=ValidationSeverity.ERROR,
                location="response_body",
                json_path="$.id",
                message="Type mismatch",
            ),
            Difference(
                diff_type=DifferenceType.EXTRA_FIELD,
                severity=ValidationSeverity.WARNING,
                location="response_body",
                json_path="$.debug",
                message="Extra field",
            ),
        ]
        report = ValidationReport(
            endpoint="/api/v1/users",
            method="GET",
            status=ValidationStatus.FAILED,
            severity=ValidationSeverity.ERROR,
            status_code=200,
            differences=diffs,
        )
        assert report.is_valid is False
        assert report.error_count == 1
        assert report.warning_count == 1

    def test_to_dict(self):
        report = ValidationReport.create_passed(
            endpoint="/api/v1/users",
            method="GET",
            status_code=200,
        )
        result = report.to_dict()
        assert result["endpoint"] == "/api/v1/users"
        assert result["method"] == "GET"
        assert result["status"] == "PASSED"
        assert result["status_code"] == 200
        assert isinstance(result["differences"], list)
        assert "timestamp" in result

    def test_summary(self):
        report = ValidationReport.create_passed(
            endpoint="/api/v1/users/{id}",
            method="GET",
            status_code=200,
        )
        summary = report.summary()
        assert "PASSED" in summary
        assert "GET" in summary
        assert "/api/v1/users/{id}" in summary
        assert "200" in summary


class TestEnums:
    """Tests for enum values."""

    def test_validation_status_values(self):
        assert ValidationStatus.PASSED.value == "PASSED"
        assert ValidationStatus.FAILED.value == "FAILED"
        assert ValidationStatus.WARNING.value == "WARNING"

    def test_difference_type_values(self):
        assert DifferenceType.MISSING_FIELD.value == "MISSING_FIELD"
        assert DifferenceType.EXTRA_FIELD.value == "EXTRA_FIELD"
        assert DifferenceType.TYPE_MISMATCH.value == "TYPE_MISMATCH"
        assert DifferenceType.ENUM_VIOLATION.value == "ENUM_VIOLATION"
        assert DifferenceType.NULLABLE_VIOLATION.value == "NULLABLE_VIOLATION"
        assert DifferenceType.REQUIRED_FIELD_VIOLATION.value == "REQUIRED_FIELD_VIOLATION"