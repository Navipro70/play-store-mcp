"""Pydantic models for Play Store MCP Server."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - Pydantic needs this at runtime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Release(BaseModel):
    """Represents an app release on a track."""

    package_name: str = Field(..., description="App package name")
    track: str = Field(..., description="Release track")
    status: str = Field(..., description="Release status")
    version_codes: list[int] = Field(default_factory=list, description="Version codes in release")
    version_name: str | None = Field(None, description="Version name")
    rollout_percentage: float = Field(100.0, description="Rollout percentage (0-100)")
    release_notes: dict[str, str] = Field(
        default_factory=dict, description="Release notes by language"
    )


class TrackInfo(BaseModel):
    """Information about a release track."""

    track: str = Field(..., description="Track name")
    releases: list[Release] = Field(default_factory=list, description="Releases on this track")


class DeploymentResult(BaseModel):
    """Result of a deployment operation."""

    success: bool = Field(..., description="Whether deployment succeeded")
    edit_id: str | None = Field(None, description="Edit ID for the operation")
    package_name: str = Field(..., description="App package name")
    track: str = Field(..., description="Target track")
    version_code: int | None = Field(None, description="Deployed version code")
    message: str = Field(..., description="Status message")
    error: str | None = Field(None, description="Error details if failed")


class AppDetails(BaseModel):
    """Detailed app information."""

    package_name: str = Field(..., description="App package name")
    title: str | None = Field(None, description="App title")
    short_description: str | None = Field(None, description="Short description")
    full_description: str | None = Field(None, description="Full description")
    default_language: str | None = Field(None, description="Default language")
    developer_name: str | None = Field(None, description="Developer name")
    developer_email: str | None = Field(None, description="Developer email")
    developer_website: str | None = Field(None, description="Developer website")


class Review(BaseModel):
    """User review."""

    review_id: str = Field(..., description="Review ID")
    author_name: str = Field(..., description="Author name")
    star_rating: int = Field(..., description="Star rating (1-5)")
    comment: str = Field(..., description="Review comment")
    language: str = Field(..., description="Review language")
    device: str | None = Field(None, description="Device name")
    android_version: str | None = Field(None, description="Android OS version")
    app_version_code: int | None = Field(None, description="App version code")
    app_version_name: str | None = Field(None, description="App version name")
    last_modified: datetime | None = Field(None, description="Last modification time")
    developer_reply: str | None = Field(None, description="Developer reply if present")
    developer_reply_time: datetime | None = Field(None, description="Reply time")


class ReviewReplyResult(BaseModel):
    """Result of replying to a review."""

    success: bool = Field(..., description="Whether reply succeeded")
    review_id: str = Field(..., description="Review ID")
    message: str = Field(..., description="Status message")
    error: str | None = Field(None, description="Error details if failed")


class SubscriptionProduct(BaseModel):
    """Subscription product definition."""

    product_id: str = Field(..., description="Subscription product ID")
    package_name: str = Field(..., description="App package name")
    status: str | None = Field(None, description="Subscription status")
    base_plans: list[dict[str, Any]] = Field(
        default_factory=list, description="Base plan definitions"
    )


class SubscriptionPurchase(BaseModel):
    """Subscription purchase status."""

    package_name: str = Field(..., description="App package name")
    subscription_id: str = Field(..., description="Subscription product ID")
    purchase_token: str = Field(..., description="Purchase token")
    order_id: str | None = Field(None, description="Order ID")
    start_time: datetime | None = Field(None, description="Subscription start time")
    expiry_time: datetime | None = Field(None, description="Subscription expiry time")
    auto_renewing: bool = Field(False, description="Whether auto-renewing")
    cancel_reason: int | None = Field(None, description="Cancellation reason code")
    payment_state: int | None = Field(None, description="Payment state code")
    price_currency: str | None = Field(None, description="Price currency code")
    price_amount_micros: int | None = Field(None, description="Price amount in micros")


class VoidedPurchase(BaseModel):
    """Voided purchase record."""

    package_name: str = Field(..., description="App package name")
    purchase_token: str = Field(..., description="Original purchase token")
    order_id: str | None = Field(None, description="Order ID")
    voided_time: datetime | None = Field(None, description="Time of voiding")
    voided_reason: int | None = Field(None, description="Reason for voiding")
    voided_source: int | None = Field(None, description="Source of voiding")


class VitalsOverview(BaseModel):
    """Android Vitals overview metrics."""

    package_name: str = Field(..., description="App package name")
    crash_rate: float | None = Field(None, description="User-perceived crash rate")
    anr_rate: float | None = Field(None, description="User-perceived ANR rate")
    excessive_wakeups: float | None = Field(None, description="Excessive wakeups rate")
    stuck_wake_locks: float | None = Field(None, description="Stuck wake locks rate")
    freshness_info: str | None = Field(None, description="Data freshness information")


class VitalsMetric(BaseModel):
    """Specific vitals metric data."""

    metric_type: str = Field(..., description="Type of metric")
    value: float | None = Field(None, description="Metric value")
    benchmark: float | None = Field(None, description="Benchmark threshold")
    is_below_threshold: bool | None = Field(None, description="Whether below bad threshold")
    dimension: str | None = Field(None, description="Dimension (e.g., device, version)")
    dimension_value: str | None = Field(None, description="Dimension value")


class InAppProduct(BaseModel):
    """In-app product definition."""

    sku: str = Field(..., description="Product SKU")
    package_name: str = Field(..., description="App package name")
    product_type: str = Field(..., description="Product type (managed_product or subscription)")
    status: str | None = Field(None, description="Product status")
    default_language: str | None = Field(None, description="Default language")
    title: str | None = Field(None, description="Product title")
    description: str | None = Field(None, description="Product description")
    default_price: dict[str, Any] | None = Field(None, description="Default price information")


class Listing(BaseModel):
    """Store listing for a specific language."""

    language: str = Field(..., description="Language code (e.g., en-US)")
    title: str | None = Field(None, description="App title")
    full_description: str | None = Field(None, description="Full description")
    short_description: str | None = Field(None, description="Short description")
    video: str | None = Field(None, description="YouTube video URL")


class ListingUpdateResult(BaseModel):
    """Result of updating a store listing."""

    success: bool = Field(..., description="Whether update succeeded")
    package_name: str = Field(..., description="App package name")
    language: str = Field(..., description="Language code")
    message: str = Field(..., description="Status message")
    error: str | None = Field(None, description="Error details if failed")


class TesterInfo(BaseModel):
    """Information about testers for a track."""

    track: str = Field(..., description="Track name")
    google_groups: list[str] = Field(
        default_factory=list, description="List of Google Group email addresses"
    )


class Order(BaseModel):
    """Order/transaction information."""

    order_id: str = Field(..., description="Order ID")
    package_name: str = Field(..., description="App package name")
    product_id: str | None = Field(None, description="Product ID")
    purchase_time: datetime | None = Field(None, description="Purchase timestamp")
    purchase_state: int | None = Field(None, description="Purchase state")
    purchase_token: str | None = Field(None, description="Purchase token")
    quantity: int | None = Field(None, description="Quantity purchased")


class ExpansionFile(BaseModel):
    """APK expansion file information."""

    version_code: int = Field(..., description="Version code")
    expansion_file_type: str = Field(..., description="Expansion file type (main or patch)")
    file_size: int | None = Field(None, description="File size in bytes")
    references_version: int | None = Field(None, description="Referenced version code")


class BatchDeploymentResult(BaseModel):
    """Result of batch deployment to multiple tracks."""

    success: bool = Field(..., description="Whether all deployments succeeded")
    results: list[DeploymentResult] = Field(
        default_factory=list, description="Individual deployment results"
    )
    successful_count: int = Field(0, description="Number of successful deployments")
    failed_count: int = Field(0, description="Number of failed deployments")
    message: str = Field(..., description="Overall status message")


class ValidationResult(BaseModel):
    """Validation result details."""

    field: str = Field(..., description="Field that failed validation")
    message: str = Field(..., description="Error message")
    value: Any | None = Field(None, description="Invalid value")


class ImageType(StrEnum):
    """Image asset types for store listings (Publisher API v3)."""

    PHONE_SCREENSHOTS = "phoneScreenshots"
    SEVEN_INCH_SCREENSHOTS = "sevenInchScreenshots"
    TEN_INCH_SCREENSHOTS = "tenInchScreenshots"
    TV_SCREENSHOTS = "tvScreenshots"
    WEAR_SCREENSHOTS = "wearScreenshots"
    ICON = "icon"
    FEATURE_GRAPHIC = "featureGraphic"
    TV_BANNER = "tvBanner"


class StoreImage(BaseModel):
    """Image asset on a localized store listing."""

    id: str = Field(..., description="Unique image ID")
    url: str = Field(..., description="Preview URL")
    sha1: str | None = Field(None, description="SHA-1 hash")
    sha256: str | None = Field(None, description="SHA-256 hash")


class StoreImageUploadResult(BaseModel):
    """Result of uploading a single store image."""

    success: bool = Field(..., description="Whether upload succeeded")
    package_name: str = Field(..., description="App package name")
    language: str = Field(..., description="Locale tag")
    image_type: str = Field(..., description="Image type")
    image: StoreImage | None = Field(None, description="Uploaded image (if success)")
    message: str = Field(..., description="Status message")
    error: str | None = Field(None, description="Error details if failed")


class StoreImageDeleteResult(BaseModel):
    """Result of deleting one or all images of a type for a locale."""

    success: bool = Field(..., description="Whether delete succeeded")
    package_name: str = Field(..., description="App package name")
    language: str = Field(..., description="Locale tag")
    image_type: str = Field(..., description="Image type")
    image_id: str | None = Field(None, description="ID of single deleted image, if any")
    deleted_count: int | None = Field(None, description="Number of images deleted (deleteall)")
    message: str = Field(..., description="Status message")
    error: str | None = Field(None, description="Error details if failed")


class BatchImageUploadResult(BaseModel):
    """Result of batch uploading multiple images in one edit session."""

    success: bool = Field(..., description="Whether all uploads succeeded")
    package_name: str = Field(..., description="App package name")
    language: str = Field(..., description="Locale tag")
    image_type: str = Field(..., description="Image type")
    uploaded: list[StoreImage] = Field(
        default_factory=list, description="Successfully uploaded images"
    )
    successful_count: int = Field(0, description="Number of successful uploads")
    failed_count: int = Field(0, description="Number of failed uploads")
    message: str = Field(..., description="Overall status message")
    error: str | None = Field(None, description="Error details if any")


class ProductPurchase(BaseModel):
    """Server-side view of a one-time product purchase."""

    package_name: str = Field(..., description="App package name")
    product_id: str = Field(..., description="Product SKU")
    purchase_token: str = Field(..., description="Purchase token (masked when logged)")
    purchase_state: int | None = Field(None, description="0=Purchased, 1=Canceled, 2=Pending")
    consumption_state: int | None = Field(None, description="0=YetToBeConsumed, 1=Consumed")
    purchase_time: datetime | None = Field(None, description="Purchase timestamp")
    order_id: str | None = Field(None, description="Order ID")
    acknowledgement_state: int | None = Field(
        None, description="0=YetToBeAcknowledged, 1=Acknowledged"
    )
    region_code: str | None = Field(None, description="ISO 3166-1 alpha-2 region")
    purchase_type: int | None = Field(
        None, description="0=Test, 1=Promo, 2=Rewarded (absent on real purchases)"
    )
    quantity: int | None = Field(None, description="Quantity purchased")


class PurchaseAckResult(BaseModel):
    """Result of acknowledging or consuming a product purchase."""

    success: bool = Field(..., description="Whether the operation succeeded")
    package_name: str = Field(..., description="App package name")
    product_id: str = Field(..., description="Product SKU")
    operation: str = Field(..., description="acknowledge or consume")
    message: str = Field(..., description="Status message")
    error: str | None = Field(None, description="Error details if failed")


class RefundResult(BaseModel):
    """Result of refunding (and optionally revoking) an order."""

    success: bool = Field(..., description="Whether refund succeeded")
    package_name: str = Field(..., description="App package name")
    order_id: str = Field(..., description="Order ID")
    revoked: bool = Field(False, description="Whether access was revoked")
    message: str = Field(..., description="Status message")
    error: str | None = Field(None, description="Error details if failed")


class Bundle(BaseModel):
    """Android App Bundle (AAB) artifact in an edit."""

    version_code: int = Field(..., description="Version code")
    sha1: str | None = Field(None, description="SHA-1 hash")
    sha256: str | None = Field(None, description="SHA-256 hash")


class Apk(BaseModel):
    """APK artifact in an edit."""

    version_code: int = Field(..., description="Version code")
    sha1: str | None = Field(None, description="SHA-1 hash")
    sha256: str | None = Field(None, description="SHA-256 hash")


class CountryAvailability(BaseModel):
    """Country/region availability for a track."""

    track: str = Field(..., description="Track name")
    rest_of_world: bool = Field(False, description="Whether available in 'rest of world'")
    sync_with_production: bool = Field(
        False, description="Whether to sync the track's countries with production"
    )
    countries: list[str] = Field(
        default_factory=list, description="ISO 3166-1 alpha-2 country codes"
    )


class DeobfuscationResult(BaseModel):
    """Result of uploading a deobfuscation file (mapping.txt or native debug symbols)."""

    success: bool = Field(..., description="Whether upload succeeded")
    package_name: str = Field(..., description="App package name")
    version_code: int = Field(..., description="APK version code")
    file_type: str = Field(..., description="proguard or nativeCode")
    sha256: str | None = Field(None, description="SHA-256 hash of uploaded file")
    message: str = Field(..., description="Status message")
    error: str | None = Field(None, description="Error details if failed")


class CustomTrackResult(BaseModel):
    """Result of creating a custom (closed-testing) track."""

    success: bool = Field(..., description="Whether track creation succeeded")
    package_name: str = Field(..., description="App package name")
    track: str = Field(..., description="Track name")
    message: str = Field(..., description="Status message")
    error: str | None = Field(None, description="Error details if failed")


class EditValidationResult(BaseModel):
    """Result of dry-running edit validation (edits.validate)."""

    success: bool = Field(..., description="Whether validate call succeeded")
    package_name: str = Field(..., description="App package name")
    edit_id: str = Field(..., description="Edit ID validated")
    valid: bool = Field(..., description="Whether the edit passes validation")
    message: str = Field(..., description="Status message")
    error: str | None = Field(None, description="Error details if failed")


class ProductLocalization(BaseModel):
    """Localized title/description for a monetization product."""

    language_code: str = Field(..., description="BCP-47 locale tag")
    title: str = Field(..., description="Localized title")
    description: str = Field(..., description="Localized description")


class RegionalPrice(BaseModel):
    """Regional price for a one-time product purchase option."""

    region_code: str = Field(..., description="ISO 3166-1 alpha-2 region code")
    currency_code: str = Field(..., description="ISO 4217 currency")
    units: str = Field(..., description="Whole-currency units as a string (e.g. '9')")
    nanos: int = Field(0, description="Nanos part (1e-9 of a unit)")


class PurchaseOption(BaseModel):
    """A pricing option attached to a one-time product."""

    purchase_option_id: str = Field(..., description="Purchase option ID")
    state: str = Field(..., description="DRAFT, ACTIVE, or INACTIVE")
    regional_prices: list[RegionalPrice] = Field(
        default_factory=list, description="Regional prices"
    )
    legacy_compatible: bool = Field(
        False, description="Whether legacy IAP clients can resolve this option"
    )


class OnetimeProduct(BaseModel):
    """One-time product (modern monetization API, replaces inappproducts)."""

    package_name: str = Field(..., description="App package name")
    product_id: str = Field(..., description="Product ID")
    listings: list[ProductLocalization] = Field(
        default_factory=list, description="Localized listings"
    )
    purchase_options: list[PurchaseOption] = Field(
        default_factory=list, description="Purchase options"
    )
    tax_and_compliance_settings: dict[str, Any] | None = Field(
        None, description="Tax/compliance settings as raw API dict"
    )


class OnetimeProductMutationResult(BaseModel):
    """Result of mutating a one-time product (create/update/delete/activate)."""

    success: bool = Field(..., description="Whether the operation succeeded")
    package_name: str = Field(..., description="App package name")
    product_id: str = Field(..., description="Product ID")
    operation: str = Field(..., description="create_or_update, delete, activate, deactivate")
    product: OnetimeProduct | None = Field(
        None, description="Resulting product on create/update success"
    )
    message: str = Field(..., description="Status message")
    error: str | None = Field(None, description="Error details if failed")


class BasePlan(BaseModel):
    """Base plan within a subscription product."""

    base_plan_id: str = Field(..., description="Base plan ID")
    state: str = Field(..., description="DRAFT, ACTIVE, or INACTIVE")
    auto_renewing: bool = Field(False, description="Whether this is an auto-renewing plan")
    billing_period_duration: str | None = Field(
        None, description="ISO 8601 duration, e.g. P1M, P1Y, P7D"
    )
    regional_configs: list[dict[str, Any]] = Field(
        default_factory=list, description="Raw regional configs from API"
    )
    other_regions_config: dict[str, Any] | None = Field(
        None, description="Fallback config for unconfigured regions"
    )


class OfferPhase(BaseModel):
    """A phase within a subscription offer (intro, trial, etc.)."""

    duration: str = Field(..., description="ISO 8601 duration")
    recurrence_count: int = Field(1, description="How many billing cycles this phase lasts")
    free: bool = Field(False, description="Whether this phase is free (trial)")
    discount_percentage: int | None = Field(None, description="Discount % vs base price")
    regional_configs: list[dict[str, Any]] = Field(
        default_factory=list, description="Per-region pricing for this phase"
    )


class SubscriptionOffer(BaseModel):
    """A subscription offer attached to a base plan."""

    package_name: str = Field(..., description="App package name")
    product_id: str = Field(..., description="Subscription product ID")
    base_plan_id: str = Field(..., description="Base plan ID")
    offer_id: str = Field(..., description="Offer ID")
    state: str = Field(..., description="DRAFT, ACTIVE, or INACTIVE")
    phases: list[OfferPhase] = Field(default_factory=list, description="Offer phases")
    targeting: dict[str, Any] | None = Field(
        None, description="Eligibility targeting (raw API dict)"
    )


class Subscription(BaseModel):
    """Subscription product (monetization v2)."""

    package_name: str = Field(..., description="App package name")
    product_id: str = Field(..., description="Subscription product ID")
    archived: bool = Field(False, description="Whether the product is archived")
    listings: list[ProductLocalization] = Field(
        default_factory=list, description="Localized listings"
    )
    base_plans: list[BasePlan] = Field(default_factory=list, description="Base plans")
    tax_and_compliance_settings: dict[str, Any] | None = Field(
        None, description="Tax/compliance settings"
    )


class SubscriptionMutationResult(BaseModel):
    """Result of mutating a subscription, base plan, or offer."""

    success: bool = Field(..., description="Whether the operation succeeded")
    package_name: str = Field(..., description="App package name")
    product_id: str = Field(..., description="Subscription product ID")
    base_plan_id: str | None = Field(None, description="Base plan ID, if relevant")
    offer_id: str | None = Field(None, description="Offer ID, if relevant")
    operation: str = Field(..., description="Operation name")
    subscription: Subscription | None = Field(None, description="Result subscription")
    offer: SubscriptionOffer | None = Field(None, description="Result offer")
    message: str = Field(..., description="Status message")
    error: str | None = Field(None, description="Error details if failed")
