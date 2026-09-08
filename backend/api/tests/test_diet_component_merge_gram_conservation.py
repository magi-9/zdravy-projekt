"""Invariant: zlúčenie diétnej zložky (#568) PRESÚVA gramáž, nikdy ju
netvorí ani nestráca.

Existujúce testy (`test_diet_component_merge_dashboard.py`) overujú pár
ručne dopočítaných čísel pre konkrétny scenár. Tu namiesto toho pre viacero
scenárov (viac diét, kombinované diéty s kaskádou, zbalené raňajky,
diéta s vlastnou preusporiadanou šablónou) porovnávame CELKOVÝ súčet gramov
naprieč VŠETKÝMI riadkami (štandard aj každá diéta) medzi zapnutým a
vypnutým zlúčením (`?merge_diets=`) — ten sa nesmie líšiť ani o gram, lebo
merge nič nepridáva ani neuberá, len prekladá, KDE sa daná gramáž vykáže.
"""

import datetime
from decimal import Decimal

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
from api.services.meal_plan_service import (
    MealPlanService,
    apply_diet_component_merge_toggle,
)

pytestmark = pytest.mark.django_db


def _grand_total_grams(data: dict) -> Decimal:
    """Nezávislý súčet gramov naprieč ÚPLNE VŠETKÝM (každá stĺpcová skupina,
    každý sub_row — standard aj diet) — inak povedané prepočíta
    `data["totals"]` zvonka, aby test nezávisel od toho istého akumulátora,
    čo prípadnú chybu v ňom mohol zdieľať.

    Zámerne JEDEN celkový súčet, nie per-skupina: keď má diéta vlastnú
    šablónu, býva vo VLASTNEJ stĺpcovej skupine (inej než štandard) a
    zlúčenie presúva jej gramáž práve do štandardnej skupiny — porovnávanie
    súčtu po jednotlivých skupinách by preto falošne padalo aj na správnom
    prípade. Skutočný invariant je súčet dokopy, nezávisle od toho, KTORÁ
    skupina/index gramáž práve nesie."""
    total = Decimal("0")
    for row in data["rows"]:
        for sub_row in row["sub_rows"]:
            for values in sub_row["col_grams"]:
                for raw in values:
                    if raw in (None, ""):
                        continue
                    total += Decimal(str(raw))
    return total


def _assert_conserved(date_str: str) -> None:
    merged = MealPlanService.gramage_dashboard(date_str, merge_diets=True)
    unmerged = MealPlanService.gramage_dashboard(date_str, merge_diets=False)
    assert _grand_total_grams(merged) == _grand_total_grams(unmerged), (
        "Celkový súčet gramov sa zlúčením zmenil — niekde sa gramy stratili "
        "alebo zdvojili."
    )


def _celok_and_user(name: str, email: str) -> tuple[Prevadzka, User]:
    celok = Celok.objects.create(nazov=name)
    prevadzka = Prevadzka.objects.create(celok=celok, nazov=name)
    user = User.objects.create_user(username=email, password="x")
    return prevadzka, user


def _main_course_plan(date, components=None) -> DailyMealPlan:
    call_command("init_reference_data")
    plan = DailyMealPlan.objects.create(date=date)
    MealPlanItem.objects.create(
        meal_plan=plan,
        template=MealTemplate.objects.create(
            name="Obed A",
            category="main_course",
            components=components
            or [
                {"label": "Hlavná časť", "grams": "200", "unit": "g"},
                {"label": "Príloha", "grams": "100", "unit": "g"},
            ],
            base_weight_grams="300",
        ),
        category="main_course",
        menu_variant="A",
    )
    return plan


def test_partial_merge_conserves_total_grams():
    date = datetime.date(2026, 9, 20)
    plan = _main_course_plan(date)
    diet = Diet.objects.create(name="Bez lepku")
    prevadzka, user = _celok_and_user("MŠ A", "gc-a@example.com")
    DailyOrder.objects.create(
        user=user,
        prevadzka=prevadzka,
        date=date,
        data={"lunch": {"Škôlka": {"menuCounts": {"A": 6}, "diets": {"Bez lepku": 2}}}},
    )
    DietComponentMerge.objects.create(
        date=plan.date, meal=MealCategory.MAIN_COURSE, component_index=0, diet=diet
    )
    _assert_conserved(date.isoformat())


def test_full_merge_conserves_total_grams_even_after_the_diet_row_disappears():
    date = datetime.date(2026, 9, 21)
    plan = _main_course_plan(date)
    diet = Diet.objects.create(name="Bez lepku")
    prevadzka, user = _celok_and_user("MŠ B", "gc-b@example.com")
    DailyOrder.objects.create(
        user=user,
        prevadzka=prevadzka,
        date=date,
        data={"lunch": {"Škôlka": {"menuCounts": {"A": 6}, "diets": {"Bez lepku": 2}}}},
    )
    for component_index in (0, 1):
        DietComponentMerge.objects.create(
            date=plan.date,
            meal=MealCategory.MAIN_COURSE,
            component_index=component_index,
            diet=diet,
        )
    _assert_conserved(date.isoformat())


def test_multiple_diets_with_mixed_merge_states_conserve_total_grams():
    """Tri diéty, tri rôzne stavy (nezlúčená / čiastočne / úplne) na tom
    istom jedle v ten istý deň — presuny sa nesmú navzájom pomiešať."""
    date = datetime.date(2026, 9, 22)
    plan = _main_course_plan(date)
    untouched = Diet.objects.create(name="Bez laktózy")
    partial = Diet.objects.create(name="Bez lepku")
    full = Diet.objects.create(name="Vegetariánska")
    prevadzka, user = _celok_and_user("MŠ C", "gc-c@example.com")
    DailyOrder.objects.create(
        user=user,
        prevadzka=prevadzka,
        date=date,
        data={
            "lunch": {
                "Škôlka": {
                    "menuCounts": {"A": 10},
                    "diets": {"Bez laktózy": 2, "Bez lepku": 3, "Vegetariánska": 1},
                }
            }
        },
    )
    DietComponentMerge.objects.create(
        date=plan.date, meal=MealCategory.MAIN_COURSE, component_index=0, diet=partial
    )
    for component_index in (0, 1):
        DietComponentMerge.objects.create(
            date=plan.date,
            meal=MealCategory.MAIN_COURSE,
            component_index=component_index,
            diet=full,
        )
    _assert_conserved(date.isoformat())


def test_composite_diet_cascade_conserves_total_grams():
    """Základné diéty NoMilk/NoGluten aj ich kombinácia majú v ten istý deň
    vlastné objednávky; kaskáda (`apply_diet_component_merge_toggle`)
    kombináciu raz odomkne, raz naspäť zamkne — súčet gramov sa nesmie
    hnúť ani pri jednom kroku."""
    date = datetime.date(2026, 9, 23)
    plan = _main_course_plan(date)
    milk = Diet.objects.create(name="NoMilk")
    gluten = Diet.objects.create(name="NoGluten")
    combo = Diet.objects.create(name="NoMilk+NoGluten")
    combo.base_diets.set([milk, gluten])
    prevadzka, user = _celok_and_user("MŠ D", "gc-d@example.com")
    DailyOrder.objects.create(
        user=user,
        prevadzka=prevadzka,
        date=date,
        data={
            "lunch": {
                "Škôlka": {
                    "menuCounts": {"A": 12},
                    "diets": {"NoMilk": 2, "NoGluten": 2, "NoMilk+NoGluten": 1},
                }
            }
        },
    )
    _assert_conserved(date.isoformat())  # nič zlúčené

    apply_diet_component_merge_toggle(
        date, MealCategory.MAIN_COURSE, 0, milk, merged=True
    )
    _assert_conserved(date.isoformat())  # len NoMilk zlúčená

    apply_diet_component_merge_toggle(
        date, MealCategory.MAIN_COURSE, 0, gluten, merged=True
    )
    apply_diet_component_merge_toggle(
        date, MealCategory.MAIN_COURSE, 0, combo, merged=True
    )
    _assert_conserved(date.isoformat())  # kombinácia teraz tiež zlúčená

    apply_diet_component_merge_toggle(
        date, MealCategory.MAIN_COURSE, 0, milk, merged=False
    )
    _assert_conserved(date.isoformat())  # kaskáda vrátila kombináciu na zvlášť


def test_breakfast_snack_collapsed_merge_conserves_total_grams():
    """Raňajky/desiata sa v tabuľke zobrazujú ako jeden zbalený stĺpec
    (`collapse_breakfast_snack_components`) — zlúčenie tohto jediného
    indexu musí preniesť CELÚ gramáž, nič nesmie zmiznúť pri zbaľovaní."""
    call_command("init_reference_data")
    date = datetime.date(2026, 9, 24)
    plan = DailyMealPlan.objects.create(date=date)
    MealPlanItem.objects.create(
        meal_plan=plan,
        template=MealTemplate.objects.create(
            name="Raňajky",
            category="breakfast_snack",
            components=[
                {"label": "Hlavná zložka", "grams": "50", "unit": "g"},
                {"label": "Extra zložka", "grams": "15", "unit": "g"},
            ],
            base_weight_grams="65",
        ),
        category="breakfast_snack",
    )
    diet = Diet.objects.create(name="Bez lepku")
    prevadzka, user = _celok_and_user("MŠ E", "gc-e@example.com")
    DailyOrder.objects.create(
        user=user,
        prevadzka=prevadzka,
        date=date,
        data={
            "breakfast": {"Škôlka": {"menuCounts": {"A": 6}, "diets": {"Bez lepku": 2}}}
        },
    )
    DietComponentMerge.objects.create(
        date=date, meal=MealCategory.BREAKFAST_SNACK, component_index=0, diet=diet
    )
    _assert_conserved(date.isoformat())


def test_reordered_diet_template_merge_conserves_total_grams():
    """Regresný scenár k label-matching fixu (#568): diétna šablóna má
    zložky v opačnom poradí než štandard. Zlúčenie podľa mena musí gramáž
    preniesť na správne miesto, nie ju stratiť medzi nesedivými indexmi."""
    call_command("init_reference_data")
    date = datetime.date(2026, 9, 25)
    plan = _main_course_plan(date)
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
    prevadzka, user = _celok_and_user("MŠ F", "gc-f@example.com")
    DailyOrder.objects.create(
        user=user,
        prevadzka=prevadzka,
        date=date,
        data={"lunch": {"Škôlka": {"menuCounts": {"A": 6}, "diets": {"Bez lepku": 2}}}},
    )
    # Klik z boardu adresuje "Hlavná časť" indexom 0 v ŠTANDARDNEJ šablóne.
    DietComponentMerge.objects.create(
        date=plan.date, meal=MealCategory.MAIN_COURSE, component_index=0, diet=diet
    )
    _assert_conserved(date.isoformat())
