"""API pre klikací zoznam "spolu/zvlášť" (#568, flip 10.9.2026): `board` +
`toggle`. Default je "spolu", riadok v DB je "zvlášť" výnimka."""

import datetime

import pytest
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import (
    Celok,
    DailyMealPlan,
    DailyOrder,
    DeliveryBlock,
    DeliveryRoute,
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
        assert {
            "id": self.diet.id,
            "name": "Bez lepku",
            "base_diet_names": [],
            "text_color": "",
            "background_color": "",
        } in data["diets"]
        # Default je "spolu" — bez výnimiek sú obe zložky zlúčené.
        assert sorted(data["merged"], key=lambda m: m["component_index"]) == [
            {"meal": "main_course", "diet_name": "Bez lepku", "component_index": 0},
            {"meal": "main_course", "diet_name": "Bez lepku", "component_index": 1},
        ]

    def test_board_lists_the_diets_own_explicit_colors(self):
        self.diet.text_color = "#123456"
        self.diet.background_color = "#ABCDEF"
        self.diet.save()

        response = self.client.get(
            "/api/admin/diet-component-merge/board/",
            {"date": self.plan.date.isoformat()},
        )

        assert response.status_code == status.HTTP_200_OK, response.content
        by_id = {d["id"]: d for d in response.json()["diets"]}
        assert by_id[self.diet.id]["text_color"] == "#123456"
        assert by_id[self.diet.id]["background_color"] == "#ABCDEF"

    def test_client_cannot_read_the_board(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(
            "/api/admin/diet-component-merge/board/",
            {"date": self.plan.date.isoformat()},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_toggle_merged_false_creates_the_separation_row(self):
        response = self.client.post(
            "/api/admin/diet-component-merge/toggle/",
            {
                "date": self.plan.date.isoformat(),
                "meal": MealCategory.MAIN_COURSE,
                "component_index": 0,
                "diet_id": self.diet.id,
                "merged": False,
                "component_label": "Hlavná časť",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.content
        # Index 0 je teraz explicitne zvlášť, index 1 ostáva default spolu.
        assert response.json()["merged"] == [
            {"meal": "main_course", "diet_name": "Bez lepku", "component_index": 1}
        ]
        row = DietComponentMerge.objects.get()
        assert row.component_label == "Hlavná časť"
        assert row.updated_by_id == self.admin.id

    def test_toggle_merged_true_deletes_the_separation_row(self):
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
                "merged": True,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.content
        assert sorted(
            response.json()["merged"], key=lambda m: m["component_index"]
        ) == [
            {"meal": "main_course", "diet_name": "Bez lepku", "component_index": 0},
            {"meal": "main_course", "diet_name": "Bez lepku", "component_index": 1},
        ]
        assert DietComponentMerge.objects.count() == 0

    def test_toggle_accepts_soup_as_its_own_independent_meal(self):
        """Polievka (11.9.2026) je nezávislá od hlavného jedla — vlastný
        "spolu/zvlášť" riadok, nie zdieľaný s `main_course`."""
        response = self.client.post(
            "/api/admin/diet-component-merge/toggle/",
            {
                "date": self.plan.date.isoformat(),
                "meal": "soup",
                "component_index": 0,
                "diet_id": self.diet.id,
                "merged": False,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.content
        assert DietComponentMerge.objects.filter(meal="soup", diet=self.diet).exists()
        # Hlavné jedlo ostáva netknuté (default "spolu") — nezávislá bunka.
        assert not DietComponentMerge.objects.filter(
            meal=MealCategory.MAIN_COURSE, diet=self.diet
        ).exists()

    def test_toggle_rejects_unsupported_meal(self):
        response = self.client.post(
            "/api/admin/diet-component-merge/toggle/",
            {
                "date": self.plan.date.isoformat(),
                "meal": "dessert",
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

    def test_board_lists_base_diet_names_for_composites(self):
        milk = Diet.objects.create(name="NoMilk")
        combo = Diet.objects.create(name="NoMilk+Bez lepku")
        combo.base_diets.set([milk, self.diet])

        response = self.client.get(
            "/api/admin/diet-component-merge/board/",
            {"date": self.plan.date.isoformat()},
        )

        assert response.status_code == status.HTTP_200_OK, response.content
        by_id = {d["id"]: d for d in response.json()["diets"]}
        assert by_id[self.diet.id]["base_diet_names"] == []
        assert set(by_id[combo.id]["base_diet_names"]) == {"NoMilk", "Bez lepku"}

    def test_toggling_a_base_diet_to_separate_cascades_to_its_composites(self):
        milk = Diet.objects.create(name="NoMilk")
        combo = Diet.objects.create(name="NoMilk+Bez lepku")
        combo.base_diets.set([milk, self.diet])
        # Default "spolu" pre všetky tri — žiadny zvlášť-riadok zatiaľ.

        response = self.client.post(
            "/api/admin/diet-component-merge/toggle/",
            {
                "date": self.plan.date.isoformat(),
                "meal": MealCategory.MAIN_COURSE,
                "component_index": 0,
                "diet_id": milk.id,
                "merged": False,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK, response.content
        # NoMilk aj kombinácia (kaskáda) sú teraz zvlášť — vypadli z merged
        # setu pre index 0; index 1 ostáva default spolu pre všetky diéty.
        merged_at_index_0 = {
            m["diet_name"]
            for m in response.json()["merged"]
            if m["component_index"] == 0
        }
        assert merged_at_index_0 == {"Bez lepku"}

    def test_toggling_a_composite_to_spolu_is_rejected_while_a_base_is_separate(
        self,
    ):
        milk = Diet.objects.create(name="NoMilk")
        combo = Diet.objects.create(name="NoMilk+Bez lepku")
        combo.base_diets.set([milk, self.diet])
        DietComponentMerge.objects.create(
            date=self.plan.date,
            meal=MealCategory.MAIN_COURSE,
            component_index=0,
            diet=milk,
        )

        response = self.client.post(
            "/api/admin/diet-component-merge/toggle/",
            {
                "date": self.plan.date.isoformat(),
                "meal": MealCategory.MAIN_COURSE,
                "component_index": 0,
                "diet_id": combo.id,
                "merged": True,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "NoMilk" in response.json()["error"]
        assert DietComponentMerge.objects.filter(diet=combo).count() == 0


class GramageDashboardMergeDietsToggleApiTest(APITestCase):
    """Prepínač `?merge_diets=` (#568, retirované 10.9.2026) na
    gramage-dashboard endpointe — gatuje LEN súhrnný riadok "Zabaliť
    spolu:" (`spec.rows`), samotné `sub_rows` (diétny riadok) sa ním
    nemenia vôbec (viď `build_table_spec` docstring)."""

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
        celok = Celok.objects.create(nazov="MŠ Testovacia")
        prevadzka = Prevadzka.objects.create(celok=celok, nazov="MŠ Testovacia")
        # `_pack_together_row` sa počíta len v rámci vydajov/trás
        # (`build_table_spec`, per prevádzka) — prevádzka bez trasy padá do
        # "Nepriradené", ktoré túto vetvu nemá, tak jej priradíme reálnu.
        block = DeliveryBlock.objects.create(name="Trasa", sort_order=1)
        route = DeliveryRoute.objects.create(name="Trasa 1", block=block, sort_order=1)
        prevadzka.delivery_route = route
        prevadzka.save(update_fields=["delivery_route"])
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

    def _spec_kinds(self, payload):
        return [row["kind"] for row in payload["spec"]["rows"]]

    def test_default_shows_the_pack_together_row(self):
        response = self.client.get(
            f"/api/admin/meal-plans/gramage-dashboard/?date={self.plan.date.isoformat()}"
        )
        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert self._sub_row_types(payload) == ["standard", "diet"]
        assert "pack-together" in self._spec_kinds(payload)

    def test_merge_diets_0_hides_the_pack_together_row_only(self):
        response = self.client.get(
            "/api/admin/meal-plans/gramage-dashboard/"
            f"?date={self.plan.date.isoformat()}&merge_diets=0"
        )
        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        # sub_rows (skutočná tabuľka) sa prepínačom nemenia vôbec.
        assert self._sub_row_types(payload) == ["standard", "diet"]
        assert "pack-together" not in self._spec_kinds(payload)
