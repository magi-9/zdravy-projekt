"""Integration tests for H1: DailyOrder.data schema validation."""

import datetime

import pytest
from django.urls import reverse
from rest_framework import status

pytestmark = pytest.mark.integration

DATE = datetime.date(2099, 3, 3)  # Far-future Monday — no deadline interference

VALID_DATA = {
    "breakfast": {
        "Dospelý (SŠ)": {"menuCounts": {"A": 2, "B": 1}, "diets": {"Bez lepku": 0}},
        "Škôlka": {"menuCounts": {"A": 5}, "diets": {}},
    },
    "lunch": {
        "Dospelý (SŠ)": {"menuCounts": {"A": 3}, "diets": {}},
    },
    "olovrant": {},
}


@pytest.mark.django_db
class TestOrderDataValidation:
    """DailyOrderSerializer.validate_data() rejects malformed payloads."""

    def _post(self, client, data):
        url = reverse("dailyorder-list")
        return client.post(
            url,
            {"date": str(DATE), "data": data},
            format="json",
        )

    # ------------------------------------------------------------------ #
    # Happy paths
    # ------------------------------------------------------------------ #

    def test_valid_category_nested_data_accepted(self, authenticated_client):
        response = self._post(authenticated_client, VALID_DATA)
        assert response.status_code == status.HTTP_201_CREATED

    def test_empty_data_accepted(self, authenticated_client):
        response = self._post(authenticated_client, {})
        assert response.status_code == status.HTTP_201_CREATED

    def test_partial_meals_accepted(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {"lunch": {"Jasle": {"menuCounts": {"A": 1}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_zero_counts_accepted(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {
                "lunch": {
                    "Dospelý (SŠ)": {"menuCounts": {"A": 0}, "diets": {"Bez lepku": 0}}
                }
            },
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_max_count_accepted(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {"lunch": {"Dospelý (SŠ)": {"menuCounts": {"A": 9999}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_pack_separately_subset_accepted(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {
                "lunch": {
                    "Dospelý (SŠ)": {
                        "menuCounts": {"A": 3},
                        "diets": {"Bez lepku": 2},
                        "packSeparately": {
                            "menus": {"A": 2},
                            "diets": {"Bez lepku": 1},
                        },
                    }
                }
            },
        )
        assert response.status_code == status.HTTP_201_CREATED

    # ------------------------------------------------------------------ #
    # Unknown top-level keys
    # ------------------------------------------------------------------ #

    def test_unknown_meal_key_rejected(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {"lunch": {}, "dinner": {"Cat": {"menuCounts": {"A": 1}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert (
            "dinner" in str(response.data).lower()
            or "unknown" in str(response.data).lower()
        )

    # ------------------------------------------------------------------ #
    # special_diet_note (klient aj admin editor ju posielajú vnútri `data`)
    # ------------------------------------------------------------------ #

    def test_special_diet_note_accepted(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {**VALID_DATA, "special_diet_note": "Bez orechov a zeleru"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["special_diet_note"] == "Bez orechov a zeleru"

    def test_special_diet_note_alone_accepted(self, authenticated_client):
        response = self._post(authenticated_client, {"special_diet_note": "Bez sóje"})
        assert response.status_code == status.HTTP_201_CREATED

    def test_special_diet_note_must_be_text(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {**VALID_DATA, "special_diet_note": {"text": "nope"}},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_special_diet_note_is_not_a_meal_change(self):
        """Zmena samotnej poznámky nesmie znovu spustiť deadline pre jedlá."""
        from api.serializers import DailyOrderSerializer

        previous = {**VALID_DATA, "special_diet_note": "Bez orechov"}
        current = {**VALID_DATA, "special_diet_note": "Bez orechov a zeleru"}
        assert DailyOrderSerializer._changed_meals(current, previous) == []

    def test_special_diet_note_length_capped(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {**VALID_DATA, "special_diet_note": "x" * 1001},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # ------------------------------------------------------------------ #
    # full_day_order (Celodenná objednávka) — príznak žil doteraz len
    # v localStorage frontendu, takže sa medzi zariadeniami/prehliadačmi
    # potichu strácal: klient v móde "celý deň naraz" na jednom zariadení
    # si na inom myslel to isté, appka ale editovala jedlá nezávisle a
    # klient omylom odoslal len časť dňa (Veselý Úľ, 4.9.2026 — raňajky
    # ostali na starom počte, keď sa obed aj olovrant znížili). Príznak
    # teraz ide v `data` vedľa jedál (rovnaký vzor ako `special_diet_note`),
    # aby ho server vedel vrátiť ako autoritatívny pri ďalšom načítaní.
    # ------------------------------------------------------------------ #

    def test_full_day_order_flag_accepted(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {**VALID_DATA, "full_day_order": True},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["full_day_order"] is True

    def test_full_day_order_flag_alone_accepted(self, authenticated_client):
        response = self._post(authenticated_client, {"full_day_order": False})
        assert response.status_code == status.HTTP_201_CREATED

    def test_full_day_order_flag_must_be_boolean(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {**VALID_DATA, "full_day_order": "yes"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_full_day_order_flag_is_not_a_meal_change(self):
        """Zmena samotného príznaku nesmie znovu spustiť deadline pre jedlá."""
        from api.serializers import DailyOrderSerializer

        previous = {**VALID_DATA, "full_day_order": False}
        current = {**VALID_DATA, "full_day_order": True}
        assert DailyOrderSerializer._changed_meals(current, previous) == []

    def test_special_diet_ordered_without_note_rejected(self, authenticated_client):
        """Kuchyňa nevie čo dieťaťu naložiť, ak 'Špeciálna' nemá poznámku."""
        data = {
            "lunch": {
                "Škôlka": {"menuCounts": {"A": 1}, "diets": {"Špeciálna": 1}},
            },
        }
        response = self._post(authenticated_client, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_special_diet_ordered_with_blank_note_rejected(self, authenticated_client):
        data = {
            "lunch": {
                "Škôlka": {"menuCounts": {"A": 1}, "diets": {"Špeciálna": 1}},
            },
            "special_diet_note": "   ",
        }
        response = self._post(authenticated_client, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_special_diet_ordered_with_note_accepted(self, authenticated_client):
        data = {
            "lunch": {
                "Škôlka": {"menuCounts": {"A": 1}, "diets": {"Špeciálna": 1}},
            },
            "special_diet_note": "Bez orechov",
        }
        response = self._post(authenticated_client, data)
        assert response.status_code == status.HTTP_201_CREATED

    def test_special_diet_zero_count_does_not_require_note(self, authenticated_client):
        data = {
            "lunch": {
                "Škôlka": {"menuCounts": {"A": 1}, "diets": {"Špeciálna": 0}},
            },
        }
        response = self._post(authenticated_client, data)
        assert response.status_code == status.HTTP_201_CREATED

    # ------------------------------------------------------------------ #
    # Flat shape compatibility
    # ------------------------------------------------------------------ #

    def test_flat_shape_with_menu_counts_accepted(self, authenticated_client):
        """Legacy flat shape {meal: {menuCounts: ...}} remains supported."""
        response = self._post(
            authenticated_client,
            {"lunch": {"menuCounts": {"A": 5}, "diets": {}}},
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_flat_shape_with_diets_accepted(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {"lunch": {"diets": {"Bez lepku": 1}}},
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_flat_shape_negative_menu_count_rejected(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {"lunch": {"menuCounts": {"A": -1}, "diets": {}}},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # ------------------------------------------------------------------ #
    # Negative and out-of-range counts
    # ------------------------------------------------------------------ #

    def test_negative_menu_count_rejected(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {"lunch": {"Dospelý (SŠ)": {"menuCounts": {"A": -1}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_count_exceeding_max_rejected(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {"lunch": {"Dospelý (SŠ)": {"menuCounts": {"A": 10000}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_negative_diet_count_rejected(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {
                "lunch": {
                    "Dospelý (SŠ)": {"menuCounts": {"A": 1}, "diets": {"Bez lepku": -1}}
                }
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_pack_separately_menu_exceeding_base_rejected(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {
                "lunch": {
                    "Dospelý (SŠ)": {
                        "menuCounts": {"A": 1},
                        "diets": {},
                        "packSeparately": {"menus": {"A": 2}},
                    }
                }
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "nemôže byť väčšie" in str(response.data)

    def test_pack_separately_diet_exceeding_base_rejected(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {
                "lunch": {
                    "Dospelý (SŠ)": {
                        "menuCounts": {"A": 2},
                        "diets": {"Bez lepku": 1},
                        "packSeparately": {"diets": {"Bez lepku": 2}},
                    }
                }
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "nemôže byť väčšie" in str(response.data)

    def test_pack_separately_gn_subset_accepted(self, authenticated_client):
        """ "Zabaliť zvlášť do GN" je nezávislé pole s rovnakou validáciou."""
        response = self._post(
            authenticated_client,
            {
                "lunch": {
                    "Dospelý (SŠ)": {
                        "menuCounts": {"A": 3},
                        "diets": {"Bez lepku": 2},
                        "packSeparatelyGn": {
                            "menus": {"A": 2},
                            "diets": {"Bez lepku": 1},
                        },
                    }
                }
            },
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_pack_separately_split_between_zvlast_and_gn_accepted(
        self, authenticated_client
    ):
        """3 objednané: 2 "zvlášť" + 1 "do GN" - dokopy presne sedí, prijme sa."""
        response = self._post(
            authenticated_client,
            {
                "lunch": {
                    "Dospelý (SŠ)": {
                        "menuCounts": {"A": 3},
                        "diets": {},
                        "packSeparately": {"menus": {"A": 2}},
                        "packSeparatelyGn": {"menus": {"A": 1}},
                    }
                }
            },
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_pack_separately_zvlast_and_gn_combined_exceeding_base_rejected(
        self, authenticated_client
    ):
        """Súčet "zvlášť" a "do GN" nesmie prekročiť objednaný počet, aj keď
        každé zvlášť je v limite - jedna porcia sa nedá zabaliť dvakrát."""
        response = self._post(
            authenticated_client,
            {
                "lunch": {
                    "Dospelý (SŠ)": {
                        "menuCounts": {"A": 3},
                        "diets": {},
                        "packSeparately": {"menus": {"A": 2}},
                        "packSeparatelyGn": {"menus": {"A": 2}},
                    }
                }
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "nemôže byť väčší" in str(response.data)

    # ------------------------------------------------------------------ #
    # Non-integer counts
    # ------------------------------------------------------------------ #

    def test_string_menu_count_rejected(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {"lunch": {"Dospelý (SŠ)": {"menuCounts": {"A": "five"}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_float_menu_count_rejected(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {"lunch": {"Dospelý (SŠ)": {"menuCounts": {"A": 1.5}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_boolean_menu_count_rejected(self, authenticated_client):
        """True/False must not be accepted as integers (bool subclasses int in Python)."""
        response = self._post(
            authenticated_client,
            {"lunch": {"Dospelý (SŠ)": {"menuCounts": {"A": True}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # ------------------------------------------------------------------ #
    # Structural violations
    # ------------------------------------------------------------------ #

    def test_data_not_object_rejected(self, authenticated_client):
        response = self._post(authenticated_client, [1, 2, 3])
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_meal_not_object_rejected(self, authenticated_client):
        response = self._post(authenticated_client, {"lunch": "invalid"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_category_not_object_rejected(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {"lunch": {"Dospelý (SŠ)": "invalid"}},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_menu_counts_not_object_rejected(self, authenticated_client):
        response = self._post(
            authenticated_client,
            {"lunch": {"Dospelý (SŠ)": {"menuCounts": [1, 2], "diets": {}}}},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_null_menu_counts_rejected(self, authenticated_client):
        """Explicit null for menuCounts must be rejected (not silently treated as empty)."""
        response = self._post(
            authenticated_client,
            {"lunch": {"Dospelý (SŠ)": {"menuCounts": None, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_null_diets_rejected(self, authenticated_client):
        """Explicit null for diets must be rejected (not silently treated as empty)."""
        response = self._post(
            authenticated_client,
            {"lunch": {"Dospelý (SŠ)": {"menuCounts": {"A": 1}, "diets": None}}},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_boolean_diet_count_rejected(self, authenticated_client):
        """Boolean values in diets must be rejected (bool is a subclass of int in Python)."""
        response = self._post(
            authenticated_client,
            {
                "lunch": {
                    "Dospelý (SŠ)": {
                        "menuCounts": {"A": 1},
                        "diets": {"Bez lepku": True},
                    }
                }
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # ------------------------------------------------------------------ #
    # Size limit
    # ------------------------------------------------------------------ #

    def test_oversized_payload_rejected(self, authenticated_client):
        """A payload exceeding 10 KB must be rejected."""
        big_data = {
            "lunch": {
                f"Cat{i}": {
                    "menuCounts": {"A": 1},
                    "diets": {f"diet_{j}": 0 for j in range(200)},
                }
                for i in range(50)
            }
        }
        response = self._post(authenticated_client, big_data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestPortionTypeRestriction:
    """DailyOrderSerializer._enforce_portion_types (#Rusovce — jasle napriek
    tomu, že prevádzka má povolené len Škôlku a Dospelých, 1.9.2026)."""

    def _post(self, client, data):
        url = reverse("dailyorder-list")
        return client.post(url, {"date": str(DATE), "data": data}, format="json")

    def test_rejects_a_size_the_prevadzka_does_not_allow(
        self, authenticated_client, user
    ):
        from api.models import PortionType

        prevadzka = user.profile.dostupne_prevadzky().get()
        allowed, _ = PortionType.objects.get_or_create(
            name="Škôlka", defaults={"coefficient": 1}
        )
        prevadzka.visible_portion_types.set([allowed])

        response = self._post(
            authenticated_client,
            {"lunch": {"Jasle": {"menuCounts": {"A": 1}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_accepts_an_allowed_size(self, authenticated_client, user):
        from api.models import PortionType

        prevadzka = user.profile.dostupne_prevadzky().get()
        allowed, _ = PortionType.objects.get_or_create(
            name="Škôlka", defaults={"coefficient": 1}
        )
        prevadzka.visible_portion_types.set([allowed])

        response = self._post(
            authenticated_client,
            {"lunch": {"Škôlka": {"menuCounts": {"A": 1}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_empty_visible_portion_types_means_unrestricted(
        self, authenticated_client, user
    ):
        """Prázdne M2M = ešte nezakonfigurované, nie zámerne nič nepovolené."""
        prevadzka = user.profile.dostupne_prevadzky().get()
        prevadzka.visible_portion_types.clear()

        response = self._post(
            authenticated_client,
            {"lunch": {"Jasle": {"menuCounts": {"A": 1}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_a_zero_count_in_a_disallowed_size_is_not_rejected(
        self, authenticated_client, user
    ):
        """Nulová kostra kategórie (napr. z auto-objednávky) nie je 'objednávka'."""
        from api.models import PortionType

        prevadzka = user.profile.dostupne_prevadzky().get()
        allowed, _ = PortionType.objects.get_or_create(
            name="Škôlka", defaults={"coefficient": 1}
        )
        prevadzka.visible_portion_types.set([allowed])

        response = self._post(
            authenticated_client,
            {
                "lunch": {
                    "Škôlka": {"menuCounts": {"A": 1}, "diets": {}},
                    "Jasle": {"menuCounts": {"A": 0}, "diets": {}},
                }
            },
        )
        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
class TestMenuDayRestriction:
    """DailyOrderSerializer._enforce_menu_day_restrictions ('menu B len v
    piatok') — AdminOrderEditorModal aj priamy zápis obchádzali klientský
    filter (`filterMenusByDay`), ktorý toto obmedzenie skrýval len vizuálne."""

    TUESDAY = DATE  # 2099-03-03
    FRIDAY = DATE + datetime.timedelta(days=3)  # 2099-03-06

    def _post(self, client, order_date, data):
        url = reverse("dailyorder-list")
        return client.post(url, {"date": str(order_date), "data": data}, format="json")

    def test_rejects_the_restricted_menu_on_a_disallowed_day(
        self, authenticated_client, user
    ):
        prevadzka = user.profile.dostupne_prevadzky().get()
        prevadzka.menu_day_restrictions = {"B": [5]}  # 5 = piatok
        prevadzka.save(update_fields=["menu_day_restrictions"])

        response = self._post(
            authenticated_client,
            self.TUESDAY,
            {"lunch": {"Dospelý (SŠ)": {"menuCounts": {"B": 1}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_accepts_the_restricted_menu_on_its_allowed_day(
        self, authenticated_client, user
    ):
        prevadzka = user.profile.dostupne_prevadzky().get()
        prevadzka.menu_day_restrictions = {"B": [5]}
        prevadzka.save(update_fields=["menu_day_restrictions"])

        response = self._post(
            authenticated_client,
            self.FRIDAY,
            {"lunch": {"Dospelý (SŠ)": {"menuCounts": {"B": 1}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_a_menu_without_a_restriction_is_unaffected(
        self, authenticated_client, user
    ):
        prevadzka = user.profile.dostupne_prevadzky().get()
        prevadzka.menu_day_restrictions = {"B": [5]}
        prevadzka.save(update_fields=["menu_day_restrictions"])

        response = self._post(
            authenticated_client,
            self.TUESDAY,
            {"lunch": {"Dospelý (SŠ)": {"menuCounts": {"A": 1}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_no_restrictions_configured_means_every_day_is_allowed(
        self, authenticated_client, user
    ):
        prevadzka = user.profile.dostupne_prevadzky().get()
        assert prevadzka.menu_day_restrictions == {}

        response = self._post(
            authenticated_client,
            self.TUESDAY,
            {"lunch": {"Dospelý (SŠ)": {"menuCounts": {"B": 1}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_a_zero_count_on_the_restricted_menu_is_not_rejected(
        self, authenticated_client, user
    ):
        prevadzka = user.profile.dostupne_prevadzky().get()
        prevadzka.menu_day_restrictions = {"B": [5]}
        prevadzka.save(update_fields=["menu_day_restrictions"])

        response = self._post(
            authenticated_client,
            self.TUESDAY,
            {"lunch": {"Dospelý (SŠ)": {"menuCounts": {"A": 1, "B": 0}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
class TestMealDayRestriction:
    """DailyOrderSerializer._enforce_meal_day_restrictions ('raňajky len v
    piatok') — rovnaká sémantika ako menu_day_restrictions, len na úrovni
    celého jedla (breakfast/lunch/olovrant), nie jednotlivého menu písmena."""

    TUESDAY = DATE  # 2099-03-03
    FRIDAY = DATE + datetime.timedelta(days=3)  # 2099-03-06

    def _post(self, client, order_date, data):
        url = reverse("dailyorder-list")
        return client.post(url, {"date": str(order_date), "data": data}, format="json")

    def test_rejects_the_restricted_meal_on_a_disallowed_day(
        self, authenticated_client, user
    ):
        prevadzka = user.profile.dostupne_prevadzky().get()
        prevadzka.meal_day_restrictions = {"breakfast": [5]}  # 5 = piatok
        prevadzka.save(update_fields=["meal_day_restrictions"])

        response = self._post(
            authenticated_client,
            self.TUESDAY,
            {"breakfast": {"Dospelý (SŠ)": {"menuCounts": {"A": 1}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_accepts_the_restricted_meal_on_its_allowed_day(
        self, authenticated_client, user
    ):
        prevadzka = user.profile.dostupne_prevadzky().get()
        prevadzka.meal_day_restrictions = {"breakfast": [5]}
        prevadzka.save(update_fields=["meal_day_restrictions"])

        response = self._post(
            authenticated_client,
            self.FRIDAY,
            {"breakfast": {"Dospelý (SŠ)": {"menuCounts": {"A": 1}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_a_meal_without_a_restriction_is_unaffected(
        self, authenticated_client, user
    ):
        prevadzka = user.profile.dostupne_prevadzky().get()
        prevadzka.meal_day_restrictions = {"breakfast": [5]}
        prevadzka.save(update_fields=["meal_day_restrictions"])

        response = self._post(
            authenticated_client,
            self.TUESDAY,
            {"lunch": {"Dospelý (SŠ)": {"menuCounts": {"A": 1}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_no_restrictions_configured_means_every_day_is_allowed(
        self, authenticated_client, user
    ):
        prevadzka = user.profile.dostupne_prevadzky().get()
        assert prevadzka.meal_day_restrictions == {}

        response = self._post(
            authenticated_client,
            self.TUESDAY,
            {"breakfast": {"Dospelý (SŠ)": {"menuCounts": {"A": 1}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_a_zero_count_on_the_restricted_meal_is_not_rejected(
        self, authenticated_client, user
    ):
        prevadzka = user.profile.dostupne_prevadzky().get()
        prevadzka.meal_day_restrictions = {"breakfast": [5]}
        prevadzka.save(update_fields=["meal_day_restrictions"])

        response = self._post(
            authenticated_client,
            self.TUESDAY,
            {"breakfast": {"Dospelý (SŠ)": {"menuCounts": {"A": 0}, "diets": {}}}},
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_a_positive_diet_count_on_the_restricted_meal_is_rejected(
        self, authenticated_client, user
    ):
        """Nielen menuCounts, aj len 'diets' počet musí spustiť obmedzenie."""
        prevadzka = user.profile.dostupne_prevadzky().get()
        prevadzka.meal_day_restrictions = {"breakfast": [5]}
        prevadzka.save(update_fields=["meal_day_restrictions"])

        response = self._post(
            authenticated_client,
            self.TUESDAY,
            {
                "breakfast": {
                    "Dospelý (SŠ)": {"menuCounts": {}, "diets": {"Bez lepku": 1}}
                }
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
