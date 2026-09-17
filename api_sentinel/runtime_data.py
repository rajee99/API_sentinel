"""
API Sentinel - Runtime Data Model
Defines the structure representing captured runtime HTTP request and response information.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class RuntimeData:
    """
    Model representing all captured information from a runtime HTTP request/response cycle.
    """
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

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert the runtime data instance into a dictionary."""
        return asdict(self)
