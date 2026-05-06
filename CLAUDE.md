# CLAUDE.md

Guidance for AI coding agents (Claude Code and friends) working on
`play-store-mcp` — an MCP server that wraps the Google Play Developer API.

When working in a subdirectory, also read its nested `CLAUDE.md`:

- [`src/play_store_mcp/CLAUDE.md`](src/play_store_mcp/CLAUDE.md) — codebase
  conventions, edit-session pattern, structlog rules, security patterns,
  tool docstring style.
- [`tests/CLAUDE.md`](tests/CLAUDE.md) — test layout, required tests for new
  tools, fixtures, client/server-layer templates.

## What this repo is

An MCP server exposing Google Play Developer API (Publisher v3 + Reporting
v1beta1) as MCP tools. Three layers, in this order:

```
models.py     — Pydantic models for all data structures (NO logic, ONLY shape)
client.py     — PlayStoreClient: low-level Google API wrapper (logging, errors,
                edit-session helpers)
server.py     — MCP tool functions: input validation + call client + return dict/model
```

**Don't collapse the layers.** Don't put validation logic in `client.py`.
Don't put Google API calls in `server.py`. Always go through `models.py` for
return types.

## High-level workflow for adding a tool

1. **Read existing code first.** Before adding anything, read the relevant
   parts of `client.py`, `server.py`, `models.py` to match style. Skim
   `tests/test_client_extended.py` for test patterns.
2. **Get the Discovery doc.** Always work against the live spec, not from
   memory. See [Source of truth for the API](#source-of-truth-for-the-api) below.
3. **Implement in this order:** models → client method → server tool → tests
   → docs.
4. **Run local checks** (pre-commit, pytest, mypy, ruff) before committing.
5. **Test the MCP locally** via `mcp inspector` or by reconnecting Claude Code
   to verify the new tool appears.

## Critical repo-specific rules

### Always use the edit-session helpers

The repo provides `_create_edit`, `_commit_edit`, `_delete_edit` in
`PlayStoreClient`. Every tool that mutates app data via the `edits` resource
MUST use this pattern:

```python
edit_id = self._create_edit(package_name)
try:
    # ... do work using service.edits()...().method(editId=edit_id, ...) ...
    self._commit_edit(package_name, edit_id)
    return result
except Exception:
    self._delete_edit(package_name, edit_id)
    raise
```

If you find yourself calling `service.edits().insert()` directly inside a tool
function, you're doing it wrong. See [Edit sessions](#edit-sessions--the-critical-concept)
below.

### Tests are required

Every new tool gets:

1. **Happy path test** with `assert_called_once_with(...)` checking exact
   parameters passed to the Google API mock.
2. **Boundary value tests** for any numeric/enum/string-format parameters.
3. **Edit-session cleanup test** if the tool uses edits (verify
   `_delete_edit` is called on failure).
4. **Validation test** for any client-side validation (file existence,
   ranges, formats).

Run locally:
```bash
pytest tests/ -v
pytest tests/test_server_extended.py::test_<your_tool> -v
```

See [`tests/CLAUDE.md`](tests/CLAUDE.md) for templates.

### structlog logging is required

Every method in `client.py` starts with:

```python
self._logger.info("Doing X", package_name=package_name, other_relevant_field=...)
```

Use `info` for tool entry, `debug` for intermediate steps, `exception` for
errors (`exception()` auto-includes traceback). Full rules in
[`src/play_store_mcp/CLAUDE.md`](src/play_store_mcp/CLAUDE.md).

### Validation tools (no API call) are encouraged

If your group of tools has a validatable input (file path, format string,
enum, regex pattern), add a `validate_X` tool that does it without calling
the API. This saves quota and gives the LLM agent fast feedback.

Examples already in repo: `validate_package_name`, `validate_track`,
`validate_listing_text`.

### Security patterns from PR #31

The repo had a security pass closing path traversal, localhost binding, and
credential leaks. Match that bar:

- File paths from users: validate extension, existence, no `..` traversal
  (use `Path.resolve()`).
- Numeric inputs: validate ranges (0-100 for percentages, 0+ for counts).
- Sensitive params (tokens, credentials): never log unmasked.

See [`src/play_store_mcp/CLAUDE.md`](src/play_store_mcp/CLAUDE.md) for code
samples.

## Source of truth for the API

**Always** check the live Discovery document, not blog posts or other repos:

```bash
curl -o /tmp/androidpublisher-v3.json \
  "https://androidpublisher.googleapis.com/\$discovery/rest?version=v3"
```

Mirror (always reachable):
https://github.com/googleapis/google-api-go-client/blob/main/androidpublisher/v3/androidpublisher-api.json

Human-readable docs:
https://developers.google.com/android-publisher/api-ref/rest

For each method you implement, verify in Discovery:

- Resource path: `resources.<top>.[resources.<sub>...]methods.<name>`
- HTTP verb (POST vs PATCH matters!)
- Required vs optional parameters
- Request body schema (if applicable)
- Response schema (use this to design pydantic model)

## Discovery doc structure

```
{
  "name": "androidpublisher",
  "version": "v3",
  "revision": "20260416",
  "baseUrl": "https://androidpublisher.googleapis.com/",
  "schemas": { ... },           // pydantic-equivalent definitions
  "resources": {
    "edits": {
      "methods": { ... },        // edits.insert, edits.commit, etc.
      "resources": {
        "tracks": { "methods": { ... } },
        "listings": { "methods": { ... } },
        ...
      }
    },
    "monetization": { ... },
    "purchases": { ... },
    ...
  }
}
```

For each method:

1. Locate it: `resources.<top>.[resources.<sub>...]methods.<name>`
2. Read `httpMethod` (POST/GET/PATCH/PUT/DELETE).
3. Read `parameters` (path + query params).
4. Read `request.$ref` and look up that schema for body.
5. Read `response.$ref` for return type — basis for your pydantic model.

## Top-level resources

```
monetization                42 methods
edits                       37
purchases                   15
inappproducts                9   (legacy — prefer monetization)
applications                 5
apprecovery                  5
systemapks                   4
users                        4
externaltransactions         3
grants                       3
orders                       3
reviews                      3
generatedapks                2
internalappsharingartifacts  2
─────────────────────────────────
TOTAL                      137
```

## Authentication

**OAuth 2.0 with service account.** Process:

1. User creates a Google Cloud project and a service account.
2. Service account is granted access to the app in Play Console (Settings →
   API access → Grant access to specific app).
3. User downloads JSON key file.
4. The repo reads JSON via `google-auth`:

```python
from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/androidpublisher"]
creds = service_account.Credentials.from_service_account_file(
    "key.json", scopes=SCOPES
)
```

5. Library auto-handles access_token (TTL 1 hour) refresh — no manual logic.

For the Play Developer Reporting API (vitals):

```python
REPORTING_SCOPE = "https://www.googleapis.com/auth/playdeveloperreporting"
```

This is a **separate API and separate scope** from Publisher.

## Edit sessions — the critical concept

Most write operations on an app go through **edits**, a transactional protocol:

```
1. POST /edits                    → editId
2. PATCH/PUT/POST sub-resources    (with editId in path)
   - tracks, listings, images, bundles, apks, deobfuscationfiles, etc.
3. POST /edits/{editId}:validate   (optional — dry-run)
4. POST /edits/{editId}:commit     → applies changes to live app
   OR
   DELETE /edits/{editId}          → discard
```

### Important details

- **Edit lifetime:** ~24 hours. Stale edits silently expire.
- **Concurrency:** Only one active edit per app at a time (last-write-wins
  for race conditions).
- **No partial commits:** Either all changes commit or none.
- **Draft apps quirk:** For unpublished apps, commit fails unless an
  `internal` track release with `status=draft` exists in the edit. The
  client handles this automatically in `_commit_edit`.
- **Validate before commit:** `:validate` checks the edit but doesn't apply.
  Useful for CI dry-runs.

### Operations that DON'T need edits

These are stateless calls without a transactional wrapper:

- All `purchases.*` methods (validation, refund, acknowledge)
- All `reviews.*` methods (list, get, reply)
- `monetization.*` (subscriptions, onetimeproducts) — has its own state
  model with `state: ACTIVE | INACTIVE | DRAFT`
- `orders.*` (refund, batchGet)
- `applications.*` (data safety, content rating)
- `users.*` and `grants.*` (Console user management)

## Specific quirks

### Regional pricing — `convertRegionPrices`

For monetization (subscriptions, onetime products), don't manually price in
150+ regions. Use Google's auto-conversion:

```python
result = service.monetization().convertRegionPrices(
    packageName=package_name,
    body={"price": {"currencyCode": "USD", "units": "9", "nanos": 990000000}}
).execute()

# result has:
# - convertedRegionPrices: dict per region with localized price
# - convertedOtherRegionsPrice: USD/EUR fallback
# - regionVersion: {"version": "..."} — required for next request
```

The returned `regionVersion.version` MUST be passed back when creating the
product. But there's a quirk:

### `regionsVersion.version` URL trick

`google-api-python-client` doesn't support parameter names with dots. To pass
`regionsVersion.version=...` to a request, append it to the URL manually:

```python
request = service.monetization().onetimeproducts().patch(
    packageName=package_name,
    productId=sku,
    body=body,
    allowMissing=True,
    updateMask="listings,purchaseOptions",
)

sep = "&" if "?" in request.uri else "?"
request.uri += f"{sep}regionsVersion.version={version}"

result = request.execute()
```

This is a documented workaround. Refactor it into a helper:

```python
def _patch_with_regions_version(self, request, version: str):
    sep = "&" if "?" in request.uri else "?"
    request.uri += f"{sep}regionsVersion.version={version}"
    return request
```

### `allowMissing=True` for UPSERT

For `monetization.onetimeproducts.patch` and `monetization.subscriptions.patch`,
passing `allowMissing=True` makes the call act as UPSERT (create if missing,
update if exists). This avoids needing separate `create_X` and `update_X` tools.

### Subscriptions v2 vs v1

For runtime queries about a specific user's subscription:

- ✅ Use `purchases.subscriptionsv2.get` (modern)
- ❌ Don't use `purchases.subscriptions.get` (legacy)

The v2 response has different shape:

- `subscriptionState`: `SUBSCRIPTION_STATE_ACTIVE`, `_CANCELED`, etc.
- `lineItems[]`: array of products in the subscription. Each has either
  `autoRenewingPlan` (if auto-renewing) or `prepaidPlan`.
- **Auto-renewing detection:** check
  `lineItems[i].autoRenewingPlan.autoRenewEnabled`, NOT `subscriptionState`.
  PR #31 fixed this bug — a subscription can be active but not auto-renewing
  (user canceled, still has access until period end).

### Acknowledgement — 3-day rule

After a user makes a purchase, the app must **acknowledge** it within 3 days
or Google auto-refunds. The `acknowledge` endpoints exist precisely for
backend services that handle this server-side.

### Rate limits

Default quota: **6000 requests/day per project** for Publisher API. There's
also a per-second limit (~3-5 RPS sustained). The 429 response includes
`Retry-After` header.

For Reporting API (vitals): much lower limits, ~1 RPS. Don't poll vitals
aggressively.

The repo doesn't implement explicit rate limiting — relies on
`google-api-python-client`'s default retry on 429.

### Image upload — special handling

`edits.images.upload` requires multipart/form-data. With
`google-api-python-client`:

```python
from googleapiclient.http import MediaFileUpload

media = MediaFileUpload(file_path, mimetype="image/png", resumable=True)
result = service.edits().images().upload(
    packageName=package_name,
    editId=edit_id,
    language=language,
    imageType=image_type,
    media_body=media,
).execute()
```

For large files (AAB > 100MB), use `resumable=True` to enable chunked upload
with auto-retry on network blips.

### Bundle/APK upload — long timeouts

Google's docs warn: AAB upload can take 2+ minutes. The default
`googleapiclient` timeout (60s) will fail. Adjust:

```python
from googleapiclient.http import build_http
http = build_http()
http.timeout = 600  # 10 minutes
service = build("androidpublisher", "v3", credentials=creds, http=http)
```

The repo handles this in `_get_service`. Don't override unless your specific
operation needs longer.

### Bundles vs APKs

Google strongly prefers AAB (Android App Bundle) over APK. The repo's
`deploy_app` auto-detects from extension and routes to the right uploader.
Match this pattern in any new tool that uploads binaries.

## Locales

Locale = `language[-region]`, e.g.:

- `en-US`, `en-GB`
- `es-ES`, `es-419` (Latin America Spanish)
- `pt-BR`, `pt-PT`
- `zh-CN`, `zh-TW`
- `ko-KR`, `ja-JP`

Google Play supports 77 locales. The full list is in the google-api docs and
also in Discovery (under various enum schemas like `ListingLanguage`).

When implementing localized tools, **don't hardcode locales**. Accept a
`language` parameter as `str`. Validate format with regex
`^[a-z]{2}(-[A-Z0-9]+)?$`.

## Discovery method types you'll encounter

When reading Discovery, the `httpMethod` tells you what to do in
`google-api-python-client`:

| HTTP | Discovery field | Python call |
|---|---|---|
| GET | parameters only | `.method(...).execute()` |
| POST (create) | `request.$ref` body | `.method(body=..., ...).execute()` |
| POST (action) | sometimes no body | `.method(...).execute()` |
| PATCH | partial update | `.patch(body=..., updateMask=..., ...)` |
| PUT | full replace | `.update(body=..., ...)` |
| DELETE | parameters only | `.delete(...).execute()` |

`PATCH` always wants `updateMask` parameter — list of fields to update,
comma-separated. e.g. `updateMask="listings,purchaseOptions"`.

## Adding a tool — step-by-step recipe

### Step 1: Pydantic model

Add to `src/play_store_mcp/models.py`. Match existing style — see
[`src/play_store_mcp/CLAUDE.md`](src/play_store_mcp/CLAUDE.md#pydantic-style)
for the conventions.

### Step 2: Client method

Add to `src/play_store_mcp/client.py`. Inside the `PlayStoreClient` class.
Pattern:

```python
def my_new_method(
    self,
    package_name: str,
    other_param: str,
) -> MyModel:
    """One-line summary.

    Longer description of what this does and any quirks.

    Args:
        package_name: App package name.
        other_param: Description.

    Returns:
        MyModel with the result.

    Raises:
        PlayStoreClientError: On API failure.
    """
    self._logger.info(
        "Doing the thing",
        package_name=package_name,
        other_param=other_param,
    )
    service = self._get_service()

    try:
        # If this needs an edit session:
        edit_id = self._create_edit(package_name)
        try:
            result = (
                service.edits()
                .someResource()
                .someMethod(packageName=package_name, editId=edit_id, ...)
                .execute()
            )
            self._commit_edit(package_name, edit_id)
        except Exception:
            self._delete_edit(package_name, edit_id)
            raise

        # If this is a non-edit call:
        # result = service.someResource().method(packageName=package_name, ...).execute()

        return MyModel(
            # Map API fields to model
            field_a=result.get("fieldA"),
            field_b=int(result.get("fieldB", 0)),
        )
    except HttpError as e:
        self._logger.exception("Failed to do the thing", error=str(e))
        raise PlayStoreClientError(f"Failed to do the thing: {e.reason}") from e
```

### Step 3: Server tool

Add to `src/play_store_mcp/server.py`:

```python
@mcp.tool()
def my_new_tool(
    package_name: str,
    other_param: str,
) -> dict[str, Any]:
    """User-facing summary (this becomes the tool description for the LLM).

    Detailed description visible to the LLM. Include:
    - When to use this tool
    - Important caveats (e.g., "this requires the app to be published")
    - What the result looks like

    Args:
        package_name: App package name (e.g. "com.example.myapp").
        other_param: Description with example.

    Returns:
        Dict with the result fields.
    """
    # Input validation FIRST — fail fast, save Google API quota
    if not package_name or "." not in package_name:
        return {"success": False, "error": "Invalid package_name"}

    client = get_client_from_context()
    try:
        result = client.my_new_method(package_name, other_param)
        return result.model_dump()
    except PlayStoreClientError as e:
        return {"success": False, "error": str(e)}
```

### Step 4: Tests

See [`tests/CLAUDE.md`](tests/CLAUDE.md) for full templates.

### Step 5: Docs

Keep docs current so future-you remembers what was added:

- `README.md` — add tool to the table of tools.
- `docs/tools-reference.md` — add a section with examples.

Create **if the group is 3+ tools**:

- `docs/tools/<group-name>.md` — dedicated page for the feature group.

### Step 6: Local validation

```bash
# Format and lint
pre-commit run --all-files

# Type check
mypy src/

# Tests
pytest tests/ -v
```

Fix every warning before committing.

### Step 7: Test in Claude Code

After committing, restart Claude Code (or the MCP client of choice) and
verify the new tool appears in the tools list. Try a simple invocation:

```
Use list_store_images to check what icons are uploaded for com.example.app
```

If the tool doesn't show up, common causes:

1. Forgot to register the tool with `@mcp.tool()` decorator.
2. Syntax error in `server.py` — check the MCP process logs.
3. Need to fully restart the MCP host (not just reload chat).

## Common mistakes to avoid

1. **Calling Google API directly from `server.py`** — always go through
   `client.py`.
2. **Skipping pydantic models** — return raw dicts and the architecture rots.
3. **Forgetting `_delete_edit` in except block** — leaves orphaned edit
   sessions.
4. **Logging tokens/credentials/sensitive data.**
5. **`assert_called_once`** instead of `assert_called_once_with(...)` — too
   weak.
6. **Using camelCase in pydantic model fields** — repo convention is
   snake_case.
7. **Ignoring `regionsVersion.version` URL trick** for monetization —
   request will fail.
8. **Forgetting that `purchases.subscriptionsv2` is preferred** over legacy
   `purchases.subscriptions`.
9. **Adding tools without updating README** — future you will not remember
   what was added.

## Keeping the fork mergeable with upstream

This repo is a fork of [`lusky3/play-store-mcp`](https://github.com/lusky3/play-store-mcp),
which is actively maintained. To make merges painless:

- Keep new code in **separate files where possible** (e.g.,
  `src/play_store_mcp/extensions/` if you go far).
- If editing existing files, keep changes **localized** to specific functions
  rather than scattered across files.
- Use clear commit messages: `add: edits.images tools`, `add: monetization
  onetime products`.
- Periodically rebase on upstream main:

  ```bash
  git remote add upstream https://github.com/lusky3/play-store-mcp.git
  git fetch upstream
  git rebase upstream/main
  ```

If a future upstream change refactors the architecture, your local additions
might need adjustment. Limiting blast radius now saves time later.
