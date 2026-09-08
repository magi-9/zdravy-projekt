"""End-to-end cez `gramage_dashboard`: `DietComponentMerge` (#568) presúva
gramáž zložiek označených ako "spolu" z diétneho riadku do štandardného.

Menu A má dve zložky (Hlavná časť 200 g, Príloha 100 g na hlavu) — testy
pokrývajú čiastočné zlúčenie (jedna zložka spolu, druhá zvlášť — diétny
riadok ostáva, len ochudobnený o presunutú zložku) aj úplné (obe zložky
spolu — diéta sa v tomto jedle od štandardu nedá rozoznať, vlastný riadok
nedostane vôbec, jej hlavy sa pripočítajú do štandardného riadku)."""

import datetime

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

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
from api.services.meal_plan_service import MealPlanService

MAIN_COURSE_COMPONENTS = [
    {"label": "Hlavná časť", "grams": "200", "unit": "g"},
    {"label": "Príloha", "grams": "100", "unit": "g"},
]


def _plan_with_menu_a(date):
    call_command("init_reference_data")
    plan = DailyMealPlan.objects.create(date=date)
    MealPlanItem.objects.create(
        meal_plan=plan,
        template=MealTemplate.objects.create(
            name="Obed A",
            category="main_course",
            components=MAIN_COURSE_COMPONENTS,
            base_weight_grams="300",
        ),
        category="main_course",
        menu_variant="A",
    )
    return plan


def _order(prevadzka, user, date, diet_count):
    return DailyOrder.objects.create(
        user=user,
        prevadzka=prevadzka,
        date=date,
        data={
            "lunch": {
                "Škôlka": {
                    "menuCounts": {"A": 6},
                    "diets": {"Bez lepku": diet_count},
                }
            }
        },
    )


def _setup(date, diet_count=2):
    plan = _plan_with_menu_a(date)
    diet = Diet.objects.create(name="Bez lepku")
    celok = Celok.objects.create(nazov="MŠ Testovacia")
    prevadzka = Prevadzka.objects.create(celok=celok, nazov="MŠ Testovacia")
    user = User.objects.create_user(username="test@example.com", password="x")
    _order(prevadzka, user, plan.date, diet_count)
    return plan, diet


@pytest.mark.django_db
def test_no_merge_rows_keeps_todays_behaviour():
    plan, _diet = _setup(datetime.date(2026, 9, 14))

    data = MealPlanService.gramage_dashboard(plan.date.isoformat())
    row = data["rows"][0]

    standard = next(sr for sr in row["sub_rows"] if sr["type"] == "standard")
    diet_row = next(sr for sr in row["sub_rows"] if sr["type"] == "diet")
    # `menuCounts.A=6` už zahŕňa 2 diétne hlavy (diéta je podmnožina, nie
    # navyše) — čistý štandard je 4 hlavy, diéta 2.
    assert standard["col_grams"][0] == ["800.00", "400.00"]  # 4 hlavy × 200/100
    assert diet_row["col_grams"][0] == ["400.00", "200.00"]  # 2 hlavy × 200/100
    assert diet_row["count"] == 2


@pytest.mark.django_db
def test_partial_merge_moves_only_the_marked_component():
    plan, diet = _setup(datetime.date(2026, 9, 15))
    DietComponentMerge.objects.create(
        date=plan.date,
        meal=MealCategory.MAIN_COURSE,
        component_index=0,  # Hlavná časť
        diet=diet,
    )

    data = MealPlanService.gramage_dashboard(plan.date.isoformat())
    row = data["rows"][0]

    standard = next(sr for sr in row["sub_rows"] if sr["type"] == "standard")
    diet_row = next(sr for sr in row["sub_rows"] if sr["type"] == "diet")

    # 4 čisté hlavy (800) + Hlavná časť 2 diétnych hláv (400) = 1200.
    assert standard["col_grams"][0] == ["1200.00", "400.00"]
    # Diétny riadok ostáva (Príloha je stále zvlášť), Hlavná časť je "0".
    assert diet_row["col_grams"][0] == ["0.00", "200.00"]
    # Počet hláv diéty sa nemení — je to gramové presunutie, nie hlavové.
    assert diet_row["count"] == 2
    assert standard["count"] == 4

    # Dňový súčet stĺpca musí sedieť na presne to isté číslo ako predtým
    # (400 + 800 nezlúčené == 1200 zlúčené) — presun nesmie stratiť gramy.
    assert data["totals"][0] == ["1200.00", "400.00"]


@pytest.mark.django_db
def test_full_merge_removes_the_diet_row_and_folds_the_heads_into_standard():
    plan, diet = _setup(datetime.date(2026, 9, 16))
    for component_index in (0, 1):
        DietComponentMerge.objects.create(
            date=plan.date,
            meal=MealCategory.MAIN_COURSE,
            component_index=component_index,
            diet=diet,
        )

    data = MealPlanService.gramage_dashboard(plan.date.isoformat())
    row = data["rows"][0]

    assert [sr["type"] for sr in row["sub_rows"]] == ["standard"]
    standard = row["sub_rows"][0]
    # 4 čisté + 2 zlúčené = 6 hláv na oboch zložkách.
    assert standard["col_grams"][0] == ["1200.00", "600.00"]
    assert standard["count"] == 6
    assert data["totals"][0] == ["1200.00", "600.00"]

    # Diéta sa v tomto jedle nemá čo sumarizovať zvlášť.
    assert row["diet_summary_rows"] == []
    assert row["total_count"] == 6


@pytest.mark.django_db
def test_merge_only_applies_to_the_configured_diet():
    """Iná diéta v ten istý deň, bez vlastného merge riadku, ostáva
    nezlúčená — flag je per (deň, jedlo, zložka, DIÉTA)."""
    plan = _plan_with_menu_a(datetime.date(2026, 9, 17))
    merged_diet = Diet.objects.create(name="Bez lepku")
    Diet.objects.create(name="Bez laktózy")
    DietComponentMerge.objects.create(
        date=plan.date,
        meal=MealCategory.MAIN_COURSE,
        component_index=0,
        diet=merged_diet,
    )
    celok = Celok.objects.create(nazov="MŠ Testovacia")
    prevadzka = Prevadzka.objects.create(celok=celok, nazov="MŠ Testovacia")
    user = User.objects.create_user(username="test2@example.com", password="x")
    DailyOrder.objects.create(
        user=user,
        prevadzka=prevadzka,
        date=plan.date,
        data={
            "lunch": {
                "Škôlka": {
                    "menuCounts": {"A": 6},
                    "diets": {"Bez lepku": 2, "Bez laktózy": 1},
                }
            }
        },
    )

    data = MealPlanService.gramage_dashboard(plan.date.isoformat())
    row = data["rows"][0]
    diet_rows = {sr["diet_name"]: sr for sr in row["sub_rows"] if sr["type"] == "diet"}

    assert diet_rows["Bez lepku"]["col_grams"][0] == ["0.00", "200.00"]
    assert diet_rows["Bez laktózy"]["col_grams"][0] == ["200.00", "100.00"]


@pytest.mark.django_db
def test_merge_matches_by_component_label_not_position():
    """Diéta má vlastnú šablónu so zložkami v OPAČNOM poradí než štandard
    (Príloha/Hlavná časť namiesto Hlavná časť/Príloha) — kliknutá "Hlavná
    časť" (index 0 v štandardnom boarde) sa musí spárovať s "Hlavná časť"
    v diétnej šablóne (tam na indexe 1), nie s tým, čo je na indexe 0 tam
    (Príloha) len preto, že čísla sedia."""
    call_command("init_reference_data")
    plan = _plan_with_menu_a(datetime.date(2026, 9, 18))
    diet = Diet.objects.create(name="Bez lepku")
    MealPlanItem.objects.create(
        meal_plan=plan,
        template=MealTemplate.objects.create(
            name="Obed A bezlepkový",
            category="main_course",
            components=[
                {"label": "Príloha", "grams": "90", "unit": "g"},
                {"label": "Hlavná časť", "grams": "180", "unit": "g"},
            ],
            base_weight_grams="270",
        ),
        category="main_course",
        menu_variant="A",
        diet=diet,
    )
    celok = Celok.objects.create(nazov="MŠ Testovacia")
    prevadzka = Prevadzka.objects.create(celok=celok, nazov="MŠ Testovacia")
    user = User.objects.create_user(username="label-match@example.com", password="x")
    DailyOrder.objects.create(
        user=user,
        prevadzka=prevadzka,
        date=plan.date,
        data={
            "lunch": {
                "Škôlka": {
                    "menuCounts": {"A": 6},
                    "diets": {"Bez lepku": 2},
                }
            }
        },
    )
    # Klik z boardu je vždy voči štandardnej šablóne: index 0 tam je
    # "Hlavná časť" (viď MAIN_COURSE_COMPONENTS).
    DietComponentMerge.objects.create(
        date=plan.date,
        meal=MealCategory.MAIN_COURSE,
        component_index=0,
        diet=diet,
    )

    data = MealPlanService.gramage_dashboard(plan.date.isoformat())
    row = data["rows"][0]
    standard_group_index = next(
        i
        for i, g in enumerate(data["col_groups"])
        if g["meal"] == "main_course" and not g.get("diet_id")
    )
    diet_group_index = next(
        i
        for i, g in enumerate(data["col_groups"])
        if g["meal"] == "main_course" and g.get("diet_id")
    )
    standard = next(sr for sr in row["sub_rows"] if sr["type"] == "standard")
    diet_row = next(sr for sr in row["sub_rows"] if sr["type"] == "diet")

    # 4 čisté hlavy × 200 (800) + 2 diétne hlavy × 180 "Hlavná časť" (360).
    assert standard["col_grams"][standard_group_index] == ["1160.00", "400.00"]
    # Diétny riadok si necháva len svoju Prílohu (2 × 90 = 180), Hlavná časť
    # (na indexe 1 v JEJ VLASTNEJ šablóne) je vynulovaná.
    assert diet_row["col_grams"][diet_group_index] == ["180.00", "0.00"]
