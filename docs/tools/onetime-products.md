# One-Time Products (Monetization API)

Tools that wrap `monetization.onetimeproducts.*` — the **modern** one-time
IAP API. This replaces the legacy `inappproducts.*` resource. Use these
for any new IAP work; only fall back to `list_in_app_products` /
`get_in_app_product` for inspecting non-migrated legacy products.

## Modern vs legacy

| | Legacy (`inappproducts`) | Modern (`monetization.onetimeproducts`) |
|---|---|---|
| Resource | `inappproducts` | `oneTimeProducts` |
| Pricing | Single `defaultPrice` + per-region overrides | `purchaseOptions[].regionalPricingAndAvailabilityConfigs[]` |
| Listings | `listings: dict[lang -> {title, description}]` | `listings: list[{languageCode, title, description}]` |
| State machine | `status: active/inactive` | `purchaseOptions[].state: DRAFT / ACTIVE / INACTIVE` |
| Legacy compat | n/a | `buyOption.legacyCompatible` per option |

You can keep using legacy products that already exist; new products
should be created via this group.

## How `create_onetime_product` builds regional prices

It takes a single `price_micros` (USD) and calls
`monetization.convertRegionPrices` to fan it out into ~150 regional
prices in local currencies. The returned `regionsVersion.version` is then
appended to the PATCH URL because google-api-python-client cannot pass
parameter names containing dots — see `_patch_with_regions_version` in
`client.py`.

So a single call to `create_onetime_product` results in two API
round-trips: one `POST .../pricing:convertRegionPrices`, one
`PATCH .../onetimeproducts/{productId}` with `allowMissing=True` and
`updateMask=listings,purchaseOptions`.

## UPSERT vs create + update

The Publisher API's PATCH-with-`allowMissing=True` is an UPSERT — the
same call creates a new product or updates an existing one. We expose
both `create_onetime_product` and `update_onetime_product` for clarity in
your scripts; both route through `client.upsert_onetime_product` with
different `operation` labels in the result.

---

### `list_onetime_products`

Read all one-time products on the app.

### `get_onetime_product`

Get one product by ID.

### `create_onetime_product` / `update_onetime_product`

```text
create_onetime_product(
    package_name="com.example.app",
    product_id="premium_unlock",
    listings=[
        {"language_code": "en-US",
         "title": "Premium Unlock",
         "description": "Unlock all premium features."},
        {"language_code": "ko-KR",
         "title": "프리미엄 잠금 해제",
         "description": "모든 프리미엄 기능을 잠금 해제합니다."},
    ],
    price_micros=9_990_000,            # $9.99
    purchase_option_id="default",      # lowercase, [a-z0-9-], ≤63 chars
    legacy_compatible=True,            # default — legacy clients can buy it
)
```

Constraints (enforced by the API):

- `title` ≤ 55 chars, `description` ≤ 200 chars per listing
- `purchase_option_id` regex: `^[a-z0-9][a-z0-9\-]{0,62}$`
- At least one listing required

### `delete_onetime_product`

DELETEs the product. Will fail (HTTP 4xx) if there are active orders or
entitlements depending on it.

### `activate_onetime_product` / `deactivate_onetime_product`

Toggle a single purchase option's state via
`purchaseOptions.batchUpdateStates`. Activation is required after creation
— newly created products are in DRAFT.

```text
activate_onetime_product(
    package_name="com.example.app",
    product_id="premium_unlock",
    purchase_option_id="default",
)
```

### `batch_create_onetime_products`

Loop helper — same as creating each one individually. Each entry runs its
own `convertRegionPrices` + PATCH. Per-item failures don't stop the
others; the result has `successful_count` / `failed_count`.

```text
batch_create_onetime_products(
    package_name="com.example.app",
    products=[
        {
            "product_id": "premium",
            "listings": [{"language_code": "en-US",
                          "title": "Premium",
                          "description": "..."}],
            "price_micros": 9_990_000,
        },
        {
            "product_id": "coins_100",
            "listings": [...],
            "price_micros": 990_000,
        },
    ],
)
```

## Typical full lifecycle

```text
1. create_onetime_product(...)                # creates in DRAFT state
2. activate_onetime_product(product_id, ...)  # flip to ACTIVE
3. # ... users buy it via BillingClient ...
4. update_onetime_product(price_micros=...)   # change price
5. deactivate_onetime_product(...)            # stop sales
6. delete_onetime_product(...)                # only when no entitlements
```
