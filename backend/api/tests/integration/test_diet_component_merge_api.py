"""API pre klikací zoznam "spolu/zvlášť" (#568): `board` + `toggle`."""

import datetime

import pytest
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import (
    Celok,
    DailyMealPlan,
    DailyOrder,
    Diet,
    DietComponentMerge,
    MealCategory,
    MealPlanItem,
    MealTemplate,
    Prevadzka,
)

pytestmark = pytest.mark.integration


class DietComponentMergeApiTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="dcm-admin@example.com",
            password="password",
            email="dcm-admin@example.com",
            is_staff=True,
        )
        self.client_user = User.objects.create_user(
            username="dcm-client@example.com",
            password="password",
            email="dcm-client@example.com",
        )
        self.diet = Diet.objects.create(name="Bez lepku")
        self.plan = DailyMealPlan.objects.create(date=datetime.date(2026, 9, 28))
        MealPlanItem.objects.create(
            meal_plan=self.plan,
            template=MealTemplate.objects.create(
                name="Obed A",
                category="main_course",
                components=[
                    {"label": "Hlavná časť", "grams": "200", "unit": "g"},
                    {"label": "Príloha", "grams": "100", "unit": "g"},
                ],
                base_weight_grams="300",
            ),
            category="main_course",
            menu_variant="A",
        )
        self.client.force_authenticate(user=self.admin)

    def test_board_requires_date(self):
        response = self.client.get("/api/admin/diet-component-merge/board/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_board_lists_todays_components_and_diets(self):
        response = self.client.get(
            "/api/admin/diet-component-merge/board/",
            {"date": self.plan.date.isoformat()},
        )
        assert response.status_code == status.HTTP_200_OK, response.content
        data = response.json()
        [main] = [m for m in data["meals"] if m["meal"] == "main_course"]
        assert main["components"] == [
            {"index": 0, "label": "Hlavná časť"},
            {"index": 1, "label": "Príloha"},
        ]
        assert {"id": self.diet.id, "name": "Bez lepku"} in data["diets"]
        assert data["merged"] == []

    def test_client_cannot_read_the_board(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(
            "/api/admin/diet-component-merge/board/",
            {"date": self.plan.date.isoformat()},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_toggle_merged_true_creates_the_row(self):
        response = self.client.post(
            "/api/admin/diet-component-merge/toggle/",
            {
                "date": self.plan.date.isoformat(),
                "meal": MealCategory.MAIN_COURSE,
                "component_index": 0,
                "diet_id": self.diet.id,
                "merged": True,
                "component_label": "Hlavná časť",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.content
        assert response.json()["merged"] == [
            {"meal": "main_course", "diet_name": "Bez lepku", "component_index": 0}
        ]
        row = DietComponentMerge.objects.get()
        assert row.component_label == "Hlavná časť"
        assert row.updated_by_id == self.admin.id

    def test_toggle_merged_false_deletes_the_row(self):
        DietComponentMerge.objects.create(
            date=self.plan.date,
            meal=MealCategory.MAIN_COURSE,
            component_index=0,
            diet=self.diet,
        )
        response = self.client.post(
            "/api/admin/diet-component-merge/toggle/",
            {
                "date": self.plan.date.isoformat(),
                "meal": MealCategory.MAIN_COURSE,
                "component_index": 0,
                "diet_id": self.diet.id,
                "merged": False,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.content
        assert response.json()["merged"] == []
        assert DietComponentMerge.objects.count() == 0

    def test_toggle_rejects_soup_as_unsupported_meal(self):
        response = self.client.post(
            "/api/admin/diet-component-merge/toggle/",
            {
                "date": self.plan.date.isoformat(),
                "meal": "soup",
                "component_index": 0,
                "diet_id": self.diet.id,
                "merged": True,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_toggle_requires_admin_or_kuchyna(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(
            "/api/admin/diet-component-merge/toggle/",
            {
                "date": self.plan.date.isoformat(),
                "meal": MealCategory.MAIN_COURSE,
                "component_index": 0,
                "diet_id": self.diet.id,
                "merged": True,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class GramageDashboardMergeDietsToggleApiTest(APITestCase):
    """Prepínač `?merge_diets=` (#568) na gramage-dashboard endpointe."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="dcm-toggle-admin@example.com",
            password="password",
            email="dcm-toggle-admin@example.com",
            is_staff=True,
        )
        self.diet = Diet.objects.create(name="Bez lepku")
        self.plan = DailyMealPlan.objects.create(date=datetime.date(2026, 9, 29))
        MealPlanItem.objects.create(
            meal_plan=self.plan,
            template=MealTemplate.objects.create(
                name="Obed A",
                category="main_course",
                components=[{"label": "Hlavná časť", "grams": "200", "unit": "g"}],
                base_weight_grams="200",
            ),
            category="main_course",
            menu_variant="A",
        )
        DietComponentMerge.objects.create(
            date=self.plan.date,
            meal=MealCategory.MAIN_COURSE,
            component_index=0,
            diet=self.diet,
        )
        celok = Celok.objects.create(nazov="MŠ Testovacia")
        prevadzka = Prevadzka.objects.create(celok=celok, nazov="MŠ Testovacia")
        user = User.objects.create_user(username="dcm-order@example.com", password="x")
        DailyOrder.objects.create(
            user=user,
            prevadzka=prevadzka,
            date=self.plan.date,
            data={
                "lunch": {
                    "Škôlka": {
                        "menuCounts": {"A": 4},
                        "diets": {"Bez lepku": 2},
                    }
                }
            },
        )
        self.client.force_authenticate(user=self.admin)

    def _sub_row_types(self, payload):
        return [sr["type"] for sr in payload["rows"][0]["sub_rows"]]

    def test_default_applies_the_full_merge(self):
        response = self.client.get(
            f"/api/admin/meal-plans/gramage-dashboard/?date={self.plan.date.isoformat()}"
        )
        assert response.status_code == status.HTTP_200_OK
        assert self._sub_row_types(response.json()) == ["standard"]

    def test_merge_diets_0_falls_back_to_the_unmerged_table(self):
        response = self.client.get(
            "/api/admin/meal-plans/gramage-dashboard/"
            f"?date={self.plan.date.isoformat()}&merge_diets=0"
        )
        assert response.status_code == status.HTTP_200_OK
        assert self._sub_row_types(response.json()) == ["standard", "diet"]
