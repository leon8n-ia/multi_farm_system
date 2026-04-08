"""Tests for BackblazeBridge — no real network calls."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from farms.shared.backblaze_bridge import (
    BackblazeBridge,
    B2_BUCKET_NAMES,
    _MAX_RETRIES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_b2_api():
    """Create a mock B2 API instance."""
    api = MagicMock()
    return api


def _mock_bucket():
    """Create a mock B2 bucket."""
    bucket = MagicMock()
    return bucket


def _mock_file_version(file_id: str = "4_file123", file_name: str = "test.csv", size: int = 100):
    """Create a mock file version object."""
    fv = MagicMock()
    fv.id_ = file_id
    fv.file_name = file_name
    fv.size = size
    fv.upload_timestamp = 1704067200000
    return fv


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bridge_sim(monkeypatch):
    """Bridge in simulation mode (no credentials)."""
    monkeypatch.delenv("B2_KEY_ID", raising=False)
    monkeypatch.delenv("B2_APPLICATION_KEY", raising=False)
    monkeypatch.delenv("BACKBLAZE_ENABLED", raising=False)
    return BackblazeBridge()


@pytest.fixture
def bridge_disabled(monkeypatch):
    """Bridge explicitly disabled via env var."""
    monkeypatch.setenv("BACKBLAZE_ENABLED", "false")
    monkeypatch.setenv("B2_KEY_ID", "test_key_id")
    monkeypatch.setenv("B2_APPLICATION_KEY", "test_app_key")
    return BackblazeBridge()


@pytest.fixture
def bridge_with_creds(monkeypatch):
    """Bridge with credentials (will need mocked API)."""
    monkeypatch.setenv("BACKBLAZE_ENABLED", "true")
    monkeypatch.setenv("B2_KEY_ID", "test_key_id")
    monkeypatch.setenv("B2_APPLICATION_KEY", "test_app_key")
    return BackblazeBridge()


@pytest.fixture
def tmp_file(tmp_path):
    """Create a temporary file for upload tests."""
    file_path = tmp_path / "test_file.csv"
    file_path.write_text("col1,col2\n1,2\n3,4")
    return file_path


# ---------------------------------------------------------------------------
# Simulation mode detection
# ---------------------------------------------------------------------------

class TestSimulationMode:
    def test_no_credentials_is_simulation(self, bridge_sim):
        assert bridge_sim._simulation is True

    def test_disabled_env_is_simulation(self, bridge_disabled):
        assert bridge_disabled._simulation is True

    def test_credentials_present_not_simulation(self, bridge_with_creds):
        assert bridge_with_creds._simulation is False

    def test_env_var_false_stays_simulation(self, monkeypatch):
        monkeypatch.setenv("BACKBLAZE_ENABLED", "false")
        monkeypatch.setenv("B2_KEY_ID", "test_key_id")
        monkeypatch.setenv("B2_APPLICATION_KEY", "test_app_key")
        b = BackblazeBridge()
        assert b._simulation is True

    def test_env_var_true_with_creds_activates(self, monkeypatch):
        monkeypatch.setenv("BACKBLAZE_ENABLED", "true")
        monkeypatch.setenv("B2_KEY_ID", "test_key_id")
        monkeypatch.setenv("B2_APPLICATION_KEY", "test_app_key")
        b = BackblazeBridge()
        assert b._simulation is False

    def test_missing_key_id_falls_back_to_simulation(self, monkeypatch):
        monkeypatch.setenv("BACKBLAZE_ENABLED", "true")
        monkeypatch.delenv("B2_KEY_ID", raising=False)
        monkeypatch.setenv("B2_APPLICATION_KEY", "test_app_key")
        b = BackblazeBridge()
        assert b._simulation is True

    def test_missing_app_key_falls_back_to_simulation(self, monkeypatch):
        monkeypatch.setenv("BACKBLAZE_ENABLED", "true")
        monkeypatch.setenv("B2_KEY_ID", "test_key_id")
        monkeypatch.delenv("B2_APPLICATION_KEY", raising=False)
        b = BackblazeBridge()
        assert b._simulation is True


# ---------------------------------------------------------------------------
# Bucket configuration
# ---------------------------------------------------------------------------

class TestBucketConfiguration:
    def test_all_farm_types_have_buckets(self):
        expected_types = [
            "data_cleaning", "auto_reports", "product_listing",
            "monetized_content", "react_nextjs", "devops_cloud", "mobile_dev"
        ]
        for farm_type in expected_types:
            assert farm_type in B2_BUCKET_NAMES

    def test_bucket_names_follow_pattern(self):
        for bucket_name in B2_BUCKET_NAMES.values():
            assert bucket_name.startswith("multifarm-")

    def test_seven_buckets_configured(self):
        assert len(B2_BUCKET_NAMES) == 7


# ---------------------------------------------------------------------------
# upload_file — simulation mode
# ---------------------------------------------------------------------------

class TestUploadFileSimulation:
    def test_returns_dict(self, bridge_sim, tmp_file):
        result = bridge_sim.upload_file("data_cleaning", tmp_file)
        assert isinstance(result, dict)

    def test_simulation_flag_true(self, bridge_sim, tmp_file):
        result = bridge_sim.upload_file("data_cleaning", tmp_file)
        assert result["simulation"] is True

    def test_file_name_preserved(self, bridge_sim, tmp_file):
        result = bridge_sim.upload_file("data_cleaning", tmp_file, "custom_name.csv")
        assert result["file_name"] == "custom_name.csv"

    def test_default_file_name_from_path(self, bridge_sim, tmp_file):
        result = bridge_sim.upload_file("data_cleaning", tmp_file)
        assert result["file_name"] == "test_file.csv"

    def test_file_id_has_sim_prefix(self, bridge_sim, tmp_file):
        result = bridge_sim.upload_file("data_cleaning", tmp_file)
        assert result["file_id"].startswith("sim-")

    def test_unique_file_ids(self, bridge_sim, tmp_file):
        r1 = bridge_sim.upload_file("data_cleaning", tmp_file)
        r2 = bridge_sim.upload_file("data_cleaning", tmp_file)
        assert r1["file_id"] != r2["file_id"]

    def test_bucket_included(self, bridge_sim, tmp_file):
        result = bridge_sim.upload_file("data_cleaning", tmp_file)
        assert result["bucket"] == B2_BUCKET_NAMES["data_cleaning"]

    def test_download_url_included(self, bridge_sim, tmp_file):
        result = bridge_sim.upload_file("data_cleaning", tmp_file)
        assert "download_url" in result
        assert "backblazeb2.com" in result["download_url"]

    def test_unknown_farm_type_returns_error(self, bridge_sim, tmp_file):
        result = bridge_sim.upload_file("invalid_type", tmp_file)
        assert result["file_id"] is None
        assert "error" in result


# ---------------------------------------------------------------------------
# upload_file — live mode (mocked)
# ---------------------------------------------------------------------------

class TestUploadFileLive:
    def test_calls_b2_api(self, bridge_with_creds, tmp_file):
        mock_bucket = _mock_bucket()
        mock_file = _mock_file_version()
        mock_bucket.upload_local_file.return_value = mock_file

        with patch.object(bridge_with_creds, "_get_bucket", return_value=mock_bucket):
            result = bridge_with_creds.upload_file("data_cleaning", tmp_file)

        assert result["simulation"] is False
        assert result["file_id"] == mock_file.id_
        mock_bucket.upload_local_file.assert_called_once()

    def test_file_not_found_returns_error(self, bridge_with_creds):
        nonexistent = Path("/nonexistent/file.csv")
        result = bridge_with_creds.upload_file("data_cleaning", nonexistent)
        assert result["file_id"] is None
        assert "error" in result

    def test_api_error_falls_back_to_simulation(self, bridge_with_creds, tmp_file):
        mock_bucket = _mock_bucket()
        mock_bucket.upload_local_file.side_effect = Exception("Upload failed")

        with patch.object(bridge_with_creds, "_get_bucket", return_value=mock_bucket), \
             patch("time.sleep"):
            result = bridge_with_creds.upload_file("data_cleaning", tmp_file)

        assert result["simulation"] is True


# ---------------------------------------------------------------------------
# get_download_url — simulation mode
# ---------------------------------------------------------------------------

class TestGetDownloadUrlSimulation:
    def test_returns_url(self, bridge_sim):
        url = bridge_sim.get_download_url("data_cleaning", "test.csv")
        assert url is not None
        assert "backblazeb2.com" in url
        assert "test.csv" in url

    def test_unknown_farm_type_returns_none(self, bridge_sim):
        url = bridge_sim.get_download_url("invalid_type", "test.csv")
        assert url is None

    def test_sim_flag_in_url(self, bridge_sim):
        url = bridge_sim.get_download_url("data_cleaning", "test.csv")
        assert "sim=true" in url


# ---------------------------------------------------------------------------
# get_download_url — live mode (mocked)
# ---------------------------------------------------------------------------

class TestGetDownloadUrlLive:
    def test_returns_signed_url(self, bridge_with_creds):
        mock_bucket = _mock_bucket()
        mock_bucket.get_download_authorization.return_value = "auth_token_123"

        with patch.object(bridge_with_creds, "_get_bucket", return_value=mock_bucket):
            url = bridge_with_creds.get_download_url("data_cleaning", "test.csv")

        assert url is not None
        assert "Authorization=auth_token_123" in url

    def test_api_error_returns_none(self, bridge_with_creds):
        mock_bucket = _mock_bucket()
        mock_bucket.get_download_authorization.side_effect = Exception("Auth failed")

        with patch.object(bridge_with_creds, "_get_bucket", return_value=mock_bucket):
            url = bridge_with_creds.get_download_url("data_cleaning", "test.csv")

        assert url is None


# ---------------------------------------------------------------------------
# delete_file — simulation mode
# ---------------------------------------------------------------------------

class TestDeleteFileSimulation:
    def test_simulation_returns_true(self, bridge_sim):
        assert bridge_sim.delete_file("data_cleaning", "test.csv") is True

    def test_unknown_farm_type_returns_false(self, bridge_sim):
        assert bridge_sim.delete_file("invalid_type", "test.csv") is False


# ---------------------------------------------------------------------------
# delete_file — live mode (mocked)
# ---------------------------------------------------------------------------

class TestDeleteFileLive:
    def test_calls_delete_api(self, bridge_with_creds):
        mock_bucket = _mock_bucket()
        mock_fv = _mock_file_version()
        mock_bucket.ls.return_value = [(mock_fv, None)]

        with patch.object(bridge_with_creds, "_get_bucket", return_value=mock_bucket):
            result = bridge_with_creds.delete_file("data_cleaning", "test.csv")

        assert result is True
        mock_bucket.delete_file_version.assert_called_once()

    def test_file_not_found_returns_true(self, bridge_with_creds):
        mock_bucket = _mock_bucket()
        mock_bucket.ls.return_value = []

        with patch.object(bridge_with_creds, "_get_bucket", return_value=mock_bucket):
            result = bridge_with_creds.delete_file("data_cleaning", "nonexistent.csv")

        assert result is True  # Already gone

    def test_api_error_returns_false(self, bridge_with_creds):
        mock_bucket = _mock_bucket()
        mock_bucket.ls.side_effect = Exception("API Error")

        with patch.object(bridge_with_creds, "_get_bucket", return_value=mock_bucket), \
             patch("time.sleep"):
            result = bridge_with_creds.delete_file("data_cleaning", "test.csv")

        assert result is False


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------

class TestListFiles:
    def test_simulation_returns_empty(self, bridge_sim):
        assert bridge_sim.list_files("data_cleaning") == []

    def test_unknown_farm_type_returns_empty(self, bridge_sim):
        assert bridge_sim.list_files("invalid_type") == []

    def test_live_returns_files(self, bridge_with_creds):
        mock_bucket = _mock_bucket()
        mock_fv1 = _mock_file_version("f1", "file1.csv")
        mock_fv2 = _mock_file_version("f2", "file2.csv")
        mock_bucket.ls.return_value = [(mock_fv1, None), (mock_fv2, None)]

        with patch.object(bridge_with_creds, "_get_bucket", return_value=mock_bucket):
            result = bridge_with_creds.list_files("data_cleaning")

        assert len(result) == 2
        assert result[0]["file_id"] == "f1"
        assert result[1]["file_id"] == "f2"


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

class TestRetryLogic:
    def test_retries_on_failure(self, bridge_with_creds, tmp_file):
        mock_bucket = _mock_bucket()
        mock_file = _mock_file_version()

        # Fail twice, succeed on third attempt
        mock_bucket.upload_local_file.side_effect = [
            Exception("Fail 1"),
            Exception("Fail 2"),
            mock_file,
        ]

        with patch.object(bridge_with_creds, "_get_bucket", return_value=mock_bucket), \
             patch("time.sleep"):
            result = bridge_with_creds.upload_file("data_cleaning", tmp_file)

        assert result["file_id"] == mock_file.id_
        assert mock_bucket.upload_local_file.call_count == 3

    def test_fails_after_max_retries(self, bridge_with_creds, tmp_file):
        mock_bucket = _mock_bucket()
        mock_bucket.upload_local_file.side_effect = Exception("Persistent failure")

        with patch.object(bridge_with_creds, "_get_bucket", return_value=mock_bucket), \
             patch("time.sleep"):
            result = bridge_with_creds.upload_file("data_cleaning", tmp_file)

        assert result["simulation"] is True  # Falls back to simulation
        assert mock_bucket.upload_local_file.call_count == _MAX_RETRIES


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_import_error_falls_back_to_simulation(self, monkeypatch):
        monkeypatch.setenv("BACKBLAZE_ENABLED", "true")
        monkeypatch.setenv("B2_KEY_ID", "test_key_id")
        monkeypatch.setenv("B2_APPLICATION_KEY", "test_app_key")
        b = BackblazeBridge()

        with patch.dict("sys.modules", {"b2sdk.v2": None}):
            with patch("builtins.__import__", side_effect=ImportError("No module")):
                api = b._get_api()

        assert b._simulation is True

    def test_auth_failure_falls_back_to_simulation(self, monkeypatch):
        monkeypatch.setenv("BACKBLAZE_ENABLED", "true")
        monkeypatch.setenv("B2_KEY_ID", "invalid_key")
        monkeypatch.setenv("B2_APPLICATION_KEY", "invalid_secret")
        b = BackblazeBridge()

        mock_b2sdk = MagicMock()
        mock_api = MagicMock()
        mock_api.authorize_account.side_effect = Exception("Invalid credentials")
        mock_b2sdk.B2Api.return_value = mock_api

        with patch.dict("sys.modules", {"b2sdk.v2": mock_b2sdk}):
            api = b._get_api()

        assert b._simulation is True

    def test_exception_does_not_propagate_upload(self, bridge_with_creds, tmp_file):
        mock_bucket = _mock_bucket()
        mock_bucket.upload_local_file.side_effect = Exception("API Error")

        with patch.object(bridge_with_creds, "_get_bucket", return_value=mock_bucket), \
             patch("time.sleep"):
            try:
                result = bridge_with_creds.upload_file("data_cleaning", tmp_file)
            except Exception as exc:
                pytest.fail(f"Exception propagated: {exc}")

        assert result["simulation"] is True

    def test_exception_does_not_propagate_delete(self, bridge_with_creds):
        mock_bucket = _mock_bucket()
        mock_bucket.ls.side_effect = Exception("Delete failed")

        with patch.object(bridge_with_creds, "_get_bucket", return_value=mock_bucket), \
             patch("time.sleep"):
            try:
                result = bridge_with_creds.delete_file("data_cleaning", "test.csv")
            except Exception as exc:
                pytest.fail(f"Exception propagated: {exc}")

        assert result is False


# ---------------------------------------------------------------------------
# API initialization
# ---------------------------------------------------------------------------

class TestApiInitialization:
    def test_api_lazy_initialized(self, bridge_with_creds):
        assert bridge_with_creds._b2_api is None

    def test_buckets_cached(self, bridge_with_creds):
        mock_api = _mock_b2_api()
        mock_bucket = _mock_bucket()
        mock_api.get_bucket_by_name.return_value = mock_bucket

        with patch.object(bridge_with_creds, "_get_api", return_value=mock_api):
            bucket1 = bridge_with_creds._get_bucket("data_cleaning")
            bucket2 = bridge_with_creds._get_bucket("data_cleaning")

        assert bucket1 is bucket2
        assert mock_api.get_bucket_by_name.call_count == 1

    def test_different_buckets_for_different_farms(self, bridge_with_creds):
        mock_api = _mock_b2_api()
        mock_bucket1 = _mock_bucket()
        mock_bucket2 = _mock_bucket()
        mock_api.get_bucket_by_name.side_effect = [mock_bucket1, mock_bucket2]

        with patch.object(bridge_with_creds, "_get_api", return_value=mock_api):
            bucket1 = bridge_with_creds._get_bucket("data_cleaning")
            bucket2 = bridge_with_creds._get_bucket("auto_reports")

        assert bucket1 is not bucket2
