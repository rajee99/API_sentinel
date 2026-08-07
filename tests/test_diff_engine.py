"""
Tests for api_sentinel.diff_engine — load_openapi_spec and match_route functions
"""

import os
import tempfile

import pytest
import yaml

from api_sentinel.diff_engine import (
    load_openapi_spec,
    match_route,
    OpenAPISpecParser,
    APIDiffEngine,
    DriftType,
    DriftSeverity,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Test API", "version": "1.0.0"},
    "paths": {
        "/api/v1/users": {
            "get": {
                "operationId": "listUsers",
                "parameters": [
                    {"name": "role", "in": "query", "required": False, "schema": {"type": "string"}}
                ],
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/User"}
                                }
                            }
                        }
                    }
                }
            },
            "post": {
                "operationId": "createUser",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/UserCreate"}
                        }
                    }
                },
                "responses": {
                    "201": {"description": "Created"}
                }
            }
        },
        "/api/v1/users/{id}": {
            "get": {
                "operationId": "getUserById",
                "parameters": [
                    {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}
                ],
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/User"}
                            }
                        }
                    },
                    "404": {"description": "Not found"}
                }
            }
        },
        "/api/v1/users/{user_id}/posts/{post_id}": {
            "get": {
                "operationId": "getUserPost",
                "responses": {"200": {"description": "OK"}}
            }
        },
        "/api/v1/auth/login": {
            "post": {
                "operationId": "login",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/LoginRequest"}
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/LoginResponse"}
                            }
                        }
                    }
                }
            }
        },
    },
    "components": {
        "schemas": {
            "User": {
                "type": "object",
                "required": ["id", "name", "email"],
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "role": {"type": "string"},
                }
            },
            "UserCreate": {
                "type": "object",
                "required": ["name", "email"],
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "role": {"type": "string"},
                }
            },
            "LoginRequest": {
                "type": "object",
                "required": ["username", "password"],
                "properties": {
                    "username": {"type": "string"},
                    "password": {"type": "string"},
                }
            },
            "LoginResponse": {
                "type": "object",
                "required": ["access_token", "token_type"],
                "properties": {
                    "access_token": {"type": "string"},
                    "token_type": {"type": "string"},
                }
            },
        }
    }
}


@pytest.fixture
def spec_yaml_file(tmp_path):
    """Create a temporary YAML spec file."""
    spec_file = tmp_path / "openapi.yaml"
    spec_file.write_text(yaml.dump(SAMPLE_SPEC, default_flow_style=False))
    return str(spec_file)


@pytest.fixture
def spec_json_file(tmp_path):
    """Create a temporary JSON spec file."""
    import json
    spec_file = tmp_path / "openapi.json"
    spec_file.write_text(json.dumps(SAMPLE_SPEC))
    return str(spec_file)


@pytest.fixture
def openapi_paths():
    """List of OpenAPI path templates."""
    return list(SAMPLE_SPEC["paths"].keys())


# ---------------------------------------------------------------------------
# Tests for load_openapi_spec
# ---------------------------------------------------------------------------


class TestLoadOpenAPISpec:
    """Tests for the load_openapi_spec function."""

    def test_load_yaml_spec(self, spec_yaml_file):
        """Load a YAML OpenAPI spec file."""
        spec = load_openapi_spec(spec_yaml_file)
        assert spec["openapi"] == "3.0.3"
        assert spec["info"]["title"] == "Test API"
        assert "/api/v1/users" in spec["paths"]
        assert "/api/v1/users/{id}" in spec["paths"]

    def test_load_json_spec(self, spec_json_file):
        """Load a JSON OpenAPI spec file."""
        spec = load_openapi_spec(spec_json_file)
        assert spec["openapi"] == "3.0.3"
        assert "/api/v1/auth/login" in spec["paths"]

    def test_load_nonexistent_file(self):
        """Raise FileNotFoundError for missing spec file."""
        with pytest.raises(FileNotFoundError):
            load_openapi_spec("/nonexistent/path/openapi.yaml")

    def test_load_returns_complete_paths(self, spec_yaml_file):
        """Verify all paths are loaded correctly."""
        spec = load_openapi_spec(spec_yaml_file)
        expected_paths = {
            "/api/v1/users",
            "/api/v1/users/{id}",
            "/api/v1/users/{user_id}/posts/{post_id}",
            "/api/v1/auth/login",
        }
        assert set(spec["paths"].keys()) == expected_paths

    def test_load_components_schemas(self, spec_yaml_file):
        """Verify component schemas are loaded."""
        spec = load_openapi_spec(spec_yaml_file)
        schemas = spec["components"]["schemas"]
        assert "User" in schemas
        assert "UserCreate" in schemas
        assert "LoginRequest" in schemas
        assert "LoginResponse" in schemas

    def test_load_actual_project_spec(self):
        """Load the actual project openapi.yaml if it exists."""
        project_spec = "/workspace/uploads/API_sentinel/openapi.yaml"
        if os.path.exists(project_spec):
            spec = load_openapi_spec(project_spec)
            assert spec["openapi"] == "3.0.3"
            assert "/api/v1/users" in spec["paths"]
            assert "/api/v1/users/{id}" in spec["paths"]
            assert "/api/v1/auth/login" in spec["paths"]


# ---------------------------------------------------------------------------
# Tests for match_route
# ---------------------------------------------------------------------------


class TestMatchRoute:
    """Tests for the match_route function."""

    def test_exact_static_match(self, openapi_paths):
        """Match a static path exactly."""
        result = match_route("/api/v1/users", openapi_paths)
        assert result == "/api/v1/users"

    def test_exact_static_match_login(self, openapi_paths):
        """Match the login path exactly."""
        result = match_route("/api/v1/auth/login", openapi_paths)
        assert result == "/api/v1/auth/login"

    def test_single_path_parameter_integer(self, openapi_paths):
        """Match a path with a numeric ID parameter."""
        result = match_route("/api/v1/users/42", openapi_paths)
        assert result == "/api/v1/users/{id}"

    def test_single_path_parameter_uuid(self, openapi_paths):
        """Match a path with a UUID parameter."""
        result = match_route("/api/v1/users/94a82f3c-1234-5678-9abc-def012345678", openapi_paths)
        assert result == "/api/v1/users/{id}"

    def test_single_path_parameter_short_uuid(self, openapi_paths):
        """Match a path with a short hex string parameter."""
        result = match_route("/api/v1/users/94a82f3c", openapi_paths)
        assert result == "/api/v1/users/{id}"

    def test_single_path_parameter_slug(self, openapi_paths):
        """Match a path with a slug-style parameter."""
        result = match_route("/api/v1/users/john-doe", openapi_paths)
        assert result == "/api/v1/users/{id}"

    def test_multiple_path_parameters(self, openapi_paths):
        """Match a path with multiple dynamic segments."""
        result = match_route("/api/v1/users/123/posts/456", openapi_paths)
        assert result == "/api/v1/users/{user_id}/posts/{post_id}"

    def test_multiple_path_parameters_uuids(self, openapi_paths):
        """Match a path with multiple UUID parameters."""
        result = match_route(
            "/api/v1/users/a1b2c3d4/posts/e5f6g7h8",
            openapi_paths
        )
        assert result == "/api/v1/users/{user_id}/posts/{post_id}"

    def test_no_match_returns_none(self, openapi_paths):
        """Return None for an unmatched path."""
        result = match_route("/api/v1/unknown/endpoint", openapi_paths)
        assert result is None

    def test_no_match_completely_different(self, openapi_paths):
        """Return None for a completely different path."""
        result = match_route("/health", openapi_paths)
        assert result is None

    def test_no_match_extra_segments(self, openapi_paths):
        """Return None when path has extra segments beyond any template."""
        result = match_route("/api/v1/users/42/posts/99/comments/1", openapi_paths)
        assert result is None

    def test_trailing_slash_normalization(self, openapi_paths):
        """Match paths with trailing slashes correctly."""
        result = match_route("/api/v1/users/", openapi_paths)
        assert result == "/api/v1/users"

    def test_trailing_slash_with_param(self, openapi_paths):
        """Match parameterized paths with trailing slashes."""
        result = match_route("/api/v1/users/42/", openapi_paths)
        assert result == "/api/v1/users/{id}"

    def test_empty_paths_list(self):
        """Return None when openapi_paths list is empty."""
        result = match_route("/api/v1/users", [])
        assert result is None

    def test_root_path(self):
        """Handle root path correctly."""
        paths = ["/", "/api"]
        result = match_route("/", paths)
        assert result == "/"

    def test_case_sensitive_matching(self, openapi_paths):
        """Paths are case-sensitive."""
        result = match_route("/API/V1/USERS", openapi_paths)
        assert result is None

    def test_parameter_does_not_match_slash(self, openapi_paths):
        """Parameters should not match across path segments (no slashes)."""
        # /api/v1/users/{id} should NOT match /api/v1/users/42/extra
        result = match_route("/api/v1/users/42/extra", openapi_paths)
        # This should not match /api/v1/users/{id} because "42/extra" contains a slash
        assert result is None


# ---------------------------------------------------------------------------
# Integration tests: OpenAPISpecParser using standalone functions
# ---------------------------------------------------------------------------


class TestOpenAPISpecParserIntegration:
    """Integration tests verifying OpenAPISpecParser uses the standalone functions."""

    def test_from_file_uses_load_openapi_spec(self, spec_yaml_file):
        """OpenAPISpecParser.from_file should use load_openapi_spec internally."""
        parser = OpenAPISpecParser.from_file(spec_yaml_file)
        assert parser.paths is not None
        assert "/api/v1/users" in parser.paths

    def test_match_route_method_delegates(self, spec_yaml_file):
        """Parser.match_route should use the standalone match_route function."""
        parser = OpenAPISpecParser.from_file(spec_yaml_file)

        # Static path
        result = parser.match_route("/api/v1/users")
        assert result is not None
        template, path_item = result
        assert template == "/api/v1/users"

        # Parameterized path
        result = parser.match_route("/api/v1/users/94a82f3c")
        assert result is not None
        template, path_item = result
        assert template == "/api/v1/users/{id}"

    def test_get_operation(self, spec_yaml_file):
        """Verify get_operation works with path matching."""
        parser = OpenAPISpecParser.from_file(spec_yaml_file)

        result = parser.get_operation("/api/v1/users/42", "get")
        assert result is not None
        path_template, operation = result
        assert path_template == "/api/v1/users/{id}"
        assert operation["operationId"] == "getUserById"

    def test_get_operation_no_match(self, spec_yaml_file):
        """get_operation returns None for unmatched paths."""
        parser = OpenAPISpecParser.from_file(spec_yaml_file)
        result = parser.get_operation("/api/v1/nonexistent", "get")
        assert result is None


# ---------------------------------------------------------------------------
# Integration tests: APIDiffEngine drift detection
# ---------------------------------------------------------------------------


class TestAPIDiffEngineIntegration:
    """Integration tests for the full drift detection pipeline."""

    def test_detect_extra_field(self, spec_yaml_file):
        """Detect an extra undocumented field in response body."""
        parser = OpenAPISpecParser.from_file(spec_yaml_file)
        engine = APIDiffEngine(parser)

        response_body = {
            "id": 42,
            "name": "Alice",
            "email": "alice@example.com",
            "role": "admin",
            "debug_internal_id": "usr_internal_00000042",  # Extra field!
        }

        issues = engine.compare_response("/api/v1/users/42", "get", 200, response_body)
        extra_field_issues = [i for i in issues if i.issue_type == DriftType.EXTRA_FIELD]
        assert len(extra_field_issues) == 1
        assert extra_field_issues[0].actual == "debug_internal_id"

    def test_detect_missing_required_field(self, spec_yaml_file):
        """Detect a missing required field in response body."""
        parser = OpenAPISpecParser.from_file(spec_yaml_file)
        engine = APIDiffEngine(parser)

        response_body = {
            "access_token": "eyJ...",
            # "token_type" is missing but required!
        }

        issues = engine.compare_response("/api/v1/auth/login", "post", 200, response_body)
        missing_issues = [i for i in issues if i.issue_type == DriftType.MISSING_REQUIRED_FIELD]
        assert len(missing_issues) == 1
        assert missing_issues[0].expected == "token_type"

    def test_undocumented_endpoint(self, spec_yaml_file):
        """Detect an undocumented endpoint."""
        parser = OpenAPISpecParser.from_file(spec_yaml_file)
        engine = APIDiffEngine(parser)

        issues = engine.compare_request("/api/v1/unknown", "get", {}, None)
        assert len(issues) == 1
        assert issues[0].issue_type == DriftType.UNDOCUMENTED_ENDPOINT