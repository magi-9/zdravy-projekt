"""End-to-end cez `gramage_dashboard`: `DietComponentMerge` (#568) už NEOVPLYVŇUJE
skutočnú gramážnu tabuľku (retirované 10.9.2026 — pôvodne presúvalo gramáž
zložiek do štandardného riadku, kým sa nezistilo, že admin/kuchyňa chce
tabuľku nezmenenú a nový súhrn navyše, nie prepisovanie existujúcich
riadkov, viď `test_gramage_table_spec_pack_together.py`).

Diétny riadok (`sub_row.type == "diet"`) sa preto vždy zobrazuje celý, bez
ohľadu na to, čo je (alebo nie je) nastavené na `diet-component-merge`
boarde — presne ako pred #568. Board ostáva len ako referenčný nástroj pre
kuchyňu (a vstup do "Zabaliť spolu:" riadku), tabuľku samotnú už nemení."""

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
def test_diet_keeps_its_own_row_with_no_board_state_at_all():
    plan, _diet = _setup(datetime.date(2026, 9, 14))

    data = MealPlanService.gramage_dashboard(plan.date.isoformat())
    row = data["rows"][0]

    assert [sr["type"] for sr in row["sub_rows"]] == ["standard", "diet"]
    standard = row["sub_rows"][0]
    diet_row = row["sub_rows"][1]
    # 4 čisté hlavy (800/400), 2 diétne hlavy vo vlastnom riadku (400/200) —
    # presne ako pred #568, nič sa nepresúva.
    assert standard["col_grams"][0] == ["800.00", "400.00"]
    assert standard["count"] == 4
    assert diet_row["col_grams"][0] == ["400.00", "200.00"]
    assert diet_row["count"] == 2
    # `totals` sčítava len štandardné (bezdiétne) riadky — presne ako
    # vždy, diétne porcie majú vlastný súhrn (`diet_summary_rows`).
    assert data["totals"][0] == ["800.00", "400.00"]


@pytest.mark.django_db
def test_board_state_has_no_effect_on_the_diet_row_spolu():
    """Diéta odklikaná ako "spolu" (default, žiadny riadok) na boarde —
    tabuľka sa nesmie líšiť od predchádzajúceho testu (bez akéhokoľvek
    board stavu)."""
    plan, diet = _setup(datetime.date(2026, 9, 15))
    assert not DietComponentMerge.objects.filter(diet=diet).exists()

    data = MealPlanService.gramage_dashboard(plan.date.isoformat())
    row = data["rows"][0]

    assert [sr["type"] for sr in row["sub_rows"]] == ["standard", "diet"]
    assert row["sub_rows"][0]["col_grams"][0] == ["800.00", "400.00"]
    assert row["sub_rows"][1]["col_grams"][0] == ["400.00", "200.00"]


@pytest.mark.django_db
def test_board_state_has_no_effect_on_the_diet_row_zvlast():
    """Diéta odklikaná ako "zvlášť" na boarde (oba komponenty) — tabuľka sa
    aj tak nesmie líšiť, board už tabuľku neovplyvňuje."""
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

    assert [sr["type"] for sr in row["sub_rows"]] == ["standard", "diet"]
    assert row["sub_rows"][0]["col_grams"][0] == ["800.00", "400.00"]
    assert row["sub_rows"][1]["col_grams"][0] == ["400.00", "200.00"]


@pytest.mark.django_db
def test_diet_pack_state_defaults_to_spolu_with_no_board_rows():
    """`data["diet_pack_state"]` (10.9.2026) je vstup pre "S"/"Z" odznak a
    pre "Zabaliť spolu:" (`gramage_table_spec`) — bez board riadkov nemá
    žiadna diéta zápis (default "S" sa aplikuje až u volajúceho)."""
    plan, _diet = _setup(datetime.date(2026, 9, 19))

    data = MealPlanService.gramage_dashboard(plan.date.isoformat())

    assert data["diet_pack_state"] == {}


@pytest.mark.django_db
def test_diet_pack_state_reports_zvlast_for_a_diet_with_any_separated_component():
    """Diéta so zvlášť-riadkom na hoci len JEDNOM komponente je "Z" pre celé
    jedlo — kuchyňa to vníma ako jedno rozhodnutie, nie po zložkách."""
    plan, diet = _setup(datetime.date(2026, 9, 20))
    DietComponentMerge.objects.create(
        date=plan.date,
        meal=MealCategory.MAIN_COURSE,
        component_index=1,  # len Príloha zvlášť, Hlavná časť ostáva spolu
        diet=diet,
    )

    data = MealPlanService.gramage_dashboard(plan.date.isoformat())

    assert data["diet_pack_state"] == {"main_course": {"Bez lepku": "Z"}}


@pytest.mark.django_db
def test_each_diet_keeps_its_own_row_regardless_of_board_state():
    """Viac diét v ten istý deň, rôzny (irelevantný) board stav — každá má
    vlastný, nedotknutý riadok."""
    plan = _plan_with_menu_a(datetime.date(2026, 9, 17))
    diet_a = Diet.objects.create(name="Bez lepku")
    diet_b = Diet.objects.create(name="Bez laktózy")
    DietComponentMerge.objects.create(
        date=plan.date, meal=MealCategory.MAIN_COURSE, component_index=1, diet=diet_a
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

    assert diet_rows["Bez lepku"]["col_grams"][0] == ["400.00", "200.00"]
    assert diet_rows["Bez laktózy"]["col_grams"][0] == ["200.00", "100.00"]
