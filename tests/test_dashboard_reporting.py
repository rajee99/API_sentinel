"""
Unit & Integration Tests for API Sentinel - Task 3 Dashboard & Reporting Layer
"""

import json
import os
import pytest
from fastapi.testclient import TestClient

from api_sentinel.validation_report import (
    AggregateReport,
    EndpointValidationResult,
    ValidationStatus,
)
from api_sentinel.diff_engine import DriftSeverity, DriftType
from html_report import generate_html_report, export_json_report
from dashboard.app import app, set_active_report, get_active_report


@pytest.fixture
def sample_report() -> AggregateReport:
    return AggregateReport(
        title="Test Validation Report",
        results=[
            EndpointValidationResult(
                endpoint="/api/v1/test_pass",
                method="GET",
                status_code=200,
                validation_status=ValidationStatus.PASSED,
                severity=None,
                expected_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
                actual_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
                differences=[],
            ),
            EndpointValidationResult(
                endpoint="/api/v1/test_warn",
                method="POST",
                status_code=201,
                validation_status=ValidationStatus.WARNING,
                severity=DriftSeverity.WARNING,
                expected_schema={"type": "object", "properties": {"id": {"type": "integer"}}},
                actual_schema={"type": "object", "properties": {"id": {"type": "integer"}, "warn": {"type": "string"}}},
                differences=[
                    {
                        "issue_type": DriftType.EXTRA_FIELD.value,
                        "severity": DriftSeverity.WARNING.value,
                        "location": "response_body",
                        "message": "Extra field warn",
                    }
                ],
            ),
            EndpointValidationResult(
                endpoint="/api/v1/test_fail",
                method="DELETE",
                status_code=500,
                validation_status=ValidationStatus.FAILED,
                severity=DriftSeverity.ERROR,
                expected_schema={"type": "object", "properties": {"status": {"type": "string"}}},
                actual_schema={"type": "object"},
                differences=[
                    {
                        "issue_type": DriftType.MISSING_REQUIRED_FIELD.value,
                        "severity": DriftSeverity.ERROR.value,
                        "location": "response_body",
                        "message": "Missing field status",
                    }
                ],
            ),
        ],
    )


def test_validation_report_metrics(sample_report: ValidationReport):
    assert sample_report.total_endpoints == 3
    assert sample_report.passed_endpoints == 1
    assert sample_report.warning_count == 1
    assert sample_report.failed_endpoints == 1

    report_dict = sample_report.to_dict()
    assert report_dict["summary"]["total_endpoints"] == 3
    assert report_dict["summary"]["passed_endpoints"] == 1
    assert report_dict["summary"]["warning_count"] == 1
    assert report_dict["summary"]["failed_endpoints"] == 1


def test_validation_report_json_serialization(sample_report: AggregateReport):
    json_str = sample_report.to_json()
    reconstructed = AggregateReport.from_json(json_str)

    assert reconstructed.title == sample_report.title
    assert reconstructed.total_endpoints == sample_report.total_endpoints
    assert reconstructed.passed_endpoints == sample_report.passed_endpoints
    assert reconstructed.results[0].endpoint == "/api/v1/test_pass"
    assert reconstructed.results[1].validation_status == ValidationStatus.WARNING
    assert reconstructed.results[2].severity == DriftSeverity.ERROR


def test_html_report_generator(sample_report: AggregateReport, tmp_path):
    output_html_path = os.path.join(tmp_path, "report.html")
    html_content = generate_html_report(sample_report, output_path=output_html_path)

    assert "<!DOCTYPE html>" in html_content
    assert "API Sentinel" in html_content
    assert "/api/v1/test_pass" in html_content
    assert "/api/v1/test_fail" in html_content
    assert os.path.exists(output_html_path)

    with open(output_html_path, "r", encoding="utf-8") as f:
        saved_html = f.read()
    assert saved_html == html_content


def test_json_report_exporter(sample_report: AggregateReport, tmp_path):
    output_json_path = os.path.join(tmp_path, "report.json")
    json_content = export_json_report(sample_report, output_path=output_json_path)

    assert os.path.exists(output_json_path)
    loaded_data = json.loads(json_content)
    assert loaded_data["summary"]["total_endpoints"] == 3


def test_dashboard_fastapi_endpoints(sample_report: AggregateReport):
    set_active_report(sample_report)
    client = TestClient(app)

    # Test Dashboard Home
    resp_home = client.get("/")
    assert resp_home.status_code == 200
    assert "API Sentinel" in resp_home.text
    assert "/api/v1/test_pass" in resp_home.text

    # Test Endpoint Detail Page
    resp_detail = client.get("/endpoint/detail?index=1")
    assert resp_detail.status_code == 200
    assert "/api/v1/test_warn" in resp_detail.text
    assert "Extra field warn" in resp_detail.text

    # Test API Get Report
    resp_api = client.get("/api/report")
    assert resp_api.status_code == 200
    data = resp_api.json()
    assert data["summary"]["total_endpoints"] == 3

    # Test API Export JSON
    resp_export_json = client.get("/api/export/json")
    assert resp_export_json.status_code == 200
    assert "attachment; filename=\"validation_report.json\"" in resp_export_json.headers["content-disposition"]

    # Test API Export HTML
    resp_export_html = client.get("/api/export/html")
    assert resp_export_html.status_code == 200
    assert "attachment; filename=\"validation_report.html\"" in resp_export_html.headers["content-disposition"]
    assert "<!DOCTYPE html>" in resp_export_html.text

    # Test API Update Report
    new_report = AggregateReport(
        title="Updated Report",
        results=[
            EndpointValidationResult(
                endpoint="/api/v2/new_route",
                method="GET",
                status_code=200,
                validation_status=ValidationStatus.PASSED,
            )
        ],
    )
    resp_post = client.post("/api/report", json=new_report.to_dict())
    assert resp_post.status_code == 200
    assert resp_post.json()["total_endpoints"] == 1
    assert get_active_report().results[0].endpoint == "/api/v2/new_route"

    # Test API Append Result
    append_data = {
        "endpoint": "/api/v1/live_stream",
        "method": "POST",
        "status_code": 200,
        "validation_status": "WARNING",
        "severity": "WARNING",
        "differences": [{"issue_type": "EXTRA_FIELD", "message": "Live drift detected"}],
    }
    resp_append = client.post("/api/report/append", json=append_data)
    assert resp_append.status_code == 200
    assert resp_append.json()["total_endpoints"] == 2
    assert get_active_report().results[0].endpoint == "/api/v1/live_stream"

    # Test API Clear Report
    resp_clear = client.post("/api/report/clear")
    assert resp_clear.status_code == 200
    assert resp_clear.json()["total_endpoints"] == 0
    assert get_active_report().total_endpoints == 0

