# Edits Miscellaneous Tools

Smaller `edits.*` operations that didn't need their own page: deobfuscation
file uploads, bundle/APK listings, country availability, custom track
creation, and the dry-run `edits.validate`.

## When edits get used here

- `upload_deobfuscation_file` and `create_custom_track` use one-shot edit
  sessions internally (`_create_edit` / mutate / `_commit_edit` / cleanup
  on failure).
- `list_bundles`, `list_apks`, `get_country_availability` create a
  short-lived edit just to read state — committed never, deleted in a
  `finally` block.
- `validate_edit` is the only one that takes an external `edit_id` — for
  advanced flows that manage edits outside of this MCP.

---

### `upload_deobfuscation_file`

ProGuard/R8 mapping or native debug symbols, attached to a specific APK
version code.

```text
upload_deobfuscation_file(
    package_name="com.example.app",
    version_code=12345,
    file_path="/path/to/build/outputs/mapping/release/mapping.txt",
    file_type="proguard",     # or "nativeCode" for NDK symbol zip
)
```

Without this, Play Console crash stack traces stay obfuscated and Vitals
data is much less useful. Run after every release with a non-debug build.

`file_type` is constrained to `proguard` or `nativeCode` (the only values
in the v3 Discovery enum besides the unused `Unspecified` sentinel).

**File extension allowlist:** `.txt`, `.zip`, `.gz`, `.map`. Path is
canonicalised via `Path.resolve()` so `..` is harmless.

### `list_bundles` / `list_apks`

Read-only. Useful to:

- Confirm a `version_code` was uploaded
- Map a version_code to its sha1/sha256 (for binary attestation)
- Audit which versions exist before deleting an old edit

```text
list_bundles(package_name="com.example.app")
# {
#   "success": true,
#   "bundles": [
#     {"version_code": 100, "sha1": "...", "sha256": "..."},
#     ...
#   ]
# }
```

### `get_country_availability`

```text
get_country_availability(package_name="com.example.app", track="production")
# {
#   "success": true,
#   "track": "production",
#   "rest_of_world": false,
#   "sync_with_production": false,
#   "countries": ["US", "GB", "DE", ...]   # ISO 3166-1 alpha-2
# }
```

### `create_custom_track`

Publisher API only allows **closed-testing** tracks via this endpoint —
the API rejects `production` / `internal` / `alpha` / `beta` (those are
fixed defaults).

```text
create_custom_track(
    package_name="com.example.app",
    track="qa-team",            # arbitrary identifier
    form_factor="DEFAULT",      # or WEAR / AUTOMOTIVE
)
```

For non-DEFAULT form factors the track id must be prefixed (e.g.
`wear:qa-team`).

### `validate_edit`

Calls `edits.validate` against an existing `edit_id`. Most repo tools
manage edit lifecycle internally, so you usually don't have an edit_id
sitting around — this exists for users wiring multi-step flows from
outside.

Note: a successful API call returns `success=True` regardless of the
validation outcome. The actual outcome is in `valid`. If the API call
fails (auth/network), `success=False` with `error` filled in.
