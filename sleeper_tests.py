import os
import yaml
import pytest


SPEC_PATH = os.path.join(os.path.dirname(__file__), "openapi", "sleeper.yaml")


@pytest.fixture(scope="session")
def spec_text():
    with open(SPEC_PATH, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="session")
def spec(spec_text):
    # Parse YAML; if invalid, this will raise and fail tests immediately
    return yaml.safe_load(spec_text)


def test_spec_basic_shape(spec):
    # Ensure core OpenAPI fields exist
    assert spec.get("openapi", "").startswith("3."), "OpenAPI version missing or not 3.x"
    for key in ["info", "paths", "components"]:
        assert key in spec, f"Missing top-level field: {key}"


@pytest.mark.parametrize(
    "path,method",
    [
        ("/user/{id}", "get"),
        ("/user/{user_id}/leagues/{sport}/{season}", "get"),
        ("/league/{league_id}", "get"),
        ("/league/{league_id}/rosters", "get"),
        ("/league/{league_id}/users", "get"),
        ("/league/{league_id}/matchups/{week}", "get"),
        ("/league/{league_id}/winners_bracket", "get"),
        ("/league/{league_id}/losers_bracket", "get"),
        ("/league/{league_id}/transactions/{round}", "get"),
        ("/league/{league_id}/traded_picks", "get"),
        ("/state/{sport}", "get"),
        ("/league/{league_id}/drafts", "get"),
        ("/user/{user_id}/drafts/{sport}/{season}", "get"),
        ("/draft/{draft_id}", "get"),
        ("/draft/{draft_id}/picks", "get"),
        ("/draft/{draft_id}/traded_picks", "get"),
        ("/players/{sport}", "get"),
        ("/players/{sport}/trending/{type}", "get"),
    ],
)
def test_required_paths_present(spec, path, method):
    assert path in spec["paths"], f"Missing path: {path}"
    assert method in spec["paths"][path], f"Missing method {method} for path {path}"
    # Check that 200 response exists
    responses = spec["paths"][path][method].get("responses", {})
    assert "200" in responses, f"Missing 200 response for {method.upper()} {path}"


@pytest.mark.parametrize(
    "schema_name",
    [
        "User",
        "League",
        "Roster",
        "Matchup",
        "BracketItem",
        "Transaction",
        "TradedPick",
        "State",
        "Draft",
        "DraftPick",
        "Player",
        "TrendingPlayer",
        "Error",
    ],
)
def test_required_schemas_exist(spec, schema_name):
    components = spec.get("components", {})
    schemas = components.get("schemas", {})
    assert schema_name in schemas, f"Missing schema: {schema_name}"


def test_parameters_referenced_exist(spec):
    # Walk all operations and ensure $ref parameters exist in components.parameters
    params_def = spec["components"].get("parameters", {})
    for path_item in spec["paths"].values():
        for method, op in path_item.items():
            if method.startswith("x-"):
                continue
            if method not in {"get", "post", "put", "patch", "delete", "options", "head", "trace"}:
                continue
            for p in op.get("parameters", []):
                if "$ref" in p:
                    ref = p["$ref"]
                    assert ref.startswith(
                        "#/components/parameters/"
                    ), f"Unexpected param ref: {ref}"
                    name = ref.split("/")[-1]
                    assert name in params_def, f"Parameter ref not found: {name}"


def test_response_schemas_or_content(spec):
    # Ensure each 200 response has either a schema in content or at least a content type stub
    for path, path_item in spec["paths"].items():
        for method, op in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete", "options", "head", "trace"}:
                continue
            responses = op.get("responses", {})
            if "200" in responses:
                content = responses["200"].get("content", {})
                # For image endpoints, content may be image/* without schema; but ideally schema exists
                if content:
                    # if application/json present, require a schema
                    if "application/json" in content:
                        assert (
                            "schema" in content["application/json"]
                        ), f"Missing schema under 200 application/json for {method.upper()} {path}"
                else:
                    # No content means likely a problem for JSON endpoints
                    raise AssertionError(
                        f"Missing content for 200 response on {method.upper()} {path}"
                    )


def test_tags_present(spec):
    # All operations should have at least one tag
    for path_item in spec["paths"].values():
        for method, op in path_item.items():
            if method in {"get", "post", "put", "patch", "delete", "options", "head", "trace"}:
                assert "tags" in op and op["tags"], "Operation missing tags"
