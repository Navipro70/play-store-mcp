# CLAUDE.md — `src/play_store_mcp/`

Conventions for the source tree. Read [root `CLAUDE.md`](../../CLAUDE.md) first
for the high-level architecture and API quirks.

The repo has consistent patterns; breaking them creates fork drift that's
painful to merge later.

## File layout

```
src/play_store_mcp/
├── __init__.py        # version + package metadata
├── __main__.py        # entry point: `python -m play_store_mcp`
├── models.py          # ALL Pydantic models live here (~250 lines)
├── client.py          # PlayStoreClient — Google API wrapper (~1700 lines)
└── server.py          # MCP tools — @mcp.tool() decorated functions (~1000 lines)
```

**Almost never touch:** `__init__.py`, `__main__.py`, `Dockerfile`,
workflows. If editing these — pause and reconsider.

## Coding conventions

### Python version

`requires-python = ">=3.11"`. Use modern syntax:

- `str | None` not `Optional[str]`
- `list[X]` not `List[X]`
- `from __future__ import annotations` at top of every file

### Naming

- **Functions/methods:** `snake_case`
- **Classes:** `PascalCase`
- **Constants:** `UPPER_SNAKE_CASE`
- **MCP tool names** = function names. They become the tool ID for the
  agent. Use clear verbs: `list_X`, `get_X`, `create_X`, `update_X`,
  `delete_X`, `upload_X`, `validate_X`. For complex operations: `deploy_app`,
  `promote_release`, `halt_release`. For batch ops: `batch_X`.
- **Pydantic field names:** `snake_case` even when the API uses camelCase.
  Map manually in client. Example: API `versionCode` → model `version_code`.

### Pydantic style

```python
from pydantic import BaseModel, Field
from enum import StrEnum

class MyModel(BaseModel):
    """One-line docstring describing what this represents."""

    required_field: str = Field(..., description="Description shown in tool schema")
    optional_field: str | None = Field(None, description="...")
    enum_field: str = Field(..., description="One of: A, B, C")
    list_field: list[str] = Field(default_factory=list, description="...")
    bool_field: bool = Field(False, description="...")
```

Use `StrEnum` for known closed sets:

```python
class Track(StrEnum):
    INTERNAL = "internal"
    ALPHA = "alpha"
    BETA = "beta"
    PRODUCTION = "production"
```

But **don't add a StrEnum if the API doesn't formally enumerate values**.
Better to use `str` with a docstring constraint than to invent an enum that
diverges from API.

### Logging — structlog

Always use structured logging:

```python
self._logger.info(
    "Verb-noun summary",
    package_name=package_name,
    field_a=field_a,
)
```

Levels:

- `info` — entry/exit of public methods, important state changes
- `debug` — intermediate steps inside a method
- `warning` — recoverable issues (e.g. expired edit session being recreated)
- `exception` — errors with full traceback (use only inside `except`)

**Never log:**

- Service-account JSON or private keys
- OAuth access tokens
- Purchase tokens (mask: `token=...{token[-8:]}`)
- User PII

### Error handling

The client raises `PlayStoreClientError` for any API/business failure:

```python
try:
    result = service.X().Y().execute()
except HttpError as e:
    self._logger.exception("Failed to do X", error=str(e))
    raise PlayStoreClientError(f"Failed to do X: {e.reason}") from e
```

Server tools wrap client calls and return error dicts (don't raise to MCP):

```python
try:
    result = client.do_x(...)
    return result.model_dump()
except PlayStoreClientError as e:
    return {"success": False, "error": str(e)}
```

### Edit-session pattern

The client provides three helpers. Use them:

```python
def _create_edit(self, package_name: str) -> str:
    """Create new edit, return editId."""

def _commit_edit(self, package_name: str, edit_id: str) -> None:
    """Commit and apply changes."""

def _delete_edit(self, package_name: str, edit_id: str) -> None:
    """Discard edit (already-committed/expired edits silently ignored)."""
```

Standard pattern in client methods that mutate via edits:

```python
edit_id = self._create_edit(package_name)
try:
    # 1+ operations using service.edits()...().method(editId=edit_id, ...)
    ...
    self._commit_edit(package_name, edit_id)
except Exception:
    self._delete_edit(package_name, edit_id)
    raise
```

**Anti-pattern (don't do this):**

```python
# DON'T: opens edit but never commits/deletes on early return
edit_id = self._create_edit(package_name)
if some_condition:
    return None  # LEAK — edit hangs for 24h
self._commit_edit(...)
```

### Validation tools (no API call)

If your group of tools has validatable inputs, add a `validate_X` tool. The
agent can call it before doing real work, saving API quota.

Pattern:

```python
@mcp.tool()
def validate_X(input: str) -> dict[str, Any]:
    """Check if X is valid. Does not call the API.

    Returns:
        {"valid": bool, "errors": [...] | None}
    """
    errors = []
    if not input:
        errors.append("input cannot be empty")
    if "/" in input:
        errors.append("path separators not allowed")

    return {
        "valid": len(errors) == 0,
        "errors": errors if errors else None,
    }
```

### Security patterns (from PR #31)

These protect you from shooting yourself in the foot.

**File path validation:**

```python
from pathlib import Path

def _validate_file_path(file_path: str, allowed_extensions: tuple[str, ...]) -> None:
    """Validate user-provided file path. Raises ValueError if invalid."""
    path = Path(file_path).resolve()  # canonicalize, handles `..`

    if not path.exists():
        raise ValueError(f"File not found: {file_path}")
    if not path.is_file():
        raise ValueError(f"Not a regular file: {file_path}")
    if not file_path.endswith(allowed_extensions):
        raise ValueError(f"Expected one of {allowed_extensions}, got: {file_path}")
```

Don't add naive `..` checks — `Path.resolve()` already canonicalizes. PR #31
removed false-positive `..` checks. Trust `resolve()`.

**Numeric range validation:**

```python
def _validate_rollout(rollout_percentage: float) -> None:
    if not 0 <= rollout_percentage <= 100:
        raise ValueError(
            f"rollout_percentage must be 0-100, got: {rollout_percentage}"
        )
```

**Localhost binding** (if you add HTTP endpoints):

```python
import ipaddress

def _is_localhost(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"
```

## Tool docstrings — what the LLM sees

The MCP framework exposes the tool's docstring to the LLM as the tool
description. Write it for the LLM, not for human developers reading code.

**Bad:**

```python
def upload_store_image(...) -> dict:
    """Uploads image."""
```

**Good:**

```python
def upload_store_image(
    package_name: str,
    language: str,
    image_type: str,
    file_path: str,
) -> dict[str, Any]:
    """Upload an image asset (screenshot, icon, feature graphic) to a localized
    store listing.

    Use this when the user wants to update visual assets on Google Play.
    Image_type must be one of: phoneScreenshots, sevenInchScreenshots,
    tenInchScreenshots, tvScreenshots, wearScreenshots, icon, featureGraphic,
    promoGraphic, tvBanner.

    The file must be PNG or JPEG. Google enforces specific dimensions per type
    (1024x500 for featureGraphic, 512x512 for icon, etc.); on dimension
    mismatch this returns an error from the API.

    The upload is committed in its own edit session. To upload multiple images
    in one session (faster), use batch_upload_store_images instead.

    Args:
        package_name: App package name, e.g. "com.example.app".
        language: BCP-47 language tag, e.g. "en-US", "ko-KR", "es-419".
        image_type: One of the 9 supported image types.
        file_path: Absolute path to the .png or .jpg file.

    Returns:
        Dict with `success` (bool), and on success `image` (with `id`, `url`,
        `sha1`, `sha256`).
    """
```

Length: 5-30 lines is the sweet spot. Too short = LLM doesn't know when to
use. Too long = wastes context tokens.

## Pre-commit and linters

The repo runs:

- `ruff` (formatter + linter)
- `mypy` (strict type checking)
- Various `pre-commit` hooks (trailing whitespace, etc.)

Run before every commit:

```bash
pre-commit run --all-files
mypy src/
pytest
```

Fix every issue. Disabling rules creates technical debt that compounds in a
fork — eventually you can't merge upstream changes cleanly.
