# API Sentinel — Architecture, Execution & Output Guide (`readmeUnderstand.md`)

## 1. Project Overview & Technologies Used

**API Sentinel** is an asynchronous FastAPI/Starlette ASGI middleware that provides **real-time OpenAPI contract drift detection** with **zero perceived latency impact** on host application responses.

### Tech Stack & Core Libraries Used
- **Python 3.10+**: Core programming language using modern typing annotations (`from __future__ import annotations`, `typing.Optional`, etc.).
- **FastAPI & Starlette**: Web framework and underlying ASGI toolkit (`BaseHTTPMiddleware`, `Request`, `Response`, `ASGIApp`).
- **Uvicorn**: High-performance ASGI server handling asynchronous network requests over HTTP/1.1.
- **PyYAML (`yaml`)**: Parses and resolves YAML/JSON OpenAPI 3.0+ specifications (`openapi.yaml`).
- **Rich (`rich`)**: Renders beautifully styled tables, severity badges (`[ERROR]`, `[WARNING]`), and color-coded panels in the terminal.
- **Pydantic**: Request/response schema definitions used in sample endpoints.
- **GenSON (`genson`)**: Schema inference engine for generating OpenAPI schemas dynamically from runtime JSON payloads.
- **Asyncio**: Standard Python asynchronous runtime for non-blocking fire-and-forget background analysis tasks (`asyncio.create_task`).

---

## 2. How Everything Works Under the Hood

### System Architecture Flow

```
[ Client Request ]
       │
       ▼
┌────────────────────────────────────────────────────────────────────────┐
│  APISentinelMiddleware (api_sentinel/middleware.py)                   │
│  1. Intercepts incoming HTTP request & buffers request body bytes.     │
│  2. Calls upstream FastAPI route handler: response = await call_next()  │
│  3. Consumes response streaming body into byte array & reconstructs it. │
│  4. Immediately dispatches reconstructed Response back to Client!     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                         (Dispatched to Client)
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  Fire-and-Forget Background Task (asyncio.create_task)                 │
│  5. Schedules analyze_payload_async(...) on the running event loop.    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  APIDiffEngine (api_sentinel/diff_engine.py)                           │
│  6. OpenAPISpecParser matches URL (/api/v1/users/42 -> /users/{id}).  │
│  7. Compares query params, request body & response body against spec. │
│  8. Generates List[DriftIssue] objects.                                │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  SentinelReporter (api_sentinel/reporter.py)                           │
│  9. Formats and prints colorized Rich panels to the terminal console.  │
└────────────────────────────────────────────────────────────────────────┘
```

### Key Architectural Pillars

1. **Zero Perceived Latency**:
   The response payload is returned to the HTTP client **before** drift analysis begins. The drift calculation coroutine is wrapped in `asyncio.create_task()`, offloading all JSON schema parsing off the critical response path.
2. **Fail-Safe Monitoring**:
   Every line of code inside the background analysis task is wrapped in a top-level `try/except Exception` block. Monitoring failures can **never** crash or interrupt the host application.
3. **Regex Path Resolution**:
   Endpoints like `/api/v1/users/42` are dynamically matched against OpenAPI path templates like `/api/v1/users/{id}` using converted regular expression patterns.

---

## 3. Specific Logic Calculating the Drift (`diff_engine.py`)

The core validation engine performs targeted structural checks between runtime payloads and `openapi.yaml`:

### 1. `MISSING_REQUIRED_FIELD` (Severity: `ERROR`)
- **Logic**: Inspects the `required` array in the OpenAPI schema object for a given status code.
- **Trigger**: If a field is listed in `required: ["access_token", "token_type"]` but `token_type` is absent in the actual response JSON dictionary.

### 2. `EXTRA_FIELD` (Severity: `WARNING`)
- **Logic**: Compares all keys returned in the actual JSON response dict against `properties` documented in the OpenAPI specification.
- **Trigger**: If a handler returns `"debug_internal_id": "usr_001"` which is omitted from `openapi.yaml`.

### 3. `TYPE_MISMATCH` (Severity: `ERROR`)
- **Logic**: Validates Python primitive types (`int`, `str`, `bool`, `list`, `dict`) against expected OpenAPI types (`integer`, `string`, `boolean`, `array`, `object`).
- **Trigger**: If a field is documented as `integer` but the API returns `"42"` (string).

### 4. `UNDOCUMENTED_STATUS_CODE` (Severity: `WARNING`)
- **Logic**: Checks if the response HTTP status code (e.g. `401`, `500`) exists under `responses:` in `openapi.yaml`.

### 5. `UNDOCUMENTED_ENDPOINT` (Severity: `WARNING`)
- **Logic**: Raised when a request hits a URL route not present anywhere in the specification file.

---

## 4. How Output is Shown & What to Understand From It

### Console Output Format
When drift is detected, `SentinelReporter` renders a highlighted **Rich Panel** in your terminal server log:

```text
╭────────────────── API Sentinel — Schema Drift Detected ──────────────────╮
│ Request: POST /api/v1/auth/login → Status 200                             │
│ Matched Spec Path: /api/v1/auth/login                                    │
├──────────────────────────────────────────────────────────────────────────┤
│ Severity │ Drift Type                │ Location      │ Message           │
├──────────┼───────────────────────────┼───────────────┼───────────────────┤
│ [ERROR]  │ MISSING_REQUIRED_FIELD    │ response_body │ Field 'token_type'│
│          │                           │               │ is required by    │
│          │                           │               │ spec but missing  │
├──────────┼───────────────────────────┼───────────────┼───────────────────┤
│ [WARN]   │ EXTRA_FIELD               │ response_body │ Undocumented field│
│          │                           │               │ 'debug_id' found  │
╰──────────────────────────────────────────────────────────────────────────╯
```

### How to Interpret & Act Upon Terminal Output

| Terminal Badge | Drift Type | Meaning / Cause | Action Required |
| :--- | :--- | :--- | :--- |
| `[ERROR]` | `MISSING_REQUIRED_FIELD` | The API response is missing a key promised to clients in `openapi.yaml`. | **Fix backend code**: Ensure the endpoint returns the required field, or update the OpenAPI spec if it's optional. |
| `[ERROR]` | `TYPE_MISMATCH` | A field returned a data type different from the OpenAPI spec. | **Fix backend serializer**: Cast field to the correct type (e.g., int vs string). |
| `[WARN]` | `EXTRA_FIELD` | API returned new/undocumented fields not listed in the spec. | **Update OpenAPI spec**: Add the new property to `openapi.yaml` documentation. |
| `[WARN]` | `UNDOCUMENTED_STATUS` | API returned a status code (e.g., 422 or 500) not covered in spec. | **Document status code**: Add response schema for that status code in `openapi.yaml`. |
| `[INFO]` | `CLEAN` | Request payload and response match `openapi.yaml` perfectly. | No action required. |

---

## 5. How to Run and Test

### Setup
```powershell
# 1. Create & activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows PowerShell (Set-ExecutionPolicy -Scope Process RemoteSigned if needed)

# 2. Install dependencies in editable mode
pip install -e .
```

### Running the Demo Application
```powershell
# Start the Uvicorn dev server
python example_app.py
```

### Triggering Drift Alerts
In a second terminal window:

```powershell
# Test 1: Trigger EXTRA_FIELD Warning (returns debug_internal_id)
curl http://127.0.0.1:8000/api/v1/users/42

# Test 2: Trigger MISSING_REQUIRED_FIELD Error (omits token_type)
curl -X POST http://127.0.0.1:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"username": "alice", "password": "secret"}'
```
