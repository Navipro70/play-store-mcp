# CLAUDE.md — `tests/`

Testing requirements for `play-store-mcp`. Read [root `CLAUDE.md`](../CLAUDE.md)
for the high-level architecture and [`src/play_store_mcp/CLAUDE.md`](../src/play_store_mcp/CLAUDE.md)
for code conventions.

The repo has high test standards (PR #31 added 357+ lines of new tests as
part of a quality pass). Match this bar — broken tools that fail silently
waste more time than the tests would have taken.

## Test files — where new tests go

```
tests/test_client_extended.py    ← NEW client-layer tests go here
tests/test_server_extended.py    ← NEW server-layer (tool) tests go here
tests/test_models.py             ← Add when introducing new pydantic models
```

Don't modify the original `test_client.py` and `test_server.py` unless
fixing existing tests. New stuff goes in `_extended.py`.

Other files in this directory:

```
tests/
├── conftest.py                    # shared fixtures (mock service, mock client)
├── test_client.py                 # original client tests
├── test_client_extended.py        # NEW client tests go here
├── test_server.py                 # original server tests
├── test_server_extended.py        # NEW server tests go here
├── test_models.py                 # pydantic model tests
├── test_integration.py            # multi-component flows (mocked)
├── test_credentials_endpoint.py   # tests for /credentials HTTP endpoint
└── test_live_api.py               # REAL API calls — gated by env
```

## What's required for every new tool

1. **Happy path test** with `assert_called_once_with(...)` — exact parameter
   verification, not just "called once".
2. **Boundary value tests** — for any numeric, enum, format-constrained input.
3. **Edit-session cleanup test** — if the tool uses edits, verify
   `_delete_edit` is called when the operation fails mid-flow.
4. **Validation tests** — for any client-side validation (file existence,
   ranges, enums, formats).
5. **Mock argument verification** — every mock call inside the test should be
   asserted with the exact expected parameters.

## Fixtures — read `tests/conftest.py` first

The repo provides fixtures you should use:

```python
# Available in conftest.py:
@pytest.fixture
def mock_credentials() -> Mock: ...

@pytest.fixture
def mock_service() -> MagicMock: ...

@pytest.fixture
def client_with_mocks(mock_credentials, mock_service) -> tuple[PlayStoreClient, MagicMock]: ...
```

Use `client_with_mocks` for client-layer tests. It returns a
`PlayStoreClient` with a fully mocked Google API service object, so you can
stub any chain like
`mock_service.edits().tracks().update().execute.return_value = {...}`.

For server-layer tests, you patch `get_client_from_context()` directly:

```python
from unittest.mock import patch, Mock
from play_store_mcp.server import my_new_tool

def test_my_new_tool_happy():
    with patch("play_store_mcp.server.get_client_from_context") as mock_get:
        mock_client = Mock()
        mock_client.my_new_method.return_value = MyModel(field_a="x", field_b=42)
        mock_get.return_value = mock_client

        result = my_new_tool(package_name="com.example.app", other_param="x")

        assert result["field_a"] == "x"
        mock_client.my_new_method.assert_called_once_with(
            package_name="com.example.app",
            other_param="x",
        )
```

## Client-layer test template

For a method that uses an edit session:

```python
def test_my_new_method_happy_path(client_with_mocks):
    client, mock_service = client_with_mocks

    # Mock edit lifecycle
    mock_service.edits().insert().execute.return_value = {"id": "edit-123"}

    # Mock the actual operation
    mock_service.edits().some_resource().some_method().execute.return_value = {
        "fieldA": "value",
        "fieldB": "42",
    }

    result = client.my_new_method(
        package_name="com.example.app",
        other_param="value",
    )

    # Verify return value
    assert result.field_a == "value"
    assert result.field_b == 42

    # Verify the API call had correct args
    mock_service.edits().some_resource().some_method.assert_called_with(
        packageName="com.example.app",
        editId="edit-123",
        body={"field": "value"},
    )

    # Verify edit was committed (not deleted)
    mock_service.edits().commit.assert_called_once_with(
        packageName="com.example.app",
        editId="edit-123",
    )
    mock_service.edits().delete.assert_not_called()


def test_my_new_method_failure_cleans_up_edit(client_with_mocks):
    client, mock_service = client_with_mocks

    mock_service.edits().insert().execute.return_value = {"id": "edit-456"}
    mock_service.edits().some_resource().some_method().execute.side_effect = HttpError(
        Mock(status=400), b'{"error": "bad request"}'
    )

    with pytest.raises(PlayStoreClientError):
        client.my_new_method("com.example.app", "value")

    # Edit must be deleted on failure
    mock_service.edits().delete.assert_called_once_with(
        packageName="com.example.app",
        editId="edit-456",
    )
    mock_service.edits().commit.assert_not_called()


def test_my_new_method_empty_response(client_with_mocks):
    """API returns minimal/empty response — model should still construct."""
    client, mock_service = client_with_mocks

    mock_service.edits().insert().execute.return_value = {"id": "edit-789"}
    mock_service.edits().some_resource().some_method().execute.return_value = {}

    result = client.my_new_method("com.example.app", "value")

    assert result.field_a is None or result.field_a == ""
    assert result.field_b == 0  # default
```

## Server-layer test template

```python
def test_my_new_tool_invalid_package_name():
    """Validation should fail before any API call."""
    result = my_new_tool(package_name="invalid", other_param="x")

    assert result["success"] is False
    assert "package_name" in result["error"].lower()


def test_my_new_tool_calls_client_correctly():
    with patch("play_store_mcp.server.get_client_from_context") as mock_get:
        mock_client = Mock()
        mock_client.my_new_method.return_value = MyModel(
            package_name="com.example.app",
            field_a="result",
            field_b=42,
        )
        mock_get.return_value = mock_client

        result = my_new_tool(
            package_name="com.example.app",
            other_param="param-value",
        )

        # Tool returns dict (model_dump)
        assert isinstance(result, dict)
        assert result["field_a"] == "result"

        # Client called with EXACT args
        mock_client.my_new_method.assert_called_once_with(
            package_name="com.example.app",
            other_param="param-value",
        )


def test_my_new_tool_handles_client_error():
    with patch("play_store_mcp.server.get_client_from_context") as mock_get:
        mock_client = Mock()
        mock_client.my_new_method.side_effect = PlayStoreClientError("API failed")
        mock_get.return_value = mock_client

        result = my_new_tool(package_name="com.example.app", other_param="x")

        assert result["success"] is False
        assert "API failed" in result["error"]
```

## Boundary value tests

For every input with constraints, test the boundaries:

```python
@pytest.mark.parametrize("rollout", [0, 0.1, 50, 99.9, 100])
def test_update_rollout_valid_values(rollout):
    """All values in [0, 100] are accepted."""
    # ... (mock setup) ...
    result = update_rollout(package_name="com.x", track="production",
                            rollout_percentage=rollout)
    assert result.get("success") is not False  # not rejected by validation


@pytest.mark.parametrize("rollout", [-0.01, -1, 100.01, 200])
def test_update_rollout_invalid_values(rollout):
    """Values outside [0, 100] are rejected before API call."""
    result = update_rollout(package_name="com.x", track="production",
                            rollout_percentage=rollout)
    assert result["success"] is False
    assert "rollout_percentage" in result["error"].lower()


@pytest.mark.parametrize("image_type", [
    "phoneScreenshots", "icon", "featureGraphic", "promoGraphic",
    "tvBanner", "wearScreenshots",
])
def test_image_type_accepted(image_type, ...):
    ...

@pytest.mark.parametrize("bad_type", ["invalid", "PHONE", "phone_screenshots", ""])
def test_image_type_rejected(bad_type):
    result = upload_store_image(..., image_type=bad_type, ...)
    assert result["success"] is False
```

## Models tests

When adding new pydantic models to `models.py`, add tests to
`tests/test_models.py`:

```python
def test_my_model_required_fields():
    """Required fields raise when missing."""
    with pytest.raises(ValidationError):
        MyModel()  # missing required fields

def test_my_model_optional_fields_default_to_none():
    m = MyModel(required_field="x")
    assert m.optional_field is None

def test_my_model_field_types():
    m = MyModel(
        required_field="x",
        list_field=["a", "b"],
        bool_field=True,
    )
    assert isinstance(m.list_field, list)
    assert m.bool_field is True
```

## Live API tests

`tests/test_live_api.py` runs against the real Google API. **Only add to it
if absolutely necessary.** Most things should be mocked.

If you must add a live test:

```python
@pytest.mark.live_api
@pytest.mark.skipif(not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
                   reason="No live credentials")
def test_my_new_method_against_real_api(real_client):
    """Verify the actual Google API responds as expected."""
    result = real_client.my_new_method(...)
    assert result is not None
```

## Running tests locally

```bash
# All tests
pytest

# Just your new tests
pytest tests/test_client_extended.py::test_my_new_method_happy_path -v

# Coverage check
pytest --cov=play_store_mcp --cov-report=term-missing

# Skip live API tests (default)
pytest -m "not live_api"

# Type check
mypy src/

# Lint
ruff check src/ tests/
ruff format --check src/ tests/
```

The repo aims for **>90% coverage on changed files**. Check coverage of your
specific changes:

```bash
pytest --cov=play_store_mcp.client --cov-report=term-missing tests/test_client_extended.py
```

## Common test mistakes

1. **`assert_called_once`** instead of `assert_called_once_with(args)` —
   too weak.
2. **Hardcoded test data without explanation** — add comments why specific
   values matter.
3. **Mocking too deep** — mock at `service.X().Y().method()` level, not at
   the transport layer.
4. **Skipping the failure path** — every tool needs at least one error case
   test.
5. **`return_value` vs `side_effect`** — for raising exceptions use
   `side_effect`.
