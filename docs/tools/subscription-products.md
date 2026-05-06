# Subscription Products (Modern Monetization API)

Tools that wrap `monetization.subscriptions.*` and its nested
`basePlans` / `offers` resources. This is the **product configuration** API
— for runtime queries about a specific user's subscription state, use
`get_subscription_status` (powered by `purchases.subscriptionsv2`).

## Architecture

A Google Play subscription product has **3 levels**:

```
Subscription (productId)
├── BasePlan A (e.g. monthly auto-renewing, P1M)
│   ├── Offer 1 (e.g. 7-day free trial)
│   └── Offer 2 (e.g. 50% off first 3 months)
└── BasePlan B (e.g. yearly auto-renewing, P1Y)
    └── Offer 3 (e.g. 20% off first year)
```

- **Subscription** — the product as users perceive it (one product ID,
  shared listings).
- **BasePlan** — pricing tier and billing period. A subscription can have
  multiple base plans (monthly + yearly). Identified by `basePlanId`.
- **Offer** — promotional pricing attached to a base plan. 1-2 phases each
  (e.g. "free for 7 days, then 50% off for 3 months").

## ISO 8601 billing periods

`billing_period_duration` must be ISO 8601, e.g. `P1W`, `P1M`, `P3M`,
`P6M`, `P1Y`. The validator rejects malformed strings like `monthly` or
`1month`. Common valid values:

| Period      | ISO 8601 |
| ----------- | -------- |
| 1 week      | `P1W`    |
| 1 month     | `P1M`    |
| 3 months    | `P3M`    |
| 6 months    | `P6M`    |
| 1 year      | `P1Y`    |

## Auto-renewing vs prepaid

`add_base_plan(auto_renewing=True)` sets `autoRenewingBasePlanType`
(default). `auto_renewing=False` sets `prepaidBasePlanType` — users buy a
fixed-duration grant and must manually top up to extend.

## Typical lifecycle

```text
1. create_subscription_product(product_id="premium",
                               listings=[{...}])
2. add_base_plan(product_id="premium", base_plan_id="monthly",
                 billing_period_duration="P1M",
                 regional_configs=[{"regionCode": "US",
                                    "price": {...}}])
3. activate_base_plan(product_id, base_plan_id="monthly")
4. create_subscription_offer(product_id, base_plan_id, offer_id="trial",
                             phases=[{"duration": "P7D",
                                      "recurrenceCount": 1,
                                      "regionalConfigs": [...]}],
                             regional_configs=[...])
5. activate_subscription_offer(...)
```

To shut a subscription down without deleting:

```text
deactivate_subscription_offer(...)
deactivate_base_plan(...)
archive_subscription_product(...)
```

## ID format constraints

- `product_id`: 1-40 chars, `[a-z0-9_.]` starting with `[a-z0-9]`
- `base_plan_id`: ≤63 chars, `[a-z0-9-]` starting with `[a-z0-9]`
- `offer_id`: ≤63 chars, `[a-z0-9-]` starting with `[a-z0-9]`

The validators reject violations before any API call. Run
`get_subscription_product(...)` first if you don't remember the IDs.

## Regional pricing

Unlike `create_onetime_product`, the subscription tools **do not**
auto-convert from a single USD price. You provide `regional_configs`
directly — list of dicts matching Google's `RegionalBasePlanConfig` /
`RegionalSubscriptionOfferConfig` schemas. Use
`monetization.convertRegionPrices` if you want to derive them; the helper
exists in `client.py` (`_convert_region_prices`).

## migrate_base_plan_prices

Use sparingly. This is the API path for the "increase prices for existing
subscribers with notice" workflow. Each entry in
`regional_price_migrations` is a `RegionalPriceMigrationConfig` dict —
fields like `regionCode`, `oldestAllowedPriceVersionTime`,
`priceIncreaseType`. See Google's
[Help Center on price changes](https://support.google.com/googleplay/android-developer/answer/13064252).
