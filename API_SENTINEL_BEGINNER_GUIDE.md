# 🛡️ API Sentinel: Complete Beginner-Friendly Request Lifecycle Guide

---

## 📖 The Big Picture: The Restaurant & The Sentinel Guard

Imagine our application is a restaurant:
1. 📜 **The Menu Rulebook (`openapi.yaml`):** Defines the exact contract — what customers can order and what the kitchen must return.
2. 👨‍🍳 **The Chef (`example_app.py` / FastAPI):** The actual backend route handlers that compute and return the response.
3. 🛡️ **The Sentinel Guard (`APISentinelMiddleware`):** A smart middleware guard standing at the kitchen door. The guard:
   * Captures the incoming request and outgoing response.
   * Hands the response to the customer **immediately** with **0 delay**.
   * In the background, checks whether the response obeyed every rule in `openapi.yaml`.
   * Alerts developers on the terminal and web dashboard if any contract drift is detected.

---

## 🎯 The Concrete Request We Are Tracing

* **Endpoint:** `POST /api/v1/auth/login`
* **Client Payload:**
  ```json
  {
    "username": "alice",
    "password": "secret"
  }
  ```
* **Expected Response according to `openapi.yaml` (`LoginResponse`):**
  - Status `200 OK`
  - Required fields: `["access_token", "token_type"]`
* **Actual Response returned by `example_app.py`:**
  - Status `200 OK`
  - Body: `{"access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.demo.signature"}`
  - **The Drift Bug:** The developer forgot to include `"token_type": "bearer"`.

---

## 🔄 The 13-Step End-to-End Execution Lifecycle

### Step 1: Receiving the Client Request
📁 **File:** `api_sentinel/middleware.py` (Line 82)
```python
request_body_bytes: bytes = await request.body()
```
* **What it does:** Reads the raw incoming bytes of the client request (the JSON payload).
* **The "Juice Box" Problem:** In Python ASGI web servers, reading the stream empties it. Once read, the stream cannot be read a second time by default.

---

### Step 2: Restoring the Request Stream for Downstream Handlers
📁 **File:** `api_sentinel/middleware.py` (Lines 88–93)
```python
_cached_body = request_body_bytes

async def _restore_receive() -> dict:
    return {"type": "http.request", "body": _cached_body, "more_body": False}

request._receive = _restore_receive
```
* **What it does:** Caches the bytes and replaces the empty stream straw with a refill function (`_restore_receive`) so that FastAPI can read the request body normally without errors or hanging.

---

### Step 3: Forwarding the Request to the Route Handler
📁 **File:** `api_sentinel/middleware.py` (Line 110)
```python
response: Response = await call_next(request)
```
* **What it does:** `call_next` is FastAPI's internal router. It reads the URL (`POST /api/v1/auth/login`), looks up the matching `@app.post` route in `example_app.py`, executes `login(credentials)`, and brings back the `JSONResponse`.

---

### Step 4: Buffering the Response Body and Metadata
📁 **File:** `api_sentinel/middleware.py` (Lines 113–118)
```python
try:
    response_body_bytes = await self._buffer_response_body(response)
except Exception:
    logger.debug("APISentinelMiddleware: failed to buffer response body", exc_info=True)
    return response
```
* **What it does:** Collects any streamed chunks from `response.body_iterator` and glues them into a single byte string (`response_body_bytes`).

---

### Step 5: Extracting and Sanitizing Response Information
📁 **File:** `api_sentinel/middleware.py` (Lines 120–125)
```python
path_parameters = dict(request.path_params)
status_code = response.status_code
response_headers_raw = dict(response.headers)
response_headers = sanitize_headers(response_headers_raw)
response_content_type = get_content_type(response_headers_raw)
response_body = safe_parse_body(response_body_bytes, response_content_type)
```
* **`path_parameters`** → Extracts URL variables (e.g., `{"id": "42"}`).
* **`status_code`** → Gets the HTTP status code (e.g., `200`).
* **`response_headers_raw`** → Gets raw headers returned by the server.
* **`response_headers`** → Uses `sanitize_headers` (black marker 🖍️) to redact secrets (`Authorization: Bearer [REDACTED]`, `Cookie: [REDACTED]`).
* **`response_content_type`** → Extracts media type (`"application/json"`).
* **`response_body`** → Translates raw bytes into a Python dictionary (`{"access_token": "..."}`).

---

### Step 6: Making a Fresh Response Package for the Client
📁 **File:** `api_sentinel/middleware.py` (Lines 128–135)
```python
headers = dict(response.headers)
headers.pop("content-length", None)

reconstructed = Response(
    content=response_body_bytes,
    status_code=status_code,
    headers=headers,
    media_type=response.media_type,
)
```
* **What it does:** Because we read the original response stream, Sentinel creates a clean `Response` object with the original bytes, headers, and status code to send to the client.

---

### Step 7: Packing Everything into the `RuntimeData` Box
📁 **File:** `api_sentinel/middleware.py` (Lines 138–149)
```python
runtime_data = RuntimeData(
    method=method,                           # "POST"
    endpoint=endpoint,                       # "/api/v1/auth/login"
    path_parameters=path_parameters,         # {}
    query_parameters=query_parameters,       # {}
    request_headers=request_headers,         # Sanitized headers
    request_body=request_body,               # {"username": "alice", "password": "secret"}
    authentication_type=authentication_type, # "Anonymous"
    status_code=status_code,                 # 200
    response_headers=response_headers,       # Sanitized headers
    response_body=response_body,             # {"access_token": "eyJhbGci..."}
)
```
* **What it does:** Packs all the cleaned request and response details into an organized Python dataclass instance.

---

### Step 8: Immediate Client Return & Spawning Background Task
📁 **File:** `api_sentinel/middleware.py` (Lines 152–157)
```python
# A. Start checking for drift quietly in the background
asyncio.create_task(
    self._process_captured_data(runtime_data),
    name=f"sentinel:capture:{method}:{endpoint}",
)

# B. Return the response to the client immediately!
return reconstructed
```
* **What it does:**
  1. The client receives their HTTP `200 OK` response with **zero added latency**.
  2. In the background (`asyncio.create_task`), Python starts `_process_captured_data` to inspect the `runtime_data` box.

---

### Step 9: Looking Up the Rulebook Operation via `self._parser`
📁 **File:** `api_sentinel/middleware.py` (Line 175) & `api_sentinel/diff_engine.py` (Line 225)
```python
op_match = self._parser.get_operation(data.endpoint, data.method)
matched_path = op_match[0] if op_match else None
```
* **What it does:**
  * `self._parser` is the `OpenAPISpecParser` holding `openapi.yaml`.
  * `get_operation` calls `match_route`, which matches `"/api/v1/auth/login"` against the YAML paths.
  * It returns `("/api/v1/auth/login", operation_dict)` containing the expected request body schema and response status codes.

---

### Step 10: Calling the Master Async Diff Engine
📁 **File:** `api_sentinel/middleware.py` (Lines 178–188)
```python
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
```
* **What it does:** Invokes the `analyze_payload_async` method on the `_diff_engine` object (`APIDiffEngine`).

---

### Step 11: Inside `analyze_payload_async` (Comparison & Terminal Alert)
📁 **File:** `api_sentinel/diff_engine.py` (Lines 475–528)
```python
# Step A: Check request side
request_issues = self.compare_request(path=raw_path, method=method, query_params=query_params, body=request_body)

# Step B: Check response side
response_issues = self.compare_response(path=raw_path, method=method, status_code=status_code, body=response_body)

# Step C: Combine all issues
all_issues = request_issues + response_issues

# Step D: Alert developer on terminal
if all_issues:
    reporter.report_drift(all_issues)
elif print_clean:
    reporter.report_clean(method, raw_path, status_code)

# Step E: Return issues
return all_issues
```
* **Step A (`compare_request`):** Validates query params and request body schema. Returns `[]` (no bugs).
* **Step B (`compare_response`):** Checks status `200` schema. Spots that `"token_type"` is missing! Returns `[DriftIssue(MISSING_REQUIRED_FIELD, ERROR)]`.
* **Step C (`all_issues`):** Combines into a list of 1 issue.
* **Step D (`reporter.report_drift`):** Prints a red alert table to the console via Rich.
* **Step E (`return all_issues`):** Returns the issue list to `_process_captured_data`.

---

### Step 12: Sending the Report to the Web Dashboard
📁 **File:** `api_sentinel/middleware.py` (Lines 195–267) & `dashboard/app.py` (Lines 164–181)
```python
async def _post_to_dashboard(self, data: RuntimeData, matched_path: Optional[str], issues: list) -> None:
    has_error = any(getattr(i, 'severity', None) == DriftSeverity.ERROR for i in issues)
    status = "FAILED" if has_error else "PASSED"

    payload = {
        "endpoint": matched_path or data.endpoint,
        "method": data.method.upper(),
        "status_code": data.status_code,
        "validation_status": status,
        "severity": "ERROR",
        "expected_schema": expected_schema,
        "actual_schema": data.response_body,
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

    # Sends async HTTP POST to Dashboard server on port 8001
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{self.dashboard_url}/api/report/append",
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    await asyncio.to_thread(_send)
```
* **What it does:** Converts the detected issues into JSON and posts to `http://127.0.0.1:8001/api/report/append`.
* The dashboard prepends this result into its in-memory list (`report.results.insert(0, result)`). Developers can view the failure live in their web browser!

---

### Step 13: Deep Dive into How the Comparison Works Under the Hood

#### 13.1 Endpoint & Query Param Validation (`compare_request`)
* **Endpoint check:** Verifies if the requested path exists in `openapi.yaml`. If not, flags `UNDOCUMENTED_ENDPOINT`.
* **Query param check:** Loops over documented parameters to ensure all `required: true` params were sent, and flags any unexpected query parameters as `UNDOCUMENTED_QUERY_PARAM`.

#### 13.2 Resolving `$ref` Hyperlinks
* In `openapi.yaml`, schemas are defined under `components: schemas:` and referenced as `$ref: '#/components/schemas/LoginResponse'`.
* `self.parser.resolve_ref(schema)` follows the `$ref` pointer and replaces it with the full dictionary:
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

#### 13.3 Regex Route Matching (`match_route`)
* Converts path templates like `/api/v1/users/{id}` into regex pattern `^/api/v1/users/[^/]+$`.
* Matches dynamic paths (like `/api/v1/users/42` or `/api/v1/users/alice`) directly to the template.

#### 13.4 Recursive Schema Validation (`_validate_schema`)
When comparing the response body `{"access_token": "eyJhb..."}` against `LoginResponse`:
1. **Type Check:** Checks if `type` is `"object"` (dict). Both match ✅.
2. **Required Fields Check:**
   ```python
   for req in ["access_token", "token_type"]:
       if req not in data:
           issues.append(DriftIssue(issue_type=DriftType.MISSING_REQUIRED_FIELD, severity=DriftSeverity.ERROR, ...))
   ```
   * `"access_token"` is present ✅.
   * `"token_type"` is **missing** ❌ ➔ Flagged as `MISSING_REQUIRED_FIELD` (`ERROR`).
3. **Extra Fields Check:** Checks if any unapproved fields were returned.

---

## 📊 Summary Cheat Sheet: Files, Classes & Functions

| Step | Component | File | Class / Function | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **1–2** | Capture & Restore | `api_sentinel/capture.py` | `_restore_receive`, `sanitize_headers` | Buffer request stream & redact secrets |
| **3** | Downstream Handler | `example_app.py` | `login(credentials)` | Execute route & generate response |
| **4–6** | Response Capture | `api_sentinel/middleware.py` | `_buffer_response_body`, `Response(...)` | Buffer response bytes & rebuild for client |
| **7–8** | Data Packaging | `api_sentinel/runtime_data.py` | `RuntimeData`, `asyncio.create_task` | Package data & return to user with 0 delay |
| **9** | Spec Parsing | `api_sentinel/diff_engine.py` | `OpenAPISpecParser.get_operation` | Look up path template & operation in YAML |
| **10–11**| Diff Comparison | `api_sentinel/diff_engine.py` | `APIDiffEngine.compare_response` | Compare response body against schema rules |
| **11D** | Terminal Alert | `api_sentinel/reporter.py` | `SentinelReporter.report_drift` | Print Rich warning panel and table |
| **12** | Dashboard Sync | `dashboard/app.py` | `append_report_result` | Post JSON diff to live web dashboard |
| **13** | Schema Resolution | `api_sentinel/diff_engine.py` | `_validate_schema`, `resolve_ref` | Check types, required fields, and $refs |
