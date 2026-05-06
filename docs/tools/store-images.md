# Store Images Tools

Tools that wrap `edits.images.*` from the Publisher API v3. Use these to
manage screenshots, icons, feature graphics, and other localized image
assets for a Google Play store listing.

## Image types

The Publisher API v3 enumerates 8 image types. Pass any of these strings as
`image_type`:

| `image_type`              | Notes                                       |
| ------------------------- | ------------------------------------------- |
| `phoneScreenshots`        | Phone screenshots (the most common one)     |
| `sevenInchScreenshots`    | 7-inch tablet                               |
| `tenInchScreenshots`      | 10-inch tablet                              |
| `tvScreenshots`           | Android TV                                  |
| `wearScreenshots`         | Wear OS                                     |
| `icon`                    | High-resolution icon (512×512 PNG)          |
| `featureGraphic`          | Feature graphic banner (1024×500)           |
| `tvBanner`                | TV banner (1280×720)                        |

`promoGraphic` from older docs is **not** part of the current Discovery doc
— don't use it. Call `validate_image_type` if you're not sure whether a
value is supported.

## Locales

`language` is a BCP-47 tag like `en-US`, `es-419`, `pt-BR`, `ko-KR`,
`zh-CN`. Google Play accepts 77 locales; pass exactly the tag the listing
uses (the tag from `list_all_listings`).

## Edit-session behaviour

Every mutating tool runs inside its own edit session — `_create_edit`, the
mutation, `_commit_edit`. On any failure the edit is `_delete_edit`'d so
you don't accumulate orphan edits.

`batch_upload_store_images` is the exception: it opens **one** edit, runs
N uploads, and commits once. If one upload fails the whole edit is
discarded; the result reports the partial counts.

---

### `validate_image_type`

Server-side check that an `image_type` value matches the API enum. No API
call. Use to short-circuit before mutation tools — saves the daily quota.

**Returns**

```json
{
  "valid": true,
  "image_type": "icon",
  "errors": [],
  "allowed": ["phoneScreenshots", "sevenInchScreenshots", "tenInchScreenshots",
              "tvScreenshots", "wearScreenshots", "icon", "featureGraphic",
              "tvBanner"]
}
```

### `list_store_images`

List currently uploaded images of one type for one locale.

**Args**

- `package_name`: e.g. `com.example.app`
- `language`: BCP-47 tag (`en-US`)
- `image_type`: one of the 8 types

**Returns**

```json
{
  "success": true,
  "package_name": "com.example.app",
  "language": "en-US",
  "image_type": "phoneScreenshots",
  "images": [
    {"id": "img-1", "url": "https://...", "sha1": "abc...", "sha256": "def..."}
  ]
}
```

### `upload_store_image`

Upload **one** PNG/JPEG file in its own edit session.

**Args**

- `package_name`, `language`, `image_type`
- `file_path`: absolute path to a `.png`/`.jpg`/`.jpeg`. Path is canonicalised
  via `Path.resolve()` (handles `..`); non-image extensions are rejected.

Google enforces dimensions per type (e.g. 1024×500 for `featureGraphic`,
512×512 for `icon`). On dimension mismatch the API rejects the upload and
the tool returns `success=False` with the API's error.

### `batch_upload_store_images`

Same as `upload_store_image` but uploads `file_paths: list[str]` of one
type in **one** edit session. Faster and atomic. Use when refreshing a
whole screenshot set for a locale.

If any upload fails mid-batch the entire edit is discarded; the result
reports `successful_count`, `failed_count`, and the partial list of
successful uploads (which were also rolled back).

### `delete_store_image`

Delete a single image by `image_id` (returned by `list_store_images` or
`upload_store_image`).

### `delete_all_store_images`

Delete every image of a given type for a locale. Useful before
`batch_upload_store_images` to fully replace a set.

---

## Typical workflow

Replace the phone-screenshot set for `en-US`:

```text
1. validate_image_type("phoneScreenshots")        # cheap check
2. list_store_images("com.example.app", "en-US",
                     "phoneScreenshots")          # see what's there now
3. delete_all_store_images("com.example.app", "en-US",
                           "phoneScreenshots")    # wipe in one edit
4. batch_upload_store_images("com.example.app", "en-US",
                             "phoneScreenshots",
                             [path1, path2, path3, path4])
                                                  # upload new set in one edit
```

Update just the icon:

```text
upload_store_image("com.example.app", "en-US", "icon", "/path/to/icon.png")
```
