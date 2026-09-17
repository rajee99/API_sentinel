# API Sentinel — Step-by-Step Code Explanation

This document explains the **Runtime Data Collection Layer** we implemented for the API Sentinel project. It is designed to be very simple, using analogies to help explain how the code works under the hood, where function parameters come from, and why they are passed.

---

## The Big Picture (Analogy)

Imagine you run a **secured post office**:
1. **The Client** is a customer sending a letter (an HTTP Request).
2. **The Upstream App** is the clerk in the back room who processes the mail (the backend server).
3. **The Middleware** is a security guard standing at the front door. 

Every time a customer comes in:
- The security guard stops the customer, copies down their details (method, query params, headers), and makes a photocopy of the package contents (the request body).
- To keep the line moving fast, the guard immediately hands the package to the back-room clerk, gets the receipt (the response), and hands it back to the customer.
- *After* the customer leaves, the guard sits down at their desk in the background (using an asynchronous background task) to write a detailed report of what was captured (the `RuntimeData` object) without making the customer wait.

---

## 1. `runtime_data.py` (The Logbook Form)
*Location: `api_sentinel/runtime_data.py`*

This file defines a **blueprint** (a class called `RuntimeData`) for the storage box we use to hold the captured data. Think of it like a printed form with empty blanks that the security guard fills out.

### The Code Explained Line-by-Line:

```python
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
```
- **`from dataclasses import asdict, dataclass`**: Python has a built-in tool called `dataclass` which automatically writes standard boilerplate code (like setup initializers) for classes that mainly store data. We import `asdict` to easily convert our form into a simple Python dictionary (key-value list) later.
- **`from datetime import datetime, timezone`**: We import this to get the exact current time in UTC (coordinated universal time) to stamp our reports.
- **`from typing import Any, Dict, Optional`**: Python typing hints. `Any` means a value can be anything (number, text, etc.), `Dict` represents a dictionary (lookup table), and `Optional` means a field can either contain data or be empty (`None`).

```python
@dataclass
class RuntimeData:
```
- **`@dataclass`**: This decorator tells Python: *"Treat this class as a simple data container. Automatically generate the code that lets me write `RuntimeData(method='GET', ...)`."*
- **`class RuntimeData:`**: Defines our container name.

```python
    method: str                           # HTTP method, e.g., "GET", "POST"
    endpoint: str                         # Endpoint URL path, e.g., "/api/v1/users/42"
    path_parameters: Dict[str, str]       # Extracted path parameters
    query_parameters: Dict[str, Any]      # Captured query parameters
    request_headers: Dict[str, str]       # Captured request headers
    request_body: Optional[Any]           # Captured request body (parsed JSON or raw text)
    authentication_type: str              # Detected auth: "Bearer Token", "API Key", or "Anonymous"
    status_code: int                      # HTTP Status Code returned by the server
    response_headers: Dict[str, str]      # Captured response headers
    response_body: Optional[Any]          # Captured response body (parsed JSON or raw text)
    timestamp: str = None                 # ISO 8601 formatted timestamp of the request
```
These are the **fields** (the blanks on our form) that we want to store:
- **`method`**: The type of request (e.g., `GET` to fetch data, `POST` to create data).
- **`endpoint`**: The URL folder path requested (e.g. `/api/v1/users/42`).
- **`path_parameters`**: Part of the URL containing dynamic values (like `id = 42` in `/users/{id}`).
- **`query_parameters`**: Extra filters added to the end of a URL (e.g. `?limit=10`).
- **`request_headers` / `response_headers`**: Meta-information about the request/response (like content-type or authorization details).
- **`request_body` / `response_body`**: The actual content payload sent or received.
- **`authentication_type`**: The category of security pass detected.
- **`status_code`**: The server's answer code (e.g. `200 OK`, `201 Created`, `401 Unauthorized`).
- **`timestamp: str = None`**: Set to `None` by default; we will automatically fill it in if it is not provided.

```python
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()
```
- **`def __post_init__(self):`**: This is a special function that runs automatically *after* the `RuntimeData` object is created.
- **`if self.timestamp is None:`**: Checks if a timestamp wasn't provided.
- **`self.timestamp = datetime.now(timezone.utc).isoformat()`**: Gets the current date/time in UTC format (e.g. `2026-08-08T00:00:00Z`) and saves it.

```python
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
```
- **`def to_dict(self):`**: A custom method to turn the object into a standard Python dictionary.
- **`return asdict(self)`**: Translates all dataclass attributes into key-value pairs (helpful for saving or transmitting data).

---

## 2. `capture.py` (The Inspector Utilities)
*Location: `api_sentinel/capture.py`*

This file contains utility functions that do the heavy lifting of extracting information, classifying authentication, and cleaning sensitive data.

### `detect_auth_type`
This function determines what type of security pass the request is using.

```python
def detect_auth_type(headers: Dict[str, str], query_params: Dict[str, Any]) -> str:
```
- **Parameters**: 
  - `headers`: A dictionary of request headers. *Where does it come from?* The middleware extracts it from the incoming client request and passes it here.
  - `query_params`: A dictionary of request query parameters. *Where does it come from?* Also extracted from the request by the middleware.
- **Return value**: A string ("Bearer Token", "API Key", or "Anonymous") that goes back to the caller (the middleware) so it can write it in the `RuntimeData` object.

```python
    headers_lower = {k.lower(): v for k, v in headers.items()}
```
- **Line explanation**: Converts all header names to lowercase (e.g. `Authorization` becomes `authorization`). *Why?* HTTP headers are case-insensitive, so we normalize them to avoid missing them due to spelling case mismatches.

```python
    auth_header = headers_lower.get("authorization", "").strip()
    if auth_header:
        if auth_header.lower().startswith("bearer "):
            return "Bearer Token"
        if auth_header.lower().startswith("apikey "):
            return "API Key"
```
- **Line explanation**: Gets the value of the `authorization` header. If it starts with the word `Bearer ` (case-insensitive), it is a Bearer Token (JWT). If it starts with `ApiKey `, it is classified as an API Key.

```python
    has_api_key_header = any(
        k in headers_lower for k in ("x-api-key", "api-key", "apikey")
    )
    has_api_key_query = any(
        k in query_params for k in ("api_key", "apikey", "api-key")
    )
```
- **Line explanation**: Checks if common API Key parameters exist in the headers (like `x-api-key`) or query parameters (like `?api_key=...`).

```python
    if has_api_key_header or has_api_key_query:
        return "API Key"
        
    return "Anonymous"
```
- **Line explanation**: If either check is true, return `"API Key"`. Otherwise, if no authentication headers/queries are found, return `"Anonymous"`.

---

### `sanitize_headers`
We must **never** write passwords, session keys, or API tokens directly to disk. This function replaces sensitive credentials with `[REDACTED]`.

```python
def sanitize_headers(headers: Dict[str, str]) -> Dict[str, str]:
```
- **Parameters**: `headers` (the raw headers dictionary sent by the client or server).
- **Why**: Security compliance.

```python
    sanitized = {}
    sensitive_keys = {
        "authorization", "cookie", "set-cookie", "x-api-key", "api-key", 
        "apikey", "proxy-authorization", "token", "session", "session-id"
    }
```
- **Line explanation**: We initialize an empty dict `sanitized` and define a list (`sensitive_keys`) of headers containing credentials.

```python
    for k, v in headers.items():
        k_lower = k.lower()
        if k_lower in sensitive_keys:
            if k_lower == "authorization":
                parts = v.strip().split(" ", 1)
                if len(parts) == 2:
                    sanitized[k] = f"{parts[0]} [REDACTED]"
                else:
                    sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = "[REDACTED]"
        else:
            sanitized[k] = v
```
- **Line explanation**: We look at each header name (`k`) and value (`v`). 
  - If the name is in our sensitive list, we replace it.
  - For `Authorization`, we keep the prefix (e.g. `Bearer`) but hide the token itself: `Bearer [REDACTED]`.
  - For other sensitive keys, we replace the entire value with `[REDACTED]`.
  - Normal headers are copied as-is.

```python
    return sanitized
```
- **Line explanation**: Returns the clean dictionary to the middleware.

---

### `safe_parse_body`
Translates incoming raw byte packages into readable text or structured JSON.

```python
def safe_parse_body(body_bytes: bytes, content_type: str) -> Optional[Any]:
```
- **Parameters**:
  - `body_bytes`: Raw binary data (zeros and ones) received from the socket.
  - `content_type`: The format indicator (e.g. `application/json` or `text/plain`).
- **Return**: A parsed JSON object (dictionary/list), a decoded string, or `None` if it fails.

```python
    if not body_bytes:
        return None
        
    try:
        decoded = body_bytes.decode("utf-8")
        if "json" in content_type:
            return json.loads(decoded)
        return decoded
    except Exception:
        return None
```
- **Line explanation**:
  - If the body is empty, return `None`.
  - Try to decode the binary bytes into a regular UTF-8 text string.
  - If the `content_type` contains `"json"`, we run `json.loads(decoded)` to parse the text string into a Python dictionary.
  - If anything fails (like invalid JSON formatting), we return `None` rather than crashing the application.

---

## 3. `middleware.py` (The Interceptor)
*Location: `api_sentinel/middleware.py`*

The middleware is the glue. It intercepts the request before it reaches the backend, lets the backend generate the response, captures everything, and returns the response immediately to the client before kicking off background processing.

### The `dispatch` Method Explained:

```python
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
```
- **Parameters**:
  - `request`: The incoming HTTP request object from the client.
  - `call_next`: A function representing the next step on the conveyor belt (the backend application handler). We call this to run your backend code and get the response.
- **Return**: The HTTP Response object sent back to the client.

```python
        if not self.enabled or self._is_excluded(request.url.path):
            return await call_next(request)
```
- **Line explanation**: Fast pass-through. If the middleware is turned off or the URL path is excluded (like `/docs` or `/health`), we bypass capture and proceed directly to the backend.

```python
        try:
            request_body_bytes: bytes = await request.body()
        except Exception:
            logger.debug("APISentinelMiddleware: failed to buffer request body", exc_info=True)
            return await call_next(request)
```
- **Line explanation**: We read and copy the request body bytes into memory. If we cannot read it, we yield and proceed without capturing.

```python
        _cached_body = request_body_bytes

        async def _restore_receive() -> dict:
            return {"type": "http.request", "body": _cached_body, "more_body": False}

        request._receive = _restore_receive
```
- **Line explanation**: *The Restore Trick.* Reading the request body drains the incoming network stream. If we didn't do this, when the backend tries to read the body, it would find it empty and hang. By replacing `request._receive` with our custom function, we make sure the backend gets a fresh copy of the body bytes when it asks for it.

```python
        method = request.method
        endpoint = request.url.path
        query_parameters = dict(request.query_params)
        request_headers_raw = dict(request.headers)
        request_headers = sanitize_headers(request_headers_raw)
        
        authentication_type = detect_auth_type(request_headers_raw, query_parameters)
        request_content_type = get_content_type(request_headers_raw)
        request_body = safe_parse_body(_cached_body, request_content_type)
```
- **Line explanation**: We extract request metadata and body. We pass `request_headers_raw` to `sanitize_headers` and `detect_auth_type` so they can do their analysis without storing raw keys.

```python
        response: Response = await call_next(request)
```
- **Line explanation**: We send the request downstream to your actual backend handler (e.g., your FastAPI endpoints) and wait for the response to be generated.

```python
        try:
            response_body_bytes = await self._buffer_response_body(response)
        except Exception:
            logger.debug("APISentinelMiddleware: failed to buffer response body", exc_info=True)
            return response
```
- **Line explanation**: We copy the response body bytes. If it fails, we return the original response immediately.

```python
        path_parameters = dict(request.path_params)
        status_code = response.status_code
        response_headers_raw = dict(response.headers)
        response_headers = sanitize_headers(response_headers_raw)
        response_content_type = get_content_type(response_headers_raw)
        response_body = safe_parse_body(response_body_bytes, response_content_type)
```
- **Line explanation**: We capture response details.
  - **`dict(request.path_params)`**: *Why do we extract path params here instead of earlier?* Because Starlette only runs its router *during* `call_next`. Before `call_next`, the URL has not been matched to a route, so `request.path_params` is empty. Extracting it here ensures we capture path parameters (like `{id}`) correctly!

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
- **Line explanation**: We reconstruct the Response object. We pop `content-length` so Starlette recalculates it automatically, ensuring it matches our buffered bytes.

```python
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
```
- **Line explanation**: We construct our blueprint logbook (`RuntimeData`) using all the data we collected in the steps above.

```python
        asyncio.create_task(
            self._process_captured_data(runtime_data),
            name=f"sentinel:capture:{method}:{endpoint}",
        )
```
- **Line explanation**: *The Zero-Latency Secret.* `asyncio.create_task` registers the background function `_process_captured_data` to run on the event loop concurrently. It **returns immediately** without waiting for the background function to execute.

```python
        return reconstructed
```
- **Line explanation**: Hands the response back to the client immediately. The client gets their API response with zero perceived delay!

---

### The Background Worker Method:

```python
    async def _process_captured_data(self, data: RuntimeData) -> None:
        try:
            logger.info(
                "Captured RuntimeData: method=%s, endpoint=%s, status_code=%d, auth=%s",
                data.method,
                data.endpoint,
                data.status_code,
                data.authentication_type,
            )

            if self._diff_engine:
                op_match = self._parser.get_operation(data.endpoint, data.method)
                matched_path = op_match[0] if op_match else None
                
                await self._diff_engine.analyze_payload_async(
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
        except Exception:
            logger.error("Error in Sentinel capture background task", exc_info=True)
```
- **Parameters**: `data` (our constructed `RuntimeData` object). *Where does it come from?* Passed by the middleware when spawning the background task.
- **Line explanation**:
  - We log the collection summary (method, URL, status code, and authentication type).
  - If a drift validation engine (`self._diff_engine`) is active, we trigger the schema validation asynchronously using the captured data fields.
  - Wrap everything in `try/except` so that if anything fails, it logs the error but never crashes the web server.
