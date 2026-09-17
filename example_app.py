"""
example_app.py — API Sentinel Demo Application
===============================================
A minimal, self-contained FastAPI application that demonstrates
``APISentinelMiddleware`` in action.

Endpoints
---------
GET  /api/v1/users/{id}   — Returns a user object; intentionally includes an
                            extra undocumented field to trigger EXTRA_FIELD drift.
POST /api/v1/auth/login   — Validates credentials; intentionally omits the
                            documented ``token_type`` field to trigger
                            MISSING_REQUIRED_FIELD drift.

Running locally
---------------
1. Install dependencies:
       pip install -e .

2. Start the dev server:
       uvicorn example_app:app --reload

3. Make test requests:
       curl http://localhost:8000/api/v1/users/42
       curl -X POST http://localhost:8000/api/v1/auth/login \\
            -H "Content-Type: application/json" \\
            -d '{"username": "alice", "password": "secret"}'

Observe the rich-formatted drift alerts printed to the uvicorn console.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api_sentinel.middleware import APISentinelMiddleware

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="API Sentinel — Demo Application",
    description="Demonstrates real-time OpenAPI contract drift detection.",
    version="0.1.0",
)

# Register the middleware.
# ``openapi_path`` points at the spec file that defines the *expected* contract.
# ``print_clean=True`` logs a confirmation line for every passing request so
# you can clearly see which calls are clean vs. drifted.
app.add_middleware(
    APISentinelMiddleware,
    openapi_path="openapi.yaml",   # relative to the working directory
    enabled=True,
    print_clean=True,
)


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    """Credentials submitted to the login endpoint."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """
    Access token returned on successful login.

    The OpenAPI spec documents both ``access_token`` **and** ``token_type``
    as required.  The endpoint implementation below deliberately omits
    ``token_type`` so that Sentinel flags a MISSING_REQUIRED_FIELD issue.
    """
    access_token: str
    # token_type: str   ← intentionally omitted to demonstrate drift detection


class UserResponse(BaseModel):
    """
    Standard user object returned by the users endpoint.

    The OpenAPI spec does *not* document ``debug_internal_id``; the endpoint
    below returns it anyway so Sentinel flags an EXTRA_FIELD warning.
    """
    id: int
    name: str
    email: str
    role: str
    # debug_internal_id ← extra field injected in the handler below


# ---------------------------------------------------------------------------
# Endpoint: GET /api/v1/users/{id}
# ---------------------------------------------------------------------------

@app.get(
    "/api/v1/users/{id}",
    summary="Retrieve a user by ID",
    response_model=UserResponse,
    tags=["users"],
)
async def get_user(
    id: int = Path(..., description="Numeric user identifier", ge=1),
) -> JSONResponse:
    """
    Returns a synthetic user object for the given ``id``.

    **Intentional drift**: the response includes ``debug_internal_id``, a
    field that is not documented in ``openapi.yaml``.  Sentinel will surface
    this as an ``EXTRA_FIELD`` WARNING.
    """
    if id > 9999:
        # Simulate a 404 for non-existent users.
        raise HTTPException(status_code=404, detail=f"User {id} not found.")

    payload = {
        "id": id,
        "name": "Alice Wonderland",
        "email": "alice@example.com",
        "role": "admin",
        # ↓ Not documented in openapi.yaml — Sentinel will flag this.
        "debug_internal_id": f"usr_internal_{id:08d}",
    }
    return JSONResponse(content=payload)


# ---------------------------------------------------------------------------
# Endpoint: POST /api/v1/auth/login
# ---------------------------------------------------------------------------

@app.post(
    "/api/v1/auth/login",
    summary="Authenticate a user and issue a JWT",
    tags=["auth"],
    status_code=200,
)
async def login(credentials: LoginRequest) -> JSONResponse:
    """
    Accepts ``username`` + ``password`` and returns a synthetic JWT.

    **Intentional drift**: the response omits ``token_type`` which the
    OpenAPI spec marks as required.  Sentinel will surface this as a
    ``MISSING_REQUIRED_FIELD`` ERROR.
    """
    # Hard-coded credential check — for demo purposes only.
    if credentials.password != "secret":
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    payload = {
        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.demo.signature",
        # ↓ ``token_type`` is required by the spec but deliberately omitted.
        # "token_type": "bearer",
    }
    return JSONResponse(content=payload)


# ---------------------------------------------------------------------------
# Endpoint: GET /api/v1/users (Clean list - PASSED)
# ---------------------------------------------------------------------------

@app.get(
    "/api/v1/users",
    summary="List all users",
    tags=["users"],
)
async def list_users() -> JSONResponse:
    """Returns clean list of users matching OpenAPI spec."""
    users = [
        {"id": 1, "name": "Alice Wonderland", "email": "alice@example.com", "role": "admin"},
        {"id": 2, "name": "Bob Builder", "email": "bob@example.com", "role": "user"},
    ]
    return JSONResponse(content=users)


# ---------------------------------------------------------------------------
# Endpoint: GET /api/v1/products/{id} (Custom Drift Demo)
# ---------------------------------------------------------------------------

@app.get(
    "/api/v1/products/{id}",
    summary="Retrieve a product (Demo Drift)",
    tags=["products"],
)
async def get_product(
    id: int = Path(..., description="Numeric product ID"),
) -> JSONResponse:
    """
    **Intentional drift**: Returns undocumented endpoint + extra unapproved field.
    """
    payload = {
        "id": id,
        "name": "Super Sentinel Widget",
        "price": 49.99,
        "unapproved_extra_field": "This triggers EXTRA_FIELD drift",
    }
    return JSONResponse(content=payload)


# ---------------------------------------------------------------------------
# Dev-server entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "example_app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )
