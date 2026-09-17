# API Sentinel: Comprehensive Request Lifecycle & Contract Drift Guide

---

## 1. Scenario & Architectural Context

When a company fills out their API documentation using an OpenAPI 3.0 specification (`openapi.yaml`), **API Sentinel** operates as an **asynchronous, non-blocking ASGI / Starlette middleware** embedded directly inside the application runtime.

### High-Level Principle of Operation
1. **Zero Latency Overhead for the Client:** API Sentinel buffers the request, lets the application handler execute, captures the response, and **immediately streams the response back to the client**.
2. **Asynchronous Fire-and-Forget Drift Analysis:** Drift detection, schema comparison, terminal reporting, and dashboard synchronization are dispatched to a **background task** (`asyncio.create_task`) on the Python asyncio event loop.
3. **Fail-Open Design:** If any parsing, schema comparison, or reporting exception occurs, it is trapped and logged. **Sentinel will never interrupt, degrade, or crash the host application**.

---

## 2. The Concrete Request Traced

For this end-to-end trace, we trace a real endpoint from the repository:

* **Endpoint:** `POST /api/v1/auth/login`
* **Target Application File:** `example_app.py`
* **OpenAPI Specification File:** `openapi.yaml`
* **Client Request:**
  ```http
  POST /api/v1/auth/login HTTP/1.1
  Host: 127.0.0.1:8000
  Content-Type: application/json
  Accept: application/json

  {
    "username": "alice",
    "password": "secret"
  }
  ```
* **Documented Schema in `openapi.yaml` (`LoginResponse`):**
  - Requires: `["access_token", "token_type"]`
* **Actual Application Response returned by `example_app.py`:**
  - Status: `200 OK`
  - Body: `{"access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.demo.signature"}`
  - **Inconsistency:** The handler deliberately omits `token_type`, triggering a **`MISSING_REQUIRED_FIELD`** drift error.

---

## 3. End-to-End Execution Flow Diagram

```
CLIENT (curl / Browser / Mobile App)
   │
   │  [HTTP POST /api/v1/auth/login]
   ▼
[Uvicorn ASGI Web Server] (Network socket layer)
   │
   ▼
[FastAPI / Starlette Middleware Stack]
   │
   ▼
[APISentinelMiddleware.dispatch()] (api_sentinel/middleware.py)
   │
   ├─► 1. Pre-execution Capture:
   │      - Reads request body bytes: await request.body()
   │      - Re-arms receive channel: request._receive = _restore_receive
   │      - Sanitizes headers (masks secrets): sanitize_headers()
   │      - Detects authentication type: detect_auth_type()
   │      - Parses JSON request body: safe_parse_body()
   │
   ├─► 2. Downstream Execution:
   │      - Calls route handler: response = await call_next(request)
   │      - FastAPI executes login(credentials: LoginRequest) in example_app.py
   │      - Handler returns JSONResponse(content={"access_token": "..."})
   │
   ├─► 3. Post-execution Capture:
   │      - Buffers response stream: await self._buffer_response_body(response)
   │      - Reconstructs clean Response object for client
   │      - Sanitizes response headers & parses JSON response body
   │      - Instantiates RuntimeData dataclass
   │
   ├─► 4. Immediate Client Return:
   │      - Returns reconstructed Response to Client (No latency added!)
   │
   └─► 5. Background Task Spawned (asyncio.create_task):
          │
          ▼
       [_process_captured_data(runtime_data)]
          │
          ├─► OpenAPISpecParser.get_operation("/api/v1/auth/login", "POST")
          │      - Regex route matching: match_route()
          │      - Resolves $ref pointers: resolve_ref()
          │
          ├─► APIDiffEngine.analyze_payload_async()
          │      ├─► compare_request()  ── (validates query params & body) -> []
          │      └─► compare_response() ── (validates status code & body)
          │            └─► _validate_schema() ── detects missing "token_type"
          │                  └─► Generates DriftIssue(MISSING_REQUIRED_FIELD, ERROR)
          │
          ├─► SentinelReporter.report_drift(issues)
          │      - Rich terminal output (Table + Panel) rendered to console
          │
          └─► _post_to_dashboard(data, matched_path, issues)
                 - Posts JSON to http://127.0.0.1:8001/api/report/append
                 - In-memory dashboard state (_active_report) updated
```

---

## 4. Microscopic Code Walkthrough (Step-by-Step)

### Step 1: Startup & Initialization
When `uvicorn example_app:app` starts, FastAPI registers `APISentinelMiddleware`.

* **File:** `api_sentinel/middleware.py`
* **Class:** `APISentinelMiddleware`
* **Method:** `__init__()` (Lines 41–71)

```python
# Parse spec at startup
self._parser = OpenAPISpecParser.from_file(openapi_path)
self._diff_engine = APIDiffEngine(self._parser)
self._reporter = SentinelReporter()
```
* **What happens:** 
  - `OpenAPISpecParser.from_file("openapi.yaml")` invokes `yaml.safe_load()` in `diff_engine.py` (Lines 49–55).
  - Routes in `openapi.yaml` are pre-compiled into regular expressions (e.g., `/api/v1/users/{id}` becomes `^/api/v1/users/[^/]+$`).

---

### Step 2: Request Enters Middleware Dispatch
The HTTP request arrives at Uvicorn, which wraps the ASGI receive channel into a Starlette `Request` object and invokes `APISentinelMiddleware.dispatch()`.

* **File:** `api_sentinel/middleware.py`
* **Class:** `APISentinelMiddleware`
* **Method:** `dispatch(self, request: Request, call_next: Callable)` (Lines 73–108)

```python
async def dispatch(self, request: Request, call_next: Callable) -> Response:
    if not self.enabled or self._is_excluded(request.url.path):
        return await call_next(request)

    # 1. Capture request body and metadata pre-execution
    try:
        request_body_bytes: bytes = await request.body()
    except Exception:
        logger.debug("APISentinelMiddleware: failed to buffer request body", exc_info=True)
        return await call_next(request)
```

1. **Exclusion Check (`_is_excluded`):** Paths like `/docs`, `/openapi.json`, and `/favicon.ico` bypass validation. `/api/v1/auth/login` is not excluded.
2. **Body Buffering & Stream Preservation:** In ASGI, request body streams can only be read once. Sentinel reads `await request.body()`, caches the bytes in `_cached_body`, and **restores the receive channel**:
   ```python
   _cached_body = request_body_bytes

   async def _restore_receive() -> dict:
       return {"type": "http.request", "body": _cached_body, "more_body": False}

   request._receive = _restore_receive
   ```
   *Note:* Without `_restore_receive`, downstream FastAPI Pydantic parsing would hang or receive an empty body.

---

### Step 3: Request Header Sanitization and Parsing
* **File:** `api_sentinel/capture.py`
* **Functions:** `sanitize_headers()`, `detect_auth_type()`, `get_content_type()`, `safe_parse_body()`

```python
# Pre-capture request fields
method = request.method                                         # "POST"
endpoint = request.url.path                                     # "/api/v1/auth/login"
query_parameters = dict(request.query_params)                   # {}
request_headers_raw = dict(request.headers)
request_headers = sanitize_headers(request_headers_raw)
authentication_type = detect_auth_type(request_headers_raw, query_parameters) # "Anonymous"
request_content_type = get_content_type(request_headers_raw)   # "application/json"
request_body = safe_parse_body(_cached_body, request_content_type)
# request_body becomes: {"username": "alice", "password": "secret"}
```

* **Header Sanitization Logic:**
  ```python
  sensitive_keys = {
      "authorization", "cookie", "set-cookie", "x-api-key", "api-key", 
      "apikey", "proxy-authorization", "token", "session", "session-id"
  }
  ```
  Any matching key is redacted (e.g., `Authorization: Bearer [REDACTED]` or `[REDACTED]`).

---

### Step 4: Downstream Route Execution
* **File:** `api_sentinel/middleware.py` (Line 110)

```python
# 2. Call upstream route handler
response: Response = await call_next(request)
```

- Control passes into FastAPI routing.
- FastAPI parses the body into `credentials: LoginRequest` in `example_app.py` (Lines 137–161).
- The `login` handler verifies `credentials.password == "secret"` and returns:
  ```python
  payload = {
      "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.demo.signature",
      # "token_type": "bearer", ← Intentionally omitted by developer!
  }
  return JSONResponse(content=payload)
  ```

---

### Step 5: Response Buffering and Immediate Re-delivery
* **File:** `api_sentinel/middleware.py` (Lines 113–157)

```python
# 3. Capture response body and metadata
try:
    response_body_bytes = await self._buffer_response_body(response)
except Exception:
    logger.debug("APISentinelMiddleware: failed to buffer response body", exc_info=True)
    return response

path_parameters = dict(request.path_params)
status_code = response.status_code                     # 200
response_headers_raw = dict(response.headers)
response_headers = sanitize_headers(response_headers_raw)
response_content_type = get_content_type(response_headers_raw)
response_body = safe_parse_body(response_body_bytes, response_content_type)

# Reconstruct response to send to client immediately
headers = dict(response.headers)
headers.pop("content-length", None)
reconstructed = Response(
    content=response_body_bytes,
    status_code=status_code,
    headers=headers,
    media_type=response.media_type,
)

# 4. Construct RuntimeData
runtime_data = RuntimeData(
    method=method,
    endpoint=endpoint,
    path_parameters=path_parameters,
    query_parameters=query_parameters,
    request_headers=request_headers,
    request_body=request_body,
    authentication_type=authentication_type,
    status_code=status_code,
    response_headers=response_headers,
    response_body=response_body,
)

# 5. Fire-and-forget background processing
asyncio.create_task(
    self._process_captured_data(runtime_data),
    name=f"sentinel:capture:{method}:{endpoint}",
)

return reconstructed
```

* **Data state of `RuntimeData` object at this moment:**
  - `method`: `"POST"`
  - `endpoint`: `"/api/v1/auth/login"`
  - `path_parameters`: `{}`
  - `query_parameters`: `{}`
  - `request_headers`: `{"content-type": "application/json", ...}` (sanitized)
  - `request_body`: `{"username": "alice", "password": "secret"}`
  - `authentication_type`: `"Anonymous"`
  - `status_code`: `200`
  - `response_headers`: `{"content-type": "application/json", ...}` (sanitized)
  - `response_body`: `{"access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.demo.signature"}`
  - `timestamp`: ISO-8601 UTC string

---

### Step 6: Asynchronous Validation in Background Task
The background task runs `_process_captured_data()` concurrently without blocking the client.

* **File:** `api_sentinel/middleware.py` (Lines 159–194)

```python
async def _process_captured_data(self, data: RuntimeData) -> None:
    try:
        logger.info(
            "Captured RuntimeData: method=%s, endpoint=%s, status_code=%d, auth=%s",
            data.method, data.endpoint, data.status_code, data.authentication_type,
        )

        if self._diff_engine:
            op_match = self._parser.get_operation(data.endpoint, data.method)
            matched_path = op_match[0] if op_match else None
            
            issues = await self._diff_engine.analyze_payload_async(
                method=data.method,
                raw_path=data.endpoint,
                matched_path=matched_path,
                status_code=data.status_code,
                query_params=data.query_parameters,
                request_body=data.request_body,
                response_body=data.response_body,
                reporter=self._reporter,
                print_clean=self.print_clean,
            )

            if self.dashboard_url:
                await self._post_to_dashboard(data, matched_path, issues)
    except Exception:
        logger.error("Error in Sentinel capture background task", exc_info=True)
```

---

### Step 7: OpenAPI Operation Lookup & Route Matching
* **File:** `api_sentinel/diff_engine.py`
* **Function:** `match_route(live_path, openapi_paths)` (Lines 57–136)

```python
def match_route(live_path: str, openapi_paths: list) -> Optional[str]:
    clean_path = live_path.rstrip("/") if len(live_path) > 1 else live_path
    if clean_path in openapi_paths:
        return clean_path
    ...
```
1. `match_route("/api/v1/auth/login", ["/api/v1/users", "/api/v1/users/{id}", "/api/v1/auth/login"])` finds an exact match: `"/api/v1/auth/login"`.
2. `get_operation` retrieves the spec dictionary for `post`:
   ```yaml
   operationId: loginUser
   requestBody:
     required: true
     content:
       application/json:
         schema:
           $ref: '#/components/schemas/LoginRequest'
   responses:
     '200':
       content:
         application/json:
           schema:
             $ref: '#/components/schemas/LoginResponse'
   ```

---

### Step 8: Diff Engine Comparison & Drift Detection
* **File:** `api_sentinel/diff_engine.py`
* **Class:** `APIDiffEngine`
* **Methods:** `compare_request()`, `compare_response()`, `_validate_schema()` (Lines 247–443)

#### A. Request Validation (`compare_request`):
1. Resolves `$ref: '#/components/schemas/LoginRequest'` into `{type: object, required: [username, password], properties: {...}}`.
2. Validates `{"username": "alice", "password": "secret"}` against `LoginRequest`:
   - `username` is present and is `string` (Match).
   - `password` is present and is `string` (Match).
   - No extra fields.
3. `request_issues` returns `[]`.

#### B. Response Validation (`compare_response`):
1. Looks up status code `200` in `responses`.
2. Resolves `$ref: '#/components/schemas/LoginResponse'` via `self.parser.resolve_ref()`:
   ```python
   {
       "type": "object",
       "required": ["access_token", "token_type"],
       "properties": {
           "access_token": {"type": "string"},
           "token_type": {"type": "string"}
       }
   }
   ```
3. Calls `_validate_schema(data=body, schema=resolved_schema, ...)`:
   ```python
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
   ```
4. **Mismatch Detected:**
   - For `req = "token_type"`, `"token_type"` is not in `data` (`["access_token"]`).
   - A `DriftIssue` is instantiated:
     ```python
     DriftIssue(
         issue_type=DriftType.MISSING_REQUIRED_FIELD,
         severity=DriftSeverity.ERROR,
         path="/api/v1/auth/login",
         method="POST",
         location="response_body",
         message="Missing required field 'token_type' at $",
         expected="token_type",
         actual=["access_token"]
     )
     ```

---

### Step 9: Real-Time Console Alert Generation
Because `all_issues` contains a `DriftIssue`, Sentinel calls `SentinelReporter.report_drift(all_issues)`.

* **File:** `api_sentinel/reporter.py`
* **Class:** `SentinelReporter`
* **Method:** `report_drift(self, issues: List[DriftIssue])` (Lines 21–64)

```python
table = Table(
    title="[bold underline cyan]🛡️ API Sentinel - Schema Drift Detected[/bold underline cyan]",
    show_header=True,
    header_style="bold magenta",
    border_style="dim white",
    expand=True,
)
...
panel = Panel(
    table,
    title="[bold red]🚨 API DRIFT WARNING[/bold red]",
    subtitle="[dim]API Sentinel Middleware[/dim]",
    border_style="red",
    expand=True,
)
self.console.print(panel)
```

---

### Step 10: Asynchronous Dashboard Synchronization
* **File:** `api_sentinel/middleware.py`
* **Method:** `_post_to_dashboard(self, data: RuntimeData, matched_path: Optional[str], issues: list)` (Lines 195–267)

```python
payload = {
    "endpoint": matched_path or data.endpoint,
    "method": data.method.upper(),
    "status_code": data.status_code,
    "validation_status": "FAILED",
    "severity": "ERROR",
    "expected_schema": expected_schema,
    "actual_schema": data.response_body if isinstance(data.response_body, (dict, list)) else {},
    "differences": [
        {
            "issue_type": "MISSING_REQUIRED_FIELD",
            "severity": "ERROR",
            "location": "response_body",
            "message": "Missing required field 'token_type' at $",
            "expected": "token_type",
            "actual": ["access_token"]
        }
    ],
}
```
1. Builds standard HTTP request payload.
2. Sends async HTTP POST via `await asyncio.to_thread(_send)` to `http://127.0.0.1:8001/api/report/append`.
3. The Dashboard application (`dashboard/app.py` Lines 164–181) receives the payload:
   ```python
   result = EndpointValidationResult.from_dict(data)
   report.results.insert(0, result) # Prepends result
   if len(report.results) > 100:    # Keeps latest 100 in memory
       report.results = report.results[:100]
   ```
4. Navigating to `http://127.0.0.1:8001` immediately renders the updated status (`FAILED`), summary KPI metrics, and diff modal.

---

## 5. Comprehensive Answers to All 43 Technical Audit Questions

### Framework, Middleware, & Request Entry
1. **Where the request first enters the application:** At the ASGI web server (e.g., Uvicorn) listening on the host network socket.
2. **Which framework receives it:** *THIS PART IS PROVIDED BY FASTAPI / STARLETTE / UVICORN, NOT IMPLEMENTED BY API SENTINEL.*
3. **How the middleware gets involved:** Registered via `app.add_middleware(APISentinelMiddleware, ...)` into Starlette's `BaseHTTPMiddleware` stack.
4. **Which middleware class handles it:** `APISentinelMiddleware` (`api_sentinel/middleware.py`).
5. **Which method/function is called:** `async def dispatch(self, request: Request, call_next: Callable) -> Response`.
6. **Exact file name:** `middleware.py`.
7. **Exact file path:** `D:/api drift/API_sentinel-main/api_sentinel/middleware.py`.
8. **Relevant class name:** `APISentinelMiddleware`.
9. **Relevant function/method name:** `dispatch`.
10. **Relevant code snippet:** Lines 73–158 in `api_sentinel/middleware.py`.
11. **What each important line does:** 
    - Line 82: `request_body_bytes = await request.body()` buffers incoming stream.
    - Line 93: `request._receive = _restore_receive` restores ASGI receive channel for FastAPI.
    - Line 100: `sanitize_headers()` redacts passwords, tokens, session IDs.
    - Line 110: `await call_next(request)` invokes the downstream FastAPI handler.
    - Line 114: `_buffer_response_body(response)` reads the response stream.
    - Line 130: Reconstructs clean `Response` for the client.
    - Line 152: `asyncio.create_task(self._process_captured_data(runtime_data))` schedules background validation.
12. **What data exists at that moment:** `Request` object with headers, URL, path params, query params, and raw body bytes.
13. **Where that data goes next:** Sent into `call_next(request)` for route execution, then copied into `RuntimeData`.
14. **Which function calls which function:** Uvicorn → `APISentinelMiddleware.dispatch()` → `call_next()` → `example_app.login()` → `APISentinelMiddleware._buffer_response_body()` → `APISentinelMiddleware._process_captured_data()` → `APIDiffEngine.analyze_payload_async()` → `APIDiffEngine.compare_response()` → `APIDiffEngine._validate_schema()` → `SentinelReporter.report_drift()` → `APISentinelMiddleware._post_to_dashboard()`.
15. **What is returned:** The original HTTP Response is returned immediately to the client with identical status code and headers.
16. **How control moves back:** Execution exits `dispatch()` by returning `reconstructed`, while the asyncio event loop switches to the background task `_process_captured_data()`.
17. **How the response is captured:** Via `_buffer_response_body(response)`, which iterates through `response.body_iterator` (or reads `response.body`) into a single byte buffer.

### Internal Representation & Spec Matching
18. **How the request/response data is represented internally:** Stored as an instance of `RuntimeData` dataclass (`api_sentinel/runtime_data.py`).
19. **How the API documentation/OpenAPI specification is loaded:** Loaded at startup via `OpenAPISpecParser.from_file(openapi_path)`, which calls `yaml.safe_load()` in `diff_engine.py`.
20. **How the actual endpoint is matched against the documented endpoint:** Handled by `match_route(live_path, openapi_paths)` in `diff_engine.py`, converting `{param}` into regex `[^/]+` and sorting by path template length.
21. **How request data is compared with the specification:** `APIDiffEngine.compare_request()` validates documented query parameters (`required`, unexpected) and compares JSON request body against `requestBody.content['application/json'].schema`.
22. **How response data is compared with the specification:** `APIDiffEngine.compare_response()` validates status code matches `responses[status_code]` (or wildcards) and runs `_validate_schema()` on `response_body`.
23. **How a mismatch is detected:** Recursive JSON schema validation checking:
    - Expected data type vs. actual data type (`_get_json_type` / `_types_match`).
    - Presence of keys in `schema["required"]`.
    - Extra keys not declared in `schema["properties"]`.
    - Array item schema compliance.
24. **How an issue/difference is represented:** As a `DriftIssue` dataclass (`issue_type`, `severity`, `path`, `method`, `location`, `message`, `expected`, `actual`) in `api_sentinel/diff_engine.py` or `Difference` dataclass in `api_sentinel/validation_report.py`.
25. **How severity/status is determined:**
    - Missing required fields, undocumented status codes, undocumented endpoints, type mismatches = `ERROR` (`FAILED`).
    - Undocumented extra fields, undocumented query params = `WARNING` (`WARNING`).
    - No differences = `INFO` (`PASSED`).
26. **How the final report is constructed:** Formatted as a Rich Console Panel/Table by `SentinelReporter.report_drift()`, and converted to JSON for the dashboard's `EndpointValidationResult` / `AggregateReport`.
27. **Where the report is sent/stored:** 
    - Printed to stdout (terminal/uvicorn console).
    - Sent via HTTP POST to `http://127.0.0.1:8001/api/report/append` into the in-memory array `_active_report.results`.
28. **What happens after the report is generated:** The background task completes and garbage collection frees the task; the client has already received its response.

### Data Storage, Privacy, & Persistence
29. **Whether the original API request is saved:** NOT SAVED permanently to disk or database. Kept temporarily in RAM during validation.
30. **If it is saved, WHERE, HOW, FOR HOW LONG, and IN WHAT FORM:** The dashboard maintains an in-memory list `_active_report.results` holding up to the **last 100 execution reports** in RAM. When the process restarts, all in-memory records are cleared.
31. **If it is NOT saved, explicitly explain that:** *NO PERSISTENT DATABASE (POSTGRESQL, MYSQL, SQLITE, MONGODB) IS IMPLEMENTED IN THIS CODEBASE.*
32. **Whether request bodies are stored:** Request bodies are only held in memory in `RuntimeData.request_body` for validation. They are NOT forwarded to the dashboard payload or written to disk.
33. **Whether headers are stored:** Headers are sanitized via `sanitize_headers()` in RAM and discarded after comparison.
34. **Whether authentication tokens/secrets are stored or sanitized:** `sanitize_headers()` in `api_sentinel/capture.py` automatically replaces `Authorization`, `Cookie`, `x-api-key`, `token`, `session`, etc. with `Bearer [REDACTED]` or `[REDACTED]`.
35. **Whether responses are stored:** Only the JSON response body structure is stored in the dashboard's in-memory `actual_schema` field for the last 100 requests.
36. **Whether logs contain request/response information:** `logger.info` logs only metadata (`method`, `endpoint`, `status_code`, `authentication_type`). It does not log raw payload bodies.
37. **Whether data is persisted in a database/file/dashboard:** Persisted in dashboard RAM only (100 items). Persistent files are created ONLY when a user explicitly calls `/api/export/json` or `/api/export/html`.

### Error Handling & Edge Cases
38. **What happens if validation fails:** Drift issues are logged to the console and sent to the dashboard as `FAILED` / `ERROR`, but the API client receives their HTTP response normally (no HTTP 500 generated).
39. **What happens if the endpoint is not found in the specification:** `match_route()` returns `None`, generating a `DriftIssue` of type `UNDOCUMENTED_ENDPOINT` with severity `ERROR`.
40. **What happens if the request body cannot be parsed:** `safe_parse_body()` catches the JSON decode error and falls back to a raw string or `None`.
41. **What happens if the response body cannot be parsed:** `safe_parse_body()` returns raw string or `None`, preventing schema validation from throwing unhandled exceptions.
42. **What happens if the dashboard/reporting system is unavailable:** `_post_to_dashboard()` wraps `urllib.request.urlopen` in `try...except Exception: pass`, silently ignoring connection errors so the application continues running smoothly.
43. **What happens if an exception occurs:** All major validation steps in `dispatch()` and `_process_captured_data()` are wrapped in `try...except Exception:` blocks with fallback handlers. Monitoring failures can never crash the host application.

---

## 6. Verification & Live Demonstration

1. **Start Dashboard (Port 8001):**
   ```cmd
   start_dashboard.cmd
   ```
2. **Start Demo API (Port 8000):**
   ```cmd
   start_api.cmd
   ```
3. **Execute the Traced Request:**
   ```bash
   curl -X POST http://127.0.0.1:8000/api/v1/auth/login ^
        -H "Content-Type: application/json" ^
        -d "{\"username\": \"alice\", \"password\": \"secret\"}"
   ```
4. **Observe the Results:**
   - **Terminal 1:** Rich Table alert shows `MISSING_REQUIRED_FIELD` (`ERROR`).
   - **Browser (`http://127.0.0.1:8001`):** Dashboard displays the failed request with detailed expected vs. actual schema comparison.
