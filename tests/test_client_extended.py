"""Extended tests for PlayStoreClient — covers error paths, retry logic, and uncovered methods."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from play_store_mcp.client import (
    MAX_RETRIES,
    PlayStoreClient,
    PlayStoreClientError,
    retry_with_backoff,
)

# =========================================================================
# Helpers
# =========================================================================


def _make_http_error(status: int, reason: str = "error") -> HttpError:
    """Create a mock HttpError with given status."""
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=reason.encode())


# =========================================================================
# retry_with_backoff tests
# =========================================================================


class TestRetryWithBackoff:
    """Test the retry decorator."""

    @patch("play_store_mcp.client.time.sleep")
    def test_retries_on_500(self, mock_sleep: MagicMock) -> None:
        """Test that 500 errors trigger retries."""
        call_count = 0

        @retry_with_backoff
        def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise _make_http_error(500)
            return "ok"

        result = flaky()
        assert result == "ok"
        assert call_count == 3
        assert mock_sleep.call_count == 2

    @patch("play_store_mcp.client.time.sleep")
    def test_retries_on_429(self, _mock_sleep: MagicMock) -> None:
        """Test that 429 rate limit errors trigger retries."""
        call_count = 0

        @retry_with_backoff
        def rate_limited() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise _make_http_error(429)
            return "ok"

        result = rate_limited()
        assert result == "ok"
        assert call_count == 2

    @patch("play_store_mcp.client.time.sleep")
    def test_retries_on_503(self, _mock_sleep: MagicMock) -> None:
        """Test that 503 errors trigger retries."""
        call_count = 0

        @retry_with_backoff
        def unavailable() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise _make_http_error(503)
            return "ok"

        result = unavailable()
        assert result == "ok"

    def test_no_retry_on_400(self) -> None:
        """Test that 400 errors are not retried."""

        @retry_with_backoff
        def bad_request() -> str:
            raise _make_http_error(400)

        with pytest.raises(HttpError):
            bad_request()

    def test_no_retry_on_403(self) -> None:
        """Test that 403 errors are not retried."""

        @retry_with_backoff
        def forbidden() -> str:
            raise _make_http_error(403)

        with pytest.raises(HttpError):
            forbidden()

    def test_no_retry_on_non_http_error(self) -> None:
        """Test that non-HttpError exceptions are not retried."""

        @retry_with_backoff
        def broken() -> str:
            raise ValueError("not an http error")

        with pytest.raises(ValueError, match="not an http error"):
            broken()

    @patch("play_store_mcp.client.time.sleep")
    def test_max_retries_exceeded(self, mock_sleep: MagicMock) -> None:
        """Test that exceeding max retries raises the error."""

        @retry_with_backoff
        def always_fails() -> str:
            raise _make_http_error(500)

        with pytest.raises(HttpError):
            always_fails()

        # Should have slept MAX_RETRIES - 1 times then raised on the last attempt
        assert mock_sleep.call_count == MAX_RETRIES - 1

    def test_success_on_first_try(self) -> None:
        """Test that successful calls work without retries."""

        @retry_with_backoff
        def works() -> str:
            return "immediate"

        assert works() == "immediate"


# =========================================================================
# _get_service error path
# =========================================================================


class TestGetServiceErrors:
    """Test _get_service error handling."""

    def test_service_init_failure(self, tmp_path: Any) -> None:
        """Test that service initialization failure wraps the error."""
        creds_file = tmp_path / "bad-creds.json"
        creds_file.write_text('{"type": "invalid"}')

        client = PlayStoreClient(credentials_path=str(creds_file))

        with (
            patch(
                "play_store_mcp.client.service_account.Credentials.from_service_account_file",
                side_effect=ValueError("bad creds"),
            ),
            pytest.raises(PlayStoreClientError, match="Failed to initialize API client"),
        ):
            client._get_service()

    def test_cached_service_returned(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test that cached service is returned on subsequent calls."""
        svc1 = client._get_service()
        svc2 = client._get_service()
        assert svc1 is svc2


# =========================================================================
# deploy_app error paths
# =========================================================================


class TestDeployAppErrors:
    """Test deploy_app error handling."""

    def test_deploy_http_error(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
        tmp_path: Any,
    ) -> None:
        """Test deployment failure from HttpError."""
        apk_file = tmp_path / "app.apk"
        apk_file.write_bytes(b"content")

        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.apks.return_value.upload.return_value.execute.side_effect = _make_http_error(
            403, "forbidden"
        )
        mock_edits.delete.return_value.execute.return_value = None

        result = client.deploy_app(
            package_name="com.example.app",
            track="internal",
            file_path=str(apk_file),
        )

        assert result.success is False
        assert "Deployment failed" in result.message

    def test_deploy_generic_exception(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
        tmp_path: Any,
    ) -> None:
        """Test deployment failure from generic Exception."""
        apk_file = tmp_path / "app.apk"
        apk_file.write_bytes(b"content")

        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.apks.return_value.upload.return_value.execute.side_effect = RuntimeError(
            "disk full"
        )
        mock_edits.delete.return_value.execute.return_value = None

        result = client.deploy_app(
            package_name="com.example.app",
            track="internal",
            file_path=str(apk_file),
        )

        assert result.success is False
        assert "disk full" in result.message


# =========================================================================
# promote_release error paths
# =========================================================================


class TestPromoteReleaseErrors:
    """Test promote_release error handling."""

    def test_promote_http_error(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test promotion failure from HttpError."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.tracks.return_value.get.return_value.execute.side_effect = _make_http_error(
            404, "not found"
        )
        mock_edits.delete.return_value.execute.return_value = None

        result = client.promote_release(
            package_name="com.example.app",
            from_track="beta",
            to_track="production",
            version_code=100,
        )

        assert result.success is False
        assert "Promotion failed" in result.message

    def test_promote_generic_exception(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test promotion failure from generic Exception."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.tracks.return_value.get.return_value.execute.side_effect = RuntimeError("boom")
        mock_edits.delete.return_value.execute.return_value = None

        result = client.promote_release(
            package_name="com.example.app",
            from_track="beta",
            to_track="production",
            version_code=100,
        )

        assert result.success is False
        assert "boom" in result.message

    def test_promote_staged_rollout(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test promotion with staged rollout percentage."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.tracks.return_value.get.return_value.execute.return_value = {
            "track": "beta",
            "releases": [{"versionCodes": ["100"], "releaseNotes": []}],
        }
        mock_edits.tracks.return_value.update.return_value.execute.return_value = {}
        mock_edits.commit.return_value.execute.return_value = {}

        result = client.promote_release(
            package_name="com.example.app",
            from_track="beta",
            to_track="production",
            version_code=100,
            rollout_percentage=25.0,
        )

        assert result.success is True
        update_call = mock_edits.tracks.return_value.update.call_args
        body = update_call.kwargs["body"]
        assert body["releases"][0]["status"] == "inProgress"
        assert body["releases"][0]["userFraction"] == 0.25


# =========================================================================
# halt_release tests
# =========================================================================


class TestHaltRelease:
    """Test halt_release method."""

    def test_halt_success(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test successful halt."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.tracks.return_value.get.return_value.execute.return_value = {
            "track": "production",
            "releases": [{"versionCodes": ["100"], "status": "inProgress"}],
        }
        mock_edits.tracks.return_value.update.return_value.execute.return_value = {}
        mock_edits.commit.return_value.execute.return_value = {}

        result = client.halt_release("com.example.app", "production", 100)

        assert result.success is True
        assert "halted" in result.message.lower()

    def test_halt_version_not_found(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test halt with nonexistent version."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.tracks.return_value.get.return_value.execute.return_value = {
            "track": "production",
            "releases": [{"versionCodes": ["99"]}],
        }
        mock_edits.delete.return_value.execute.return_value = None

        result = client.halt_release("com.example.app", "production", 100)

        assert result.success is False
        assert "not found" in result.message

    def test_halt_http_error(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test halt failure from HttpError."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.tracks.return_value.get.return_value.execute.side_effect = _make_http_error(500)
        mock_edits.delete.return_value.execute.return_value = None

        result = client.halt_release("com.example.app", "production", 100)

        assert result.success is False
        assert "Halt failed" in result.message

    def test_halt_generic_exception(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test halt failure from generic Exception."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.tracks.return_value.get.return_value.execute.side_effect = RuntimeError("oops")
        mock_edits.delete.return_value.execute.return_value = None

        result = client.halt_release("com.example.app", "production", 100)

        assert result.success is False
        assert "oops" in result.message


# =========================================================================
# update_rollout tests
# =========================================================================


class TestUpdateRollout:
    """Test update_rollout method."""

    def test_update_rollout_success(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test successful rollout update."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.tracks.return_value.get.return_value.execute.return_value = {
            "track": "production",
            "releases": [{"versionCodes": ["100"], "status": "inProgress", "userFraction": 0.1}],
        }
        mock_edits.tracks.return_value.update.return_value.execute.return_value = {}
        mock_edits.commit.return_value.execute.return_value = {}

        result = client.update_rollout("com.example.app", "production", 100, 50.0)

        assert result.success is True
        assert "50.0%" in result.message

    def test_update_rollout_complete(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test completing a rollout (100%)."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.tracks.return_value.get.return_value.execute.return_value = {
            "track": "production",
            "releases": [{"versionCodes": ["100"], "status": "inProgress", "userFraction": 0.5}],
        }
        mock_edits.tracks.return_value.update.return_value.execute.return_value = {}
        mock_edits.commit.return_value.execute.return_value = {}

        result = client.update_rollout("com.example.app", "production", 100, 100.0)

        assert result.success is True

    def test_update_rollout_version_not_found(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test rollout update with nonexistent version."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.tracks.return_value.get.return_value.execute.return_value = {
            "track": "production",
            "releases": [{"versionCodes": ["99"]}],
        }
        mock_edits.delete.return_value.execute.return_value = None

        result = client.update_rollout("com.example.app", "production", 100, 50.0)

        assert result.success is False
        assert "not found" in result.message

    def test_update_rollout_http_error(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test rollout update failure from HttpError."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.tracks.return_value.get.return_value.execute.side_effect = _make_http_error(500)
        mock_edits.delete.return_value.execute.return_value = None

        result = client.update_rollout("com.example.app", "production", 100, 50.0)

        assert result.success is False

    def test_update_rollout_generic_exception(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test rollout update failure from generic Exception."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.tracks.return_value.get.return_value.execute.side_effect = RuntimeError("fail")
        mock_edits.delete.return_value.execute.return_value = None

        result = client.update_rollout("com.example.app", "production", 100, 50.0)

        assert result.success is False
        assert "fail" in result.message


# =========================================================================
# get_app_details tests
# =========================================================================


class TestGetAppDetails:
    """Test get_app_details method."""

    def test_get_app_details_listing_not_found(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test get_app_details when listing is not found for language."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.details.return_value.get.return_value.execute.return_value = {
            "defaultLanguage": "en-US",
            "contactEmail": "dev@example.com",
        }
        # Listing fetch fails with 404
        mock_edits.listings.return_value.get.return_value.execute.side_effect = _make_http_error(
            404
        )
        mock_edits.delete.return_value.execute.return_value = None

        details = client.get_app_details("com.example.app", "fr-FR")

        assert details.package_name == "com.example.app"
        assert details.title is None  # No listing found
        assert details.default_language == "en-US"


# =========================================================================
# Reviews error paths
# =========================================================================


class TestReviewsExtended:
    """Extended review tests."""

    def test_get_reviews_with_translation(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test get_reviews with translation language."""
        _mock_service.reviews.return_value.list.return_value.execute.return_value = {
            "reviews": [
                {
                    "reviewId": "r1",
                    "authorName": "User",
                    "comments": [
                        {
                            "userComment": {
                                "starRating": 4,
                                "text": "Good",
                                "reviewerLanguage": "es",
                                "lastModified": {"seconds": "1700000000", "nanos": 0},
                            }
                        }
                    ],
                }
            ]
        }

        reviews = client.get_reviews("com.example.app", translation_language="en")

        assert len(reviews) == 1
        assert reviews[0].star_rating == 4

    def test_get_reviews_http_error(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test get_reviews HttpError."""
        _mock_service.reviews.return_value.list.return_value.execute.side_effect = _make_http_error(
            403
        )

        with pytest.raises(PlayStoreClientError, match="Failed to fetch reviews"):
            client.get_reviews("com.example.app")

    def test_reply_to_review_http_error(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test reply_to_review HttpError."""
        _mock_service.reviews.return_value.reply.return_value.execute.side_effect = (
            _make_http_error(403)
        )

        result = client.reply_to_review("com.example.app", "r1", "Thanks!")

        assert result.success is False
        assert "Failed to reply" in result.message


# =========================================================================
# Subscriptions error paths
# =========================================================================


class TestSubscriptionsExtended:
    """Extended subscription tests."""

    def test_list_subscriptions_http_error(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test list_subscriptions HttpError."""
        _mock_service.monetization.return_value.subscriptions.return_value.list.return_value.execute.side_effect = _make_http_error(
            403
        )

        with pytest.raises(PlayStoreClientError, match="Failed to list subscriptions"):
            client.list_subscriptions("com.example.app")

    def test_get_subscription_purchase_success(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test successful subscription purchase fetch."""
        _mock_service.purchases.return_value.subscriptionsv2.return_value.get.return_value.execute.return_value = {
            "latestOrderId": "order-123",
            "subscriptionState": "SUBSCRIPTION_STATE_ACTIVE",
            "lineItems": [
                {
                    "productId": "premium",
                    "autoRenewingPlan": {"autoRenewEnabled": True},
                }
            ],
        }

        result = client.get_subscription_purchase("com.example.app", "premium", "token123")

        assert result.subscription_id == "premium"
        assert result.auto_renewing is True
        assert result.order_id == "order-123"

    def test_get_subscription_purchase_inactive(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test subscription purchase that is not active."""
        _mock_service.purchases.return_value.subscriptionsv2.return_value.get.return_value.execute.return_value = {
            "latestOrderId": "order-456",
            "subscriptionState": "SUBSCRIPTION_STATE_EXPIRED",
            "lineItems": [
                {
                    "productId": "premium",
                    "autoRenewingPlan": {"autoRenewEnabled": False},
                }
            ],
        }

        result = client.get_subscription_purchase("com.example.app", "premium", "token456")

        assert result.auto_renewing is False

    def test_get_subscription_purchase_http_error(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test get_subscription_purchase HttpError."""
        _mock_service.purchases.return_value.subscriptionsv2.return_value.get.return_value.execute.side_effect = _make_http_error(
            404
        )

        with pytest.raises(PlayStoreClientError, match="Failed to get subscription status"):
            client.get_subscription_purchase("com.example.app", "premium", "token")


# =========================================================================
# Voided purchases
# =========================================================================


class TestVoidedPurchases:
    """Test voided purchases methods."""

    def test_list_voided_purchases_success(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test successful voided purchases fetch."""
        _mock_service.purchases.return_value.voidedpurchases.return_value.list.return_value.execute.return_value = {
            "voidedPurchases": [
                {
                    "purchaseToken": "tok1",
                    "orderId": "order1",
                    "voidedReason": 1,
                    "voidedSource": 0,
                    "voidedTimeMillis": "1700000000000",
                },
                {
                    "purchaseToken": "tok2",
                    "orderId": "order2",
                    "voidedTimeMillis": "1700000100000",
                },
            ]
        }

        voided = client.list_voided_purchases("com.example.app")

        assert len(voided) == 2
        assert voided[0].purchase_token == "tok1"
        assert voided[0].voided_reason == 1
        assert voided[1].order_id == "order2"

    def test_list_voided_purchases_empty(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test voided purchases when none exist."""
        _mock_service.purchases.return_value.voidedpurchases.return_value.list.return_value.execute.return_value = {}

        voided = client.list_voided_purchases("com.example.app")

        assert voided == []

    def test_list_voided_purchases_http_error(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test list_voided_purchases HttpError."""
        _mock_service.purchases.return_value.voidedpurchases.return_value.list.return_value.execute.side_effect = _make_http_error(
            403
        )

        with pytest.raises(PlayStoreClientError, match="Failed to list voided purchases"):
            client.list_voided_purchases("com.example.app")


# =========================================================================
# Listing update error paths
# =========================================================================


class TestUpdateListingErrors:
    """Test update_listing error handling."""

    def test_update_listing_http_error(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test update_listing HttpError."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.listings.return_value.get.return_value.execute.return_value = {
            "title": "Old",
            "fullDescription": "Old desc",
            "shortDescription": "Old short",
        }
        mock_edits.listings.return_value.update.return_value.execute.side_effect = _make_http_error(
            403
        )
        mock_edits.delete.return_value.execute.return_value = None

        result = client.update_listing(
            package_name="com.example.app",
            language="en-US",
            title="New Title",
        )

        assert result.success is False
        assert "Failed to update listing" in result.message

    def test_update_listing_generic_exception(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test update_listing generic Exception."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.listings.return_value.get.return_value.execute.return_value = {}
        mock_edits.listings.return_value.update.return_value.execute.side_effect = RuntimeError(
            "boom"
        )
        mock_edits.delete.return_value.execute.return_value = None

        result = client.update_listing(
            package_name="com.example.app",
            language="en-US",
            full_description="New desc",
        )

        assert result.success is False
        assert "boom" in result.message

    def test_update_listing_current_listing_not_found(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test update_listing when current listing doesn't exist."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        # Current listing fetch fails
        mock_edits.listings.return_value.get.return_value.execute.side_effect = _make_http_error(
            404
        )
        mock_edits.listings.return_value.update.return_value.execute.return_value = {}
        mock_edits.commit.return_value.execute.return_value = {}

        # Need to reset side_effect after first call
        call_count = 0

        def get_side_effect() -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _make_http_error(404)
            return {}

        mock_edits.listings.return_value.get.return_value.execute.side_effect = get_side_effect

        result = client.update_listing(
            package_name="com.example.app",
            language="en-US",
            title="Brand New",
            short_description="New short",
        )

        assert result.success is True


# =========================================================================
# Testers error paths
# =========================================================================


class TestTestersExtended:
    """Extended testers tests."""

    def test_get_testers_404(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test get_testers when no testers configured (404)."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.testers.return_value.get.return_value.execute.side_effect = _make_http_error(404)
        mock_edits.delete.return_value.execute.return_value = None

        testers = client.get_testers("com.example.app", "internal")

        assert testers.track == "internal"
        assert testers.google_groups == []

    def test_get_testers_other_error(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test get_testers with non-404 error."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.testers.return_value.get.return_value.execute.side_effect = _make_http_error(500)
        mock_edits.delete.return_value.execute.return_value = None

        with pytest.raises(PlayStoreClientError, match="Failed to get testers"):
            client.get_testers("com.example.app", "internal")

    def test_update_testers_http_error(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test update_testers HttpError."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.testers.return_value.update.return_value.execute.side_effect = _make_http_error(
            403
        )
        mock_edits.delete.return_value.execute.return_value = None

        result = client.update_testers("com.example.app", "beta", ["test@example.com"])

        assert result["success"] is False
        assert result["error"]


# =========================================================================
# Orders error paths
# =========================================================================


class TestOrdersExtended:
    """Extended orders tests."""

    def test_get_order_http_error(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test get_order HttpError."""
        _mock_service.orders.return_value.get.return_value.execute.side_effect = _make_http_error(
            404
        )

        with pytest.raises(PlayStoreClientError, match="Failed to get order"):
            client.get_order("com.example.app", "order-123")


# =========================================================================
# Expansion files error paths
# =========================================================================


class TestExpansionFilesExtended:
    """Extended expansion file tests."""

    def test_get_expansion_file_404(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test get_expansion_file when no expansion file exists (404)."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.expansionfiles.return_value.get.return_value.execute.side_effect = (
            _make_http_error(404)
        )
        mock_edits.delete.return_value.execute.return_value = None

        expansion = client.get_expansion_file("com.example.app", 100, "main")

        assert expansion.version_code == 100
        assert expansion.file_size is None

    def test_get_expansion_file_other_error(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test get_expansion_file with non-404 error."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.expansionfiles.return_value.get.return_value.execute.side_effect = (
            _make_http_error(500)
        )
        mock_edits.delete.return_value.execute.return_value = None

        with pytest.raises(PlayStoreClientError, match="Failed to get expansion file"):
            client.get_expansion_file("com.example.app", 100, "main")


# =========================================================================
# Validation edge cases
# =========================================================================


class TestValidationExtended:
    """Extended validation tests."""

    def test_validate_empty_package_name(self, client: PlayStoreClient) -> None:
        """Test validating empty package name."""
        errors = client.validate_package_name("")
        assert len(errors) == 1
        assert "empty" in errors[0].message.lower()

    def test_validate_short_description_too_long(self, client: PlayStoreClient) -> None:
        """Test validating short description that's too long."""
        errors = client.validate_listing_text(short_description="A" * 81)
        assert len(errors) == 1
        assert "short_description" in errors[0].field

    def test_validate_full_description_too_long(self, client: PlayStoreClient) -> None:
        """Test validating full description that's too long."""
        errors = client.validate_listing_text(full_description="A" * 4001)
        assert len(errors) == 1
        assert "full_description" in errors[0].field

    def test_validate_all_listing_text_too_long(self, client: PlayStoreClient) -> None:
        """Test validating all listing text fields too long."""
        errors = client.validate_listing_text(
            title="A" * 51,
            short_description="B" * 81,
            full_description="C" * 4001,
        )
        assert len(errors) == 3


# =========================================================================
# Batch deploy edge cases
# =========================================================================


class TestBatchDeployExtended:
    """Extended batch deploy tests."""

    def test_batch_deploy_with_rollout_percentages(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
        tmp_path: Any,
    ) -> None:
        """Test batch deploy with custom rollout percentages."""
        apk_file = tmp_path / "app.apk"
        apk_file.write_bytes(b"content")

        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.apks.return_value.upload.return_value.execute.return_value = {"versionCode": 100}
        mock_edits.tracks.return_value.update.return_value.execute.return_value = {}
        mock_edits.commit.return_value.execute.return_value = {}

        result = client.batch_deploy(
            package_name="com.example.app",
            file_path=str(apk_file),
            tracks=["internal", "production"],
            release_notes="Test",
            rollout_percentages={"production": 10.0},
        )

        assert result.success is True
        assert result.successful_count == 2

    def test_batch_deploy_partial_failure(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
        tmp_path: Any,
    ) -> None:
        """Test batch deploy where one track fails."""
        apk_file = tmp_path / "app.apk"
        apk_file.write_bytes(b"content")

        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}

        call_count = 0

        def upload_side_effect(**_kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            mock = MagicMock()
            if call_count > 1:
                mock.execute.side_effect = _make_http_error(403)
            else:
                mock.execute.return_value = {"versionCode": 100}
            return mock

        mock_edits.apks.return_value.upload.side_effect = upload_side_effect
        mock_edits.tracks.return_value.update.return_value.execute.return_value = {}
        mock_edits.commit.return_value.execute.return_value = {}
        mock_edits.delete.return_value.execute.return_value = None

        result = client.batch_deploy(
            package_name="com.example.app",
            file_path=str(apk_file),
            tracks=["internal", "beta"],
        )

        assert result.success is False
        assert result.successful_count == 1
        assert result.failed_count == 1
        assert "failed" in result.message.lower()


# =========================================================================
# _delete_edit edge case
# =========================================================================


class TestDeleteEdit:
    """Test _delete_edit error handling."""

    def test_delete_edit_ignores_http_error(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test that _delete_edit silently ignores HttpError."""
        # First call _get_service to initialize
        client._get_service()

        _mock_service.edits.return_value.delete.return_value.execute.side_effect = _make_http_error(
            404
        )

        # Should not raise
        client._delete_edit("com.example.app", "edit-123")


# =========================================================================
# Empty responses edge cases (#40)
# =========================================================================


class TestEmptyResponses:
    """Test handling of empty API responses."""

    def test_get_reviews_empty(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test get_reviews with empty response."""
        _mock_service.reviews.return_value.list.return_value.execute.return_value = {}

        reviews = client.get_reviews("com.example.app")

        assert reviews == []

    def test_get_releases_empty_tracks(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test get_releases with empty tracks."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.tracks.return_value.list.return_value.execute.return_value = {"tracks": []}
        mock_edits.delete.return_value.execute.return_value = None

        tracks = client.get_releases("com.example.app")

        assert tracks == []

    def test_batch_deploy_empty_tracks(
        self,
        client: PlayStoreClient,
        tmp_path: Any,
    ) -> None:
        """Test batch_deploy with empty tracks list."""
        apk_file = tmp_path / "app.apk"
        apk_file.write_bytes(b"content")

        result = client.batch_deploy(
            package_name="com.example.app",
            file_path=str(apk_file),
            tracks=[],
        )

        assert result.success is True
        assert result.successful_count == 0
        assert result.failed_count == 0


# =========================================================================
# Boundary values (#40)
# =========================================================================


class TestBoundaryValues:
    """Test boundary value conditions."""

    def test_rollout_percentage_zero(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
        tmp_path: Any,
    ) -> None:
        """Test deployment with rollout_percentage=0.0."""
        apk_file = tmp_path / "app.apk"
        apk_file.write_bytes(b"content")

        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.apks.return_value.upload.return_value.execute.return_value = {"versionCode": 100}
        mock_edits.tracks.return_value.update.return_value.execute.return_value = {}
        mock_edits.commit.return_value.execute.return_value = {}

        result = client.deploy_app(
            package_name="com.example.app",
            track="production",
            file_path=str(apk_file),
            rollout_percentage=0.0,
        )

        assert result.success is True
        update_call = mock_edits.tracks.return_value.update.call_args
        body = update_call.kwargs["body"]
        assert body["releases"][0]["status"] == "inProgress"
        assert body["releases"][0]["userFraction"] == 0.0

    def test_rollout_percentage_100(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
        tmp_path: Any,
    ) -> None:
        """Test deployment with rollout_percentage=100.0."""
        apk_file = tmp_path / "app.apk"
        apk_file.write_bytes(b"content")

        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.return_value = {"id": "edit-123"}
        mock_edits.apks.return_value.upload.return_value.execute.return_value = {"versionCode": 100}
        mock_edits.tracks.return_value.update.return_value.execute.return_value = {}
        mock_edits.commit.return_value.execute.return_value = {}

        result = client.deploy_app(
            package_name="com.example.app",
            track="production",
            file_path=str(apk_file),
            rollout_percentage=100.0,
        )

        assert result.success is True
        update_call = mock_edits.tracks.return_value.update.call_args
        body = update_call.kwargs["body"]
        assert body["releases"][0]["status"] == "completed"

    def test_validate_listing_text_exactly_50_chars(self, client: PlayStoreClient) -> None:
        """Test title at exactly 50 characters (valid)."""
        errors = client.validate_listing_text(title="A" * 50)
        assert len(errors) == 0

    def test_validate_listing_text_exactly_80_chars(self, client: PlayStoreClient) -> None:
        """Test short_description at exactly 80 characters (valid)."""
        errors = client.validate_listing_text(short_description="B" * 80)
        assert len(errors) == 0

    def test_validate_listing_text_exactly_4000_chars(self, client: PlayStoreClient) -> None:
        """Test full_description at exactly 4000 characters (valid)."""
        errors = client.validate_listing_text(full_description="C" * 4000)
        assert len(errors) == 0


# =========================================================================
# Edit failures (#40)
# =========================================================================


class TestEditFailures:
    """Test _create_edit and _commit_edit failure handling."""

    def test_create_edit_failure(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test _create_edit failure propagates."""
        mock_edits = _mock_service.edits.return_value
        mock_edits.insert.return_value.execute.side_effect = _make_http_error(403, "forbidden")

        with pytest.raises(HttpError):
            client._create_edit("com.example.app")

    def test_commit_edit_failure(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        """Test _commit_edit failure propagates."""
        # Initialize service first
        client._get_service()

        mock_edits = _mock_service.edits.return_value
        mock_edits.commit.return_value.execute.side_effect = _make_http_error(500, "server error")

        with pytest.raises(HttpError):
            client._commit_edit("com.example.app", "edit-123")


# =========================================================================
# Group #1 — edits.images (StoreImage tools)
# =========================================================================


class TestStoreImagesValidation:
    """Validation helpers for the images group."""

    def test_validate_image_file_resolves_path(self, tmp_path: Any) -> None:
        png = tmp_path / "icon.png"
        png.write_bytes(b"\x89PNG")
        resolved = PlayStoreClient._validate_image_file(str(png))
        assert resolved == png.resolve()

    def test_validate_image_file_rejects_missing(self, tmp_path: Any) -> None:
        with pytest.raises(ValueError, match="File not found"):
            PlayStoreClient._validate_image_file(str(tmp_path / "no.png"))

    def test_validate_image_file_rejects_directory(self, tmp_path: Any) -> None:
        with pytest.raises(ValueError, match="Not a regular file"):
            PlayStoreClient._validate_image_file(str(tmp_path))

    def test_validate_image_file_rejects_bad_extension(self, tmp_path: Any) -> None:
        gif = tmp_path / "img.gif"
        gif.write_bytes(b"GIF89a")
        with pytest.raises(ValueError, match=r"\.png/\.jpg/\.jpeg"):
            PlayStoreClient._validate_image_file(str(gif))

    def test_validate_image_file_traversal_canonicalised(self, tmp_path: Any) -> None:
        png = tmp_path / "icon.png"
        png.write_bytes(b"\x89PNG")
        nested = tmp_path / "sub" / ".."
        nested.mkdir(parents=True, exist_ok=True)
        traversal = str(nested / "icon.png")
        resolved = PlayStoreClient._validate_image_file(traversal)
        assert resolved == png.resolve()
        assert ".." not in str(resolved)

    @pytest.mark.parametrize(
        "ext",
        [".png", ".PNG", ".jpg", ".JPG", ".jpeg", ".JPEG"],
    )
    def test_validate_image_file_accepts_case_variants(self, tmp_path: Any, ext: str) -> None:
        f = tmp_path / f"a{ext}"
        f.write_bytes(b"data")
        assert PlayStoreClient._validate_image_file(str(f)) == f.resolve()


class TestListStoreImages:
    """list_store_images happy + failure paths."""

    def test_happy_path(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        edits = _mock_service.edits.return_value
        edits.insert.return_value.execute.return_value = {"id": "edit-1"}
        edits.images.return_value.list.return_value.execute.return_value = {
            "images": [
                {"id": "img-1", "url": "https://x", "sha1": "abc", "sha256": "def"},
                {"id": "img-2", "url": "https://y"},
            ]
        }

        result = client.list_store_images("com.example.app", "en-US", "icon")

        assert len(result) == 2
        assert result[0].id == "img-1"
        assert result[0].sha256 == "def"
        assert result[1].sha1 is None
        edits.images.return_value.list.assert_called_once_with(
            packageName="com.example.app",
            editId="edit-1",
            language="en-US",
            imageType="icon",
        )
        edits.delete.return_value.execute.assert_called_once()

    def test_unknown_image_type_rejected_before_api(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        with pytest.raises(ValueError):
            client.list_store_images("com.example.app", "en-US", "bogus")
        _mock_service.edits.return_value.images.return_value.list.assert_not_called()

    def test_http_error_raises(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        edits = _mock_service.edits.return_value
        edits.insert.return_value.execute.return_value = {"id": "edit-1"}
        edits.images.return_value.list.return_value.execute.side_effect = _make_http_error(
            403, "forbidden"
        )

        with pytest.raises(PlayStoreClientError):
            client.list_store_images("com.example.app", "en-US", "icon")

        # Cleanup is in finally
        edits.delete.return_value.execute.assert_called_once()


class TestUploadStoreImage:
    """upload_store_image happy + failure paths."""

    def test_happy_path(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
        tmp_path: Any,
    ) -> None:
        png = tmp_path / "icon.png"
        png.write_bytes(b"\x89PNG")
        edits = _mock_service.edits.return_value
        edits.insert.return_value.execute.return_value = {"id": "edit-up"}
        edits.images.return_value.upload.return_value.execute.return_value = {
            "image": {
                "id": "img-new",
                "url": "https://cdn/img-new",
                "sha256": "deadbeef",
            }
        }

        result = client.upload_store_image("com.example.app", "en-US", "icon", str(png))

        assert result.success is True
        assert result.image is not None
        assert result.image.id == "img-new"
        assert result.image.sha256 == "deadbeef"
        edits.commit.return_value.execute.assert_called_once_with()
        edits.delete.return_value.execute.assert_not_called()
        # Verify call shape
        upload_call = edits.images.return_value.upload.call_args
        assert upload_call.kwargs["packageName"] == "com.example.app"
        assert upload_call.kwargs["editId"] == "edit-up"
        assert upload_call.kwargs["language"] == "en-US"
        assert upload_call.kwargs["imageType"] == "icon"

    def test_returns_failure_on_missing_file(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
        tmp_path: Any,
    ) -> None:
        result = client.upload_store_image(
            "com.example.app",
            "en-US",
            "icon",
            str(tmp_path / "absent.png"),
        )
        assert result.success is False
        assert "File not found" in result.message
        # API not touched
        _mock_service.edits.return_value.insert.assert_not_called()

    def test_failure_cleans_up_edit(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
        tmp_path: Any,
    ) -> None:
        png = tmp_path / "icon.png"
        png.write_bytes(b"\x89PNG")
        edits = _mock_service.edits.return_value
        edits.insert.return_value.execute.return_value = {"id": "edit-fail"}
        edits.images.return_value.upload.return_value.execute.side_effect = _make_http_error(
            400, "bad image dimensions"
        )

        result = client.upload_store_image("com.example.app", "en-US", "icon", str(png))

        assert result.success is False
        assert "Upload failed" in result.message
        edits.commit.return_value.execute.assert_not_called()
        edits.delete.assert_called_once_with(packageName="com.example.app", editId="edit-fail")


class TestDeleteStoreImage:
    """delete_store_image and delete_all_store_images."""

    def test_delete_single_happy(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        edits = _mock_service.edits.return_value
        edits.insert.return_value.execute.return_value = {"id": "edit-del"}
        edits.images.return_value.delete.return_value.execute.return_value = None

        result = client.delete_store_image("com.example.app", "en-US", "icon", "img-xyz")

        assert result.success is True
        assert result.deleted_count == 1
        edits.images.return_value.delete.assert_called_once_with(
            packageName="com.example.app",
            editId="edit-del",
            language="en-US",
            imageType="icon",
            imageId="img-xyz",
        )
        edits.commit.return_value.execute.assert_called_once()
        # cleanup edit not used on success
        edits.delete.assert_not_called()

    def test_delete_single_failure_cleans_up(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        edits = _mock_service.edits.return_value
        edits.insert.return_value.execute.return_value = {"id": "edit-del-x"}
        edits.images.return_value.delete.return_value.execute.side_effect = _make_http_error(
            404, "not found"
        )

        result = client.delete_store_image("com.example.app", "en-US", "icon", "missing")

        assert result.success is False
        assert "Delete failed" in result.message
        edits.delete.assert_called_once_with(packageName="com.example.app", editId="edit-del-x")
        edits.commit.return_value.execute.assert_not_called()

    def test_delete_all_happy(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        edits = _mock_service.edits.return_value
        edits.insert.return_value.execute.return_value = {"id": "edit-da"}
        edits.images.return_value.deleteall.return_value.execute.return_value = {
            "deleted": [
                {"id": "img-a"},
                {"id": "img-b"},
                {"id": "img-c"},
            ]
        }

        result = client.delete_all_store_images("com.example.app", "en-US", "phoneScreenshots")

        assert result.success is True
        assert result.deleted_count == 3
        edits.images.return_value.deleteall.assert_called_once_with(
            packageName="com.example.app",
            editId="edit-da",
            language="en-US",
            imageType="phoneScreenshots",
        )
        edits.commit.return_value.execute.assert_called_once()


class TestBatchUploadStoreImages:
    """batch_upload_store_images: one edit, multiple files."""

    def test_happy_batch(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
        tmp_path: Any,
    ) -> None:
        files = [tmp_path / f"s{i}.png" for i in range(3)]
        for f in files:
            f.write_bytes(b"\x89PNG")
        edits = _mock_service.edits.return_value
        edits.insert.return_value.execute.return_value = {"id": "edit-batch"}
        edits.images.return_value.upload.return_value.execute.side_effect = [
            {"image": {"id": f"img-{i}", "url": f"https://x/{i}"}} for i in range(3)
        ]

        result = client.batch_upload_store_images(
            "com.example.app",
            "en-US",
            "phoneScreenshots",
            [str(f) for f in files],
        )

        assert result.success is True
        assert result.successful_count == 3
        assert result.failed_count == 0
        # Single edit session used
        assert edits.insert.call_count == 1
        edits.commit.return_value.execute.assert_called_once()
        edits.delete.assert_not_called()
        # Three uploads
        assert edits.images.return_value.upload.call_count == 3

    def test_empty_paths_short_circuits(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        result = client.batch_upload_store_images("com.example.app", "en-US", "icon", [])
        assert result.success is False
        assert "empty" in result.message.lower()
        _mock_service.edits.return_value.insert.assert_not_called()

    def test_invalid_path_short_circuits(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
        tmp_path: Any,
    ) -> None:
        bad = tmp_path / "nope.png"
        result = client.batch_upload_store_images("com.example.app", "en-US", "icon", [str(bad)])
        assert result.success is False
        assert "File not found" in result.message
        _mock_service.edits.return_value.insert.assert_not_called()

    def test_partial_failure_cleans_up_and_reports(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
        tmp_path: Any,
    ) -> None:
        f1 = tmp_path / "a.png"
        f2 = tmp_path / "b.png"
        f3 = tmp_path / "c.png"
        for f in (f1, f2, f3):
            f.write_bytes(b"\x89PNG")
        edits = _mock_service.edits.return_value
        edits.insert.return_value.execute.return_value = {"id": "edit-partial"}
        edits.images.return_value.upload.return_value.execute.side_effect = [
            {"image": {"id": "img-1", "url": "u"}},
            _make_http_error(400, "bad image"),
        ]

        result = client.batch_upload_store_images(
            "com.example.app",
            "en-US",
            "phoneScreenshots",
            [str(f1), str(f2), str(f3)],
        )

        assert result.success is False
        assert result.successful_count == 1
        assert result.failed_count == 2
        edits.delete.assert_called_once_with(packageName="com.example.app", editId="edit-partial")
        edits.commit.return_value.execute.assert_not_called()


# =========================================================================
# Group #3 — purchases.products + orders.refund
# =========================================================================


class TestGetProductPurchase:
    def test_happy_path(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        _mock_service.purchases.return_value.products.return_value.get.return_value.execute.return_value = {
            "productId": "premium",
            "purchaseState": 0,
            "consumptionState": 0,
            "orderId": "GPA.0000-1111-2222-3333",
            "purchaseTimeMillis": "1700000000000",
            "acknowledgementState": 1,
            "regionCode": "US",
            "quantity": 1,
        }

        result = client.get_product_purchase("com.example.app", "premium", "tok-abcdefgh")

        assert result.product_id == "premium"
        assert result.purchase_state == 0
        assert result.acknowledgement_state == 1
        assert result.order_id == "GPA.0000-1111-2222-3333"
        assert result.region_code == "US"
        assert result.purchase_time is not None
        _mock_service.purchases.return_value.products.return_value.get.assert_called_once_with(
            packageName="com.example.app",
            productId="premium",
            token="tok-abcdefgh",
        )

    def test_empty_token_rejected(self, client: PlayStoreClient) -> None:
        with pytest.raises(ValueError):
            client.get_product_purchase("com.example.app", "premium", "")

    def test_404_raises_client_error(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        _mock_service.purchases.return_value.products.return_value.get.return_value.execute.side_effect = _make_http_error(
            404, "not found"
        )
        with pytest.raises(PlayStoreClientError):
            client.get_product_purchase("com.example.app", "premium", "tok-abcdefgh")


class TestAcknowledgeProductPurchase:
    def test_happy_no_payload(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        _mock_service.purchases.return_value.products.return_value.acknowledge.return_value.execute.return_value = None
        result = client.acknowledge_product_purchase("com.example.app", "premium", "tok-abcdefgh")

        assert result.success is True
        _mock_service.purchases.return_value.products.return_value.acknowledge.assert_called_once_with(
            packageName="com.example.app",
            productId="premium",
            token="tok-abcdefgh",
            body={},
        )

    def test_happy_with_payload(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        _mock_service.purchases.return_value.products.return_value.acknowledge.return_value.execute.return_value = None
        result = client.acknowledge_product_purchase(
            "com.example.app", "premium", "tok-abcdefgh", developer_payload="x"
        )

        assert result.success is True
        _mock_service.purchases.return_value.products.return_value.acknowledge.assert_called_once_with(
            packageName="com.example.app",
            productId="premium",
            token="tok-abcdefgh",
            body={"developerPayload": "x"},
        )

    def test_payload_too_large_rejected(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        result = client.acknowledge_product_purchase(
            "com.example.app",
            "premium",
            "tok-abcdefgh",
            developer_payload="x" * 1025,
        )
        assert result.success is False
        assert "1024" in result.message
        _mock_service.purchases.return_value.products.return_value.acknowledge.assert_not_called()

    def test_empty_token_rejected(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        result = client.acknowledge_product_purchase("com.example.app", "premium", "")
        assert result.success is False
        _mock_service.purchases.return_value.products.return_value.acknowledge.assert_not_called()

    def test_http_error_returns_failure_dict(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        _mock_service.purchases.return_value.products.return_value.acknowledge.return_value.execute.side_effect = _make_http_error(
            410, "gone"
        )
        result = client.acknowledge_product_purchase("com.example.app", "premium", "tok-abcdefgh")
        assert result.success is False
        assert "Acknowledge failed" in result.message


class TestConsumeProductPurchase:
    def test_happy(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        _mock_service.purchases.return_value.products.return_value.consume.return_value.execute.return_value = None
        result = client.consume_product_purchase("com.example.app", "coins", "tok-abcdefgh")
        assert result.success is True
        assert result.operation == "consume"

    def test_empty_token(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        result = client.consume_product_purchase("com.example.app", "coins", "")
        assert result.success is False
        _mock_service.purchases.return_value.products.return_value.consume.assert_not_called()


class TestRefundOrder:
    def test_invalid_order_id_short_circuits(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        result = client.refund_order("com.example.app", "garbage")
        assert result.success is False
        _mock_service.orders.return_value.refund.assert_not_called()

    def test_happy_no_revoke(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        _mock_service.orders.return_value.refund.return_value.execute.return_value = None
        result = client.refund_order("com.example.app", "GPA.0001-2222-3333-4444")
        assert result.success is True
        assert result.revoked is False
        _mock_service.orders.return_value.refund.assert_called_once_with(
            packageName="com.example.app",
            orderId="GPA.0001-2222-3333-4444",
            revoke=False,
        )

    def test_happy_with_revoke(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        _mock_service.orders.return_value.refund.return_value.execute.return_value = None
        result = client.refund_order("com.example.app", "GPA.0001-2222-3333-4444", revoke=True)
        assert result.success is True
        assert result.revoked is True
        assert "revoked" in result.message
        _mock_service.orders.return_value.refund.assert_called_once_with(
            packageName="com.example.app",
            orderId="GPA.0001-2222-3333-4444",
            revoke=True,
        )

    def test_http_error_returns_failure(
        self,
        client: PlayStoreClient,
        _mock_service: MagicMock,
    ) -> None:
        _mock_service.orders.return_value.refund.return_value.execute.side_effect = (
            _make_http_error(400, "bad request")
        )
        result = client.refund_order("com.example.app", "GPA.0001-2222-3333-4444")
        assert result.success is False
        assert "Refund failed" in result.message


class TestMaskToken:
    @pytest.mark.parametrize(
        "token,expected",
        [
            ("", "<empty>"),
            ("ab", "...ab"),
            ("abcd", "...cd"),
            ("a" * 100, "..." + "a" * 8),
        ],
    )
    def test_mask(self, token: str, expected: str) -> None:
        assert PlayStoreClient._mask_token(token) == expected


class TestValidateOrderId:
    @pytest.mark.parametrize(
        "order_id",
        ["GPA.0001-1111-2222-3333", "GPA.dev.test_order", "ABC.xyz"],
    )
    def test_valid(self, order_id: str) -> None:
        PlayStoreClient._validate_order_id(order_id)

    @pytest.mark.parametrize(
        "order_id",
        ["", "no_dot", "has spaces.x", "tab\tx", "a/b"],
    )
    def test_invalid(self, order_id: str) -> None:
        with pytest.raises(ValueError):
            PlayStoreClient._validate_order_id(order_id)
