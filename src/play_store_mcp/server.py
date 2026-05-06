"""Play Store MCP Server - Main server implementation."""

from __future__ import annotations

import argparse
import base64
import binascii
import ipaddress
import json
import logging
import os
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from play_store_mcp.client import PlayStoreClient, PlayStoreClientError
from play_store_mcp.models import ImageType

# Configure structured logging to stderr (stdout is reserved for MCP JSON-RPC)
log_level = os.environ.get("PLAY_STORE_MCP_LOG_LEVEL", "INFO")
numeric_level = getattr(logging, log_level.upper(), logging.INFO)
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)
logger = structlog.get_logger(__name__)


def get_client_from_context() -> PlayStoreClient:
    """Get PlayStoreClient from request context.

    Checks for credentials in request headers first (X-Google-Credentials or
    X-Google-Credentials-Base64), then falls back to the shared client from
    lifespan context.

    Returns:
        PlayStoreClient instance

    Raises:
        PlayStoreClientError: If credentials are invalid or client cannot be created
    """
    ctx = mcp.get_context()

    # Check for per-request credentials in headers
    if hasattr(ctx, "request_context") and hasattr(ctx.request_context, "request"):
        request = ctx.request_context.request
        if request is not None and hasattr(request, "headers"):
            headers = request.headers

            # Try X-Google-Credentials header (JSON string or object)
            if "x-google-credentials" in headers:
                creds_str = headers["x-google-credentials"]
                try:
                    creds_json = json.loads(creds_str)
                    return PlayStoreClient(credentials_json=creds_json)
                except json.JSONDecodeError as e:
                    raise PlayStoreClientError(f"Invalid JSON in X-Google-Credentials header: {e}")

            # Try X-Google-Credentials-Base64 header
            if "x-google-credentials-base64" in headers:
                creds_b64 = headers["x-google-credentials-base64"]
                try:
                    creds_bytes = base64.b64decode(creds_b64)
                    creds_str = creds_bytes.decode("utf-8")
                    creds_json = json.loads(creds_str)
                    return PlayStoreClient(credentials_json=creds_json)
                except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as e:
                    raise PlayStoreClientError(
                        f"Invalid base64 or JSON in X-Google-Credentials-Base64 header: {e}"
                    )

    # Fall back to shared client from lifespan
    if hasattr(ctx, "request_context") and hasattr(ctx.request_context, "lifespan_context"):
        client: PlayStoreClient | None = ctx.request_context.lifespan_context.get("client")
        if client is not None:
            return client

    raise PlayStoreClientError(
        "No credentials provided. Set X-Google-Credentials or X-Google-Credentials-Base64 header, "
        "or configure server with GOOGLE_PLAY_STORE_CREDENTIALS environment variable."
    )


@asynccontextmanager
async def lifespan(_server: FastMCP):  # type: ignore[no-untyped-def]
    """Lifespan context manager for the MCP server.

    Initializes the PlayStoreClient and makes it available via server context.
    """
    logger.info("Initializing Play Store MCP Server")

    # Create a shared state dict that will be accessible from custom routes
    shared_state: dict[str, Any] = {"client": None, "credentials_updated": False}

    try:
        client = PlayStoreClient()
        # Validate credentials on startup
        _ = client._get_service()
        logger.info("Play Store client initialized successfully")
        shared_state["client"] = client
    except PlayStoreClientError as e:
        logger.warning("Play Store client initialization failed", error=str(e))
        shared_state["client"] = None

    # Store shared state in the server instance for access from custom routes
    _server._shared_state = shared_state  # type: ignore[attr-defined]

    yield shared_state

    logger.info("Shutting down Play Store MCP Server")


def _validate_deploy_file(file_path: str) -> str | None:
    """Return error message if file_path is invalid, None if valid."""
    resolved = os.path.realpath(file_path)
    if not resolved.lower().endswith((".apk", ".aab")):
        return "file_path must be a .apk or .aab file"
    if not Path(resolved).is_file():
        return f"File not found: {resolved}"
    return None


def _validate_rollout(pct: float) -> str | None:
    """Return error message if rollout percentage is invalid, None if valid."""
    if not (0.0 <= pct <= 100.0):
        return "rollout_percentage must be between 0.0 and 100.0"
    return None


# Initialize the MCP server
mcp = FastMCP(
    "Play Store MCP Server",
    lifespan=lifespan,
    transport_security=TransportSecuritySettings(),
)


# =============================================================================
# Publishing Tools
# =============================================================================


@mcp.tool()
def deploy_app(
    package_name: str,
    track: str,
    file_path: str,
    release_notes: str | None = None,
    release_notes_language: str = "en-US",
    rollout_percentage: float = 100.0,
) -> dict[str, Any]:
    """Deploy an APK or AAB file to a Play Store track.

    Args:
        package_name: App package name (e.g., com.example.myapp)
        track: Release track - one of: internal, alpha, beta, production
        file_path: Absolute path to APK or AAB file
        release_notes: Optional release notes for this version (string for single language,
                      or use release_notes_multilang for multiple languages)
        release_notes_language: Language code for release notes (default: en-US)
        rollout_percentage: Rollout percentage (0-100). Default 100 for full rollout.

    Returns:
        Deployment result with success status and details
    """
    if err := _validate_deploy_file(file_path):
        return {"error": err}
    if err := _validate_rollout(rollout_percentage):
        return {"error": err}

    client = get_client_from_context()

    result = client.deploy_app(
        package_name=package_name,
        track=track,
        file_path=file_path,
        release_notes=release_notes,
        release_notes_language=release_notes_language,
        rollout_percentage=rollout_percentage,
    )

    return result.model_dump()


@mcp.tool()
def deploy_app_multilang(
    package_name: str,
    track: str,
    file_path: str,
    release_notes: dict[str, str],
    rollout_percentage: float = 100.0,
) -> dict[str, Any]:
    """Deploy an APK or AAB file with multi-language release notes.

    Args:
        package_name: App package name (e.g., com.example.myapp)
        track: Release track - one of: internal, alpha, beta, production
        file_path: Absolute path to APK or AAB file
        release_notes: Dictionary mapping language codes to release notes
                      (e.g., {"en-US": "Bug fixes", "es-ES": "Corrección de errores"})
        rollout_percentage: Rollout percentage (0-100). Default 100 for full rollout.

    Returns:
        Deployment result with success status and details
    """
    if err := _validate_deploy_file(file_path):
        return {"error": err}
    if err := _validate_rollout(rollout_percentage):
        return {"error": err}

    client = get_client_from_context()

    result = client.deploy_app(
        package_name=package_name,
        track=track,
        file_path=file_path,
        release_notes=release_notes,
        rollout_percentage=rollout_percentage,
    )

    return result.model_dump()


@mcp.tool()
def promote_release(
    package_name: str,
    from_track: str,
    to_track: str,
    version_code: int,
    rollout_percentage: float = 100.0,
) -> dict[str, Any]:
    """Promote a release from one track to another.

    Args:
        package_name: App package name
        from_track: Source track (internal, alpha, beta)
        to_track: Destination track (alpha, beta, production)
        version_code: Version code to promote
        rollout_percentage: Rollout percentage for target track (0-100)

    Returns:
        Promotion result with success status and details
    """
    if err := _validate_rollout(rollout_percentage):
        return {"error": err}

    client = get_client_from_context()

    result = client.promote_release(
        package_name=package_name,
        from_track=from_track,
        to_track=to_track,
        version_code=version_code,
        rollout_percentage=rollout_percentage,
    )

    return result.model_dump()


@mcp.tool()
def get_releases(package_name: str) -> list[dict[str, Any]]:
    """Get release status for all tracks of an app.

    Args:
        package_name: App package name

    Returns:
        List of tracks with their releases and version information
    """
    client = get_client_from_context()

    tracks = client.get_releases(package_name)
    return [track.model_dump() for track in tracks]


@mcp.tool()
def halt_release(
    package_name: str,
    track: str,
    version_code: int,
) -> dict[str, Any]:
    """Halt a staged rollout.

    Use this to stop a release that is currently rolling out.
    The release will be marked as halted and users will stop receiving updates.

    Args:
        package_name: App package name
        track: Track containing the release (internal, alpha, beta, production)
        version_code: Version code of the release to halt

    Returns:
        Result with success status and details
    """
    client = get_client_from_context()

    result = client.halt_release(
        package_name=package_name,
        track=track,
        version_code=version_code,
    )

    return result.model_dump()


@mcp.tool()
def update_rollout(
    package_name: str,
    track: str,
    version_code: int,
    rollout_percentage: float,
) -> dict[str, Any]:
    """Update the rollout percentage for a staged release.

    Use this to increase or decrease the percentage of users receiving an update.
    Set to 100 to complete the rollout.

    Args:
        package_name: App package name
        track: Track containing the release
        version_code: Version code of the staged release
        rollout_percentage: New rollout percentage (0-100)

    Returns:
        Result with success status and details
    """
    if err := _validate_rollout(rollout_percentage):
        return {"error": err}

    client = get_client_from_context()

    result = client.update_rollout(
        package_name=package_name,
        track=track,
        version_code=version_code,
        rollout_percentage=rollout_percentage,
    )

    return result.model_dump()


@mcp.tool()
def get_app_details(
    package_name: str,
    language: str = "en-US",
) -> dict[str, Any]:
    """Get app details including title, description, and developer info.

    Args:
        package_name: App package name
        language: Language code for localized content (default: en-US)

    Returns:
        App details including title, descriptions, and developer information
    """
    client = get_client_from_context()

    details = client.get_app_details(package_name, language)
    return details.model_dump()


# =============================================================================
# Reviews Tools
# =============================================================================


@mcp.tool()
def get_reviews(
    package_name: str,
    max_results: int = 50,
    translation_language: str | None = None,
) -> list[dict[str, Any]]:
    """Get recent reviews for an app.

    Args:
        package_name: App package name
        max_results: Maximum number of reviews to return (default: 50, max: 100)
        translation_language: Optional language code to translate reviews to

    Returns:
        List of reviews with ratings, comments, and author info
    """
    client = get_client_from_context()

    reviews = client.get_reviews(
        package_name=package_name,
        max_results=min(max_results, 100),
        translation_language=translation_language,
    )

    return [review.model_dump() for review in reviews]


@mcp.tool()
def reply_to_review(
    package_name: str,
    review_id: str,
    reply_text: str,
) -> dict[str, Any]:
    """Reply to a user review.

    Args:
        package_name: App package name
        review_id: ID of the review to reply to (from get_reviews)
        reply_text: Text of the reply (will be visible to the reviewer)

    Returns:
        Result with success status
    """
    client = get_client_from_context()

    result = client.reply_to_review(
        package_name=package_name,
        review_id=review_id,
        reply_text=reply_text,
    )

    return result.model_dump()


# =============================================================================
# Subscription Tools
# =============================================================================


@mcp.tool()
def list_subscriptions(package_name: str) -> list[dict[str, Any]]:
    """List all subscription products for an app.

    Args:
        package_name: App package name

    Returns:
        List of subscription products with their base plans
    """
    client = get_client_from_context()

    subscriptions = client.list_subscriptions(package_name)
    return [sub.model_dump() for sub in subscriptions]


@mcp.tool()
def get_subscription_status(
    package_name: str,
    subscription_id: str,
    purchase_token: str,
) -> dict[str, Any]:
    """Get the status of a subscription purchase.

    Args:
        package_name: App package name
        subscription_id: Subscription product ID
        purchase_token: The purchase token from the client app

    Returns:
        Subscription purchase status including expiry and renewal info
    """
    client = get_client_from_context()

    status = client.get_subscription_purchase(
        package_name=package_name,
        subscription_id=subscription_id,
        token=purchase_token,
    )

    return status.model_dump()


@mcp.tool()
def list_voided_purchases(
    package_name: str,
    max_results: int = 100,
) -> list[dict[str, Any]]:
    """List voided purchases (refunds, chargebacks).

    Args:
        package_name: App package name
        max_results: Maximum number of results (default: 100)

    Returns:
        List of voided purchases with reason and timing
    """
    client = get_client_from_context()

    voided = client.list_voided_purchases(
        package_name=package_name,
        max_results=max_results,
    )

    return [v.model_dump() for v in voided]


# =============================================================================
# Vitals Tools
# =============================================================================


@mcp.tool()
def get_vitals_overview(package_name: str) -> dict[str, Any]:
    """Get Android Vitals overview for an app (placeholder - requires Play Developer Reporting API).

    Returns placeholder data. Full implementation requires the separate
    Play Developer Reporting API, not the Play Developer API.

    Args:
        package_name: App package name

    Returns:
        Vitals overview placeholder
    """
    client = get_client_from_context()

    vitals = client.get_vitals_overview(package_name)
    return vitals.model_dump()


@mcp.tool()
def get_vitals_metrics(
    package_name: str,
    metric_type: str = "crashRate",
) -> list[dict[str, Any]]:
    """Get specific Android Vitals metrics (placeholder - requires Play Developer Reporting API).

    Returns placeholder data. Full implementation requires the separate
    Play Developer Reporting API, not the Play Developer API.

    Args:
        package_name: App package name
        metric_type: Type of metric to retrieve (crashRate, anrRate, etc.)

    Returns:
        List of vitals metrics placeholders
    """
    client = get_client_from_context()

    metrics = client.get_vitals_metrics(package_name, metric_type)
    return [metric.model_dump() for metric in metrics]


# =============================================================================
# In-App Products Tools
# =============================================================================


@mcp.tool()
def list_in_app_products(package_name: str) -> list[dict[str, Any]]:
    """List all in-app products for an app.

    Args:
        package_name: App package name

    Returns:
        List of in-app products with SKU, title, description, and pricing
    """
    client = get_client_from_context()

    products = client.list_in_app_products(package_name)
    return [product.model_dump() for product in products]


@mcp.tool()
def get_in_app_product(
    package_name: str,
    sku: str,
) -> dict[str, Any]:
    """Get details of a specific in-app product.

    Args:
        package_name: App package name
        sku: Product SKU identifier

    Returns:
        In-app product details including title, description, and pricing
    """
    client = get_client_from_context()

    product = client.get_in_app_product(package_name, sku)
    return product.model_dump()


# =============================================================================
# Store Listings Tools
# =============================================================================


@mcp.tool()
def get_listing(
    package_name: str,
    language: str = "en-US",
) -> dict[str, Any]:
    """Get store listing for a specific language.

    Args:
        package_name: App package name
        language: Language code (e.g., en-US, es-ES, fr-FR)

    Returns:
        Store listing with title, descriptions, and video
    """
    client = get_client_from_context()

    listing = client.get_listing(package_name, language)
    return listing.model_dump()


@mcp.tool()
def update_listing(
    package_name: str,
    language: str,
    title: str | None = None,
    full_description: str | None = None,
    short_description: str | None = None,
    video: str | None = None,
) -> dict[str, Any]:
    """Update store listing for a specific language.

    Args:
        package_name: App package name
        language: Language code (e.g., en-US, es-ES, fr-FR)
        title: App title (max 50 characters, optional)
        full_description: Full description (max 4000 characters, optional)
        short_description: Short description (max 80 characters, optional)
        video: YouTube video URL (optional)

    Returns:
        Update result with success status
    """
    client = get_client_from_context()

    result = client.update_listing(
        package_name=package_name,
        language=language,
        title=title,
        full_description=full_description,
        short_description=short_description,
        video=video,
    )
    return result.model_dump()


@mcp.tool()
def list_all_listings(package_name: str) -> list[dict[str, Any]]:
    """List all store listings for all languages.

    Args:
        package_name: App package name

    Returns:
        List of store listings for all configured languages
    """
    client = get_client_from_context()

    listings = client.list_all_listings(package_name)
    return [listing.model_dump() for listing in listings]


# =============================================================================
# Testers Management Tools
# =============================================================================


@mcp.tool()
def get_testers(
    package_name: str,
    track: str,
) -> dict[str, Any]:
    """Get testers for a specific testing track.

    Args:
        package_name: App package name
        track: Track name (internal, alpha, beta)

    Returns:
        Tester information with list of email addresses
    """
    client = get_client_from_context()

    testers = client.get_testers(package_name, track)
    return testers.model_dump()


@mcp.tool()
def update_testers(
    package_name: str,
    track: str,
    google_groups: list[str],
) -> dict[str, Any]:
    """Update testers for a specific testing track.

    Args:
        package_name: App package name
        track: Track name (internal, alpha, beta)
        google_groups: List of Google Group email addresses

    Returns:
        Update result with success status
    """
    client = get_client_from_context()

    result = client.update_testers(package_name, track, google_groups)
    return result


# =============================================================================
# Orders Tools
# =============================================================================


@mcp.tool()
def get_order(
    package_name: str,
    order_id: str,
) -> dict[str, Any]:
    """Get detailed order/transaction information.

    Args:
        package_name: App package name
        order_id: Order ID to retrieve

    Returns:
        Order details including product, purchase state, and token
    """
    client = get_client_from_context()

    order = client.get_order(package_name, order_id)
    return order.model_dump()


# =============================================================================
# Expansion Files Tools
# =============================================================================


@mcp.tool()
def get_expansion_file(
    package_name: str,
    version_code: int,
    expansion_file_type: str = "main",
) -> dict[str, Any]:
    """Get APK expansion file information.

    Expansion files are used for large apps (especially games) that exceed
    the 100MB APK size limit.

    Args:
        package_name: App package name
        version_code: APK version code
        expansion_file_type: Type of expansion file (main or patch)

    Returns:
        Expansion file information including size and references
    """
    client = get_client_from_context()

    expansion_file = client.get_expansion_file(package_name, version_code, expansion_file_type)
    return expansion_file.model_dump()


# =============================================================================
# Validation Tools
# =============================================================================


@mcp.tool()
def validate_package_name(package_name: str) -> dict[str, Any]:
    """Validate package name format before using it in other operations.

    Args:
        package_name: Package name to validate (e.g., com.example.myapp)

    Returns:
        Validation result with any errors found
    """
    client = get_client_from_context()

    errors = client.validate_package_name(package_name)
    return {
        "valid": len(errors) == 0,
        "errors": [error.model_dump() for error in errors],
        "package_name": package_name,
    }


@mcp.tool()
def validate_track(track: str) -> dict[str, Any]:
    """Validate track name before using it in deployment operations.

    Args:
        track: Track name to validate (internal, alpha, beta, production)

    Returns:
        Validation result with any errors found
    """
    client = get_client_from_context()

    errors = client.validate_track(track)
    return {
        "valid": len(errors) == 0,
        "errors": [error.model_dump() for error in errors],
        "track": track,
    }


@mcp.tool()
def validate_listing_text(
    title: str | None = None,
    short_description: str | None = None,
    full_description: str | None = None,
) -> dict[str, Any]:
    """Validate store listing text lengths before updating.

    Args:
        title: App title (max 50 characters)
        short_description: Short description (max 80 characters)
        full_description: Full description (max 4000 characters)

    Returns:
        Validation result with any errors found
    """
    client = get_client_from_context()

    errors = client.validate_listing_text(title, short_description, full_description)
    return {
        "valid": len(errors) == 0,
        "errors": [error.model_dump() for error in errors],
    }


# =============================================================================
# Batch Operations Tools
# =============================================================================


@mcp.tool()
def batch_deploy(
    package_name: str,
    file_path: str,
    tracks: list[str],
    release_notes: str | None = None,
    rollout_percentages: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Deploy an app to multiple tracks in a single operation.

    This is useful for deploying to internal and alpha tracks simultaneously,
    or for promoting to multiple testing tracks at once.

    Args:
        package_name: App package name
        file_path: Absolute path to APK or AAB file
        tracks: List of tracks to deploy to (e.g., ["internal", "alpha"])
        release_notes: Optional release notes for all tracks
        rollout_percentages: Optional dict mapping track names to rollout percentages

    Returns:
        Batch deployment result with individual results for each track
    """
    if err := _validate_deploy_file(file_path):
        return {"error": err}

    if rollout_percentages:
        for track_name, pct in rollout_percentages.items():
            if not (0.0 <= pct <= 100.0):
                return {
                    "error": f"rollout_percentage for track '{track_name}' must be between 0.0 and 100.0"
                }

    client = get_client_from_context()

    result = client.batch_deploy(
        package_name=package_name,
        file_path=file_path,
        tracks=tracks,
        release_notes=release_notes,
        rollout_percentages=rollout_percentages,
    )
    return result.model_dump()


# =============================================================================
# Store Images Tools (edits.images)
# =============================================================================


_VALID_IMAGE_TYPES: tuple[str, ...] = tuple(t.value for t in ImageType)


def _validate_image_type_value(image_type: str) -> str | None:
    """Return error message if image_type is unknown, None if valid."""
    if image_type not in _VALID_IMAGE_TYPES:
        return f"image_type must be one of: {', '.join(_VALID_IMAGE_TYPES)}; got: {image_type}"
    return None


def _validate_language_tag(language: str) -> str | None:
    """Return error message if language tag is malformed, None if valid."""
    if not re.match(r"^[a-z]{2,3}(-[A-Z0-9]{2,4})?$", language):
        return f"language must be a BCP-47 tag like 'en-US', 'es-419', 'pt-BR'; got: {language}"
    return None


@mcp.tool()
def validate_image_type(image_type: str) -> dict[str, Any]:
    """Validate that an image_type matches the Publisher API enum.

    Use before upload/delete tools to fail fast without burning quota. The
    valid set is: phoneScreenshots, sevenInchScreenshots, tenInchScreenshots,
    tvScreenshots, wearScreenshots, icon, featureGraphic, tvBanner.

    Args:
        image_type: Candidate image type string.

    Returns:
        Dict with `valid` (bool), `image_type`, and `errors` (list of strings).
    """
    err = _validate_image_type_value(image_type)
    return {
        "valid": err is None,
        "image_type": image_type,
        "errors": [err] if err else [],
        "allowed": list(_VALID_IMAGE_TYPES),
    }


@mcp.tool()
def list_store_images(
    package_name: str,
    language: str,
    image_type: str,
) -> dict[str, Any]:
    """List uploaded images of one type for a localized store listing.

    Use to inspect what icons/screenshots/feature graphics already exist for a
    given app + locale before uploading new ones.

    Args:
        package_name: App package name (e.g. "com.example.app").
        language: BCP-47 locale tag (e.g. "en-US", "es-419", "ko-KR").
        image_type: One of the 8 supported types — call validate_image_type to
            check.

    Returns:
        Dict with `success`, `images` (list of {id, url, sha1, sha256}),
        `package_name`, `language`, `image_type`. On error: `success=False`
        and `error`.
    """
    if err := _validate_image_type_value(image_type):
        return {"success": False, "error": err}
    if err := _validate_language_tag(language):
        return {"success": False, "error": err}

    client = get_client_from_context()
    try:
        images = client.list_store_images(package_name, language, image_type)
        return {
            "success": True,
            "package_name": package_name,
            "language": language,
            "image_type": image_type,
            "images": [img.model_dump() for img in images],
        }
    except PlayStoreClientError as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def upload_store_image(
    package_name: str,
    language: str,
    image_type: str,
    file_path: str,
) -> dict[str, Any]:
    """Upload an image asset (screenshot, icon, feature graphic) to a localized
    store listing.

    Each call runs in its own edit session and is committed independently.
    To upload multiple files of the same type at once, use
    batch_upload_store_images instead — it commits all uploads in one edit
    and is faster.

    The file must be PNG or JPEG. Google enforces specific dimensions per
    image_type (e.g. 1024x500 for featureGraphic, 512x512 for icon); on
    dimension mismatch the API rejects the upload and the tool returns
    success=False with the API error message.

    Args:
        package_name: App package name.
        language: BCP-47 locale tag.
        image_type: One of phoneScreenshots, sevenInchScreenshots,
            tenInchScreenshots, tvScreenshots, wearScreenshots, icon,
            featureGraphic, tvBanner.
        file_path: Absolute path to the .png or .jpg/.jpeg file.

    Returns:
        Dict with `success`, `image` (id/url/sha1/sha256 on success), `message`,
        and `error` (on failure).
    """
    if err := _validate_image_type_value(image_type):
        return {"success": False, "error": err}
    if err := _validate_language_tag(language):
        return {"success": False, "error": err}

    client = get_client_from_context()
    result = client.upload_store_image(package_name, language, image_type, file_path)
    return result.model_dump()


@mcp.tool()
def delete_store_image(
    package_name: str,
    language: str,
    image_type: str,
    image_id: str,
) -> dict[str, Any]:
    """Delete a single uploaded image by ID.

    Use list_store_images to discover image IDs.

    Args:
        package_name: App package name.
        language: BCP-47 locale tag.
        image_type: One of the 8 supported types.
        image_id: ID returned by list_store_images / upload_store_image.

    Returns:
        Dict with `success`, `message`, and `error` on failure.
    """
    if err := _validate_image_type_value(image_type):
        return {"success": False, "error": err}
    if err := _validate_language_tag(language):
        return {"success": False, "error": err}
    if not image_id:
        return {"success": False, "error": "image_id cannot be empty"}

    client = get_client_from_context()
    result = client.delete_store_image(package_name, language, image_type, image_id)
    return result.model_dump()


@mcp.tool()
def delete_all_store_images(
    package_name: str,
    language: str,
    image_type: str,
) -> dict[str, Any]:
    """Delete every image of a given type for a locale.

    Useful when replacing the whole screenshot set for a locale: call
    delete_all_store_images, then batch_upload_store_images with the new files.

    Args:
        package_name: App package name.
        language: BCP-47 locale tag.
        image_type: One of the 8 supported types.

    Returns:
        Dict with `success`, `deleted_count`, `message`, and `error` on failure.
    """
    if err := _validate_image_type_value(image_type):
        return {"success": False, "error": err}
    if err := _validate_language_tag(language):
        return {"success": False, "error": err}

    client = get_client_from_context()
    result = client.delete_all_store_images(package_name, language, image_type)
    return result.model_dump()


@mcp.tool()
def batch_upload_store_images(
    package_name: str,
    language: str,
    image_type: str,
    file_paths: list[str],
) -> dict[str, Any]:
    """Upload multiple images of the same type in one edit session.

    All files are uploaded inside a single edit. If any upload fails the
    entire edit is discarded and the partial state is reported. Use this when
    refreshing a screenshot set — e.g. uploading 4 phoneScreenshots for one
    locale at once.

    Args:
        package_name: App package name.
        language: BCP-47 locale tag.
        image_type: One of the 8 supported types.
        file_paths: List of absolute paths to .png/.jpg/.jpeg files.

    Returns:
        Dict with `success`, `uploaded` (list of image dicts),
        `successful_count`, `failed_count`, `message`, `error`.
    """
    if err := _validate_image_type_value(image_type):
        return {"success": False, "error": err}
    if err := _validate_language_tag(language):
        return {"success": False, "error": err}
    if not isinstance(file_paths, list):
        return {"success": False, "error": "file_paths must be a list"}

    client = get_client_from_context()
    result = client.batch_upload_store_images(package_name, language, image_type, file_paths)
    return result.model_dump()


# =============================================================================
# Product Purchases & Refunds Tools (Group #3)
# =============================================================================


_ORDER_ID_RE = re.compile(r"^[A-Za-z0-9._\-]+$")


def _validate_order_id_value(order_id: str) -> str | None:
    """Return error message if order_id format is invalid, None if valid."""
    if not order_id:
        return "order_id cannot be empty"
    if not _ORDER_ID_RE.match(order_id):
        return f"order_id contains invalid characters: {order_id}"
    if "." not in order_id:
        return "order_id should look like GPA.XXXX-XXXX-XXXX-XXXXX"
    return None


@mcp.tool()
def get_product_purchase(
    package_name: str,
    product_id: str,
    token: str,
) -> dict[str, Any]:
    """Server-side validation of a one-time product purchase.

    Use to verify that a purchase token from a client app or webhook
    actually corresponds to a real, paid purchase. Read-only. Does not
    consume the purchase or grant entitlement on its own.

    The 3-day acknowledgement window matters here: if the purchase has
    `acknowledgement_state == 0` and is older than 3 days, Google has likely
    auto-refunded it.

    Args:
        package_name: App package name.
        product_id: Product SKU.
        token: Purchase token from BillingClient or Real Time Developer
            Notification (RTDN). Tokens are sensitive — they are masked when
            logged.

    Returns:
        Dict with `success`, the purchase record fields (purchase_state,
        consumption_state, order_id, region_code, etc.), or `error`.
    """
    if not token:
        return {"success": False, "error": "token cannot be empty"}

    client = get_client_from_context()
    try:
        purchase = client.get_product_purchase(package_name, product_id, token)
        result = purchase.model_dump(mode="json")
        result["success"] = True
        return result
    except PlayStoreClientError as e:
        return {"success": False, "error": str(e)}
    except ValueError as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def acknowledge_product_purchase(
    package_name: str,
    product_id: str,
    token: str,
    developer_payload: str | None = None,
) -> dict[str, Any]:
    """Acknowledge a one-time product purchase.

    **Required within 3 days** of purchase, otherwise Google auto-refunds.
    For backend services that handle acknowledgement server-side instead of
    in the client app.

    Args:
        package_name: App package name.
        product_id: Product SKU.
        token: Purchase token. Masked in logs.
        developer_payload: Optional developer-controlled string attached to the
            purchase. Capped at 1024 bytes (UTF-8 encoded).

    Returns:
        Dict with `success`, `message`, `error`.
    """
    client = get_client_from_context()
    result = client.acknowledge_product_purchase(package_name, product_id, token, developer_payload)
    return result.model_dump()


@mcp.tool()
def consume_product_purchase(
    package_name: str,
    product_id: str,
    token: str,
) -> dict[str, Any]:
    """Consume a consumable one-time product purchase.

    Marks the purchase consumed so the user can buy this SKU again. Only
    relevant for consumable IAPs (coins, gems, single-use rewards). Don't
    call for non-consumable products.

    Args:
        package_name: App package name.
        product_id: Product SKU.
        token: Purchase token. Masked in logs.

    Returns:
        Dict with `success`, `message`, `error`.
    """
    client = get_client_from_context()
    result = client.consume_product_purchase(package_name, product_id, token)
    return result.model_dump()


@mcp.tool()
def refund_order(
    package_name: str,
    order_id: str,
    revoke: bool = False,
) -> dict[str, Any]:
    """Refund (and optionally revoke) a Google Play order.

    Defaults to refund-without-revoke. Pass `revoke=True` only when you also
    want to strip the user's entitlement (e.g. policy violation). For most
    "issue a refund on user request" flows you want the default.

    Args:
        package_name: App package name.
        order_id: Order ID, typically `GPA.XXXX-XXXX-XXXX-XXXXX`.
        revoke: If True, also revoke entitlement. Default False.

    Returns:
        Dict with `success`, `revoked`, `message`, `error`.
    """
    if err := _validate_order_id_value(order_id):
        return {"success": False, "error": err}

    client = get_client_from_context()
    result = client.refund_order(package_name, order_id, revoke)
    return result.model_dump()


# =============================================================================
# Group #4: deobfuscation, bundles/apks list, country availability,
# custom tracks, edits.validate
# =============================================================================


_FORM_FACTORS: tuple[str, ...] = ("DEFAULT", "WEAR", "AUTOMOTIVE")


@mcp.tool()
def upload_deobfuscation_file(
    package_name: str,
    version_code: int,
    file_path: str,
    file_type: str = "proguard",
) -> dict[str, Any]:
    """Upload a deobfuscation/mapping file (ProGuard / R8 mapping.txt or
    native debug symbols) for an APK or AAB version.

    Without a mapping file, Google Play Console crash stack traces stay
    obfuscated and Vitals data is much less useful. After uploading the
    binary via deploy_app, call this tool with the version_code from the
    deploy result and the path to mapping.txt.

    For native crashes (NDK), set `file_type="nativeCode"` and pass a zip
    of the symbol files.

    Args:
        package_name: App package name.
        version_code: APK/AAB version code that this mapping applies to.
        file_path: Path to mapping.txt / .zip / .gz / .map.
        file_type: "proguard" (default) or "nativeCode".

    Returns:
        Dict with `success`, `version_code`, `file_type`, `message`, `error`.
    """
    if version_code <= 0:
        return {"success": False, "error": "version_code must be positive"}

    client = get_client_from_context()
    result = client.upload_deobfuscation_file(package_name, version_code, file_path, file_type)
    return result.model_dump()


@mcp.tool()
def list_bundles(package_name: str) -> dict[str, Any]:
    """List Android App Bundles uploaded to the app's edit area.

    Useful to discover which version_codes have been uploaded but not yet
    rolled out, or to map a version_code to its sha1/sha256 binary hash.

    Args:
        package_name: App package name.

    Returns:
        Dict with `success`, `bundles` (list of {version_code, sha1, sha256}).
    """
    client = get_client_from_context()
    try:
        bundles = client.list_bundles(package_name)
        return {
            "success": True,
            "package_name": package_name,
            "bundles": [b.model_dump() for b in bundles],
        }
    except PlayStoreClientError as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def list_apks(package_name: str) -> dict[str, Any]:
    """List APKs uploaded to the app's edit area.

    Same as list_bundles but for legacy APK uploads. Most apps should be
    on App Bundles; APK list is useful for older deploys.

    Args:
        package_name: App package name.

    Returns:
        Dict with `success`, `apks` (list of {version_code, sha1, sha256}).
    """
    client = get_client_from_context()
    try:
        apks = client.list_apks(package_name)
        return {
            "success": True,
            "package_name": package_name,
            "apks": [a.model_dump() for a in apks],
        }
    except PlayStoreClientError as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_country_availability(
    package_name: str,
    track: str,
) -> dict[str, Any]:
    """Get per-track country availability (which regions a track ships to).

    Read-only mirror of `edits.countryAvailability.get`. Helpful before
    promoting a release to verify that the target track has the expected
    regions enabled.

    Args:
        package_name: App package name.
        track: Track name (e.g. "production", "beta", or a custom closed
            testing track).

    Returns:
        Dict with `success`, `track`, `rest_of_world`, `sync_with_production`,
        `countries` (list of ISO 3166-1 alpha-2 codes).
    """
    client = get_client_from_context()
    try:
        ca = client.get_country_availability(package_name, track)
        return {
            "success": True,
            **ca.model_dump(),
        }
    except PlayStoreClientError as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def create_custom_track(
    package_name: str,
    track: str,
    form_factor: str = "DEFAULT",
) -> dict[str, Any]:
    """Create a custom closed-testing track.

    Publisher API only supports closed-testing tracks via this endpoint —
    you cannot create open testing or production tracks here. Use this when
    you need a dedicated track for a specific tester group beyond the
    default internal/alpha/beta.

    Args:
        package_name: App package name.
        track: New track identifier (e.g. "qa-team", "wear:qa-team"). For
            non-DEFAULT form_factor the prefix must match (e.g. wear: for
            WEAR).
        form_factor: One of DEFAULT, WEAR, AUTOMOTIVE. Default DEFAULT.

    Returns:
        Dict with `success`, `track`, `message`, `error`.
    """
    if form_factor not in _FORM_FACTORS:
        return {
            "success": False,
            "error": f"form_factor must be one of {_FORM_FACTORS}",
        }
    if not track:
        return {"success": False, "error": "track cannot be empty"}

    client = get_client_from_context()
    result = client.create_custom_track(package_name, track, form_factor)
    return result.model_dump()


@mcp.tool()
def validate_edit(
    package_name: str,
    edit_id: str,
) -> dict[str, Any]:
    """Dry-run validate an existing edit (`edits.validate`).

    Most tools manage edit lifecycle internally and never expose edit_ids.
    Use this when you have an edit_id from another flow and want Google to
    confirm it can commit cleanly before actually committing.

    Note: this returns success=True for a *successful API call*. The
    validation outcome itself is in the `valid` field. If the edit doesn't
    pass validation, `success=True` but `valid=False` with `error` set to
    Google's reason.

    Args:
        package_name: App package name.
        edit_id: Edit ID to validate.

    Returns:
        Dict with `success`, `valid`, `message`, `error`.
    """
    if not edit_id:
        return {"success": False, "error": "edit_id cannot be empty"}

    client = get_client_from_context()
    result = client.validate_edit(package_name, edit_id)
    return result.model_dump()


# =============================================================================
# Group #2: monetization.onetimeproducts (modern IAP API)
# =============================================================================


@mcp.tool()
def list_onetime_products(package_name: str) -> dict[str, Any]:
    """List one-time IAP products via the modern monetization API.

    `monetization.onetimeproducts` is the recommended replacement for the
    legacy `inappproducts` resource.

    Args:
        package_name: App package name.

    Returns:
        Dict with `success`, `products` (list of OnetimeProduct dicts).
    """
    client = get_client_from_context()
    try:
        products = client.list_onetime_products(package_name)
        return {
            "success": True,
            "package_name": package_name,
            "products": [p.model_dump() for p in products],
        }
    except PlayStoreClientError as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_onetime_product(
    package_name: str,
    product_id: str,
) -> dict[str, Any]:
    """Get a single one-time product.

    Args:
        package_name: App package name.
        product_id: Product ID.

    Returns:
        Dict with `success` and the OnetimeProduct fields.
    """
    if not product_id:
        return {"success": False, "error": "product_id cannot be empty"}

    client = get_client_from_context()
    try:
        product = client.get_onetime_product(package_name, product_id)
        return {"success": True, **product.model_dump()}
    except PlayStoreClientError as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def create_onetime_product(
    package_name: str,
    product_id: str,
    listings: list[dict[str, str]],
    price_micros: int,
    purchase_option_id: str = "default",
    legacy_compatible: bool = True,
) -> dict[str, Any]:
    """Create a new one-time product (UPSERT — also works as update).

    Internally PATCH'es with `allowMissing=True` so the same call creates a
    new product or updates an existing one. Use `update_onetime_product` if
    you want to make the intent explicit in your script — it routes through
    the same endpoint.

    Pricing: pass a single USD price in micros (e.g. `9_990_000` for
    `$9.99`); the tool calls `convertRegionPrices` to compute regional
    prices for ~150 regions automatically and attaches the result.

    Args:
        package_name: App package name.
        product_id: Product ID. Use lowercase letters, numbers, dot,
            underscore.
        listings: List of {language_code, title, description}. At least one
            entry required. Title ≤ 55 chars, description ≤ 200 chars.
        price_micros: USD price in micros (1 USD = 1_000_000). Must be > 0.
        purchase_option_id: Identifier for the buy option. Default
            "default". Pattern: starts with [a-z0-9], only [a-z0-9-],
            ≤ 63 chars.
        legacy_compatible: If True, this product is visible to legacy
            BillingClient flows that don't understand the new model.
            Default True.

    Returns:
        Dict with `success`, `product` (full record), `message`, `error`.
    """
    if not product_id:
        return {"success": False, "error": "product_id cannot be empty"}
    if not isinstance(listings, list) or not listings:
        return {"success": False, "error": "listings must be a non-empty list"}

    client = get_client_from_context()
    result = client.upsert_onetime_product(
        package_name,
        product_id,
        listings,
        price_micros,
        purchase_option_id,
        legacy_compatible,
        operation_label="create",
    )
    return result.model_dump()


@mcp.tool()
def update_onetime_product(
    package_name: str,
    product_id: str,
    listings: list[dict[str, str]],
    price_micros: int,
    purchase_option_id: str = "default",
    legacy_compatible: bool = True,
) -> dict[str, Any]:
    """Update an existing one-time product (UPSERT semantics).

    Same endpoint as `create_onetime_product`. Use this name when the intent
    is "update an existing product" — both work via PATCH+allowMissing.

    Args/Returns: see `create_onetime_product`.
    """
    if not product_id:
        return {"success": False, "error": "product_id cannot be empty"}
    if not isinstance(listings, list) or not listings:
        return {"success": False, "error": "listings must be a non-empty list"}

    client = get_client_from_context()
    result = client.upsert_onetime_product(
        package_name,
        product_id,
        listings,
        price_micros,
        purchase_option_id,
        legacy_compatible,
        operation_label="update",
    )
    return result.model_dump()


@mcp.tool()
def delete_onetime_product(
    package_name: str,
    product_id: str,
) -> dict[str, Any]:
    """Delete a one-time product.

    The product must not have any active orders/entitlements depending on
    it; the API will reject the call otherwise.

    Args:
        package_name: App package name.
        product_id: Product ID to delete.

    Returns:
        Dict with `success`, `message`, `error`.
    """
    if not product_id:
        return {"success": False, "error": "product_id cannot be empty"}

    client = get_client_from_context()
    result = client.delete_onetime_product(package_name, product_id)
    return result.model_dump()


@mcp.tool()
def activate_onetime_product(
    package_name: str,
    product_id: str,
    purchase_option_id: str = "default",
) -> dict[str, Any]:
    """Activate a purchase option on a one-time product.

    Toggles the option's `state` from DRAFT/INACTIVE → ACTIVE so it becomes
    purchasable in the BillingClient.

    Args:
        package_name: App package name.
        product_id: Product ID.
        purchase_option_id: Purchase option to activate. Default "default".

    Returns:
        Dict with `success`, `message`, `error`.
    """
    if not product_id:
        return {"success": False, "error": "product_id cannot be empty"}

    client = get_client_from_context()
    result = client.activate_onetime_product(package_name, product_id, purchase_option_id)
    return result.model_dump()


@mcp.tool()
def deactivate_onetime_product(
    package_name: str,
    product_id: str,
    purchase_option_id: str = "default",
) -> dict[str, Any]:
    """Deactivate a purchase option on a one-time product.

    Sets the option's state to INACTIVE so users can no longer buy it,
    without deleting the product.

    Args:
        package_name: App package name.
        product_id: Product ID.
        purchase_option_id: Purchase option to deactivate. Default "default".

    Returns:
        Dict with `success`, `message`, `error`.
    """
    if not product_id:
        return {"success": False, "error": "product_id cannot be empty"}

    client = get_client_from_context()
    result = client.deactivate_onetime_product(package_name, product_id, purchase_option_id)
    return result.model_dump()


@mcp.tool()
def batch_create_onetime_products(
    package_name: str,
    products: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create or update many one-time products.

    Each entry should be: {`product_id`, `listings` (list), `price_micros`,
    optional `purchase_option_id`, optional `legacy_compatible`}.

    Each product is upserted via its own PATCH call (one
    `convertRegionPrices` per product). On per-item failure, other items
    still proceed.

    Args:
        package_name: App package name.
        products: List of product dicts as described above.

    Returns:
        Dict with `success` (True iff all succeeded), `successful_count`,
        `failed_count`, and `results` (per-item dicts).
    """
    if not isinstance(products, list) or not products:
        return {"success": False, "error": "products must be a non-empty list"}

    client = get_client_from_context()
    item_results = client.batch_create_onetime_products(package_name, products)
    successful = sum(1 for r in item_results if r.success)
    failed = len(item_results) - successful
    return {
        "success": failed == 0,
        "package_name": package_name,
        "successful_count": successful,
        "failed_count": failed,
        "results": [r.model_dump() for r in item_results],
    }


# =============================================================================
# HTTP Endpoints for Streamable Transport
# =============================================================================


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:  # noqa: ARG001
    """Health check endpoint for monitoring and load balancers."""
    return JSONResponse({"status": "healthy", "service": "play-store-mcp"})


@mcp.custom_route("/credentials", methods=["POST"])
async def update_credentials(request: Request) -> JSONResponse:
    """Update Google Play Store credentials via HTTP POST.

    Management endpoint - restricted to localhost only.

    This endpoint allows local clients to provide credentials when using
    streamable-http transport. Accepts JSON credentials in the request body.

    Request body should be one of:
    - {"credentials": {...}} - Service account JSON object
    - {"credentials": "..."} - Service account JSON string
    - {"credentials_base64": "..."} - Base64-encoded service account JSON

    Returns:
        JSON response with success status
    """
    # Management endpoint: only allow requests from localhost
    client_host = request.client.host if request.client else None
    try:
        is_loopback = client_host is not None and ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        return JSONResponse(
            {"success": False, "error": "This endpoint is only accessible from localhost"},
            status_code=403,
        )

    try:
        body = await request.json()

        credentials = body.get("credentials")
        credentials_base64 = body.get("credentials_base64")

        if not credentials and not credentials_base64:
            return JSONResponse(
                {
                    "success": False,
                    "error": "Missing 'credentials' or 'credentials_base64' in request body",
                },
                status_code=400,
            )

        # Create new client with provided credentials
        if credentials_base64:
            # Decode base64 credentials
            try:
                decoded = base64.b64decode(credentials_base64).decode("utf-8")
                credentials_dict = json.loads(decoded)
                new_client = PlayStoreClient(credentials_json=credentials_dict)
            except (binascii.Error, UnicodeDecodeError) as e:
                return JSONResponse(
                    {"success": False, "error": f"Invalid base64 encoding: {e}"},
                    status_code=400,
                )
            except json.JSONDecodeError:
                return JSONResponse(
                    {"success": False, "error": "Invalid JSON in base64-decoded credentials"},
                    status_code=400,
                )
        elif credentials:
            if isinstance(credentials, str):
                # Validate it's valid JSON
                try:
                    json.loads(credentials)
                except json.JSONDecodeError:
                    return JSONResponse(
                        {"success": False, "error": "Invalid JSON in credentials string"},
                        status_code=400,
                    )
                new_client = PlayStoreClient(credentials_json=credentials)
            elif isinstance(credentials, dict):
                new_client = PlayStoreClient(credentials_json=credentials)
            else:
                return JSONResponse(
                    {"success": False, "error": "credentials must be a string or object"},
                    status_code=400,
                )

        # Validate credentials by attempting to get service
        try:
            _ = new_client._get_service()
        except PlayStoreClientError as e:
            return JSONResponse(
                {"success": False, "error": f"Invalid credentials: {e}"},
                status_code=401,
            )

        # Update the client in the shared state
        if hasattr(mcp, "_shared_state"):
            mcp._shared_state["client"] = new_client  # type: ignore[attr-defined]
            mcp._shared_state["credentials_updated"] = True  # type: ignore[attr-defined]

        logger.info("Credentials updated successfully via HTTP endpoint")

        return JSONResponse(
            {"success": True, "message": "Credentials updated successfully"},
            status_code=200,
        )

    except json.JSONDecodeError:
        return JSONResponse(
            {"success": False, "error": "Invalid JSON in request body"},
            status_code=400,
        )
    except Exception as e:
        logger.exception("Error updating credentials", error=str(e))
        return JSONResponse(
            {"success": False, "error": f"Internal error: {e}"},
            status_code=500,
        )


# =============================================================================
# Entry Point
# =============================================================================


def main(argv: list[str] | None = None) -> None:
    """Run the Play Store MCP Server."""
    parser = argparse.ArgumentParser(description="Play Store MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=os.environ.get("MCP_TRANSPORT", "stdio"),
        help="Transport protocol (default: stdio, or set MCP_TRANSPORT env var)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MCP_HOST", "127.0.0.1"),
        help="Host to bind to for network transports (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MCP_PORT", "8000")),
        help="Port to bind to for network transports (default: 8000)",
    )
    parser.add_argument(
        "--credentials",
        default=os.environ.get("GOOGLE_PLAY_STORE_CREDENTIALS"),
        help="Path to service account JSON key or JSON content (default: GOOGLE_PLAY_STORE_CREDENTIALS env var)",
    )
    args = parser.parse_args(argv)

    if args.credentials:
        os.environ["GOOGLE_PLAY_STORE_CREDENTIALS"] = args.credentials

    logger.info(
        "Starting Play Store MCP Server",
        transport=args.transport,
        host=args.host if args.transport != "stdio" else None,
        port=args.port if args.transport != "stdio" else None,
    )

    if args.transport != "stdio":
        mcp.settings.host = args.host
        mcp.settings.port = args.port

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
