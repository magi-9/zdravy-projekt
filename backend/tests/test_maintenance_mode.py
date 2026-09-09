"""Scheduled maintenance keeps client traffic out while admins can work."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import GlobalSettings, UserProfile


@pytest.mark.django_db
class TestMaintenanceMode:
    def _activate(self):
        settings, _ = GlobalSettings.objects.get_or_create(pk=1)
        settings.maintenance_enabled = True
        settings.maintenance_starts_at = timezone.now() - timedelta(minutes=5)
        settings.maintenance_ends_at = timezone.now() + timedelta(hours=1)
        settings.save()
        return settings

    def test_client_login_and_authenticated_api_are_blocked_but_admin_can_enter(self):
        client_user = User.objects.create_user(
            username="client-maintenance@example.com",
            email="client-maintenance@example.com",
            password="client-password",
        )
        UserProfile.objects.create(user=client_user)
        admin_user = User.objects.create_user(
            username="admin-maintenance@example.com",
            email="admin-maintenance@example.com",
            password="admin-password",
            is_staff=True,
        )
        admin_profile = UserProfile.objects.create(user=admin_user)
        admin_profile.role = UserProfile.Role.ADMIN
        admin_profile.save(update_fields=["role"])
        self._activate()

        api = APIClient()
        blocked_login = api.post(
            "/api/token/",
            {"email": client_user.email, "password": "client-password"},
            format="json",
        )
        assert blocked_login.status_code == 403
        assert "údržb" in str(blocked_login.data["error"]["message"]).lower()

        allowed_login = api.post(
            "/api/token/",
            {"email": admin_user.email, "password": "admin-password"},
            format="json",
        )
        assert allowed_login.status_code == 200

        api.credentials(HTTP_AUTHORIZATION=f"Bearer {allowed_login.data['access']}")
        assert api.get("/api/user/profile/").status_code == 200

        # Existing client sessions cannot bypass the outage with a direct API call.
        client_token = api.post(
            "/api/token/",
            {"email": admin_user.email, "password": "admin-password"},
            format="json",
        )
        assert client_token.status_code == 200
        from rest_framework_simplejwt.tokens import AccessToken

        direct_client_token = str(AccessToken.for_user(client_user))
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {direct_client_token}")
        assert api.get("/api/user/profile/").status_code == 503

    def test_enabled_maintenance_requires_a_valid_time_window(self, admin_client):
        response = admin_client.post(
            "/api/admin/global-settings/",
            {"maintenance_enabled": True},
            format="json",
        )
        assert response.status_code == 400
        assert "maintenance_ends_at" in response.data
