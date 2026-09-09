"""GET/POST /api/admin/meal-plans/diet-packing-preferences/ (9.9.2026) —
checkbox „táto diéta sa dnes balí zvlášť", plošne naprieč prevádzkami,
default (bez záznamu) = spolu."""

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import Diet, DietPackingPreference


class DietPackingPreferencesApiTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="packing-admin@example.com",
            password="password",
            email="packing-admin@example.com",
            is_staff=True,
        )
        self.no_milk = Diet.objects.create(name="No Milk")
        self.combo = Diet.objects.create(name="Diéta X + No Milk")
        self.combo.base_diets.add(self.no_milk)
        self.client.force_authenticate(user=self.admin)

    def test_get_without_preferences_defaults_to_together(self):
        response = self.client.get(
            "/api/admin/meal-plans/diet-packing-preferences/?date=2026-09-10"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        by_name = {d["name"]: d for d in response.json()["diets"]}
        self.assertFalse(by_name["No Milk"]["pack_separately"])
        self.assertFalse(by_name["No Milk"]["effective_separately"])

    def test_post_toggles_diet_to_separate(self):
        response = self.client.post(
            "/api/admin/meal-plans/diet-packing-preferences/?date=2026-09-10",
            {"diet_id": self.no_milk.id, "pack_separately": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        by_name = {d["name"]: d for d in response.json()["diets"]}
        self.assertTrue(by_name["No Milk"]["pack_separately"])
        self.assertTrue(by_name["No Milk"]["effective_separately"])
        self.assertTrue(
            DietPackingPreference.objects.filter(
                diet=self.no_milk, date="2026-09-10", pack_separately=True
            ).exists()
        )

    def test_combined_diet_shows_effective_separate_without_its_own_record(self):
        DietPackingPreference.objects.create(
            diet=self.no_milk, date="2026-09-10", pack_separately=True
        )
        response = self.client.get(
            "/api/admin/meal-plans/diet-packing-preferences/?date=2026-09-10"
        )
        by_name = {d["name"]: d for d in response.json()["diets"]}
        self.assertTrue(by_name["Diéta X + No Milk"]["effective_separately"])
        self.assertFalse(by_name["Diéta X + No Milk"]["pack_separately"])

    def test_post_false_clears_back_to_default_together(self):
        DietPackingPreference.objects.create(
            diet=self.no_milk, date="2026-09-10", pack_separately=True
        )
        response = self.client.post(
            "/api/admin/meal-plans/diet-packing-preferences/?date=2026-09-10",
            {"diet_id": self.no_milk.id, "pack_separately": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            DietPackingPreference.objects.filter(diet=self.no_milk).exists()
        )

    def test_preference_does_not_leak_into_another_day(self):
        DietPackingPreference.objects.create(
            diet=self.no_milk, date="2026-09-10", pack_separately=True
        )
        response = self.client.get(
            "/api/admin/meal-plans/diet-packing-preferences/?date=2026-09-11"
        )
        by_name = {d["name"]: d for d in response.json()["diets"]}
        self.assertFalse(by_name["No Milk"]["pack_separately"])
        self.assertFalse(by_name["No Milk"]["effective_separately"])

    def test_date_required(self):
        response = self.client.get("/api/admin/meal-plans/diet-packing-preferences/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
