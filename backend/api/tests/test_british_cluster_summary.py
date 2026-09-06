"""British School (Cluster C, #531) nemá gramážové menu-šablóny — kusový
sumár + prepočet na MŠ porcie sa počíta priamo z `DailyOrder.data`, mimo
bežného `col_groups`/`sub_rows` pipeline (MealPlanService.gramage_dashboard).
"""

import datetime
from decimal import Decimal

import pytest

from api.services.british_cluster_summary import (
    meal_items_from_order_data,
)


class TestMealItemsFromOrderData:
    """Čistá funkcia — žiadna DB, len order.data + koeficienty."""

    def test_empty_order_data_returns_no_items(self):
        assert meal_items_from_order_data({}, {}) == []

    def test_breakfast_and_olovrant_are_flat_head_counts(self):
        order_data = {
            "breakfast": {"Škôlka": {"menuCounts": {"A": 10}, "diets": {}}},
            "olovrant": {"Škôlka": {"menuCounts": {"A": 8}, "diets": {}}},
        }
        items = meal_items_from_order_data(order_data, {"Škôlka": Decimal("1")})
        by_label = {item["label"]: item for item in items}
        assert by_label["Raňajky"]["heads"] == Decimal("10")
        assert by_label["Raňajky"]["total"] == Decimal("10")
        assert by_label["Olovrant"]["heads"] == Decimal("8")

    def test_desiata_gets_its_own_band(self):
        """Desiata NIE JE náš interný olovrant/desiata koncept — samostatný
        riadok, kusovo, žiadny prepočet naviac (user 4.9.2026)."""
        order_data = {
            "desiata": {
                "ZŠ 1.stupeň": {"menuCounts": {"A": 26}, "diets": {}},
                "ZŠ 2.stupeň": {"menuCounts": {"A": 12}, "diets": {}},
            },
        }
        coeffs = {"ZŠ 1.stupeň": Decimal("1.25"), "ZŠ 2.stupeň": Decimal("1")}
        items = meal_items_from_order_data(order_data, coeffs)
        assert len(items) == 1
        assert items[0]["label"] == "Desiata"
        assert items[0]["heads"] == Decimal("38")
        # MŠ prepočet: 26 * 1.25 + 12 * 1 = 44.5
        assert items[0]["total"] == Decimal("44.50")

    def test_lunch_breaks_down_by_menu_variant_including_d_and_vege1(self):
        order_data = {
            "lunch": {
                "Dospelý (SŠ)": {
                    "menuCounts": {"A": 101, "B": 5, "C": 53, "D": 32},
                    "diets": {"VEGGIE": 4, "VEGAN": 1},
                },
                "Škôlka": {"menuCounts": {"A": 89}, "diets": {}},
            },
        }
        coeffs = {"Dospelý (SŠ)": Decimal("2"), "Škôlka": Decimal("1")}
        items = meal_items_from_order_data(order_data, coeffs)
        obed = next(item for item in items if item["label"] == "Obed")
        # heads = súčet menuCounts (diéty sú drill-down tej istej hlavičky,
        # NIE navyše — rovnaká logika ako `effective_menu` v edupage_scraper).
        assert obed["heads"] == Decimal(101 + 5 + 53 + 32 + 89)
        menus_by_label = {m["label"]: m for m in obed["menus"]}
        assert menus_by_label["Menu D"]["heads"] == Decimal("32")
        assert menus_by_label["Menu D"]["total"] == Decimal("64")  # 32 * 2
        assert "Menu VEGE1" not in menus_by_label

    def test_lunch_breaks_down_vege1_when_present(self):
        order_data = {
            "lunch": {
                "Dospelý (SŠ)": {"menuCounts": {"A": 10, "VEGE1": 3}, "diets": {}},
            },
        }
        items = meal_items_from_order_data(order_data, {"Dospelý (SŠ)": Decimal("2")})
        obed = next(item for item in items if item["label"] == "Obed")
        menus_by_label = {m["label"]: m for m in obed["menus"]}
        assert menus_by_label["Menu VEGE1"]["heads"] == Decimal("3")
        assert menus_by_label["Menu VEGE1"]["total"] == Decimal("6")

    def test_menu_order_is_stable_a_b_c_d_vege1(self):
        order_data = {
            "lunch": {
                "Škôlka": {
                    "menuCounts": {"VEGE1": 1, "D": 1, "C": 1, "A": 1, "B": 1},
                    "diets": {},
                },
            },
        }
        items = meal_items_from_order_data(order_data, {"Škôlka": Decimal("1")})
        obed = next(item for item in items if item["label"] == "Obed")
        assert [m["label"] for m in obed["menus"]] == [
            "Menu A",
            "Menu B",
            "Menu C",
            "Menu D",
            "Menu VEGE1",
        ]

    def test_meal_absent_that_day_is_not_included(self):
        """Škola nemala napr. desiatu daný deň (voľno/chyba) — riadok sa
        vôbec nemá vypísať, nie ako nula (rovnaký princíp ako `_cluster_ms_totals`)."""
        order_data = {"lunch": {"Škôlka": {"menuCounts": {"A": 5}, "diets": {}}}}
        items = meal_items_from_order_data(order_data, {"Škôlka": Decimal("1")})
        assert [item["label"] for item in items] == ["Obed"]

    def test_unknown_portion_defaults_to_coefficient_one(self):
        order_data = {"breakfast": {"Neznáma": {"menuCounts": {"A": 4}, "diets": {}}}}
        items = meal_items_from_order_data(order_data, {})
        assert items[0]["total"] == Decimal("4")

    def test_single_menu_variant_lunch_has_no_menu_breakdown(self):
        """Jediný variant (napr. len Klasik) by len duplikoval riadok Obed
        priamo nad sebou — rovnaký princíp ako `_cluster_ms_totals`."""
        order_data = {"lunch": {"Škôlka": {"menuCounts": {"A": 5}, "diets": {}}}}
        items = meal_items_from_order_data(order_data, {"Škôlka": Decimal("1")})
        obed = next(item for item in items if item["label"] == "Obed")
        assert "menus" not in obed


@pytest.mark.django_db
class TestBuildGramageSummaryOnlyClusters:
    def test_no_summary_only_prevadzky_returns_empty(self):
        from api.services.british_cluster_summary import (
            build_gramage_summary_only_clusters,
        )

        assert build_gramage_summary_only_clusters("2026-09-07") == []

    def test_builds_cluster_for_a_summary_only_prevadzka(self):
        from api.models import (
            Celok,
            DailyOrder,
            DeliveryBlock,
            DeliveryRoute,
            Prevadzka,
            Vydaj,
        )
        from api.services.british_cluster_summary import (
            build_gramage_summary_only_clusters,
        )

        celok = Celok.objects.create(nazov="British School")
        prevadzka = Prevadzka.objects.create(
            celok=celok, nazov="British School", gramage_summary_only=True
        )
        block = DeliveryBlock.objects.create(name="Trasa extra", sort_order=2)
        route = DeliveryRoute.objects.create(
            name="British School", block=block, vydaj=Vydaj.C, sort_order=1
        )
        prevadzka.delivery_route = route
        prevadzka.save(update_fields=["delivery_route"])
        target_date = datetime.date(2026, 9, 7)
        DailyOrder.objects.create(
            prevadzka=prevadzka,
            date=target_date,
            data={
                "breakfast": {"Škôlka": {"menuCounts": {"A": 10}, "diets": {}}},
                "lunch": {
                    "Škôlka": {"menuCounts": {"A": 20, "D": 3}, "diets": {}},
                },
            },
        )

        clusters = build_gramage_summary_only_clusters("2026-09-07")

        assert len(clusters) == 1
        cluster = clusters[0]
        assert cluster["vydaj_key"] == str(Vydaj.C)
        assert cluster["route_name"] == "British School"
        labels = {item["label"]: item for item in cluster["meals"]}
        assert labels["Raňajky"]["heads"] == Decimal("10")
        assert labels["Obed"]["heads"] == Decimal("23")

    def test_prevadzka_without_order_that_day_is_omitted(self):
        from api.models import Celok, Prevadzka
        from api.services.british_cluster_summary import (
            build_gramage_summary_only_clusters,
        )

        celok = Celok.objects.create(nazov="British School")
        Prevadzka.objects.create(
            celok=celok, nazov="British School", gramage_summary_only=True
        )

        assert build_gramage_summary_only_clusters("2026-09-07") == []
