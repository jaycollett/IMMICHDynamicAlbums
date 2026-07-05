"""
Tests for search_assets pagination.

Immich returns nextPage as a string (e.g. "2"). Immich v3+ strictly
validates the page field in search requests and rejects strings with a
400, so the client must coerce nextPage to an int before re-sending.

To run these tests:

    pytest tests/test_pagination.py -v
"""
import sys
from pathlib import Path
from unittest.mock import Mock

# Add src directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from immich_client import ImmichClient


def _make_response(items, next_page):
    """Build a mock requests response for /search/metadata."""
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = {
        "assets": {"items": items, "nextPage": next_page}
    }
    return response


class TestSearchAssetsPagination:
    """Test pagination behavior of search_assets."""

    def test_string_next_page_is_sent_as_int(self):
        """nextPage arrives as a string but must be re-sent as an int (v3 API)."""
        client = ImmichClient("https://immich.test/api", "test-key")
        page1 = _make_response(
            [{"id": "asset-1", "type": "IMAGE"}], next_page="2"
        )
        page2 = _make_response(
            [{"id": "asset-2", "type": "IMAGE"}], next_page=None
        )
        client.session.post = Mock(side_effect=[page1, page2])

        asset_ids = client.search_assets(created_after="2026-01-01T00:00:00.000Z")

        assert asset_ids == {"asset-1", "asset-2"}
        assert client.session.post.call_count == 2
        second_payload = client.session.post.call_args_list[1].kwargs["json"]
        assert second_payload["page"] == 2
        assert isinstance(second_payload["page"], int)

    def test_single_page_stops_when_next_page_is_none(self):
        """No second request is made when nextPage is None."""
        client = ImmichClient("https://immich.test/api", "test-key")
        page1 = _make_response(
            [{"id": "asset-1", "type": "IMAGE"}], next_page=None
        )
        client.session.post = Mock(side_effect=[page1])

        asset_ids = client.search_assets(created_after="2026-01-01T00:00:00.000Z")

        assert asset_ids == {"asset-1"}
        assert client.session.post.call_count == 1
