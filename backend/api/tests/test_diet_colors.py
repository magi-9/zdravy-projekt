"""Explicitná farba textu/pozadia diéty (`Diet.text_color`/`background_color`).

Doteraz sa farba textu a podfarbenie riadku v gramážnej tabuľke/PDF vždy
dopočítavali z `Diet.color` (stmavenie/blend, viď `gramage_dashboard_export`).
Admin teraz vie pri vytváraní/úprave diéty (jednoduchej aj kombinovanej)
vybrať oboje priamo — tieto testy zamykajú model a API vrstvu, ktorá to
umožňuje. Efekt na samotnú tabuľku/PDF je zamknutý v
`test_gramage_table_spec.py`.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from api.models import Diet, User

pytestmark = pytest.mark.django_db


def test_diet_text_and_background_color_default_to_blank():
    diet = Diet.objects.create(name="No Milk")
    assert diet.text_color == ""
    assert diet.background_color == ""


def test_diet_can_store_explicit_text_and_background_color():
    diet = Diet.objects.create(
        name="No Milk",
        color="#F59E0B",
        text_color="#111111",
        background_color="#EEEEEE",
    )
    diet.refresh_from_db()
    assert diet.text_color == "#111111"
    assert diet.background_color == "#EEEEEE"


class TestDietColorApi:
    def setup_method(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_user(
            username="admin", password="test", is_staff=True, is_superuser=True
        )
        self.client.force_authenticate(user=self.admin_user)

    def test_create_single_diet_with_explicit_colors(self):
        response = self.client.post(
            "/api/diets/",
            {
                "name": "Bez lepku",
                "sort_order": 0,
                "description": "",
                "color": "#D83131",
                "text_color": "#111111",
                "background_color": "#EEEEEE",
                "base_diets": [],
                "is_active": True,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.content
        data = response.json()
        assert data["text_color"] == "#111111"
        assert data["background_color"] == "#EEEEEE"

    def test_create_composite_diet_with_explicit_colors(self):
        base_a = Diet.objects.create(name="Bez lepku", color="#F59E0B")
        base_b = Diet.objects.create(name="Bez laktózy", color="#EF4444")

        response = self.client.post(
            "/api/diets/",
            {
                "name": "Bez lepku – Bez laktózy",
                "sort_order": 0,
                "description": "",
                "color": "#F59E0B",
                "text_color": "#000000",
                "background_color": "#FFFFFF",
                "base_diets": [base_a.id, base_b.id],
                "is_active": True,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.content
        data = response.json()
        assert data["text_color"] == "#000000"
        assert data["background_color"] == "#FFFFFF"

    def test_update_diet_clears_explicit_colors_back_to_blank(self):
        diet = Diet.objects.create(
            name="No Milk", text_color="#111111", background_color="#EEEEEE"
        )
        response = self.client.patch(
            f"/api/diets/{diet.id}/",
            {"text_color": "", "background_color": ""},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.content
        diet.refresh_from_db()
        assert diet.text_color == ""
        assert diet.background_color == ""

    def test_diet_list_returns_the_explicit_colors(self):
        Diet.objects.create(
            name="No Milk", text_color="#111111", background_color="#EEEEEE"
        )
        response = self.client.get("/api/diets/")
        assert response.status_code == status.HTTP_200_OK
        [diet] = response.json()
        assert diet["text_color"] == "#111111"
        assert diet["background_color"] == "#EEEEEE"
