r"""
push_to_dashboard.py
====================
Hits the demo API on port 8000, runs the ContractValidator against each
request/response, builds an AggregateReport, then POSTs it to the dashboard
on port 8001 so you can see real live drift results appear instantly.

Run with:
    .venv\Scripts\python push_to_dashboard.py
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

from api_sentinel.openapi_parser import OpenAPIParser
from api_sentinel.validator import ContractValidator, RuntimeData
from api_sentinel.validation_report import (
    AggregateReport,
    EndpointValidationResult,
    ValidationStatus,
)
from api_sentinel.diff_engine import DriftSeverity


DEMO_API   = "http://127.0.0.1:8000"
DASHBOARD  = "http://127.0.0.1:8001"
SPEC_PATH  = "openapi.yaml"

# ──────────────────────────────────────────────────────────────────────────────
# Helper: do a simple HTTP request and return (status_code, parsed_body)
# ──────────────────────────────────────────────────────────────────────────────

def http(method, url, body=None, content_type="application/json"):
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", content_type)
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


# ──────────────────────────────────────────────────────────────────────────────
# Build the validator
# ──────────────────────────────────────────────────────────────────────────────

validator = ContractValidator.from_file(SPEC_PATH)

def to_drift_severity(report):
    """Map ValidationSeverity → DriftSeverity for AggregateReport."""
    from api_sentinel.validation_report import ValidationSeverity
    sev_map = {
        ValidationSeverity.ERROR:   DriftSeverity.ERROR,
        ValidationSeverity.WARNING: DriftSeverity.WARNING,
        ValidationSeverity.INFO:    None,
    }
    return sev_map.get(report.severity)

def make_result(report, raw_diffs):
    """Convert a single ValidationReport → EndpointValidationResult."""
    vs_map = {
        "PASSED":  ValidationStatus.PASSED,
        "WARNING": ValidationStatus.WARNING,
        "FAILED":  ValidationStatus.FAILED,
    }
    return EndpointValidationResult(
        endpoint=report.endpoint,
        method=report.method,
        status_code=report.status_code,
        validation_status=vs_map[report.status.value],
        severity=to_drift_severity(report),
        expected_schema=report.expected_schema,
        actual_schema=report.actual_schema,
        differences=raw_diffs,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 1 — GET /api/v1/users  (clean list, should PASS)
# ──────────────────────────────────────────────────────────────────────────────

print("\n[1/5] GET /api/v1/users — expecting PASSED ...")
status, body = http("GET", f"{DEMO_API}/api/v1/users")
rd = RuntimeData(method="GET", path="/api/v1/users", status_code=status,
                 response_body=body if isinstance(body, list) else [])
r1 = validator.validate(rd)
diffs1 = [d.to_dict() for d in r1.differences]
print(f"      → {r1.status.value} | {len(diffs1)} differences")
result1 = make_result(r1, diffs1)


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 2 — GET /api/v1/users/42  (extra field 'debug_internal_id' → WARNING)
# ──────────────────────────────────────────────────────────────────────────────

print("[2/5] GET /api/v1/users/42 — expecting EXTRA_FIELD warning ...")
status, body = http("GET", f"{DEMO_API}/api/v1/users/42")
rd = RuntimeData(method="GET", path="/api/v1/users/42", status_code=status,
                 response_body=body)
r2 = validator.validate(rd)
diffs2 = [d.to_dict() for d in r2.differences]
print(f"      → {r2.status.value} | {len(diffs2)} differences: {[d['diff_type'] for d in diffs2]}")
result2 = make_result(r2, diffs2)


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 3 — POST /api/v1/auth/login  (token_type missing → FAILED)
# ──────────────────────────────────────────────────────────────────────────────

print("[3/5] POST /api/v1/auth/login — expecting MISSING_REQUIRED_FIELD error ...")
status, body = http("POST", f"{DEMO_API}/api/v1/auth/login",
                    body={"username": "alice", "password": "secret"})
rd = RuntimeData(method="POST", path="/api/v1/auth/login", status_code=status,
                 request_body={"username": "alice", "password": "secret"},
                 response_body=body)
r3 = validator.validate(rd)
diffs3 = [d.to_dict() for d in r3.differences]
print(f"      → {r3.status.value} | {len(diffs3)} differences: {[d['diff_type'] for d in diffs3]}")
result3 = make_result(r3, diffs3)


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 4 — POST /api/v1/users with type mismatch (name as integer → FAILED)
# ──────────────────────────────────────────────────────────────────────────────

print("[4/5] POST /api/v1/users — type mismatch (name=integer) ...")
rd = RuntimeData(method="POST", path="/api/v1/users", status_code=201,
                 request_body={"name": 99999, "email": "bad@example.com"},
                 response_body={"id": 1, "name": 99999, "email": "bad@example.com"})
r4 = validator.validate(rd)
diffs4 = [d.to_dict() for d in r4.differences]
print(f"      → {r4.status.value} | {len(diffs4)} differences: {[d['diff_type'] for d in diffs4]}")
result4 = make_result(r4, diffs4)


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 5 — GET /api/v1/users/999 — 404 with correct body (should PASS)
# ──────────────────────────────────────────────────────────────────────────────

print("[5/5] GET /api/v1/users/9999999 — 404 not-found (expecting PASSED) ...")
status, body = http("GET", f"{DEMO_API}/api/v1/users/9999999")
rd = RuntimeData(method="GET", path="/api/v1/users/9999999", status_code=status,
                 response_body=body)
r5 = validator.validate(rd)
diffs5 = [d.to_dict() for d in r5.differences]
print(f"      → {r5.status.value} | {len(diffs5)} differences")
result5 = make_result(r5, diffs5)


# ──────────────────────────────────────────────────────────────────────────────
# Assemble and POST to dashboard
# ──────────────────────────────────────────────────────────────────────────────

report = AggregateReport(
    title=f"Live Validation Run — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
    results=[result1, result2, result3, result4, result5],
)

print(f"\n📤 Pushing report to dashboard ({DASHBOARD}/api/report) ...")
dash_status, dash_body = http("POST", f"{DASHBOARD}/api/report", body=report.to_dict())

if dash_status == 200:
    total = dash_body.get("total_endpoints", "?")
    print(f"\n✅ Dashboard updated! {total} endpoints now visible.")
    print(f"   Open → {DASHBOARD}")
    print(f"\n   Summary:")
    print(f"   • Total    : {report.total_endpoints}")
    print(f"   • Passed   : {report.passed_endpoints}")
    print(f"   • Warnings : {report.warning_count}")
    print(f"   • Failed   : {report.failed_endpoints}")
else:
    print(f"\n❌ Dashboard push failed (HTTP {dash_status}): {dash_body}")
