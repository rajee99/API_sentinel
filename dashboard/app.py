"""
API Sentinel - Interactive Dashboard Application
FastAPI web application for visualizing ValidationReport objects, endpoint statuses, schema diffs, and exporting reports.
"""

import json
import os
from typing import Optional
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api_sentinel.validation_report import (
    AggregateReport,
    EndpointValidationResult,
    ValidationStatus,
)
from api_sentinel.diff_engine import DriftSeverity, DriftType
from html_report import generate_html_report, export_json_report


# Root directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(
    title="API Sentinel Dashboard",
    description="Real-time OpenAPI schema drift & validation dashboard",
    version="0.1.0",
)

# Mount static files and templates
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Global in-memory report store for active session
_active_report: AggregateReport = AggregateReport(
    title="API Sentinel Schema Validation Report",
    results=[
        EndpointValidationResult(
            endpoint="/api/v1/users",
            method="GET",
            status_code=200,
            validation_status=ValidationStatus.PASSED,
            severity=None,
            expected_schema={"type": "array", "items": {"type": "object", "properties": {"id": {"type": "integer"}, "name": {"type": "string"}}}},
            actual_schema={"type": "array", "items": {"type": "object", "properties": {"id": {"type": "integer"}, "name": {"type": "string"}}}},
            differences=[],
        ),
        EndpointValidationResult(
            endpoint="/api/v1/users/{id}",
            method="GET",
            status_code=200,
            validation_status=ValidationStatus.WARNING,
            severity=DriftSeverity.WARNING,
            expected_schema={"type": "object", "properties": {"id": {"type": "integer"}, "email": {"type": "string"}}},
            actual_schema={"type": "object", "properties": {"id": {"type": "integer"}, "email": {"type": "string"}, "extra_field": {"type": "string"}}},
            differences=[
                {
                    "issue_type": DriftType.EXTRA_FIELD.value,
                    "severity": DriftSeverity.WARNING.value,
                    "location": "response_body",
                    "message": "Extra undocumented field 'extra_field' returned in response",
                    "expected": None,
                    "actual": "extra_field",
                }
            ],
        ),
        EndpointValidationResult(
            endpoint="/api/v1/auth/login",
            method="POST",
            status_code=400,
            validation_status=ValidationStatus.FAILED,
            severity=DriftSeverity.ERROR,
            expected_schema={"type": "object", "properties": {"token": {"type": "string"}}, "required": ["token"]},
            actual_schema={"type": "object", "properties": {"error_code": {"type": "integer"}}},
            differences=[
                {
                    "issue_type": DriftType.MISSING_REQUIRED_FIELD.value,
                    "severity": DriftSeverity.ERROR.value,
                    "location": "response_body",
                    "message": "Missing required field 'token' in response payload",
                    "expected": "token",
                    "actual": None,
                }
            ],
        ),
    ],
)


def get_active_report() -> AggregateReport:
    """Returns the current active AggregateReport."""
    return _active_report


def set_active_report(report: AggregateReport) -> None:
    """Updates the current active AggregateReport."""
    global _active_report
    _active_report = report


@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """Renders the dashboard home page with summary metrics and endpoint table."""
    report = get_active_report()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"report": report},
    )


@app.get("/endpoint/detail", response_class=HTMLResponse)
async def endpoint_detail(request: Request, index: int = 0):
    """Renders the detailed view for a single endpoint schema validation result."""
    report = get_active_report()
    results = report.results

    if 0 <= index < len(results):
        res = results[index]
    else:
        res = EndpointValidationResult(
            endpoint="/api/unknown",
            method="GET",
            status_code=404,
            validation_status=ValidationStatus.FAILED,
            severity=DriftSeverity.ERROR,
        )

    expected_json = json.dumps(res.expected_schema or {}, indent=2)
    actual_json = json.dumps(res.actual_schema or {}, indent=2)

    return templates.TemplateResponse(
        request=request,
        name="endpoint_detail.html",
        context={
            "res": res,
            "expected_schema_json": expected_json,
            "actual_schema_json": actual_json,
        },
    )


@app.get("/api/report")
async def get_report_json():
    """Returns the active ValidationReport as JSON."""
    report = get_active_report()
    return JSONResponse(content=report.to_dict())


@app.post("/api/report")
async def update_report_json(data: dict):
    """Updates the active ValidationReport from JSON payload."""
    report = AggregateReport.from_dict(data)
    set_active_report(report)
    return {"status": "success", "total_endpoints": report.total_endpoints}


@app.post("/api/report/append")
async def append_report_result(data: dict):
    """Appends or updates an individual EndpointValidationResult in the active report."""
    report = get_active_report()
    try:
        # Check if payload is an EndpointValidationResult or a full result dict
        result = EndpointValidationResult.from_dict(data)
        # Prepend or append to results
        report.results.insert(0, result)
        # Limit in-memory history to latest 100 executions to prevent memory bloat
        if len(report.results) > 100:
            report.results = report.results[:100]
        from datetime import datetime, timezone
        report.timestamp = datetime.now(timezone.utc).isoformat()
        return {"status": "success", "total_endpoints": report.total_endpoints}
    except Exception as exc:
        return JSONResponse(status_code=400, content={"status": "error", "message": str(exc)})


@app.post("/api/report/clear")
async def clear_report():
    """Clears all validation results in the active report."""
    from datetime import datetime, timezone
    report = get_active_report()
    report.results = []
    report.timestamp = datetime.now(timezone.utc).isoformat()
    return {"status": "cleared", "total_endpoints": 0}


@app.get("/api/export/json")
async def export_json():
    """Downloads the current ValidationReport as a formatted JSON file."""
    report = get_active_report()
    json_str = report.to_json()
    return Response(
        content=json_str,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="validation_report.json"'},
    )


@app.get("/api/export/html")
async def export_html():
    """Downloads the current ValidationReport as a standalone HTML file."""
    report = get_active_report()
    html_str = generate_html_report(report)
    return Response(
        content=html_str,
        media_type="text/html",
        headers={"Content-Disposition": 'attachment; filename="validation_report.html"'},
    )

