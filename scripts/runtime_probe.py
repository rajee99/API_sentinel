"""Runtime probe script to discover bugs across the codebase."""

import asyncio
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

FAILURES: list[str] = []


def fail(name: str, detail: str):
    FAILURES.append(f"{name}: {detail}")
    print(f"FAIL {name}: {detail}")


def ok(name: str):
    print(f"OK   {name}")


# --- capture.py probes ---
from api_sentinel.capture import detect_auth_type, sanitize_headers, safe_parse_body, get_content_type

# Bug probe: API key header case insensitivity
if detect_auth_type({"X-API-KEY": "k"}, {}) != "API Key":
    fail("auth_header_case", f"X-API-KEY got {detect_auth_type({'X-API-KEY': 'k'}, {})}")
else:
    ok("auth_header_case")

# Bug probe: query param values shouldn't matter
if detect_auth_type({}, {"Api_Key": "k"}) != "API Key":
    fail("auth_query_mixed_case", detect_auth_type({}, {"Api_Key": "k"}))
else:
    ok("auth_query_mixed_case")

# Bug probe: safe_parse_body with application/json without json substring edge
body = safe_parse_body(b'{"a":1}', "application/json; charset=utf-8")
if body != {"a": 1}:
    fail("parse_body_charset", str(body))
else:
    ok("parse_body_charset")

# --- diff_engine probes ---
from api_sentinel.diff_engine import load_openapi_spec, match_route, APIDiffEngine, OpenAPISpecParser

with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
    f.write("openapi: '3.0.0'\ninfo:\n  title: t\n  version: '1'\npaths: {}\n")
    empty_spec = f.name

try:
    spec = load_openapi_spec(empty_spec)
    if spec is None:
        fail("load_empty_yaml", "yaml.safe_load returned None")
    else:
        ok("load_empty_yaml")
finally:
    os.unlink(empty_spec)

# Bug: resolve_ref with missing component
parser = OpenAPISpecParser({
    "paths": {"/x": {"get": {"responses": {"200": {"description": "ok"}}}}},
    "components": {"schemas": {}},
})
ref_schema = parser.resolve_ref({"$ref": "#/components/schemas/Missing"})
if "$ref" in ref_schema:
    fail("resolve_ref_missing", str(ref_schema))
else:
    ok("resolve_ref_missing")

# Bug: compare_response with 2XX wildcard
spec2 = {
    "paths": {
        "/items": {
            "get": {
                "responses": {
                    "2XX": {
                        "content": {
                            "application/json": {
                                "schema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}
                            }
                        }
                    }
                }
            }
        }
    }
}
engine = APIDiffEngine(OpenAPISpecParser(spec2))
issues = engine.compare_response("/items", "GET", 201, {"id": 1})
if issues:
    fail("response_2xx_wildcard", str(issues))
else:
    ok("response_2xx_wildcard")

# Bug: 404 should match 4XX wildcard
spec3 = {
    "paths": {
        "/items": {
            "get": {
                "responses": {
                    "4XX": {"description": "client error"}
                }
            }
        }
    }
}
engine3 = APIDiffEngine(OpenAPISpecParser(spec3))
issues3 = engine3.compare_response("/items", "GET", 404, None)
if issues3:
    fail("response_4xx_wildcard", str(issues3))
else:
    ok("response_4xx_wildcard")

# --- inferencer probes ---
from api_sentinel.inferencer import infer_json_schema, SchemaInferencer

try:
    infer_json_schema("not a dict")  # type: ignore
    fail("infer_invalid_type", "should have raised or handled")
except Exception as e:
    ok(f"infer_invalid_type_raises ({type(e).__name__})")

si = SchemaInferencer()
if si.infer_schema({"x": 1}).get("type") != "object":
    fail("inferencer_class", si.infer_schema({"x": 1}))
else:
    ok("inferencer_class")

# --- middleware + example_app probe ---
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from api_sentinel.middleware import APISentinelMiddleware
from api_sentinel.runtime_data import RuntimeData

captured: list[RuntimeData] = []

async def capture_process(self, data: RuntimeData):
    captured.append(data)

with tempfile.TemporaryDirectory() as d:
    spec_path = os.path.join(d, "openapi.yaml")
    with open(spec_path, "w", encoding="utf-8") as f:
        f.write("""
openapi: '3.0.0'
info: {title: t, version: '1'}
paths:
  /api/v1/users/{id}:
    get:
      responses:
        '200':
          description: ok
          content:
            application/json:
              schema:
                type: object
                properties:
                  id: {type: integer}
                required: [id]
""")

    app = FastAPI()
    app.add_middleware(APISentinelMiddleware, openapi_path=spec_path, print_clean=False)
    @app.get("/api/v1/users/{id}")
    async def u(id: int):
        return JSONResponse({"id": id, "extra": True})

    with patch.object(APISentinelMiddleware, "_process_captured_data", capture_process):
        client = TestClient(app)
        r = client.get("/api/v1/users/7")
        if r.status_code != 200:
            fail("middleware_response", f"status {r.status_code}")
        elif not captured:
            fail("middleware_capture", "no RuntimeData captured")
        elif captured[0].path_parameters.get("id") != "7":
            fail("middleware_path_param", str(captured[0].path_parameters))
        else:
            ok("middleware_e2e")

    # Excluded paths should bypass capture
    captured.clear()
    app2 = FastAPI()
    app2.add_middleware(APISentinelMiddleware, openapi_path=spec_path)
    @app2.get("/health")
    async def health():
        return {"ok": True}
    with patch.object(APISentinelMiddleware, "_process_captured_data", capture_process):
        client2 = TestClient(app2)
        client2.get("/health")
        if captured:
            fail("excluded_path", "health was captured")
        else:
            ok("excluded_path")

# --- example_app import probe ---
try:
    os.chdir(ROOT)
    import example_app
    ok("example_app_import")
except Exception as e:
    fail("example_app_import", traceback.format_exc())

print("\n=== SUMMARY ===")
if FAILURES:
    print(f"{len(FAILURES)} failure(s):")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("All probes passed")
