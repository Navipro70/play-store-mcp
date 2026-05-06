# Purchases & Refunds Tools

Tools that wrap `purchases.products.*` and `orders.refund` from the
Publisher API v3. Use these for server-side purchase validation,
acknowledgement, consumption of consumable IAPs, and refunds.

These calls are **stateless** — they do not need an edit session.

## Purchase lifecycle

```
PURCHASED ──acknowledge──▶ ACKNOWLEDGED ──consume──▶ CONSUMED
                                                    (only for consumables)
```

`get_product_purchase` reports the current state via `purchase_state`,
`acknowledgement_state`, and `consumption_state`.

State codes (from Publisher API):

| Field                  | 0                    | 1                | 2         |
| ---------------------- | -------------------- | ---------------- | --------- |
| `purchase_state`       | Purchased            | Canceled         | Pending   |
| `acknowledgement_state`| Yet to be ack'd      | Acknowledged     |           |
| `consumption_state`    | Yet to be consumed   | Consumed         |           |

## ⚠️ The 3-day acknowledge window

Google **auto-refunds** any unacknowledged purchase 3 days after purchase.
If you acknowledge in the client app via BillingClient, you don't need
`acknowledge_product_purchase`. If you acknowledge server-side (e.g. after
RTDN webhook), you must call this within 3 days.

## Token masking

Purchase tokens are sensitive. Every method that takes a `token` masks it
in logs to the last 8 characters: `...{token[-8:]}`. Don't paste tokens
into chat logs or commit them.

---

### `get_product_purchase`

Read-only validation of a purchase.

```text
get_product_purchase(
    package_name="com.example.app",
    product_id="premium_unlock",
    token="<token from BillingClient>"
)
```

**Returns** dict with `success`, `purchase_state`, `acknowledgement_state`,
`consumption_state`, `order_id`, `region_code`, `purchase_time`, etc.

Use cases:

- Webhook handler validates a token before granting entitlement
- Spot-check a suspicious purchase
- Verify `region_code` matches what the user claimed

### `acknowledge_product_purchase`

Mark a purchase acknowledged. Optional `developer_payload` (≤1 KiB).

```text
acknowledge_product_purchase(
    package_name="com.example.app",
    product_id="premium_unlock",
    token="<token>",
    developer_payload="entitlement granted to user_id=12345",  # optional
)
```

### `consume_product_purchase`

For **consumable** IAPs only (coins, gems, etc.). Marks consumed so the
user can buy again. Don't call for non-consumable products — it has no
effect there.

### `refund_order`

Refund a Play Store order, optionally revoking entitlement.

```text
# normal user-requested refund — refund money, keep access
refund_order(package_name="com.example.app",
             order_id="GPA.0001-2222-3333-4444")

# policy violation — refund and yank access
refund_order(package_name="com.example.app",
             order_id="GPA.0001-2222-3333-4444",
             revoke=True)
```

`revoke` defaults to **False** so casual misuse won't strip entitlement.
Pass `revoke=True` only intentionally.

---

## Common error responses

| HTTP | Meaning                                                         |
| ---- | --------------------------------------------------------------- |
| 400  | Bad token format / mismatched `product_id`                      |
| 404  | Token not found (typo, never existed, or already consumed)      |
| 410  | Token expired or fully consumed                                 |
| 403  | Service account lacks Finance / Order management permissions    |

The tools return `{"success": False, "error": "..."}` with the API's
reason string for any of these.
