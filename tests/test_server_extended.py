"""Extended tests for server.py — covers MCP tool handlers and lifespan."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from play_store_mcp.client import PlayStoreClient, PlayStoreClientError
from play_store_mcp.models import (
    AppDetails,
    BatchDeploymentResult,
    DeploymentResult,
    ExpansionFile,
    InAppProduct,
    Listing,
    ListingUpdateResult,
    Order,
    Release,
    Review,
    ReviewReplyResult,
    SubscriptionProduct,
    SubscriptionPurchase,
    TesterInfo,
    TrackInfo,
    ValidationResult,
    VitalsMetric,
    VitalsOverview,
    VoidedPurchase,
)
from play_store_mcp.server import (
    batch_deploy,
    deploy_app,
    deploy_app_multilang,
    get_app_details,
    get_expansion_file,
    get_in_app_product,
    get_listing,
    get_order,
    get_releases,
    get_reviews,
    get_testers,
    get_vitals_metrics,
    get_vitals_overview,
    halt_release,
    list_all_listings,
    list_in_app_products,
    list_subscriptions,
    list_voided_purchases,
    mcp,
    promote_release,
    reply_to_review,
    update_listing,
    update_rollout,
    update_testers,
    validate_listing_text,
    validate_package_name,
    validate_track,
)


def _mock_context(client: MagicMock) -> MagicMock:
    """Create a mock MCP context with the given client."""
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {"client": client}
    return ctx


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock PlayStoreClient."""
    return MagicMock(spec=PlayStoreClient)


@pytest.fixture
def tmp_apk(tmp_path: Any) -> str:
    """Create a temporary APK file for deploy tests."""
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"fake apk")
    return str(apk)


@pytest.fixture
def tmp_aab(tmp_path: Any) -> str:
    """Create a temporary AAB file for deploy tests."""
    aab = tmp_path / "app.aab"
    aab.write_bytes(b"fake aab")
    return str(aab)


@pytest.fixture(autouse=True)
def _patch_mcp_context(mock_client: MagicMock) -> Any:
    """Patch mcp.get_context to return our mock client."""
    ctx = _mock_context(mock_client)
    with patch.object(mcp, "get_context", return_value=ctx):
        yield


# =========================================================================
# Lifespan
# =========================================================================


class TestLifespan:
    """Test server lifespan."""

    @pytest.mark.asyncio
    async def test_lifespan_success(self) -> None:
        """Test successful lifespan initialization."""
        from play_store_mcp.server import lifespan

        mock_server = MagicMock()

        with (
            patch("play_store_mcp.server.PlayStoreClient") as MockClient,
            patch("play_store_mcp.server.PlayStoreClientError", PlayStoreClientError),
        ):
            instance = MockClient.return_value
            instance._get_service.return_value = MagicMock()

            async with lifespan(mock_server) as ctx:
                assert "client" in ctx
                assert ctx["client"] is instance

    @pytest.mark.asyncio
    async def test_lifespan_credentials_failure(self) -> None:
        """Test lifespan when credentials fail."""
        from play_store_mcp.server import lifespan

        mock_server = MagicMock()

        with (
            patch("play_store_mcp.server.PlayStoreClient") as MockClient,
            patch("play_store_mcp.server.PlayStoreClientError", PlayStoreClientError),
        ):
            instance = MockClient.return_value
            instance._get_service.side_effect = PlayStoreClientError("bad creds")

            async with lifespan(mock_server) as ctx:
                assert "client" in ctx
                # Client should be None on failure
                assert ctx["client"] is None


# =========================================================================
# Publishing tools
# =========================================================================


class TestDeployAppTool:
    """Test deploy_app server tool."""

    def test_deploy_app(self, mock_client: MagicMock, tmp_apk: str) -> None:
        """Test deploy_app tool."""
        mock_client.deploy_app.return_value = DeploymentResult(
            success=True,
            package_name="com.example.app",
            track="internal",
            version_code=100,
            message="Deployed",
        )

        result = deploy_app("com.example.app", "internal", tmp_apk)

        mock_client.deploy_app.assert_called_once_with(
            package_name="com.example.app",
            track="internal",
            file_path=tmp_apk,
            release_notes=None,
            release_notes_language="en-US",
            rollout_percentage=100.0,
        )
        assert result["success"] is True
        assert result["version_code"] == 100

    def test_deploy_app_multilang(self, mock_client: MagicMock, tmp_aab: str) -> None:
        """Test deploy_app_multilang tool."""
        mock_client.deploy_app.return_value = DeploymentResult(
            success=True,
            package_name="com.example.app",
            track="beta",
            version_code=101,
            message="Deployed",
        )

        notes = {"en-US": "Notes", "es-ES": "Notas"}
        result = deploy_app_multilang(
            "com.example.app",
            "beta",
            tmp_aab,
            notes,
        )

        mock_client.deploy_app.assert_called_once_with(
            package_name="com.example.app",
            track="beta",
            file_path=tmp_aab,
            release_notes=notes,
            rollout_percentage=100.0,
        )
        assert result["success"] is True


class TestPromoteReleaseTool:
    """Test promote_release server tool."""

    def test_promote_release(self, mock_client: MagicMock) -> None:
        """Test promote_release tool."""
        mock_client.promote_release.return_value = DeploymentResult(
            success=True,
            package_name="com.example.app",
            track="production",
            version_code=100,
            message="Promoted",
        )

        result = promote_release("com.example.app", "beta", "production", 100)

        mock_client.promote_release.assert_called_once_with(
            package_name="com.example.app",
            from_track="beta",
            to_track="production",
            version_code=100,
            rollout_percentage=100.0,
        )
        assert result["success"] is True


class TestGetReleasesTool:
    """Test get_releases server tool."""

    def test_get_releases(self, mock_client: MagicMock) -> None:
        """Test get_releases tool."""
        mock_client.get_releases.return_value = [
            TrackInfo(
                track="production",
                releases=[
                    Release(
                        package_name="com.example.app",
                        track="production",
                        status="completed",
                        version_codes=[100],
                    )
                ],
            )
        ]

        result = get_releases("com.example.app")

        mock_client.get_releases.assert_called_once_with("com.example.app")
        assert len(result) == 1
        assert result[0]["track"] == "production"


class TestHaltReleaseTool:
    """Test halt_release server tool."""

    def test_halt_release(self, mock_client: MagicMock) -> None:
        """Test halt_release tool."""
        mock_client.halt_release.return_value = DeploymentResult(
            success=True,
            package_name="com.example.app",
            track="production",
            version_code=100,
            message="Halted",
        )

        result = halt_release("com.example.app", "production", 100)

        mock_client.halt_release.assert_called_once_with(
            package_name="com.example.app",
            track="production",
            version_code=100,
        )
        assert result["success"] is True


class TestUpdateRolloutTool:
    """Test update_rollout server tool."""

    def test_update_rollout(self, mock_client: MagicMock) -> None:
        """Test update_rollout tool."""
        mock_client.update_rollout.return_value = DeploymentResult(
            success=True,
            package_name="com.example.app",
            track="production",
            version_code=100,
            message="Updated",
        )

        result = update_rollout("com.example.app", "production", 100, 50.0)

        mock_client.update_rollout.assert_called_once_with(
            package_name="com.example.app",
            track="production",
            version_code=100,
            rollout_percentage=50.0,
        )
        assert result["success"] is True


class TestGetAppDetailsTool:
    """Test get_app_details server tool."""

    def test_get_app_details(self, mock_client: MagicMock) -> None:
        """Test get_app_details tool."""
        mock_client.get_app_details.return_value = AppDetails(
            package_name="com.example.app",
            title="My App",
        )

        result = get_app_details("com.example.app")

        mock_client.get_app_details.assert_called_once_with("com.example.app", "en-US")
        assert result["title"] == "My App"


# =========================================================================
# Reviews tools
# =========================================================================


class TestReviewsTools:
    """Test review server tools."""

    def test_get_reviews(self, mock_client: MagicMock) -> None:
        """Test get_reviews tool."""
        mock_client.get_reviews.return_value = [
            Review(
                review_id="r1",
                author_name="User",
                star_rating=5,
                comment="Great!",
                language="en",
            )
        ]

        result = get_reviews("com.example.app")

        mock_client.get_reviews.assert_called_once_with(
            package_name="com.example.app",
            max_results=50,
            translation_language=None,
        )
        assert len(result) == 1
        assert result[0]["star_rating"] == 5

    def test_get_reviews_with_options(self, mock_client: MagicMock) -> None:
        """Test get_reviews with max_results and translation."""
        mock_client.get_reviews.return_value = []

        result = get_reviews("com.example.app", max_results=10, translation_language="es")

        assert result == []
        mock_client.get_reviews.assert_called_once_with(
            package_name="com.example.app",
            max_results=10,
            translation_language="es",
        )

    def test_get_reviews_caps_at_100(self, mock_client: MagicMock) -> None:
        """Test that max_results is capped at 100."""
        mock_client.get_reviews.return_value = []

        get_reviews("com.example.app", max_results=200)

        mock_client.get_reviews.assert_called_once_with(
            package_name="com.example.app",
            max_results=100,
            translation_language=None,
        )

    def test_reply_to_review(self, mock_client: MagicMock) -> None:
        """Test reply_to_review tool."""
        mock_client.reply_to_review.return_value = ReviewReplyResult(
            success=True,
            review_id="r1",
            message="Replied",
        )

        result = reply_to_review("com.example.app", "r1", "Thanks!")

        mock_client.reply_to_review.assert_called_once_with(
            package_name="com.example.app",
            review_id="r1",
            reply_text="Thanks!",
        )
        assert result["success"] is True


# =========================================================================
# Subscription tools
# =========================================================================


class TestSubscriptionTools:
    """Test subscription server tools."""

    def test_list_subscriptions(self, mock_client: MagicMock) -> None:
        """Test list_subscriptions tool."""
        mock_client.list_subscriptions.return_value = [
            SubscriptionProduct(
                product_id="premium",
                package_name="com.example.app",
            )
        ]

        result = list_subscriptions("com.example.app")

        mock_client.list_subscriptions.assert_called_once_with("com.example.app")
        assert len(result) == 1
        assert result[0]["product_id"] == "premium"

    def test_get_subscription_status(self, mock_client: MagicMock) -> None:
        """Test get_subscription_status tool."""
        from play_store_mcp.server import get_subscription_status

        mock_client.get_subscription_purchase.return_value = SubscriptionPurchase(
            package_name="com.example.app",
            subscription_id="premium",
            purchase_token="tok123",
            auto_renewing=True,
        )

        result = get_subscription_status("com.example.app", "premium", "tok123")

        mock_client.get_subscription_purchase.assert_called_once_with(
            package_name="com.example.app",
            subscription_id="premium",
            token="tok123",
        )
        assert result["auto_renewing"] is True

    def test_list_voided_purchases(self, mock_client: MagicMock) -> None:
        """Test list_voided_purchases tool."""
        mock_client.list_voided_purchases.return_value = [
            VoidedPurchase(
                package_name="com.example.app",
                purchase_token="tok1",
            )
        ]

        result = list_voided_purchases("com.example.app")

        mock_client.list_voided_purchases.assert_called_once_with(
            package_name="com.example.app",
            max_results=100,
        )
        assert len(result) == 1


# =========================================================================
# Vitals tools
# =========================================================================


class TestVitalsTools:
    """Test vitals server tools."""

    def test_get_vitals_overview(self, mock_client: MagicMock) -> None:
        """Test get_vitals_overview tool."""
        mock_client.get_vitals_overview.return_value = VitalsOverview(
            package_name="com.example.app",
            crash_rate=0.5,
        )

        result = get_vitals_overview("com.example.app")

        mock_client.get_vitals_overview.assert_called_once_with("com.example.app")
        assert result["crash_rate"] == 0.5

    def test_get_vitals_metrics(self, mock_client: MagicMock) -> None:
        """Test get_vitals_metrics tool."""
        mock_client.get_vitals_metrics.return_value = [
            VitalsMetric(metric_type="crashRate", value=0.5)
        ]

        result = get_vitals_metrics("com.example.app")

        mock_client.get_vitals_metrics.assert_called_once_with("com.example.app", "crashRate")
        assert len(result) == 1
        assert result[0]["metric_type"] == "crashRate"


# =========================================================================
# In-App Products tools
# =========================================================================


class TestInAppProductsTools:
    """Test in-app products server tools."""

    def test_list_in_app_products(self, mock_client: MagicMock) -> None:
        """Test list_in_app_products tool."""
        mock_client.list_in_app_products.return_value = [
            InAppProduct(
                sku="premium",
                package_name="com.example.app",
                product_type="managedProduct",
            )
        ]

        result = list_in_app_products("com.example.app")

        mock_client.list_in_app_products.assert_called_once_with("com.example.app")
        assert len(result) == 1

    def test_get_in_app_product(self, mock_client: MagicMock) -> None:
        """Test get_in_app_product tool."""
        mock_client.get_in_app_product.return_value = InAppProduct(
            sku="premium",
            package_name="com.example.app",
            product_type="managedProduct",
            title="Premium",
        )

        result = get_in_app_product("com.example.app", "premium")

        mock_client.get_in_app_product.assert_called_once_with("com.example.app", "premium")
        assert result["title"] == "Premium"


# =========================================================================
# Store Listings tools
# =========================================================================


class TestListingsTools:
    """Test store listings server tools."""

    def test_get_listing(self, mock_client: MagicMock) -> None:
        """Test get_listing tool."""
        mock_client.get_listing.return_value = Listing(
            language="en-US",
            title="My App",
        )

        result = get_listing("com.example.app")

        mock_client.get_listing.assert_called_once_with("com.example.app", "en-US")
        assert result["title"] == "My App"

    def test_update_listing(self, mock_client: MagicMock) -> None:
        """Test update_listing tool."""
        mock_client.update_listing.return_value = ListingUpdateResult(
            success=True,
            package_name="com.example.app",
            language="en-US",
            message="Updated",
        )

        result = update_listing("com.example.app", "en-US", title="New Title")

        mock_client.update_listing.assert_called_once_with(
            package_name="com.example.app",
            language="en-US",
            title="New Title",
            full_description=None,
            short_description=None,
            video=None,
        )
        assert result["success"] is True

    def test_list_all_listings(self, mock_client: MagicMock) -> None:
        """Test list_all_listings tool."""
        mock_client.list_all_listings.return_value = [
            Listing(language="en-US", title="My App"),
            Listing(language="es-ES", title="Mi App"),
        ]

        result = list_all_listings("com.example.app")

        mock_client.list_all_listings.assert_called_once_with("com.example.app")
        assert len(result) == 2


# =========================================================================
# Testers tools
# =========================================================================


class TestTestersTools:
    """Test testers server tools."""

    def test_get_testers(self, mock_client: MagicMock) -> None:
        """Test get_testers tool."""
        mock_client.get_testers.return_value = TesterInfo(
            track="beta",
            google_groups=["test@example.com"],
        )

        result = get_testers("com.example.app", "beta")

        mock_client.get_testers.assert_called_once_with("com.example.app", "beta")
        assert len(result["google_groups"]) == 1

    def test_update_testers(self, mock_client: MagicMock) -> None:
        """Test update_testers tool."""
        mock_client.update_testers.return_value = {
            "success": True,
            "package_name": "com.example.app",
            "track": "beta",
            "message": "Updated",
        }

        result = update_testers("com.example.app", "beta", ["test@example.com"])

        mock_client.update_testers.assert_called_once_with(
            "com.example.app", "beta", ["test@example.com"]
        )
        assert result["success"] is True


# =========================================================================
# Orders tools
# =========================================================================


class TestOrdersTools:
    """Test orders server tools."""

    def test_get_order(self, mock_client: MagicMock) -> None:
        """Test get_order tool."""
        mock_client.get_order.return_value = Order(
            order_id="order-123",
            package_name="com.example.app",
            product_id="premium",
        )

        result = get_order("com.example.app", "order-123")

        mock_client.get_order.assert_called_once_with("com.example.app", "order-123")
        assert result["order_id"] == "order-123"


# =========================================================================
# Expansion Files tools
# =========================================================================


class TestExpansionFilesTools:
    """Test expansion files server tools."""

    def test_get_expansion_file(self, mock_client: MagicMock) -> None:
        """Test get_expansion_file tool."""
        mock_client.get_expansion_file.return_value = ExpansionFile(
            version_code=100,
            expansion_file_type="main",
            file_size=104857600,
        )

        result = get_expansion_file("com.example.app", 100)

        mock_client.get_expansion_file.assert_called_once_with("com.example.app", 100, "main")
        assert result["file_size"] == 104857600


# =========================================================================
# Validation tools
# =========================================================================


class TestValidationTools:
    """Test validation server tools."""

    def test_validate_package_name_valid(self, mock_client: MagicMock) -> None:
        """Test validate_package_name with valid name."""
        mock_client.validate_package_name.return_value = []

        result = validate_package_name("com.example.app")

        mock_client.validate_package_name.assert_called_once_with("com.example.app")
        assert result["valid"] is True
        assert result["errors"] == []

    def test_validate_package_name_invalid(self, mock_client: MagicMock) -> None:
        """Test validate_package_name with invalid name."""
        mock_client.validate_package_name.return_value = [
            ValidationResult(field="package_name", message="Bad name", value="bad")
        ]

        result = validate_package_name("bad")

        mock_client.validate_package_name.assert_called_once_with("bad")
        assert result["valid"] is False
        assert len(result["errors"]) == 1

    def test_validate_track_valid(self, mock_client: MagicMock) -> None:
        """Test validate_track with valid track."""
        mock_client.validate_track.return_value = []

        result = validate_track("production")

        mock_client.validate_track.assert_called_once_with("production")
        assert result["valid"] is True

    def test_validate_listing_text(self, mock_client: MagicMock) -> None:
        """Test validate_listing_text."""
        mock_client.validate_listing_text.return_value = []

        result = validate_listing_text(title="My App")

        mock_client.validate_listing_text.assert_called_once_with("My App", None, None)
        assert result["valid"] is True


# =========================================================================
# Batch deploy tool
# =========================================================================


class TestBatchDeployTool:
    """Test batch_deploy server tool."""

    def test_batch_deploy(self, mock_client: MagicMock, tmp_apk: str) -> None:
        """Test batch_deploy tool."""
        mock_client.batch_deploy.return_value = BatchDeploymentResult(
            success=True,
            results=[],
            successful_count=2,
            failed_count=0,
            message="All good",
        )

        result = batch_deploy(
            "com.example.app",
            tmp_apk,
            ["internal", "alpha"],
        )

        mock_client.batch_deploy.assert_called_once_with(
            package_name="com.example.app",
            file_path=tmp_apk,
            tracks=["internal", "alpha"],
            release_notes=None,
            rollout_percentages=None,
        )
        assert result["success"] is True
        assert result["successful_count"] == 2


# =========================================================================
# Server main entry point
# =========================================================================


class TestServerMain:
    """Test server main function."""

    def test_main_calls_mcp_run(self) -> None:
        """Test that main() calls mcp.run()."""
        from play_store_mcp.server import main

        with patch.object(mcp, "run") as mock_run:
            main([])
            mock_run.assert_called_once()

    def test_get_subscription_status_tool(self, mock_client: MagicMock) -> None:
        """Test get_subscription_status tool."""
        from play_store_mcp.server import get_subscription_status

        mock_client.get_subscription_purchase.return_value = SubscriptionPurchase(
            package_name="com.example.app",
            subscription_id="sub1",
            purchase_token="tok",
        )

        result = get_subscription_status("com.example.app", "sub1", "tok")

        mock_client.get_subscription_purchase.assert_called_once_with(
            package_name="com.example.app",
            subscription_id="sub1",
            token="tok",
        )
        assert result["subscription_id"] == "sub1"


# =========================================================================
# Group #1 — edits.images server tools
# =========================================================================


from play_store_mcp.models import (  # noqa: E402
    BatchImageUploadResult,
    StoreImage,
    StoreImageDeleteResult,
    StoreImageUploadResult,
)
from play_store_mcp.server import (  # noqa: E402
    batch_upload_store_images,
    delete_all_store_images,
    delete_store_image,
    list_store_images,
    upload_store_image,
    validate_image_type,
)


class TestValidateImageType:
    def test_valid(self) -> None:
        result = validate_image_type("icon")
        assert result["valid"] is True
        assert result["errors"] == []
        assert "phoneScreenshots" in result["allowed"]

    def test_invalid(self) -> None:
        result = validate_image_type("PHONE_SCREENSHOTS")
        assert result["valid"] is False
        assert len(result["errors"]) == 1


class TestListStoreImagesTool:
    def test_invalid_image_type(self, mock_client: MagicMock) -> None:
        result = list_store_images(
            package_name="com.example.app",
            language="en-US",
            image_type="bogus",
        )
        assert result["success"] is False
        assert "image_type" in result["error"]
        mock_client.list_store_images.assert_not_called()

    def test_invalid_language(self, mock_client: MagicMock) -> None:
        result = list_store_images(
            package_name="com.example.app",
            language="badlang",
            image_type="icon",
        )
        assert result["success"] is False
        assert "language" in result["error"]
        mock_client.list_store_images.assert_not_called()

    def test_calls_client(self, mock_client: MagicMock) -> None:
        mock_client.list_store_images.return_value = [
            StoreImage(id="i1", url="u1"),
            StoreImage(id="i2", url="u2", sha1="aa", sha256="bb"),
        ]

        result = list_store_images(
            package_name="com.example.app",
            language="en-US",
            image_type="icon",
        )

        assert result["success"] is True
        assert len(result["images"]) == 2
        mock_client.list_store_images.assert_called_once_with("com.example.app", "en-US", "icon")

    def test_wraps_client_error(self, mock_client: MagicMock) -> None:
        mock_client.list_store_images.side_effect = PlayStoreClientError("Boom")
        result = list_store_images(
            package_name="com.example.app",
            language="en-US",
            image_type="icon",
        )
        assert result["success"] is False
        assert "Boom" in result["error"]


class TestUploadStoreImageTool:
    def test_invalid_image_type(self, mock_client: MagicMock, tmp_path: Any) -> None:
        result = upload_store_image(
            package_name="com.example.app",
            language="en-US",
            image_type="bogus",
            file_path=str(tmp_path / "x.png"),
        )
        assert result["success"] is False
        mock_client.upload_store_image.assert_not_called()

    def test_calls_client(self, mock_client: MagicMock, tmp_path: Any) -> None:
        png = tmp_path / "icon.png"
        png.write_bytes(b"\x89PNG")
        mock_client.upload_store_image.return_value = StoreImageUploadResult(
            success=True,
            package_name="com.example.app",
            language="en-US",
            image_type="icon",
            image=StoreImage(id="img-1", url="u"),
            message="Uploaded",
        )

        result = upload_store_image(
            package_name="com.example.app",
            language="en-US",
            image_type="icon",
            file_path=str(png),
        )

        assert result["success"] is True
        assert result["image"]["id"] == "img-1"
        mock_client.upload_store_image.assert_called_once_with(
            "com.example.app", "en-US", "icon", str(png)
        )


class TestDeleteStoreImageTool:
    def test_empty_image_id_rejected(self, mock_client: MagicMock) -> None:
        result = delete_store_image(
            package_name="com.example.app",
            language="en-US",
            image_type="icon",
            image_id="",
        )
        assert result["success"] is False
        mock_client.delete_store_image.assert_not_called()

    def test_calls_client(self, mock_client: MagicMock) -> None:
        mock_client.delete_store_image.return_value = StoreImageDeleteResult(
            success=True,
            package_name="com.example.app",
            language="en-US",
            image_type="icon",
            image_id="img-x",
            deleted_count=1,
            message="Deleted",
        )

        result = delete_store_image(
            package_name="com.example.app",
            language="en-US",
            image_type="icon",
            image_id="img-x",
        )

        assert result["success"] is True
        mock_client.delete_store_image.assert_called_once_with(
            "com.example.app", "en-US", "icon", "img-x"
        )


class TestDeleteAllStoreImagesTool:
    def test_calls_client(self, mock_client: MagicMock) -> None:
        mock_client.delete_all_store_images.return_value = StoreImageDeleteResult(
            success=True,
            package_name="com.example.app",
            language="en-US",
            image_type="phoneScreenshots",
            deleted_count=4,
            message="Deleted 4",
        )
        result = delete_all_store_images(
            package_name="com.example.app",
            language="en-US",
            image_type="phoneScreenshots",
        )
        assert result["success"] is True
        assert result["deleted_count"] == 4


class TestBatchUploadStoreImagesTool:
    def test_non_list_paths_rejected(self, mock_client: MagicMock) -> None:
        result = batch_upload_store_images(
            package_name="com.example.app",
            language="en-US",
            image_type="phoneScreenshots",
            file_paths="oops",  # type: ignore[arg-type]
        )
        assert result["success"] is False
        mock_client.batch_upload_store_images.assert_not_called()

    def test_calls_client(self, mock_client: MagicMock, tmp_path: Any) -> None:
        files = []
        for i in range(2):
            f = tmp_path / f"s{i}.png"
            f.write_bytes(b"\x89PNG")
            files.append(str(f))
        mock_client.batch_upload_store_images.return_value = BatchImageUploadResult(
            success=True,
            package_name="com.example.app",
            language="en-US",
            image_type="phoneScreenshots",
            uploaded=[StoreImage(id="img-1", url="u"), StoreImage(id="img-2", url="u")],
            successful_count=2,
            failed_count=0,
            message="ok",
        )

        result = batch_upload_store_images(
            package_name="com.example.app",
            language="en-US",
            image_type="phoneScreenshots",
            file_paths=files,
        )

        assert result["success"] is True
        assert result["successful_count"] == 2
        mock_client.batch_upload_store_images.assert_called_once_with(
            "com.example.app", "en-US", "phoneScreenshots", files
        )


# =========================================================================
# Group #3 — purchases.products + orders.refund server tools
# =========================================================================


from play_store_mcp.models import (  # noqa: E402
    ProductPurchase as _ProductPurchase,
)
from play_store_mcp.models import (  # noqa: E402
    PurchaseAckResult as _PurchaseAckResult,
)
from play_store_mcp.models import (  # noqa: E402
    RefundResult as _RefundResult,
)
from play_store_mcp.server import (  # noqa: E402
    acknowledge_product_purchase,
    consume_product_purchase,
    get_product_purchase,
    refund_order,
)


class TestGetProductPurchaseTool:
    def test_empty_token(self, mock_client: MagicMock) -> None:
        result = get_product_purchase(package_name="com.example.app", product_id="x", token="")
        assert result["success"] is False
        mock_client.get_product_purchase.assert_not_called()

    def test_happy(self, mock_client: MagicMock) -> None:
        mock_client.get_product_purchase.return_value = _ProductPurchase(
            package_name="com.example.app",
            product_id="premium",
            purchase_token="tok",
            purchase_state=0,
            consumption_state=0,
            order_id="GPA.0000-1111-2222-3333",
            acknowledgement_state=1,
            region_code="US",
        )

        result = get_product_purchase(
            package_name="com.example.app",
            product_id="premium",
            token="tok-abcdefgh",
        )

        assert result["success"] is True
        assert result["product_id"] == "premium"
        mock_client.get_product_purchase.assert_called_once_with(
            "com.example.app", "premium", "tok-abcdefgh"
        )

    def test_wraps_client_error(self, mock_client: MagicMock) -> None:
        mock_client.get_product_purchase.side_effect = PlayStoreClientError("Boom")
        result = get_product_purchase(
            package_name="com.example.app",
            product_id="premium",
            token="tok",
        )
        assert result["success"] is False
        assert "Boom" in result["error"]


class TestAcknowledgePurchaseTool:
    def test_calls_client(self, mock_client: MagicMock) -> None:
        mock_client.acknowledge_product_purchase.return_value = _PurchaseAckResult(
            success=True,
            package_name="com.example.app",
            product_id="x",
            operation="acknowledge",
            message="OK",
        )
        result = acknowledge_product_purchase(
            package_name="com.example.app",
            product_id="x",
            token="tok",
            developer_payload="meta",
        )
        assert result["success"] is True
        mock_client.acknowledge_product_purchase.assert_called_once_with(
            "com.example.app", "x", "tok", "meta"
        )


class TestConsumePurchaseTool:
    def test_calls_client(self, mock_client: MagicMock) -> None:
        mock_client.consume_product_purchase.return_value = _PurchaseAckResult(
            success=True,
            package_name="com.example.app",
            product_id="coins",
            operation="consume",
            message="ok",
        )
        result = consume_product_purchase(
            package_name="com.example.app", product_id="coins", token="tok-1234"
        )
        assert result["success"] is True


class TestRefundOrderTool:
    @pytest.mark.parametrize("bad", ["", "no_dot", "has spaces.x", "tab\tx"])
    def test_invalid_order_id_rejected(self, mock_client: MagicMock, bad: str) -> None:
        result = refund_order(package_name="com.example.app", order_id=bad)
        assert result["success"] is False
        mock_client.refund_order.assert_not_called()

    def test_happy_default_revoke_false(self, mock_client: MagicMock) -> None:
        mock_client.refund_order.return_value = _RefundResult(
            success=True,
            package_name="com.example.app",
            order_id="GPA.0001-2222-3333-4444",
            revoked=False,
            message="ok",
        )
        result = refund_order(package_name="com.example.app", order_id="GPA.0001-2222-3333-4444")
        assert result["success"] is True
        assert result["revoked"] is False
        mock_client.refund_order.assert_called_once_with(
            "com.example.app", "GPA.0001-2222-3333-4444", False
        )

    def test_explicit_revoke_true(self, mock_client: MagicMock) -> None:
        mock_client.refund_order.return_value = _RefundResult(
            success=True,
            package_name="com.example.app",
            order_id="GPA.0001-2222-3333-4444",
            revoked=True,
            message="ok",
        )
        result = refund_order(
            package_name="com.example.app",
            order_id="GPA.0001-2222-3333-4444",
            revoke=True,
        )
        assert result["success"] is True
        assert result["revoked"] is True
        mock_client.refund_order.assert_called_once_with(
            "com.example.app", "GPA.0001-2222-3333-4444", True
        )


# =========================================================================
# Group #4 — server tools
# =========================================================================


from play_store_mcp.models import (  # noqa: E402
    Apk as _Apk,
)
from play_store_mcp.models import (  # noqa: E402
    Bundle as _Bundle,
)
from play_store_mcp.models import (  # noqa: E402
    CountryAvailability as _CountryAvailability,
)
from play_store_mcp.models import (  # noqa: E402
    CustomTrackResult as _CustomTrackResult,
)
from play_store_mcp.models import (  # noqa: E402
    DeobfuscationResult as _DeobfuscationResult,
)
from play_store_mcp.models import (  # noqa: E402
    EditValidationResult as _EditValidationResult,
)
from play_store_mcp.server import (  # noqa: E402
    create_custom_track,
    get_country_availability,
    list_apks,
    list_bundles,
    upload_deobfuscation_file,
)
from play_store_mcp.server import (  # noqa: E402
    validate_edit as validate_edit_tool,
)


class TestUploadDeobfuscationTool:
    def test_negative_version_code(self, mock_client: MagicMock, tmp_path: Any) -> None:
        result = upload_deobfuscation_file(
            package_name="com.example.app",
            version_code=0,
            file_path=str(tmp_path / "m.txt"),
        )
        assert result["success"] is False
        mock_client.upload_deobfuscation_file.assert_not_called()

    def test_calls_client(self, mock_client: MagicMock, tmp_path: Any) -> None:
        f = tmp_path / "mapping.txt"
        f.write_text("x")
        mock_client.upload_deobfuscation_file.return_value = _DeobfuscationResult(
            success=True,
            package_name="com.example.app",
            version_code=100,
            file_type="proguard",
            message="ok",
        )
        result = upload_deobfuscation_file(
            package_name="com.example.app",
            version_code=100,
            file_path=str(f),
            file_type="proguard",
        )
        assert result["success"] is True
        mock_client.upload_deobfuscation_file.assert_called_once_with(
            "com.example.app", 100, str(f), "proguard"
        )


class TestListBundlesApksTool:
    def test_list_bundles(self, mock_client: MagicMock) -> None:
        mock_client.list_bundles.return_value = [
            _Bundle(version_code=100, sha1="a", sha256="b"),
        ]
        result = list_bundles(package_name="com.example.app")
        assert result["success"] is True
        assert len(result["bundles"]) == 1

    def test_list_apks(self, mock_client: MagicMock) -> None:
        mock_client.list_apks.return_value = [
            _Apk(version_code=50, sha256="x"),
        ]
        result = list_apks(package_name="com.example.app")
        assert result["success"] is True
        assert len(result["apks"]) == 1

    def test_list_bundles_wraps_error(self, mock_client: MagicMock) -> None:
        mock_client.list_bundles.side_effect = PlayStoreClientError("Boom")
        result = list_bundles(package_name="com.example.app")
        assert result["success"] is False
        assert "Boom" in result["error"]


class TestCountryAvailabilityTool:
    def test_happy(self, mock_client: MagicMock) -> None:
        mock_client.get_country_availability.return_value = _CountryAvailability(
            track="production",
            rest_of_world=True,
            sync_with_production=False,
            countries=["US", "DE"],
        )
        result = get_country_availability(package_name="com.example.app", track="production")
        assert result["success"] is True
        assert result["countries"] == ["US", "DE"]


class TestCreateCustomTrackTool:
    @pytest.mark.parametrize("ff", ["mobile", "default", "WEAR_OS"])
    def test_invalid_form_factor(self, mock_client: MagicMock, ff: str) -> None:
        result = create_custom_track(package_name="com.example.app", track="qa", form_factor=ff)
        assert result["success"] is False
        mock_client.create_custom_track.assert_not_called()

    def test_empty_track_rejected(self, mock_client: MagicMock) -> None:
        result = create_custom_track(package_name="com.example.app", track="")
        assert result["success"] is False
        mock_client.create_custom_track.assert_not_called()

    def test_happy(self, mock_client: MagicMock) -> None:
        mock_client.create_custom_track.return_value = _CustomTrackResult(
            success=True,
            package_name="com.example.app",
            track="qa-team",
            message="ok",
        )
        result = create_custom_track(package_name="com.example.app", track="qa-team")
        assert result["success"] is True
        mock_client.create_custom_track.assert_called_once_with(
            "com.example.app", "qa-team", "DEFAULT"
        )


class TestValidateEditTool:
    def test_empty_edit_id(self, mock_client: MagicMock) -> None:
        result = validate_edit_tool(package_name="com.example.app", edit_id="")
        assert result["success"] is False
        mock_client.validate_edit.assert_not_called()

    def test_calls_client(self, mock_client: MagicMock) -> None:
        mock_client.validate_edit.return_value = _EditValidationResult(
            success=True,
            package_name="com.example.app",
            edit_id="e1",
            valid=True,
            message="ok",
        )
        result = validate_edit_tool(package_name="com.example.app", edit_id="e1")
        assert result["success"] is True
        assert result["valid"] is True
