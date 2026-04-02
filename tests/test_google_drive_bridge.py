"""Tests for GoogleDriveBridge — no real network calls."""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from farms.shared.google_drive_bridge import (
    GoogleDriveBridge,
    DRIVE_FOLDER_IDS,
    DRIVE_FOLDER_LINKS,
    _MAX_RETRIES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_credentials() -> str:
    """Return valid-looking JSON credentials."""
    return json.dumps({
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "key123",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----\n",
        "client_email": "test@test-project.iam.gserviceaccount.com",
        "client_id": "123456789",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    })


def _mock_service():
    """Create a mock Google Drive service."""
    service = MagicMock()
    return service


def _mock_upload_response(file_id: str = "file123", web_link: str = "https://drive.google.com/file/d/file123/view"):
    """Create a mock upload response."""
    return {"id": file_id, "webViewLink": web_link}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bridge_sim(monkeypatch):
    """Bridge in simulation mode (no credentials)."""
    monkeypatch.delenv("GOOGLE_DRIVE_CREDENTIALS_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_DRIVE_ENABLED", raising=False)
    return GoogleDriveBridge()


@pytest.fixture
def bridge_disabled(monkeypatch):
    """Bridge explicitly disabled via env var."""
    monkeypatch.setenv("GOOGLE_DRIVE_ENABLED", "false")
    monkeypatch.setenv("GOOGLE_DRIVE_CREDENTIALS_JSON", _mock_credentials())
    return GoogleDriveBridge()


@pytest.fixture
def bridge_with_creds(monkeypatch):
    """Bridge with credentials (will need mocked service)."""
    monkeypatch.setenv("GOOGLE_DRIVE_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_DRIVE_CREDENTIALS_JSON", _mock_credentials())
    return GoogleDriveBridge()


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
        monkeypatch.setenv("GOOGLE_DRIVE_ENABLED", "false")
        monkeypatch.setenv("GOOGLE_DRIVE_CREDENTIALS_JSON", _mock_credentials())
        b = GoogleDriveBridge()
        assert b._simulation is True

    def test_env_var_true_with_creds_activates(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_DRIVE_ENABLED", "true")
        monkeypatch.setenv("GOOGLE_DRIVE_CREDENTIALS_JSON", _mock_credentials())
        b = GoogleDriveBridge()
        assert b._simulation is False

    def test_invalid_json_falls_back_to_simulation(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_DRIVE_ENABLED", "true")
        monkeypatch.setenv("GOOGLE_DRIVE_CREDENTIALS_JSON", "not-valid-json")
        b = GoogleDriveBridge()
        # Service init will fail, setting simulation
        b._get_service()
        assert b._simulation is True


# ---------------------------------------------------------------------------
# get_folder_link
# ---------------------------------------------------------------------------

class TestGetFolderLink:
    def test_returns_link_for_data_cleaning(self, bridge_sim):
        link = bridge_sim.get_folder_link("data_cleaning")
        assert link == DRIVE_FOLDER_LINKS["data_cleaning"]
        assert "1qjVs8bQ6XzuSzuMin1fvR82wA-7NZza9" in link

    def test_returns_link_for_auto_reports(self, bridge_sim):
        link = bridge_sim.get_folder_link("auto_reports")
        assert "1tcd4KREz_ABMzORmg_a9s5BXvuZHsjxD" in link

    def test_returns_link_for_product_listing(self, bridge_sim):
        link = bridge_sim.get_folder_link("product_listing")
        assert "1P7SCGJ0m8J-wLg678eZWkvYfcm5y5v7g" in link

    def test_returns_link_for_monetized_content(self, bridge_sim):
        link = bridge_sim.get_folder_link("monetized_content")
        assert "1GO03fu8aM0nXNYxNBOSFb4ESkWwgidcg" in link

    def test_unknown_farm_type_returns_none(self, bridge_sim):
        assert bridge_sim.get_folder_link("unknown_type") is None

    def test_all_farm_types_have_links(self, bridge_sim):
        for farm_type in DRIVE_FOLDER_IDS:
            assert bridge_sim.get_folder_link(farm_type) is not None


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

    def test_folder_id_included(self, bridge_sim, tmp_file):
        result = bridge_sim.upload_file("data_cleaning", tmp_file)
        assert result["folder_id"] == DRIVE_FOLDER_IDS["data_cleaning"]

    def test_unknown_farm_type_returns_error(self, bridge_sim, tmp_file):
        result = bridge_sim.upload_file("invalid_type", tmp_file)
        assert result["file_id"] is None
        assert "error" in result


# ---------------------------------------------------------------------------
# upload_file — live mode (mocked)
# ---------------------------------------------------------------------------

class TestUploadFileLive:
    def test_calls_drive_api(self, bridge_with_creds, tmp_file):
        mock_service = _mock_service()
        mock_service.files().create().execute.return_value = _mock_upload_response()
        mock_service.files().list().execute.return_value = {"files": []}

        mock_media = MagicMock()
        with patch.object(bridge_with_creds, "_get_service", return_value=mock_service), \
             patch("farms.shared.google_drive_bridge.MediaFileUpload", mock_media, create=True):
            # Need to mock the import inside the function
            import sys
            mock_googleapiclient = MagicMock()
            mock_googleapiclient.http.MediaFileUpload = MagicMock(return_value=mock_media)
            with patch.dict(sys.modules, {"googleapiclient.http": mock_googleapiclient.http}):
                result = bridge_with_creds.upload_file("data_cleaning", tmp_file)

        assert result["simulation"] is False
        assert result["file_id"] == "file123"

    def test_deletes_existing_file_before_upload(self, bridge_with_creds, tmp_file):
        mock_service = _mock_service()
        mock_service.files().list().execute.return_value = {
            "files": [{"id": "existing123", "name": "test_file.csv"}]
        }
        mock_service.files().create().execute.return_value = _mock_upload_response()
        mock_service.files().delete().execute.return_value = None

        import sys
        mock_googleapiclient = MagicMock()
        with patch.object(bridge_with_creds, "_get_service", return_value=mock_service), \
             patch.dict(sys.modules, {"googleapiclient.http": mock_googleapiclient.http}):
            bridge_with_creds.upload_file("data_cleaning", tmp_file)

        mock_service.files().delete.assert_called()

    def test_file_not_found_returns_error(self, bridge_with_creds):
        nonexistent = Path("/nonexistent/file.csv")
        result = bridge_with_creds.upload_file("data_cleaning", nonexistent)
        assert result["file_id"] is None
        assert "error" in result


# ---------------------------------------------------------------------------
# delete_file
# ---------------------------------------------------------------------------

class TestDeleteFile:
    def test_simulation_returns_true(self, bridge_sim):
        assert bridge_sim.delete_file("any-id") is True

    def test_live_calls_api(self, bridge_with_creds):
        mock_service = _mock_service()
        mock_service.files().delete().execute.return_value = None

        with patch.object(bridge_with_creds, "_get_service", return_value=mock_service):
            result = bridge_with_creds.delete_file("file123")

        assert result is True
        mock_service.files().delete.assert_called()

    def test_api_error_returns_false(self, bridge_with_creds):
        mock_service = _mock_service()
        mock_service.files().delete().execute.side_effect = Exception("API Error")

        with patch.object(bridge_with_creds, "_get_service", return_value=mock_service):
            result = bridge_with_creds.delete_file("file123")

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
        mock_service = _mock_service()
        mock_service.files().list().execute.return_value = {
            "files": [
                {"id": "f1", "name": "file1.csv", "mimeType": "text/csv", "webViewLink": "https://..."},
                {"id": "f2", "name": "file2.csv", "mimeType": "text/csv", "webViewLink": "https://..."},
            ]
        }

        with patch.object(bridge_with_creds, "_get_service", return_value=mock_service):
            result = bridge_with_creds.list_files("data_cleaning")

        assert len(result) == 2
        assert result[0]["id"] == "f1"


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

class TestRetryLogic:
    def test_retries_on_failure(self, bridge_with_creds, tmp_file):
        mock_service = _mock_service()
        mock_service.files().list().execute.return_value = {"files": []}

        # Fail twice, succeed on third attempt
        mock_service.files().create().execute.side_effect = [
            Exception("Fail 1"),
            Exception("Fail 2"),
            _mock_upload_response(),
        ]

        import sys
        mock_googleapiclient = MagicMock()
        with patch.object(bridge_with_creds, "_get_service", return_value=mock_service), \
             patch.dict(sys.modules, {"googleapiclient.http": mock_googleapiclient.http}), \
             patch("time.sleep"):  # Skip sleep in tests
            result = bridge_with_creds.upload_file("data_cleaning", tmp_file)

        assert result["file_id"] == "file123"
        assert mock_service.files().create().execute.call_count == 3

    def test_fails_after_max_retries(self, bridge_with_creds, tmp_file):
        mock_service = _mock_service()
        mock_service.files().list().execute.return_value = {"files": []}
        mock_service.files().create().execute.side_effect = Exception("Persistent failure")

        import sys
        mock_googleapiclient = MagicMock()
        with patch.object(bridge_with_creds, "_get_service", return_value=mock_service), \
             patch.dict(sys.modules, {"googleapiclient.http": mock_googleapiclient.http}), \
             patch("time.sleep"):
            result = bridge_with_creds.upload_file("data_cleaning", tmp_file)

        assert result["simulation"] is True  # Falls back to simulation
        assert mock_service.files().create().execute.call_count == _MAX_RETRIES


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_import_error_falls_back_to_simulation(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_DRIVE_ENABLED", "true")
        monkeypatch.setenv("GOOGLE_DRIVE_CREDENTIALS_JSON", _mock_credentials())
        b = GoogleDriveBridge()

        with patch.dict("sys.modules", {"google.oauth2": None, "googleapiclient": None}):
            with patch("builtins.__import__", side_effect=ImportError("No module")):
                service = b._get_service()

        # After failed import, should be in simulation mode
        assert b._simulation is True

    def test_invalid_credentials_json_handled(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_DRIVE_ENABLED", "true")
        monkeypatch.setenv("GOOGLE_DRIVE_CREDENTIALS_JSON", "{invalid json")
        b = GoogleDriveBridge()
        b._get_service()
        assert b._simulation is True

    def test_exception_does_not_propagate_upload(self, bridge_with_creds, tmp_file):
        mock_service = _mock_service()
        mock_service.files().list().execute.return_value = {"files": []}
        mock_service.files().create().execute.side_effect = Exception("API Error")

        with patch.object(bridge_with_creds, "_get_service", return_value=mock_service), \
             patch("time.sleep"):
            try:
                result = bridge_with_creds.upload_file("data_cleaning", tmp_file)
            except Exception as exc:
                pytest.fail(f"Exception propagated: {exc}")

        assert result["simulation"] is True

    def test_exception_does_not_propagate_delete(self, bridge_with_creds):
        mock_service = _mock_service()
        mock_service.files().delete().execute.side_effect = Exception("Delete failed")

        with patch.object(bridge_with_creds, "_get_service", return_value=mock_service), \
             patch("time.sleep"):
            try:
                result = bridge_with_creds.delete_file("file123")
            except Exception as exc:
                pytest.fail(f"Exception propagated: {exc}")

        assert result is False


# ---------------------------------------------------------------------------
# Folder IDs configuration
# ---------------------------------------------------------------------------

class TestFolderConfiguration:
    def test_all_farm_types_have_folder_ids(self):
        expected_types = ["data_cleaning", "auto_reports", "product_listing", "monetized_content"]
        for farm_type in expected_types:
            assert farm_type in DRIVE_FOLDER_IDS

    def test_folder_ids_are_valid_format(self):
        for folder_id in DRIVE_FOLDER_IDS.values():
            assert len(folder_id) > 10  # Google Drive IDs are long
            assert folder_id.replace("-", "").replace("_", "").isalnum()

    def test_folder_links_match_ids(self):
        for farm_type, folder_id in DRIVE_FOLDER_IDS.items():
            link = DRIVE_FOLDER_LINKS[farm_type]
            assert folder_id in link
            assert "drive.google.com" in link
