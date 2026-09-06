import datetime
import json

import pytest
from django.contrib.auth.models import User
from django.core import management
from django.utils import timezone
from django_celery_beat.models import PeriodicTask

from api.edupage_scraper import ScrapeResult
from api.models import (
    Celok,
    DailyOrder,
    EdupageConnection,
    EventLog,
    GlobalSettings,
    ProfileCelokAccess,
    UserProfile,
)
from api.signals import (
    EDUPAGE_SCRAPE_TASK_PREFIX,
    _sync_dedicated_connection_scrape_schedules,
    _sync_edupage_scrape_schedule,
)
from api.tasks import scrape_edupage_orders_task


def _freeze_local(monkeypatch, date_, time_=datetime.time(5, 0)):
    """Mockne `timezone.localdate` aj `timezone.localtime` na konzistentný
    (dátum, čas) — potrebné odkedy `days_ahead` beh porovnáva "teraz" oproti
    per-jedlo scrape deadlinom (`_meal_scrape_deadline_passed`); samotný
    `localdate` mock nestačí."""
    monkeypatch.setattr(timezone, "localdate", lambda: date_)
    monkeypatch.setattr(
        timezone,
        "localtime",
        lambda: timezone.make_aware(datetime.datetime.combine(date_, time_)),
    )


def _scrape_result(order_data=None, **kwargs) -> ScrapeResult:
    """Reálny ScrapeResult, nie SimpleNamespace.

    Nové polia tak dostanú defaulty automaticky a testy nepadnú vždy, keď scraper
    pridá atribút.
    """
    return ScrapeResult(
        date=datetime.date(2026, 1, 1), order_data=order_data or {}, **kwargs
    )


@pytest.fixture
def edupage_user(db):
    user = User.objects.create_user(
        username="edupage@example.com",
        email="edupage@example.com",
    )
    profile = UserProfile.objects.create(user=user, company_name="Edupage school")
    celok = profile.primary_celok()
    celok.zdroj_objednavok = Celok.ZdrojObjednavok.EDUPAGE
    celok.save(update_fields=["zdroj_objednavok"])
    connection = EdupageConnection.objects.create(
        name="Edupage school",
        mealsguest_url="https://school.edupage.org/menu/mealsGuest?id=TOKEN",
    )
    profile.dostupne_prevadzky().update(edupage_connection=connection)
    return user


@pytest.mark.django_db
def test_allowed_diet_names_includes_active_db_diets():
    """Diéta založená v appke rozšíri whitelist scrapu bez nasadenia kódu;
    neaktívna sa doň nedostane."""
    from api.edupage_scraper import ALLOWED_DIET_NAMES, allowed_diet_names
    from api.models import Diet

    Diet.objects.create(name="NO KAKAO")
    Diet.objects.create(name="ZRUŠENÁ", is_active=False)

    names = allowed_diet_names()

    assert "NO KAKAO" in names
    assert "ZRUŠENÁ" not in names
    assert ALLOWED_DIET_NAMES <= names


@pytest.mark.django_db
def test_edupage_scrape_persists_unmapped_diets_flag(edupage_user, monkeypatch):
    """Neznáma diéta sa dostane do scrape_flags, nech ju admin prehľad ukáže —
    inak by o nej nikto nevedel (Cvernička, 17. 8. 2026)."""
    GlobalSettings.objects.create(
        pk=1,
        deadline_breakfast=datetime.time(18, 0),
        deadline_lunch=datetime.time(9, 0),
        deadline_olovrant=datetime.time(10, 0),
    )
    target_date = datetime.date(2026, 6, 30)

    def fake_scrape(self, url, scrape_date, prevadzka_matches=None, allowed_diets=None):
        return _scrape_result(
            order_data={"lunch": {"menuCounts": {"A": 5}, "diets": {"NO KAKAO": 5}}},
            warnings=[],
            unmapped_letters=["N:NO KAKAO"],
        )

    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)
    scrape_edupage_orders_task.run(date_str=target_date.isoformat())

    order = DailyOrder.objects.get(user=edupage_user, date=target_date)
    assert order.scrape_flags["unmapped_diets"] == ["N:NO KAKAO"]
    # a hlavne: porcie sa naozaj zapísali
    assert order.data


@pytest.mark.django_db
def test_edupage_scrape_clears_gramage_dashboard_cache(edupage_user, monkeypatch):
    """Scrape prepíše DailyOrder.data pre svoj deň — cache gramage dashboardu
    z pred scrapu by ešte 5 minút ukazovala staré počty, tak ju zahoď."""
    from django.core.cache import cache

    from api.cache_service import get_gramage_dashboard_cache_key, set_cached

    GlobalSettings.objects.create(
        pk=1,
        deadline_breakfast=datetime.time(18, 0),
        deadline_lunch=datetime.time(9, 0),
        deadline_olovrant=datetime.time(10, 0),
    )
    target_date = datetime.date(2026, 6, 30)

    def fake_scrape(self, url, scrape_date, prevadzka_matches=None, allowed_diets=None):
        return _scrape_result(order_data={"lunch": {"menuCounts": {"A": 5}}})

    cache_key = get_gramage_dashboard_cache_key(target_date.isoformat())
    set_cached(cache_key, {"stale": True}, timeout=300)

    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)
    scrape_edupage_orders_task.run(date_str=target_date.isoformat())

    assert cache.get(cache_key) is None


@pytest.mark.django_db
def test_edupage_scrape_uses_next_workday_for_day_before_meal(
    edupage_user, monkeypatch
):
    GlobalSettings.objects.create(
        pk=1,
        deadline_breakfast=datetime.time(18, 0),
        deadline_breakfast_is_day_before=True,
        deadline_lunch=datetime.time(9, 0),
        deadline_olovrant=datetime.time(10, 0),
    )
    today = datetime.date(2026, 6, 29)  # Monday
    seen_dates = []

    def fake_scrape(self, url, target_date, prevadzka_matches=None, allowed_diets=None):
        seen_dates.append(target_date)
        return _scrape_result(
            order_data={
                "breakfast": {
                    "menuCounts": {"A": 4},
                    "diets": {"NO MILK": 4},
                },
                "lunch": {
                    "menuCounts": {"A": 10},
                    "diets": {"NO GLUTEN": 10},
                },
            },
            warnings=[],
        )

    monkeypatch.setattr(timezone, "localdate", lambda: today)
    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    result = scrape_edupage_orders_task.run(meal_types=["breakfast"])

    tomorrow = datetime.date(2026, 6, 30)
    assert result["dates"] == [str(tomorrow)]
    assert seen_dates == [tomorrow]
    order = DailyOrder.objects.get(user=edupage_user, date=tomorrow)
    assert order.data == {
        "breakfast": {
            "Edupage school": {"menuCounts": {"A": 4}, "diets": {"NO MILK": 4}}
        }
    }


@pytest.mark.django_db
def test_edupage_scrape_persists_attention_flags(edupage_user, monkeypatch):
    """Upozornenia scrapu sa uložia do DailyOrder.scrape_flags a pri čistom
    behu sa vyčistia, nech admin prehľad nezobrazuje starý výkričník."""
    GlobalSettings.objects.create(
        pk=1,
        deadline_breakfast=datetime.time(18, 0),
        deadline_lunch=datetime.time(9, 0),
        deadline_olovrant=datetime.time(10, 0),
    )
    target_date = datetime.date(2026, 6, 30)

    def flagged_scrape(
        self, url, scrape_date, prevadzka_matches=None, allowed_diets=None
    ):
        return _scrape_result(
            order_data={"lunch": {"menuCounts": {"A": 5}}},
            warnings=[],
            attention=["A:KZ?"],
            config_notes=["olovrant chýba"],
        )

    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", flagged_scrape)
    scrape_edupage_orders_task.run(date_str=target_date.isoformat())

    order = DailyOrder.objects.get(user=edupage_user, date=target_date)
    assert order.scrape_flags == {
        "attention": ["A:KZ?"],
        "config_notes": ["olovrant chýba"],
        "unmapped_diets": [],
        "uncertain_diets": [],
    }

    def clean_scrape(
        self, url, scrape_date, prevadzka_matches=None, allowed_diets=None
    ):
        return _scrape_result(
            order_data={"lunch": {"menuCounts": {"A": 5}}}, warnings=[]
        )

    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", clean_scrape)
    scrape_edupage_orders_task.run(date_str=target_date.isoformat())

    order.refresh_from_db()
    assert order.scrape_flags == {
        "attention": [],
        "config_notes": [],
        "unmapped_diets": [],
        "uncertain_diets": [],
    }


@pytest.mark.django_db
def test_edupage_scrape_splits_attention_flags_per_prevadzka(monkeypatch):
    """Pri rozdelenom celku dostane každá prevádzka len svoje flagy;
    config_notes sú zdieľané (celok-wide)."""
    from api.models import Prevadzka

    celok = Celok.objects.create(
        nazov="Jolly",
        zdroj_objednavok=Celok.ZdrojObjednavok.EDUPAGE,
    )
    connection = EdupageConnection.objects.create(
        name="Jolly",
        mealsguest_url="https://jolly.edupage.org/menu/mealsGuest?id=T",
    )
    p1 = Prevadzka.objects.create(
        celok=celok,
        nazov="Jolly 1",
        edupage_match="J1",
        edupage_connection=connection,
    )
    p2 = Prevadzka.objects.create(
        celok=celok,
        nazov="Jolly 2",
        edupage_match="J2",
        edupage_connection=connection,
    )
    user = User.objects.create_user(username="jolly@x.sk", email="jolly@x.sk")
    profile = UserProfile(user=user, company_name="Jolly")
    profile._skip_default_facility = True
    profile.save()
    ProfileCelokAccess.objects.create(profile=profile, celok=celok)
    GlobalSettings.objects.create(
        pk=1,
        deadline_breakfast=datetime.time(18, 0),
        deadline_lunch=datetime.time(9, 0),
        deadline_olovrant=datetime.time(10, 0),
    )
    target_date = datetime.date(2026, 6, 30)

    def fake_scrape(self, url, scrape_date, prevadzka_matches=None, allowed_diets=None):
        return _scrape_result(
            order_data={"lunch": {"menuCounts": {"A": 8}}},
            order_data_by_prevadzka={
                "Jolly 1": {"lunch": {"menuCounts": {"A": 5}}},
                "Jolly 2": {"lunch": {"menuCounts": {"A": 3}}},
            },
            attention=["A:ZD?"],
            attention_by_prevadzka={"Jolly 1": ["A:ZD?"]},
            unmapped_letters=["Z:Nová diéta"],
            unmapped_by_prevadzka={"Jolly 1": ["Z:Nová diéta"]},
            uncertain_letters=["Y:XY→NO MILK"],
            uncertain_by_prevadzka={"Jolly 2": ["Y:XY→NO MILK"]},
            config_notes=["olovrant chýba"],
            warnings=[],
        )

    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)
    scrape_edupage_orders_task.run(date_str=target_date.isoformat())

    o1 = DailyOrder.objects.get(prevadzka=p1, date=target_date)
    o2 = DailyOrder.objects.get(prevadzka=p2, date=target_date)
    assert o1.scrape_flags == {
        "attention": ["A:ZD?"],
        "config_notes": ["olovrant chýba"],
        "unmapped_diets": ["Z:Nová diéta"],
        "uncertain_diets": [],
    }
    # Jolly 2 nemá attention/unmapped flag, ale má svoj uncertain flag a
    # zdieľané config_notes.
    assert o2.scrape_flags == {
        "attention": [],
        "config_notes": ["olovrant chýba"],
        "unmapped_diets": [],
        "uncertain_diets": ["Y:XY→NO MILK"],
    }


@pytest.mark.django_db
def test_edupage_scrape_task_skips_automatic_run_when_disabled(
    edupage_user, monkeypatch
):
    GlobalSettings.objects.create(
        pk=1,
        deadline_breakfast=datetime.time(18, 0),
        deadline_lunch=datetime.time(9, 0),
        deadline_olovrant=datetime.time(10, 0),
        edupage_auto_scrape_enabled=False,
    )

    def fail_scrape(self, url, target_date):
        raise AssertionError("Automatic EduPage scrape should not run")

    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fail_scrape)

    result = scrape_edupage_orders_task.run(meal_types=["breakfast"])

    assert result["disabled"] is True
    assert result["scraped"] == 0
    assert result["dates"] == []
    assert not DailyOrder.objects.filter(user=edupage_user).exists()


@pytest.mark.django_db
def test_edupage_scrape_records_explicit_zero_when_structurally_empty(
    edupage_user, monkeypatch
):
    """A structurally successful scrape (no warnings) with zero counts must
    still create a DailyOrder row, so the day isn't indistinguishable from
    "never scraped" (which would block auto-orders and admin reporting)."""
    GlobalSettings.objects.create(
        pk=1,
        deadline_breakfast=datetime.time(18, 0),
        deadline_lunch=datetime.time(9, 0),
        deadline_olovrant=datetime.time(10, 0),
    )
    target_date = datetime.date(2026, 6, 30)

    def fake_scrape(self, url, scrape_date, prevadzka_matches=None, allowed_diets=None):
        return _scrape_result(order_data={}, warnings=[], unmapped_letters=[])

    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    result = scrape_edupage_orders_task.run(date_str=target_date.isoformat())

    order = DailyOrder.objects.get(user=edupage_user, date=target_date)
    assert order.data == {}
    assert result["scraped"] == 1
    assert result["skipped"] == 0

    # Idempotent: running again for the same day must not error or duplicate.
    result2 = scrape_edupage_orders_task.run(date_str=target_date.isoformat())
    assert DailyOrder.objects.filter(user=edupage_user, date=target_date).count() == 1
    assert result2["scraped"] == 1


@pytest.mark.django_db
def test_edupage_scrape_skips_without_recording_on_real_scrape_failure(
    edupage_user, monkeypatch
):
    """A scrape failure (prehlad block missing/malformed) must NOT create a
    fabricated zero-order row - that would hide a real scraping problem."""
    GlobalSettings.objects.create(
        pk=1,
        deadline_breakfast=datetime.time(18, 0),
        deadline_lunch=datetime.time(9, 0),
        deadline_olovrant=datetime.time(10, 0),
    )
    target_date = datetime.date(2026, 6, 30)

    def fake_scrape(self, url, scrape_date, prevadzka_matches=None, allowed_diets=None):
        return _scrape_result(
            order_data={},
            warnings=["prehlad block not found in HTML"],
            unmapped_letters=[],
        )

    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    result = scrape_edupage_orders_task.run(date_str=target_date.isoformat())

    assert not DailyOrder.objects.filter(user=edupage_user, date=target_date).exists()
    assert result["scraped"] == 0
    assert result["skipped"] == 1


@pytest.mark.django_db
def test_edupage_scrape_skips_without_recording_on_unmapped_letters(
    edupage_user, monkeypatch
):
    """Unmapped diet/menu letters are a real data-mapping failure, not a
    genuine zero - even though _parse reports them via unmapped_letters
    rather than warnings, they must not be recorded as a confirmed zero."""
    GlobalSettings.objects.create(
        pk=1,
        deadline_breakfast=datetime.time(18, 0),
        deadline_lunch=datetime.time(9, 0),
        deadline_olovrant=datetime.time(10, 0),
    )
    target_date = datetime.date(2026, 6, 30)

    def fake_scrape(self, url, scrape_date, prevadzka_matches=None, allowed_diets=None):
        return _scrape_result(order_data={}, warnings=[], unmapped_letters=["Z:Z"])

    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    result = scrape_edupage_orders_task.run(date_str=target_date.isoformat())

    assert not DailyOrder.objects.filter(user=edupage_user, date=target_date).exists()
    assert result["scraped"] == 0
    assert result["skipped"] == 1


@pytest.mark.django_db
def test_edupage_scrape_saves_normally_despite_uncertain_diets(
    edupage_user, monkeypatch
):
    """#527: `uncertain_letters` je len informačný "over ma" flag (ako
    `config_notes`), nie signál zlyhania — nesmie spustiť skip-on-failure guard
    (na rozdiel od `unmapped_letters`, viď test vyššie)."""
    GlobalSettings.objects.create(
        pk=1,
        deadline_breakfast=datetime.time(18, 0),
        deadline_lunch=datetime.time(9, 0),
        deadline_olovrant=datetime.time(10, 0),
    )
    target_date = datetime.date(2026, 6, 30)

    def fake_scrape(self, url, scrape_date, prevadzka_matches=None, allowed_diets=None):
        return _scrape_result(
            order_data={"lunch": {"menuCounts": {"A": 5}, "diets": {"NO MILK": 5}}},
            warnings=[],
            unmapped_letters=[],
            uncertain_letters=["A:XY→NO MILK"],
        )

    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    result = scrape_edupage_orders_task.run(date_str=target_date.isoformat())

    order = DailyOrder.objects.get(user=edupage_user, date=target_date)
    assert order.data
    assert order.scrape_flags["uncertain_diets"] == ["A:XY→NO MILK"]
    assert result["scraped"] == 1
    assert result["skipped"] == 0


@pytest.mark.django_db
def test_edupage_scrape_merges_requested_meals_without_replacing_existing_day(
    edupage_user, monkeypatch
):
    GlobalSettings.objects.create(
        pk=1,
        deadline_breakfast=datetime.time(18, 0),
        deadline_lunch=datetime.time(9, 0),
        deadline_olovrant=datetime.time(10, 0),
    )
    target_date = datetime.date(2026, 6, 30)
    DailyOrder.objects.create(
        user=edupage_user,
        date=target_date,
        data={
            "breakfast": {
                "Edupage school": {
                    "menuCounts": {"A": 4},
                    "diets": {"NO MILK": 4},
                }
            }
        },
    )

    def fake_scrape(self, url, scrape_date, prevadzka_matches=None, allowed_diets=None):
        assert scrape_date == target_date
        return _scrape_result(
            order_data={
                "lunch": {
                    "menuCounts": {"A": 10},
                    "diets": {"NO GLUTEN": 10},
                },
                "olovrant": {
                    "menuCounts": {"A": 2},
                    "diets": {"NO EGG": 2},
                },
            },
            warnings=[],
        )

    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    scrape_edupage_orders_task.run(
        date_str=target_date.isoformat(), meal_types=["lunch"]
    )

    order = DailyOrder.objects.get(user=edupage_user, date=target_date)
    assert order.data == {
        "breakfast": {
            "Edupage school": {"menuCounts": {"A": 4}, "diets": {"NO MILK": 4}}
        },
        "lunch": {
            "Edupage school": {"menuCounts": {"A": 10}, "diets": {"NO GLUTEN": 10}}
        },
    }


def test_scrape_edupage_orders_management_command(monkeypatch, capsys):
    calls = []

    def fake_run(date_str=None, meal_types=None):
        calls.append({"date_str": date_str, "meal_types": meal_types})
        return {
            "scraped": 2,
            "errors": 0,
            "skipped": 1,
            "dates": ["2026-06-30"],
            "meal_types": meal_types,
        }

    monkeypatch.setattr(scrape_edupage_orders_task, "run", fake_run)

    management.call_command(
        "scrape_edupage_orders",
        "--date",
        "2026-06-30",
        "--meal",
        "breakfast",
        "--meal",
        "lunch",
    )

    assert calls == [{"date_str": "2026-06-30", "meal_types": ["breakfast", "lunch"]}]
    assert (
        "EduPage scrape complete: scraped=2 skipped=1 errors=0"
        in capsys.readouterr().out
    )


class TestApplyScrapeIdempotency:
    """Scrape v rámci dňa musí byť UPDATE, nie ADD."""

    def test_rescrape_replaces_not_adds(self):
        from api.tasks import _apply_scrape

        existing = {"lunch": {"Škôlka": {"menuCounts": {"A": 21}}}}
        # rovnaký scrape 2x nesmie zdvojiť
        out = _apply_scrape(
            existing, {"lunch": {"Škôlka": {"menuCounts": {"A": 21}}}}, ["lunch"]
        )
        out = _apply_scrape(
            out, {"lunch": {"Škôlka": {"menuCounts": {"A": 21}}}}, ["lunch"]
        )
        assert out["lunch"]["Škôlka"]["menuCounts"]["A"] == 21

    def test_meal_dropped_to_zero_is_cleared(self):
        from api.tasks import _apply_scrape

        existing = {
            "lunch": {"Škôlka": {"menuCounts": {"A": 21}}},
            "olovrant": {"Škôlka": {"menuCounts": {"A": 5}}},
        }
        # olovrant dnes 0 → musí zmiznúť, nie ostať na 5
        out = _apply_scrape(
            existing,
            {"lunch": {"Škôlka": {"menuCounts": {"A": 20}}}},
            ["lunch", "olovrant"],
        )
        assert out["lunch"]["Škôlka"]["menuCounts"]["A"] == 20
        assert "olovrant" not in out

    def test_unrequested_meal_untouched(self):
        from api.tasks import _apply_scrape

        existing = {"olovrant": {"Škôlka": {"menuCounts": {"A": 5}}}}
        out = _apply_scrape(
            existing, {"lunch": {"Škôlka": {"menuCounts": {"A": 3}}}}, ["lunch"]
        )
        assert out["olovrant"]["Škôlka"]["menuCounts"]["A"] == 5

    def test_none_requested_means_all_meals(self):
        from api.tasks import _apply_scrape

        existing = {"breakfast": {"Škôlka": {"menuCounts": {"A": 9}}}}
        out = _apply_scrape(existing, {}, None)
        assert out == {}

    def test_desiata_applied_even_when_not_in_requested_meals(self):
        """British `desiata` (#British Cluster C) nie je v `_ALL_MEALS` —
        scrape ho vždy prinesie s tým istým HTML fetchom ako ostatné jedlá, ale
        `requested_meals` (deadline-driven) ho nikdy nepýta explicitne. Bez
        osobitného handlingu by `_apply_scrape` tento kľúč ticho zahodil, hoci
        `imported_data` ho má (rovnaký #British bug ako 885 hláv pod lunch
        namiesto rozpadu na jednotlivé jedlá, 1.9.2026, len pre nový meal_key).
        Meno "desiata", NIE "snack" — ten je legacy alias pre Olovrant."""
        from api.tasks import _apply_scrape

        existing = {}
        out = _apply_scrape(
            existing,
            {
                "lunch": {"Škôlka": {"menuCounts": {"A": 21}}},
                "desiata": {"kusy": 150},
            },
            ["lunch"],
        )
        assert out["desiata"] == {"kusy": 150}

    def test_desiata_cleared_when_scraped_empty(self):
        from api.tasks import _apply_scrape

        existing = {"desiata": {"kusy": 150}}
        out = _apply_scrape(
            existing, {"lunch": {"Škôlka": {"menuCounts": {"A": 20}}}}, ["lunch"]
        )
        assert "desiata" not in out


class TestApplyPartialMenuScrape:
    """Predbežný Menu B/C scrape 1-2 dni vopred: len B/C sa zapíšu, zvyšok
    (Menu A, diéty, iné jedlá) ostáva netknutý — user 2.9.2026."""

    def test_writes_only_bc_leaves_menu_a_and_diets_untouched(self):
        from api.tasks import _apply_partial_menu_scrape

        existing = {
            "lunch": {
                "Škôlka": {"menuCounts": {"A": 12}, "diets": {"NO MILK": 2}},
            }
        }
        imported = {"lunch": {"Škôlka": {"menuCounts": {"B": 3, "C": 1}}}}

        out = _apply_partial_menu_scrape(existing, imported)

        assert out["lunch"]["Škôlka"]["menuCounts"] == {"A": 12, "B": 3, "C": 1}
        assert out["lunch"]["Škôlka"]["diets"] == {"NO MILK": 2}

    def test_rewrite_replaces_stale_bc_not_adds(self):
        from api.tasks import _apply_partial_menu_scrape

        existing = {"lunch": {"Škôlka": {"menuCounts": {"A": 5, "B": 7}}}}
        # deň predtým vopred vopred zapísal B=7 (z behu 2 dni vopred);
        # dnešný beh (1 deň vopred) prináša presnejšie číslo, musí prepísať
        out = _apply_partial_menu_scrape(
            existing, {"lunch": {"Škôlka": {"menuCounts": {"B": 4}}}}
        )
        assert out["lunch"]["Škôlka"]["menuCounts"] == {"A": 5, "B": 4}

    def test_bc_absent_in_fresh_scrape_clears_stale_value(self):
        from api.tasks import _apply_partial_menu_scrape

        existing = {"lunch": {"Škôlka": {"menuCounts": {"A": 5, "B": 3, "C": 2}}}}
        # nikto si dnes B/C neobjednal — musí sa vynulovať, nie ostať na starom
        out = _apply_partial_menu_scrape(existing, {"lunch": {}})
        assert out["lunch"]["Škôlka"]["menuCounts"] == {"A": 5}

    def test_other_meals_untouched(self):
        from api.tasks import _apply_partial_menu_scrape

        existing = {
            "lunch": {"Škôlka": {"menuCounts": {"A": 5}}},
            "olovrant": {"Škôlka": {"menuCounts": {"A": 5}}},
        }
        out = _apply_partial_menu_scrape(
            existing, {"lunch": {"Škôlka": {"menuCounts": {"B": 2}}}}
        )
        assert out["olovrant"] == {"Škôlka": {"menuCounts": {"A": 5}}}

    def test_new_prevadzka_only_gets_bc(self):
        from api.tasks import _apply_partial_menu_scrape

        out = _apply_partial_menu_scrape(
            {}, {"lunch": {"ZŠ 1.stupeň": {"menuCounts": {"B": 2, "C": 1}}}}
        )
        assert out == {
            "lunch": {"ZŠ 1.stupeň": {"menuCounts": {"B": 2, "C": 1}, "diets": {}}}
        }

    def test_empty_result_drops_meal_key(self):
        from api.tasks import _apply_partial_menu_scrape

        existing = {"lunch": {"Škôlka": {"menuCounts": {"B": 3}}}}
        out = _apply_partial_menu_scrape(existing, {"lunch": {}})
        assert "lunch" not in out


@pytest.mark.django_db
def test_only_deadline_derived_scrape_tasks_are_scheduled():
    """Automatický je len uzávierkový scrape — žiadny ranný ani iný beh navyše.

    Ranné načítanie sa robí ručne tlačidlom v admin nastaveniach, aby scrape
    nikdy nebežal po uzávierke bez vedomia obsluhy.
    """
    settings_instance = GlobalSettings.objects.create(
        pk=1,
        deadline_breakfast=datetime.time(18, 0),
        deadline_lunch=datetime.time(21, 0),
        deadline_olovrant=datetime.time(10, 0),
        edupage_auto_scrape_enabled=True,
    )

    _sync_edupage_scrape_schedule(settings_instance)

    names = set(
        PeriodicTask.objects.filter(
            name__startswith=EDUPAGE_SCRAPE_TASK_PREFIX
        ).values_list("name", flat=True)
    )
    # 18:00 → 17:30, 21:00 → 20:30, 10:00 → 09:30
    assert names == {
        f"{EDUPAGE_SCRAPE_TASK_PREFIX}breakfast",
        f"{EDUPAGE_SCRAPE_TASK_PREFIX}lunch",
        f"{EDUPAGE_SCRAPE_TASK_PREFIX}olovrant",
    }
    for task in PeriodicTask.objects.filter(
        name__startswith=EDUPAGE_SCRAPE_TASK_PREFIX
    ):
        assert json.loads(task.kwargs)["meal_types"]


@pytest.mark.django_db
def test_edupage_scrape_time_override_decouples_crontab_from_deadline():
    """#527/#528 follow-up: `edupage_scrape_time_breakfast` lets the scrape
    run at a different clock time than the order deadline — e.g. deadline
    stays 21:00 the evening before, but the scrape only runs at 01:35, once
    orders are unambiguously closed."""
    settings_instance = GlobalSettings.objects.create(
        pk=1,
        deadline_breakfast=datetime.time(21, 0),
        deadline_breakfast_is_day_before=True,
        deadline_lunch=datetime.time(7, 35),
        deadline_olovrant=datetime.time(7, 35),
        edupage_scrape_time_breakfast=datetime.time(1, 35),
        edupage_scrape_time_breakfast_is_day_before=False,
    )

    _sync_edupage_scrape_schedule(settings_instance)

    task = PeriodicTask.objects.get(name=f"{EDUPAGE_SCRAPE_TASK_PREFIX}breakfast")
    assert task.crontab.hour == "1"
    assert task.crontab.minute == "35"
    # is_day_before=False for the override → same day_of_week rule as a
    # same-day deadline (Mon–Fri), unrelated to the order deadline's own
    # day-before flag.
    assert task.crontab.day_of_week == "1-5"
    assert "uzávierka: raňajky: 21:00" in task.description
    assert "spúšťa sa o 01:35" in task.description


@pytest.mark.django_db
def test_edupage_scrape_time_override_shapes_runtime_target_date(
    edupage_user, monkeypatch
):
    """The override's own is_day_before must drive the runtime target date —
    not the order deadline's — otherwise a scrape decoupled to run after
    midnight would still import for the wrong day (#527/#528 follow-up)."""
    GlobalSettings.objects.create(
        pk=1,
        deadline_breakfast=datetime.time(21, 0),
        deadline_breakfast_is_day_before=True,
        deadline_lunch=datetime.time(7, 35),
        deadline_olovrant=datetime.time(7, 35),
        edupage_scrape_time_breakfast=datetime.time(1, 35),
        edupage_scrape_time_breakfast_is_day_before=False,
    )
    monday = datetime.date(2026, 6, 29)
    seen_dates = []

    def fake_scrape(self, url, target_date, prevadzka_matches=None, allowed_diets=None):
        seen_dates.append(target_date)
        return _scrape_result()

    monkeypatch.setattr(timezone, "localdate", lambda: monday)
    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    result = scrape_edupage_orders_task.run(meal_types=["breakfast"])

    # Fires Monday 01:35, still targets Monday's breakfast — not Tuesday,
    # which is what the deadline's own is_day_before=True would have given.
    assert result["dates"] == [str(monday)]
    assert seen_dates == [monday]


BRITISH_SCHOOL_SCRAPE_TASK_NAME = "edupage-scrape-dedicated-british-school"


@pytest.mark.django_db
def test_dedicated_scrape_schedule_is_noop_without_a_dedicated_connection():
    """Bez pripojenia s dedicated_scrape_hour/minute sa vlastný scrape
    nezaloží — inak by čakal na dáta, ktoré nikdy neprídu."""
    settings_instance = GlobalSettings.objects.create(pk=1)

    _sync_dedicated_connection_scrape_schedules(settings_instance)

    assert not PeriodicTask.objects.filter(
        name=BRITISH_SCHOOL_SCRAPE_TASK_NAME
    ).exists()


@pytest.mark.django_db
def test_dedicated_scrape_schedule_fires_at_its_own_configured_time():
    """British School (#535) je prvé použitie: connection s
    dedicated_scrape_hour/minute=12:15 dostane vlastný cron Ne–Št, cieli na
    nasledujúci pracovný deň — nezávisle od GlobalSettings deadlinov
    ostatných celkov. Generalizované z hardcoded mena pripojenia (code
    review 2026-08-31) — čokoľvek s tými dvomi poľami nastavenými má
    fungovať rovnako, nielen British School."""
    connection = EdupageConnection.objects.create(
        name="British School",
        mealsguest_url="https://zdravyprojekt.edupage.org/menu/mealsGuest?id=Dr8kS45",
        dedicated_scrape_hour=12,
        dedicated_scrape_minute=15,
    )
    settings_instance = GlobalSettings.objects.create(pk=1)

    _sync_dedicated_connection_scrape_schedules(settings_instance)

    task = PeriodicTask.objects.get(name=BRITISH_SCHOOL_SCRAPE_TASK_NAME)
    assert task.crontab.hour == "12"
    assert task.crontab.minute == "15"
    assert task.crontab.day_of_week == "0-4"  # Ne–Št
    kwargs = json.loads(task.kwargs)
    assert kwargs == {"connection_id": connection.pk, "target_next_workday": True}


@pytest.mark.django_db
def test_dedicated_scrape_schedule_removed_when_auto_scrape_disabled():
    EdupageConnection.objects.create(
        name="British School",
        mealsguest_url="https://zdravyprojekt.edupage.org/menu/mealsGuest?id=Dr8kS45",
        dedicated_scrape_hour=12,
        dedicated_scrape_minute=15,
    )
    settings_instance = GlobalSettings.objects.create(pk=1)
    _sync_dedicated_connection_scrape_schedules(settings_instance)
    assert PeriodicTask.objects.filter(name=BRITISH_SCHOOL_SCRAPE_TASK_NAME).exists()

    settings_instance.edupage_auto_scrape_enabled = False
    settings_instance.save()

    assert not PeriodicTask.objects.filter(
        name=BRITISH_SCHOOL_SCRAPE_TASK_NAME
    ).exists()


@pytest.mark.django_db
def test_dedicated_scrape_schedule_removed_when_connection_opts_out():
    """Vyprázdnenie dedicated_scrape_hour/minute (nie deaktivácia) musí
    zmazať cron rovnako — inak by connection zostala scrapovaná na starom
    čase aj po tom, čo sa z neho odhlásila."""
    connection = EdupageConnection.objects.create(
        name="British School",
        mealsguest_url="https://zdravyprojekt.edupage.org/menu/mealsGuest?id=Dr8kS45",
        dedicated_scrape_hour=12,
        dedicated_scrape_minute=15,
    )
    settings_instance = GlobalSettings.objects.create(pk=1)
    _sync_dedicated_connection_scrape_schedules(settings_instance)
    assert PeriodicTask.objects.filter(name=BRITISH_SCHOOL_SCRAPE_TASK_NAME).exists()

    connection.dedicated_scrape_hour = None
    connection.dedicated_scrape_minute = None
    connection.save(update_fields=["dedicated_scrape_hour", "dedicated_scrape_minute"])

    _sync_dedicated_connection_scrape_schedules(settings_instance)

    assert not PeriodicTask.objects.filter(
        name=BRITISH_SCHOOL_SCRAPE_TASK_NAME
    ).exists()


@pytest.mark.django_db
def test_deadline_derived_scrape_tasks_exclude_dedicated_connections():
    """British School sa scrapuje len na svojom 12:15 cronte — nie aj na
    generických deadlinoch ostatných celkov (zdvojený scrape)."""
    EdupageConnection.objects.create(
        name="British School",
        mealsguest_url="https://zdravyprojekt.edupage.org/menu/mealsGuest?id=Dr8kS45",
        dedicated_scrape_hour=12,
        dedicated_scrape_minute=15,
    )
    settings_instance = GlobalSettings.objects.create(
        pk=1,
        deadline_breakfast=datetime.time(18, 0),
        deadline_lunch=datetime.time(21, 0),
        deadline_olovrant=datetime.time(10, 0),
    )

    _sync_edupage_scrape_schedule(settings_instance)

    british_school_id = EdupageConnection.objects.get(name="British School").pk
    for task in PeriodicTask.objects.filter(
        name__startswith=EDUPAGE_SCRAPE_TASK_PREFIX
    ).exclude(name=BRITISH_SCHOOL_SCRAPE_TASK_NAME):
        assert json.loads(task.kwargs)["exclude_connection_ids"] == [british_school_id]


@pytest.mark.django_db
def test_scrape_task_connection_id_scopes_to_one_operation(edupage_user, monkeypatch):
    """`connection_id` obmedzí scrape na jedno EduPage pripojenie (British
    School dedikovaný cron, #535) bez toho, aby sa dotkol ostatných."""
    other_connection = EdupageConnection.objects.create(
        name="Other school",
        mealsguest_url="https://other.edupage.org/menu/mealsGuest?id=OTHER",
    )
    other_user = User.objects.create_user(
        username="other@example.com", email="other@example.com"
    )
    other_profile = UserProfile.objects.create(
        user=other_user, company_name="Other school"
    )
    other_celok = other_profile.primary_celok()
    other_celok.zdroj_objednavok = Celok.ZdrojObjednavok.EDUPAGE
    other_celok.save(update_fields=["zdroj_objednavok"])
    other_profile.dostupne_prevadzky().update(edupage_connection=other_connection)

    scraped_urls = []

    def fake_scrape(self, url, target_date, prevadzka_matches=None, allowed_diets=None):
        scraped_urls.append(url)
        return _scrape_result()

    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    scrape_edupage_orders_task.run(
        date_str="2026-06-30", connection_id=other_connection.pk
    )

    assert scraped_urls == [other_connection.mealsguest_url]


@pytest.mark.django_db
def test_scrape_task_exclude_connection_ids_skips_operation(edupage_user, monkeypatch):
    connection = EdupageConnection.objects.get(name="Edupage school")

    scraped_urls = []

    def fake_scrape(self, url, target_date, prevadzka_matches=None, allowed_diets=None):
        scraped_urls.append(url)
        return _scrape_result()

    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    scrape_edupage_orders_task.run(
        date_str="2026-06-30", exclude_connection_ids=[connection.pk]
    )

    assert scraped_urls == []


@pytest.mark.django_db
def test_scrape_task_target_next_workday_without_meal_types(edupage_user, monkeypatch):
    """`target_next_workday` funguje aj bez `meal_types` (British School beh
    nemá per-jedlo deadline, len jeden denný scrape na zajtra)."""
    GlobalSettings.objects.create(pk=1)
    today = datetime.date(2026, 6, 29)  # Monday
    seen_dates = []

    def fake_scrape(self, url, target_date, prevadzka_matches=None, allowed_diets=None):
        seen_dates.append(target_date)
        return _scrape_result()

    monkeypatch.setattr(timezone, "localdate", lambda: today)
    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    result = scrape_edupage_orders_task.run(target_next_workday=True)

    tomorrow = datetime.date(2026, 6, 30)
    assert result["dates"] == [str(tomorrow)]
    assert seen_dates == [tomorrow]


@pytest.mark.django_db
def test_scrape_task_runs_on_sunday_when_target_next_workday_is_monday(
    edupage_user, monkeypatch
):
    """Regression for a real prod incident (2026-08-31): the British School
    schedule fires Sun-Thu at 12:15 specifically so its Sunday leg can
    prepare Monday. The old `_cron_skip_check` looked at "today" (always a
    weekend on that leg) instead of the resolved `target_next_workday`
    date, so it silently skipped every single Sunday and Monday's data was
    never scraped."""
    GlobalSettings.objects.create(pk=1)
    sunday = datetime.date(2026, 6, 28)
    monday = datetime.date(2026, 6, 29)
    seen_dates = []

    def fake_scrape(self, url, target_date, prevadzka_matches=None, allowed_diets=None):
        seen_dates.append(target_date)
        return _scrape_result()

    monkeypatch.setattr(timezone, "localdate", lambda: sunday)
    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    result = scrape_edupage_orders_task.run(target_next_workday=True)

    assert result.get("skipped_run") is not True
    assert result["dates"] == [str(monday)]
    assert seen_dates == [monday]


@pytest.mark.django_db
def test_scrape_task_runs_on_sunday_for_a_day_before_meal(edupage_user, monkeypatch):
    """Same regression as above, but for the shared `edupage-scrape-breakfast`
    schedule (Sun-Thu 21:00, `deadline_breakfast_is_day_before=True`) rather
    than the British School `target_next_workday` path."""
    GlobalSettings.objects.create(pk=1, deadline_breakfast_is_day_before=True)
    sunday = datetime.date(2026, 6, 28)
    monday = datetime.date(2026, 6, 29)
    seen_dates = []

    def fake_scrape(self, url, target_date, prevadzka_matches=None, allowed_diets=None):
        seen_dates.append(target_date)
        return _scrape_result()

    monkeypatch.setattr(timezone, "localdate", lambda: sunday)
    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    result = scrape_edupage_orders_task.run(meal_types=["breakfast"])

    assert result.get("skipped_run") is not True
    assert result["dates"] == [str(monday)]
    assert seen_dates == [monday]


# ── `days_ahead` — hodinový priebežný náhľad (2.9.2026) ─────────────────────


@pytest.mark.django_db
def test_scrape_task_days_ahead_scrapes_rolling_window_all_meals(
    edupage_user, monkeypatch
):
    """`days_ahead=2` scrapne dnes, dnes+1, dnes+2 — nezávisle od
    GlobalSettings deadlinov (žiadne v teste), všetky jedlá naraz."""
    GlobalSettings.objects.create(pk=1)
    monday = datetime.date(2026, 6, 29)
    seen_dates = []

    def fake_scrape(self, url, target_date, prevadzka_matches=None, allowed_diets=None):
        seen_dates.append(target_date)
        return _scrape_result(order_data={"lunch": {"menuCounts": {"A": 3}}})

    _freeze_local(monkeypatch, monday)
    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    result = scrape_edupage_orders_task.run(days_ahead=2)

    tuesday = datetime.date(2026, 6, 30)
    wednesday = datetime.date(2026, 7, 1)
    assert seen_dates == [monday, tuesday, wednesday]
    assert result["dates"] == [str(monday), str(tuesday), str(wednesday)]
    for target_date in (monday, tuesday, wednesday):
        order = DailyOrder.objects.get(user=edupage_user, date=target_date)
        assert order.data["lunch"]["Edupage school"]["menuCounts"]["A"] == 3


@pytest.mark.django_db
def test_scrape_task_days_ahead_repeated_run_updates_not_accumulates(
    edupage_user, monkeypatch
):
    """Opakovaný hodinový beh na ten istý deň musí PREPÍSAŤ, nie pripočítať —
    inak by hodinový cron postupne nafukoval počty (užívateľská požiadavka
    2.9.2026: 'ukladat updateovat NIE PRIPOCITAVAT')."""
    GlobalSettings.objects.create(pk=1)
    monday = datetime.date(2026, 6, 29)
    counts = iter([3, 5])

    def fake_scrape(self, url, target_date, prevadzka_matches=None, allowed_diets=None):
        return _scrape_result(order_data={"lunch": {"menuCounts": {"A": next(counts)}}})

    _freeze_local(monkeypatch, monday)
    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    scrape_edupage_orders_task.run(days_ahead=0)
    scrape_edupage_orders_task.run(days_ahead=0)

    assert DailyOrder.objects.filter(user=edupage_user, date=monday).count() == 1
    order = DailyOrder.objects.get(user=edupage_user, date=monday)
    assert order.data["lunch"]["Edupage school"]["menuCounts"]["A"] == 5


@pytest.mark.django_db
def test_scrape_task_days_ahead_skips_weekend_dates_and_extends_window(
    edupage_user, monkeypatch
):
    """Víkendové dátumy sa vynechajú, ALE okno sa predĺži tak, aby vždy
    pokrývalo `days_ahead + 1` pracovných dní (#588) — bez toho by piatkový
    beh (okno piatok+sobota+nedeľa, kalendárne) nevidel žiadny nadchádzajúci
    pracovný deň okrem piatku samého, hoci pondelok/utorok už majú jedálny
    lístok pripravený."""
    GlobalSettings.objects.create(pk=1)
    friday = datetime.date(2026, 6, 26)
    monday = datetime.date(2026, 6, 29)
    tuesday = datetime.date(2026, 6, 30)
    seen_dates = []

    def fake_scrape(self, url, target_date, prevadzka_matches=None, allowed_diets=None):
        seen_dates.append(target_date)
        return _scrape_result(order_data={"lunch": {"menuCounts": {"A": 1}}})

    _freeze_local(monkeypatch, friday)
    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    result = scrape_edupage_orders_task.run(days_ahead=2)

    # Piatok + 2 ďalšie pracovné dni → sobota/nedeľa sa preskočia, okno
    # sa predĺži na pondelok a utorok namiesto toho, aby sa len zmenšilo.
    assert seen_dates == [friday, monday, tuesday]
    assert result["dates"] == [str(friday), str(monday), str(tuesday)]


@pytest.mark.django_db
def test_scrape_task_days_ahead_ignored_when_auto_scrape_disabled(
    edupage_user, monkeypatch
):
    GlobalSettings.objects.create(pk=1, edupage_auto_scrape_enabled=False)
    monkeypatch.setattr(
        "api.edupage_scraper.EdupageScraper.scrape",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not scrape")),
    )

    result = scrape_edupage_orders_task.run(days_ahead=2)

    assert result.get("disabled") is True


@pytest.mark.django_db
def test_scrape_task_days_ahead_skips_meal_past_its_authoritative_deadline(
    edupage_user, monkeypatch
):
    """Preview beh nesmie znova scrapnúť jedlo na deň, ktorého autoritatívny
    deadline scrape už prebehol — inak prepíše prípadnú ručnú admin opravu
    spravenú medzitým (2026-09-03: presne to sa stalo o 8:00 dvom
    objednávkam, hoci lunch/olovrant deadline scrape bol už o 7:35)."""
    GlobalSettings.objects.create(
        pk=1,
        deadline_breakfast=datetime.time(1, 35),
        deadline_lunch=datetime.time(7, 35),
        deadline_olovrant=datetime.time(7, 35),
    )
    today = datetime.date(2026, 6, 29)
    seen_meals = []

    def fake_scrape(self, url, target_date, prevadzka_matches=None, allowed_diets=None):
        return _scrape_result(
            order_data={
                "breakfast": {"menuCounts": {"A": 1}},
                "lunch": {"menuCounts": {"A": 2}},
                "olovrant": {"menuCounts": {"A": 3}},
            }
        )

    # 8:00 — breakfast (1:35) aj lunch/olovrant (7:35) deadline scrape už
    # dávno prebehol pre dnešok, takže preview beh dnešok vôbec nescrapne.
    _freeze_local(monkeypatch, today, datetime.time(8, 0))
    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    result = scrape_edupage_orders_task.run(days_ahead=0)

    assert result["dates"] == []
    assert not DailyOrder.objects.filter(user=edupage_user, date=today).exists()


@pytest.mark.django_db
def test_scrape_task_days_ahead_still_scrapes_meal_before_its_deadline(
    edupage_user, monkeypatch
):
    """Pred 7:35 preview beh lunch/olovrant ešte scrapne normálne."""
    GlobalSettings.objects.create(
        pk=1,
        deadline_breakfast=datetime.time(1, 35),
        deadline_lunch=datetime.time(7, 35),
        deadline_olovrant=datetime.time(7, 35),
    )
    today = datetime.date(2026, 6, 29)

    def fake_scrape(self, url, target_date, prevadzka_matches=None, allowed_diets=None):
        return _scrape_result(
            order_data={
                "lunch": {"menuCounts": {"A": 2}},
                "olovrant": {"menuCounts": {"A": 3}},
            }
        )

    # 7:00 — breakfast (1:35) je už za deadlinom, lunch/olovrant (7:35) ešte nie.
    _freeze_local(monkeypatch, today, datetime.time(7, 0))
    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    result = scrape_edupage_orders_task.run(days_ahead=0)

    assert result["dates"] == [str(today)]
    order = DailyOrder.objects.get(user=edupage_user, date=today)
    assert "breakfast" not in order.data
    assert order.data["lunch"]["Edupage school"]["menuCounts"]["A"] == 2
    assert order.data["olovrant"]["Edupage school"]["menuCounts"]["A"] == 3


# ── `meals_by_date` v summary — čo presne scrape stiahol (4.9.2026) ─────────
#
# Predtým `meal_types` v summary ukazoval len samotný task kwarg (často `null`
# pri `days_ahead` behu), nie skutočne stiahnuté jedlá po jednotlivých dňoch —
# z logu sa tak nedalo overiť, že napr. o 2:00 preview beh raňajky pre dnešok
# (deadline 1:35) už správne vynechal. `meals_by_date` to robí explicitné.


@pytest.mark.django_db
def test_scrape_summary_meals_by_date_excludes_meal_past_its_deadline(
    edupage_user, monkeypatch
):
    GlobalSettings.objects.create(
        pk=1,
        deadline_breakfast=datetime.time(1, 35),
        deadline_lunch=datetime.time(7, 35),
        deadline_olovrant=datetime.time(7, 35),
    )
    today = datetime.date(2026, 6, 29)

    def fake_scrape(self, url, target_date, prevadzka_matches=None, allowed_diets=None):
        return _scrape_result(
            order_data={
                "lunch": {"menuCounts": {"A": 2}},
                "olovrant": {"menuCounts": {"A": 3}},
            }
        )

    # 2:00 — raňajkový deadline (1:35) je už za nami, obed/olovrant (7:35) ešte nie.
    _freeze_local(monkeypatch, today, datetime.time(2, 0))
    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    result = scrape_edupage_orders_task.run(days_ahead=0)

    assert result["meals_by_date"] == {str(today): ["lunch", "olovrant"]}

    log = EventLog.objects.get(
        event_type=EventLog.EventType.CRON_RUN,
        payload__task="scrape_edupage_orders_task",
    )
    assert "raňajky" not in log.summary
    assert "obed/olovrant" in log.summary
    assert str(today) in log.summary


@pytest.mark.django_db
def test_scrape_summary_meals_by_date_full_run_lists_all_meals(
    edupage_user, monkeypatch
):
    """Beh bez `meal_types`/`days_ahead` (plný denný scrape) nefiltruje po
    jedlách vôbec — `meals_by_date` to zobrazí ako všetky tri jedlá."""
    GlobalSettings.objects.create(pk=1)
    monday = datetime.date(2026, 6, 29)

    def fake_scrape(self, url, target_date, prevadzka_matches=None, allowed_diets=None):
        return _scrape_result(order_data={"lunch": {"menuCounts": {"A": 1}}})

    _freeze_local(monkeypatch, monday)
    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)

    result = scrape_edupage_orders_task.run()

    assert result["meals_by_date"] == {str(monday): ["breakfast", "lunch", "olovrant"]}


# ── EventLog zo scrapu — viditeľnosť školu po škole v Udalostiach (3.9.2026) ─


@pytest.mark.django_db
def test_scrape_logs_event_per_order_with_edupage_actor_label(
    edupage_user, monkeypatch
):
    """Prvý scrape na prázdny deň založí objednávku — Udalosti majú vidieť
    'EduPage zadal(a) objednávku', nie tichý zápis viditeľný len cez cron_run
    súhrn."""
    GlobalSettings.objects.create(pk=1)
    target_date = datetime.date(2026, 6, 30)

    def fake_scrape(self, url, scrape_date, prevadzka_matches=None, allowed_diets=None):
        return _scrape_result(order_data={"lunch": {"menuCounts": {"A": 5}}})

    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)
    scrape_edupage_orders_task.run(date_str=target_date.isoformat())

    event = EventLog.objects.get(event_type=EventLog.EventType.ORDER_ADMIN_CREATE)
    assert event.actor is None
    assert event.actor_label == "EduPage"
    assert "EduPage zadal(a) objednávku" in event.summary
    assert "Edupage school" in event.summary
    assert event.payload["changed_meals"] == ["lunch"]
    assert event.payload["meals"]["lunch"]["Edupage school"]["menuCounts"]["A"] == 5


@pytest.mark.django_db
def test_scrape_logs_update_event_when_counts_change(edupage_user, monkeypatch):
    """Zmena existujúcich počtov sa loguje ako update, s diffom v `changes`."""
    GlobalSettings.objects.create(pk=1)
    target_date = datetime.date(2026, 6, 30)
    counts = iter([5, 8])

    def fake_scrape(self, url, scrape_date, prevadzka_matches=None, allowed_diets=None):
        return _scrape_result(order_data={"lunch": {"menuCounts": {"A": next(counts)}}})

    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)
    scrape_edupage_orders_task.run(date_str=target_date.isoformat())
    EventLog.objects.all().delete()  # len druhý beh nás zaujíma

    scrape_edupage_orders_task.run(date_str=target_date.isoformat())

    event = EventLog.objects.get(event_type=EventLog.EventType.ORDER_ADMIN_UPDATE)
    assert event.actor_label == "EduPage"
    assert event.payload["changes"]["lunch.Edupage school.menuCounts.A"] == {
        "from": 5,
        "to": 8,
    }


@pytest.mark.django_db
def test_scrape_logs_nothing_when_rerun_is_a_noop(edupage_user, monkeypatch):
    """Opakovaný beh s rovnakými počtami (typicky hodinový 24/7 preview) do
    Udalostí nič nepridá — inak by ich zaplavil no-op zápismi z každej
    školy, každú hodinu."""
    GlobalSettings.objects.create(pk=1)
    target_date = datetime.date(2026, 6, 30)

    def fake_scrape(self, url, scrape_date, prevadzka_matches=None, allowed_diets=None):
        return _scrape_result(order_data={"lunch": {"menuCounts": {"A": 5}}})

    monkeypatch.setattr("api.edupage_scraper.EdupageScraper.scrape", fake_scrape)
    scrape_edupage_orders_task.run(date_str=target_date.isoformat())
    EventLog.objects.all().delete()

    scrape_edupage_orders_task.run(date_str=target_date.isoformat())

    assert not EventLog.objects.filter(
        event_type__in=[
            EventLog.EventType.ORDER_ADMIN_CREATE,
            EventLog.EventType.ORDER_ADMIN_UPDATE,
        ]
    ).exists()


EDUPAGE_PREVIEW_TASK_NAME = f"{EDUPAGE_SCRAPE_TASK_PREFIX}preview"


@pytest.mark.django_db
def test_preview_scrape_schedule_creates_hourly_task():
    from api.signals import _sync_edupage_preview_scrape_schedule

    settings_instance = GlobalSettings.objects.create(pk=1)

    _sync_edupage_preview_scrape_schedule(settings_instance)

    task = PeriodicTask.objects.get(name=EDUPAGE_PREVIEW_TASK_NAME)
    assert task.crontab.minute == "0"
    assert task.crontab.hour == "0-23"
    assert task.crontab.day_of_week == "*"
    assert json.loads(task.kwargs) == {"days_ahead": 2}


@pytest.mark.django_db
def test_preview_scrape_schedule_removed_when_auto_scrape_disabled():
    from api.signals import _sync_edupage_preview_scrape_schedule

    settings_instance = GlobalSettings.objects.create(pk=1)
    _sync_edupage_preview_scrape_schedule(settings_instance)
    assert PeriodicTask.objects.filter(name=EDUPAGE_PREVIEW_TASK_NAME).exists()

    settings_instance.edupage_auto_scrape_enabled = False
    settings_instance.save()

    assert not PeriodicTask.objects.filter(name=EDUPAGE_PREVIEW_TASK_NAME).exists()
