"""
Tests for album sharing functionality.
"""
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, MagicMock, patch

# Add src directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from immich_client import ImmichClient


class TestAlbumSharing(unittest.TestCase):
    """Test album sharing with multiple users."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = ImmichClient("https://immich.example.com/api", "test-api-key")
        self.client.session = Mock()

    def test_get_all_users(self):
        """Test getting all users from the API."""
        # Mock response
        mock_users = [
            {"id": "user1", "email": "user1@example.com", "name": "User 1"},
            {"id": "user2", "email": "user2@example.com", "name": "User 2"},
            {"id": "user3", "email": "user3@example.com", "name": "User 3"},
        ]

        mock_response = Mock()
        mock_response.json.return_value = mock_users
        mock_response.raise_for_status = Mock()
        self.client.session.get.return_value = mock_response

        # Call method
        users = self.client.get_all_users()

        # Verify
        self.assertEqual(len(users), 3)
        self.assertEqual(users[0]["id"], "user1")
        self.assertEqual(users[1]["id"], "user2")
        self.assertEqual(users[2]["id"], "user3")
        self.client.session.get.assert_called_once_with("https://immich.example.com/api/users")

    def test_create_album_without_sharing(self):
        """Test creating album without sharing (default behavior)."""
        # Mock current user
        self.client._user_cache = {"id": "owner-id", "email": "owner@example.com"}

        # Mock response
        mock_album = {
            "id": "album-123",
            "albumName": "Test Album",
            "albumUsers": [{"userId": "owner-id", "role": "editor"}]
        }

        mock_response = Mock()
        mock_response.json.return_value = mock_album
        mock_response.raise_for_status = Mock()
        self.client.session.post.return_value = mock_response

        # Call method
        album = self.client.create_album("Test Album", description="Test description")

        # Verify
        self.assertEqual(album["id"], "album-123")

        # Check the payload sent to the API
        call_args = self.client.session.post.call_args
        payload = call_args[1]["json"]

        self.assertEqual(payload["albumName"], "Test Album")
        self.assertEqual(payload["description"], "Test description")
        # Owner should NOT be in albumUsers (they're implicit)
        self.assertNotIn("albumUsers", payload)

    def test_create_album_with_sharing(self):
        """Test creating album shared with multiple users."""
        # Mock current user
        self.client._user_cache = {"id": "owner-id", "email": "owner@example.com"}

        # Mock response
        mock_album = {
            "id": "album-123",
            "albumName": "Shared Album",
            "albumUsers": [
                {"userId": "owner-id", "role": "editor"},
                {"userId": "user1", "role": "viewer"},
                {"userId": "user2", "role": "viewer"},
            ]
        }

        mock_response = Mock()
        mock_response.json.return_value = mock_album
        mock_response.raise_for_status = Mock()
        self.client.session.post.return_value = mock_response

        # Call method with share_user_ids
        share_user_ids = ["user1", "user2", "user3"]
        album = self.client.create_album("Shared Album", share_user_ids=share_user_ids)

        # Verify
        self.assertEqual(album["id"], "album-123")

        # Check the payload sent to the API
        call_args = self.client.session.post.call_args
        payload = call_args[1]["json"]

        self.assertEqual(payload["albumName"], "Shared Album")
        # Owner should NOT be in albumUsers - only the 3 other users
        self.assertEqual(len(payload["albumUsers"]), 3)

        # Verify all users are viewers (owner is implicit, not in list)
        for user_id in ["user1", "user2", "user3"]:
            user = next(u for u in payload["albumUsers"] if u["userId"] == user_id)
            self.assertEqual(user["role"], "viewer")

    def test_create_album_sharing_excludes_owner(self):
        """Test that owner is not added twice when in share_user_ids list."""
        # Mock current user
        self.client._user_cache = {"id": "owner-id", "email": "owner@example.com"}

        # Mock response
        mock_album = {"id": "album-123", "albumName": "Test Album"}
        mock_response = Mock()
        mock_response.json.return_value = mock_album
        mock_response.raise_for_status = Mock()
        self.client.session.post.return_value = mock_response

        # Call method with owner ID in share_user_ids
        share_user_ids = ["owner-id", "user1", "user2"]
        self.client.create_album("Test Album", share_user_ids=share_user_ids)

        # Check the payload sent to the API
        call_args = self.client.session.post.call_args
        payload = call_args[1]["json"]

        # Should only have 2 users (user1, user2 as viewers - owner is implicit)
        self.assertEqual(len(payload["albumUsers"]), 2)

        # Owner should NOT be in albumUsers at all
        owner_entries = [u for u in payload["albumUsers"] if u["userId"] == "owner-id"]
        self.assertEqual(len(owner_entries), 0)

        # Other users should be viewers
        self.assertEqual(payload["albumUsers"][0]["role"], "viewer")
        self.assertEqual(payload["albumUsers"][1]["role"], "viewer")

    def test_create_album_sharing_with_empty_list(self):
        """Test creating album with empty share_user_ids list."""
        # Mock current user
        self.client._user_cache = {"id": "owner-id", "email": "owner@example.com"}

        # Mock response
        mock_album = {"id": "album-123", "albumName": "Test Album"}
        mock_response = Mock()
        mock_response.json.return_value = mock_album
        mock_response.raise_for_status = Mock()
        self.client.session.post.return_value = mock_response

        # Call method with empty share_user_ids
        self.client.create_album("Test Album", share_user_ids=[])

        # Check the payload sent to the API
        call_args = self.client.session.post.call_args
        payload = call_args[1]["json"]

        # Should NOT have albumUsers key (owner is implicit)
        self.assertNotIn("albumUsers", payload)


if __name__ == "__main__":
    unittest.main()
