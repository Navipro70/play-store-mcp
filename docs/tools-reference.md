# Tools Reference

Complete reference for all MCP tools provided by the Play Store MCP server.

## Publishing Tools

| Tool | Description |
|---|---|
| [`deploy_app`](tools/publishing.md#deploy_app) | Deploy an APK/AAB to a track with optional staged rollout |
| [`deploy_app_multilang`](tools/publishing.md#deploy_app_multilang) | Deploy with multi-language release notes |
| [`promote_release`](tools/publishing.md#promote_release) | Promote a release between tracks |
| [`get_releases`](tools/publishing.md#get_releases) | Get release status for all tracks |
| [`halt_release`](tools/publishing.md#halt_release) | Halt a staged rollout |
| [`update_rollout`](tools/publishing.md#update_rollout) | Update rollout percentage |
| [`get_app_details`](tools/publishing.md#get_app_details) | Get app metadata |

## Store Listings Tools

| Tool | Description |
|---|---|
| [`get_listing`](tools/store-listings.md#get_listing) | Get store listing for a language |
| [`update_listing`](tools/store-listings.md#update_listing) | Update store listing text and video |
| [`list_all_listings`](tools/store-listings.md#list_all_listings) | List all store listings across languages |

## Store Images Tools

| Tool | Description |
|---|---|
| [`list_store_images`](tools/store-images.md#list_store_images) | List uploaded images of one type for a localized listing |
| [`upload_store_image`](tools/store-images.md#upload_store_image) | Upload one image asset (own edit session) |
| [`batch_upload_store_images`](tools/store-images.md#batch_upload_store_images) | Upload multiple images in a single edit session |
| [`delete_store_image`](tools/store-images.md#delete_store_image) | Delete a single image by ID |
| [`delete_all_store_images`](tools/store-images.md#delete_all_store_images) | Delete every image of a given type for a locale |
| [`validate_image_type`](tools/store-images.md#validate_image_type) | Verify an `image_type` value before calling the API |

## Review Tools

| Tool | Description |
|---|---|
| [`get_reviews`](tools/reviews.md#get_reviews) | Fetch recent reviews with optional filters |
| [`reply_to_review`](tools/reviews.md#reply_to_review) | Reply to a user review |

## Subscription Tools

| Tool | Description |
|---|---|
| [`list_subscriptions`](tools/subscriptions.md#list_subscriptions) | List subscription products |
| [`get_subscription_status`](tools/subscriptions.md#get_subscription_status) | Check subscription purchase status |
| [`list_voided_purchases`](tools/subscriptions.md#list_voided_purchases) | List voided purchases |

## Purchases & Refunds Tools

| Tool | Description |
|---|---|
| [`get_product_purchase`](tools/purchases.md#get_product_purchase) | Server-side validation of a one-time product purchase |
| [`acknowledge_product_purchase`](tools/purchases.md#acknowledge_product_purchase) | Acknowledge a purchase within 3 days |
| [`consume_product_purchase`](tools/purchases.md#consume_product_purchase) | Consume a consumable IAP |
| [`refund_order`](tools/purchases.md#refund_order) | Refund (and optionally revoke) an order |

## Edits Misc Tools

| Tool | Description |
|---|---|
| [`upload_deobfuscation_file`](tools/edits-misc.md#upload_deobfuscation_file) | Upload mapping.txt or native debug symbols for an APK/AAB version |
| [`list_bundles`](tools/edits-misc.md#list_bundles) | List uploaded AABs in a fresh edit |
| [`list_apks`](tools/edits-misc.md#list_apks) | List uploaded APKs in a fresh edit |
| [`get_country_availability`](tools/edits-misc.md#get_country_availability) | Read per-track country availability |
| [`create_custom_track`](tools/edits-misc.md#create_custom_track) | Create a closed-testing track |
| [`validate_edit`](tools/edits-misc.md#validate_edit) | Dry-run validate an existing edit |

## In-App Products Tools

| Tool | Description |
|---|---|
| [`list_in_app_products`](tools/subscriptions.md#list_in_app_products) | List all in-app products |
| [`get_in_app_product`](tools/subscriptions.md#get_in_app_product) | Get details of a specific product |

## Testers Tools

| Tool | Description |
|---|---|
| [`get_testers`](tools/testers.md#get_testers) | Get testers for a track |
| [`update_testers`](tools/testers.md#update_testers) | Update testers for a track |

## Orders & Expansion Files

| Tool | Description |
|---|---|
| [`get_order`](#get_order) | Get order/transaction details |
| [`get_expansion_file`](#get_expansion_file) | Get APK expansion file info |

## Validation Tools

| Tool | Description |
|---|---|
| [`validate_package_name`](tools/validation.md#validate_package_name) | Validate package name format |
| [`validate_track`](tools/validation.md#validate_track) | Validate track name |
| [`validate_listing_text`](tools/validation.md#validate_listing_text) | Validate store listing text lengths |

## Batch Operations Tools

| Tool | Description |
|---|---|
| [`batch_deploy`](tools/batch.md#batch_deploy) | Deploy to multiple tracks at once |

## Vitals Tools

| Tool | Description |
|---|---|
| [`get_vitals_overview`](tools/vitals.md#get_vitals_overview) | Get Android Vitals overview |
| [`get_vitals_metrics`](tools/vitals.md#get_vitals_metrics) | Get specific vitals metrics |

---

## get_order

Retrieve detailed order and transaction information for a specific order ID.

**Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `package_name` | string | Yes | App package name (e.g., `com.example.app`) |
| `order_id` | string | Yes | The order ID to look up |

## get_expansion_file

Get information about APK expansion files (main or patch) for a specific APK version.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `package_name` | string | Yes | — | App package name |
| `version_code` | integer | Yes | — | The APK version code |
| `expansion_file_type` | string | No | `main` | Type: `main` or `patch` |

> **Note:** The client manages edit sessions internally — you do not need to supply an `edit_id`.