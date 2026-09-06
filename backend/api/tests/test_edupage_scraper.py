"""Unit tests for EdupageScraper. No network calls — all HTTP is mocked."""

import json
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from api.edupage.base import OlovrantMode, PrevadzkaConfig
from api.edupage.overrides.zdravebrusko import (
    zdravebrusko_letter_hook,
    zdravebrusko_payer_hook,
)
from api.edupage_scraper import EdupageScraper, nest_order_data_by_category


def _make_html(
    prehlad: dict,
    nazov_menu: dict,
    nastavenia: list,
    typy_platitelov: list | None = None,
    target_date: str = "2026-06-17",
) -> str:
    """Build a minimal fake mealsGuest HTML page with embedded JS data.

    Kept on a single line inside the script so the _extract_block regex
    (which uses non-greedy .+? with a lookahead for ',\\s*key :') behaves
    the same way it does on real Edupage pages (which are also one-liners).
    """

    def _js(obj):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

    # Single-line JS call — matches the real Edupage page structure.
    js_call = (
        f"strava_numeri({{"
        f"odkedy:'{target_date}',"
        f"dokedy:'{target_date}',"
        f"prehlad:{_js(prehlad)},"
        f'prehladNG:{{"prehlad":{{}}}},'
        f"typy_platitelov:{_js(typy_platitelov or [])},"
        f"nazovMenu:{_js(nazov_menu)},"
        f"nastavenia:{_js(nastavenia)},"
        f"odhlasovania2:[]"
        f"}});"
    )
    return f"<script>{js_call}</script>"


class TestResolveDietName(unittest.TestCase):
    def _r(self, sk, naz):
        return EdupageScraper.resolve_diet_name(sk, naz)

    def test_known_skratka_nm(self):
        self.assertEqual(self._r("NM", "NoMilk"), "NO MILK")

    def test_known_skratka_ng(self):
        self.assertEqual(self._r("NG", "NoGluten"), "NO GLUTEN")

    def test_known_skratka_nmng(self):
        self.assertEqual(self._r("NMNG", "NoMilk/NoGluten"), "NO MILK/NO GLUTEN")

    def test_known_skratka_his(self):
        self.assertEqual(self._r("HIS", "Histamin"), "HISTAMIN")

    def test_known_skratka_nnn(self):
        self.assertEqual(self._r("NNN", "NoNoNo"), "NONONO")

    def test_known_skratka_ne(self):
        self.assertEqual(self._r("NE", "NoEgg"), "NO EGG")

    def test_known_skratka_ns(self):
        self.assertEqual(self._r("NS", "NoSoy"), "NO SOJA")

    def test_known_skratka_nf(self):
        self.assertEqual(self._r("NF", "NoFish"), "NO FISH")

    def test_known_skratka_case_insensitive(self):
        # skratka lookup normalises to upper
        self.assertEqual(self._r("nm", "whatever"), "NO MILK")

    def test_known_skratka_nmne(self):
        # #527 vzor: bez tejto zhody padalo len na "NO MILK" a strácalo vajíčko
        self.assertEqual(self._r("NMNE", "NoMilk/NoEgg"), "NO MILK/NO EGG")

    def test_known_skratka_nmnegg(self):
        # MŠ Naša Škola Poznania píše skratku vypísanú celú ("nMnEgg")
        self.assertEqual(self._r("nMnEgg", "NoMilk/NoEgg"), "NO MILK/NO EGG")

    def test_keyword_fallback_nomilk_in_nazov(self):
        # Unknown skratka, but nazov contains "NoMilk"
        self.assertEqual(self._r("XYZ", "NoMilk"), "NO MILK")

    def test_keyword_fallback_histamin_in_nazov(self):
        self.assertEqual(self._r("ZZ", "Histaminová strava"), "HISTAMIN")

    def test_keyword_fallback_nogluten_in_nazov(self):
        self.assertEqual(self._r("?", "NoGluten jedlo"), "NO GLUTEN")

    def test_keyword_fallback_horcica_in_nazov(self):
        self.assertEqual(self._r("AnHorčica", "Klasik/noHorčica"), "NO HORCICA")

    def test_keyword_fallback_citrus_in_nazov(self):
        self.assertEqual(self._r("KLC", "Klasik bez citrus"), "NO CITRUS")

    def test_unknown_fallback_returns_nazov(self):
        self.assertEqual(self._r("ABC", "menu A"), "menu A")

    def test_unknown_fallback_empty_nazov_returns_skratka(self):
        self.assertEqual(self._r("XZ", ""), "XZ")

    def test_real_edupage_aliases_promoted_to_exact_skratka(self):
        """Bezpečné fuzzy matche pozorované na reálnom EduPage (over_edupage
        check, 26. 8. 2026) — školy ich píšu takto konzistentne, tak sú
        povýšené na exaktnú `_SKRATKA_MAP` zhodu (žiadny `uncertain` šum)."""
        cases = [
            ("NoGluten", "NoGluten", "NO GLUTEN"),  # MŠ Dobrého Pastiera
            ("PnM", "Palisády nM", "NO MILK"),  # MŠ Edulienka
            ("Vege", "Vege", "VEGGIE"),  # British School
            # Skratka nesie 3 obmedzenia — bez exaktnej zhody by substringový
            # heuristický fallback ("nmng" v compact_sk) odrezal "orech" a
            # priradil len 2-zložkovú diétu (over_edupage check, 2.9.2026).
            (
                "NMNGnORECH",
                "NMNGnORECH",
                "NO MILK – NO GLUTEN – NO ORECH",
            ),  # ZŠ Ivanka pri Dunaji
            # Bez tejto zhody končí na generickom "ngh" fallbacku, ktorý
            # vracia len "NO GLUTEN" a stráca histamín (over_edupage check,
            # 2.9.2026).
            ("nGH", "nGH", "HISTAMIN, NO GLUTEN"),  # MŠ Edulienka
        ]
        for skratka, nazov, expected in cases:
            with self.subTest(skratka=skratka, nazov=nazov):
                name, is_exact = EdupageScraper._resolve_diet_name_with_confidence(
                    skratka, nazov
                )
                self.assertEqual(name, expected)
                self.assertTrue(is_exact)

    def test_confidence_exact_skratka_is_exact(self):
        name, is_exact = EdupageScraper._resolve_diet_name_with_confidence(
            "NM", "NoMilk"
        )
        self.assertEqual(name, "NO MILK")
        self.assertTrue(is_exact)

    def test_confidence_fuzzy_keyword_is_not_exact(self):
        name, is_exact = EdupageScraper._resolve_diet_name_with_confidence(
            "XYZ", "NoMilk"
        )
        self.assertEqual(name, "NO MILK")
        self.assertFalse(is_exact)

    def test_confidence_fuzzy_suffix_is_not_exact(self):
        name, is_exact = EdupageScraper._resolve_diet_name_with_confidence(
            "PnMG", "Palisády nMG"
        )
        self.assertEqual(name, "NO MILK/NO GLUTEN")
        self.assertFalse(is_exact)

    def test_confidence_fallback_is_not_exact(self):
        name, is_exact = EdupageScraper._resolve_diet_name_with_confidence(
            "ABC", "menu A"
        )
        self.assertEqual(name, "menu A")
        self.assertFalse(is_exact)

    def test_resolve_diet_name_unaffected_by_confidence_split(self):
        # `resolve_diet_name` musí byť naďalej tenký string-only wrapper.
        self.assertEqual(self._r("NM", "NoMilk"), "NO MILK")
        self.assertEqual(self._r("XYZ", "NoMilk"), "NO MILK")

    def test_real_edupage_prefixed_no_milk_aliases(self):
        cases = [
            ("BM", "Bruško bezMliečne"),
            ("PnM", "Palisády nM"),
            ("SnM", "Stupava nM"),
            ("mšHey. NM", "MŠHeyNoMilk"),
        ]
        for skratka, nazov in cases:
            with self.subTest(skratka=skratka, nazov=nazov):
                self.assertEqual(self._r(skratka, nazov), "NO MILK")

    def test_real_edupage_prefixed_no_gluten_aliases(self):
        cases = [
            ("BG", "Bruško bezGluténové"),
            ("PnG", "Palisády nG"),
            ("SnG", "Stupava nG"),
            ("Dosp NoG", "Dosp ob NoG"),
            ("mšMal. NG", "MŠMalNoGluten"),
        ]
        for skratka, nazov in cases:
            with self.subTest(skratka=skratka, nazov=nazov):
                self.assertEqual(self._r(skratka, nazov), "NO GLUTEN")

    def test_real_edupage_combined_aliases(self):
        cases = [
            ("BMBG", "bezMliečne+bezGluténové"),
            ("PnMG", "Palisády nMG"),
            ("SnMG", "Stupava nMG"),
            ("nGnM", "noGnoM"),
        ]
        for skratka, nazov in cases:
            with self.subTest(skratka=skratka, nazov=nazov):
                self.assertEqual(self._r(skratka, nazov), "NO MILK/NO GLUTEN")

    def test_real_edupage_other_existing_diet_aliases(self):
        cases = [
            ("BH", "bezHistamínu", "HISTAMIN"),
            ("HIT", "Palisády HIT", "HISTAMIN"),
            ("SH", "Stupava H", "HISTAMIN"),
            ("DIA", "Dia", "DIA"),
            ("NEŠpeciál", "NoEggŠpeciál", "NO EGG"),
            ("NoMO", "NoM bezO", "NO MILK"),
            ("PnGH", "Palisády NGH", "NO GLUTEN"),
            ("No orech", "No orech", "NO ORECH"),
            ("No zemiak", "No zemiak", "NO ZEMIAK"),
            ("NS", "NoSoy", "NO SOJA"),
        ]
        for skratka, nazov, expected in cases:
            with self.subTest(skratka=skratka, nazov=nazov):
                self.assertEqual(self._r(skratka, nazov), expected)

    def test_menu_v_stays_veggie_diet_until_variant_exists(self):
        self.assertEqual(self._r("PV", "Palisády V"), "VEGGIE")
        self.assertEqual(self._r("SV", "Stupava V"), "VEGGIE")

    def test_british_school_english_diet_labels_map_to_slovak_names(self):
        """British School (#531) hlási diéty po anglicky, ukladáme ich pod
        slovenským Diet.name (spätná väzba: preložiť, nie nechať po anglicky)."""
        cases = [
            ("F", "Vegan", "VEGAN"),
            ("O", "noPork", "NO BRAVCOVINA"),
            ("Q", "noRedMeat", "NO CERVENE MASO"),
            ("T", "noSugar", "NO CUKOR"),
        ]
        for skratka, nazov, expected in cases:
            with self.subTest(skratka=skratka, nazov=nazov):
                self.assertEqual(self._r(skratka, nazov), expected)


class TestResolvePayerDietName(unittest.TestCase):
    """`resolve_payer_diet_name` — payer-label fragment match used for
    meals (raňajky/olovrant) that don't have their own menu-letter split,
    only payer-name text (e.g. "1.-3.ročník noMilk/noEgg")."""

    def _r(self, nazov):
        return EdupageScraper.resolve_payer_diet_name(nazov)

    def test_compound_no_milk_no_egg_payer_label_keeps_both_parts(self):
        """MŠ Naša Škola Poznania, raňajky/olovrant (žiadny letter_hook, len
        payer text) — payer "1.-3.ročník noMilk/noEgg" bez zloženej zhody
        padol na prvý nájdený (dlhší) fragment "nomilk" a stratil "noEgg"
        (user 3.9.2026: "nečíta dobre"). Na obede rovnaký payer ide cez
        menu-písmeno (skratka "nMnEgg", `_SKRATKA_MAP` už opravené 2.9.2026)
        a správne dáva "NO MILK/NO EGG" — raňajky/olovrant musia sedieť."""
        self.assertEqual(self._r("1.-3.ročník noMilk/noEgg"), "NO MILK/NO EGG")

    def test_compound_no_egg_no_milk_order_reversed_also_works(self):
        self.assertEqual(self._r("2.stupeň noEgg/noMilk"), "NO MILK/NO EGG")

    def test_plain_no_milk_payer_label_unaffected(self):
        self.assertEqual(self._r("1.-3.ročník noMilk"), "NO MILK")


class TestResolveMenuVariant(unittest.TestCase):
    def _r(self, sk, naz):
        return EdupageScraper.resolve_menu_variant(sk, naz)

    def test_klasik_is_menu_a(self):
        self.assertEqual(self._r("A", "Klasik"), "A")

    def test_klasik_b_is_menu_b_not_menu_a(self):
        """Naša Škola Poznania má dva klasické varianty, "Klasik A" a "Klasik
        B" — paušálne "klasik" v názve → A malo prednosť pred písmenom na
        konci, takže sa "Klasik B" počítalo ako A a Menu B v appke nikdy
        neukázalo žiadne počty (nahlásené 1.9.2026, dom B)."""
        self.assertEqual(self._r("A", "Klasik A"), "A")
        self.assertEqual(self._r("B", "Klasik B"), "B")

    def test_bare_klasik_without_a_trailing_letter_stays_menu_a(self):
        """Škola s jediným "Klasik" (žiadny druhý variant) sa nesmie zlomiť —
        paušálne pravidlo je fallback, nie mŕtvy kód."""
        self.assertEqual(self._r("", "Klasik"), "A")
        self.assertEqual(self._r("", "Classic"), "A")

    def test_montessori_combined_ms_zs_class_is_menu_a(self):
        self.assertEqual(self._r("MŠ/ZŠ Iná", "MŠ/ZŠ Iná"), "A")

    def test_klasik_with_diet_signal_is_not_menu_variant(self):
        """Cvernička "AnHorčica"/"Klasik/noHorčica": nazov obsahuje "Klasik",
        takže by inak spadlo do menu-A vetvy skôr, než sa vôbec skúsi diéta —
        appka by "no horčica" reštrikciu potichu stratila (nájdené 27.8.2026
        v reálnej tabuľke — appka to počítala ako obyčajný Klasik)."""
        self.assertIsNone(self._r("AnHorčica", "Klasik/noHorčica"))

    def test_klasik_bez_citrus_is_not_menu_variant(self):
        """MŠ Rozmanitá "KLC"/"Klasik bez citrus": rovnaký vzor ako "noHorčica"
        vyššie — bez rozpoznania "citrus" ako diétneho signálu by sa dieťa
        s citrusovým obmedzením počítalo ako obyčajný Klasik (1.9.2026)."""
        self.assertIsNone(self._r("KLC", "Klasik bez citrus"))

    def test_menu_a_is_menu_a(self):
        self.assertEqual(self._r("A", "Menu A"), "A")

    def test_plain_variant_letter_is_menu(self):
        self.assertEqual(self._r("B", "B"), "B")

    def test_diet_name_is_not_menu_variant(self):
        self.assertIsNone(self._r("NM", "NoMilk"))

    def test_letter_b_with_diet_name_is_not_menu_variant(self):
        self.assertIsNone(self._r("B", "NoGluten"))

    def test_prefixed_menu_names_are_menu_variants(self):
        self.assertEqual(self._r("PA", "Palisády A"), "A")
        self.assertEqual(self._r("PB", "Palisády B"), "B")
        self.assertEqual(self._r("PC", "Menu C"), "C")

    def test_menu_d_is_menu_variant_not_an_unknown_diet(self):
        """British School (#531) hlási 4. menu ako "Menu D" — nemá byť diéta."""
        self.assertEqual(self._r("D", "Menu D"), "D")


class TestBuildJidMap(unittest.TestCase):
    TARGET_DATE = date(2026, 6, 17)

    def _build(self, vydaj_od, jid="2", target_date=None, plati_od=None, plati_do=None):
        row = {
            "setting": "vydaj_normal",
            "hodnota": json.dumps(
                {"1": {jid: {"vydaj_od": vydaj_od, "vydaj_do": "14:00"}}}
            ),
        }
        if plati_od is not None:
            row["plati_od"] = plati_od
        if plati_do is not None:
            row["plati_do"] = plati_do
        nastavenia = [row]
        return EdupageScraper._build_jid_map(
            nastavenia, target_date or self.TARGET_DATE
        )

    def test_lunch(self):
        self.assertEqual(self._build("11:00")["2"], "lunch")

    def test_breakfast(self):
        self.assertEqual(self._build("07:30")["2"], "breakfast")

    def test_olovrant(self):
        self.assertEqual(self._build("15:00")["2"], "olovrant")

    def test_boundary_exactly_10(self):
        # 10:00 → lunch (10 is not < 10, so falls to next range < 15)
        self.assertEqual(self._build("10:00")["2"], "lunch")

    def test_empty_nastavenia_returns_empty(self):
        self.assertEqual(EdupageScraper._build_jid_map([], self.TARGET_DATE), {})

    def test_wrong_setting_ignored(self):
        nastavenia = [{"setting": "something_else", "hodnota": "{}"}]
        self.assertEqual(
            EdupageScraper._build_jid_map(nastavenia, self.TARGET_DATE), {}
        )

    def test_row_within_plati_od_plati_do_is_used(self):
        result = self._build("11:00", plati_od="2025-09-01", plati_do="2026-07-31")
        self.assertEqual(result["2"], "lunch")

    def test_row_before_plati_od_is_ignored(self):
        # target_date (2026-06-17) is before this row's validity window starts.
        result = self._build("11:00", plati_od="2026-09-01", plati_do="2027-07-31")
        self.assertEqual(result, {})

    def test_row_after_plati_do_is_ignored(self):
        # target_date (2026-06-17) is after this row's validity window ended -
        # a stale schedule from a previous school year must not apply.
        result = self._build("11:00", plati_od="2024-09-01", plati_do="2025-07-31")
        self.assertEqual(result, {})

    def test_only_the_row_valid_for_target_date_is_applied(self):
        """Two schedules covering different school years must not both
        apply - only the one whose plati_od/plati_do covers target_date."""
        old_row = {
            "setting": "vydaj_normal",
            "plati_od": "2024-09-01",
            "plati_do": "2025-07-31",
            "hodnota": json.dumps(
                {"1": {"2": {"vydaj_od": "12:00", "vydaj_do": "13:00"}}}
            ),
        }
        new_row = {
            "setting": "vydaj_normal",
            "plati_od": "2025-09-01",
            "plati_do": "2026-07-31",
            "hodnota": json.dumps(
                {"1": {"2": {"vydaj_od": "11:00", "vydaj_do": "14:00"}}}
            ),
        }
        result = EdupageScraper._build_jid_map([old_row, new_row], self.TARGET_DATE)
        self.assertEqual(result["2"], "lunch")

    def test_bigger_window_wins_the_naive_collision(self):
        """Obed (11:00, 7 druhov jedál) a olovrant (14:30, tiež 'hodina 14' →
        naivne tiež obed) kolidujú v tom istom naivnom košíku — vyhráva ten s
        väčšou pestrosťou jedál (skutočný obed), olovrant sa posunie ďalej."""
        row = {
            "setting": "vydaj_normal",
            "hodnota": json.dumps(
                {
                    "1": {
                        "1": {"vydaj_od": "09:30", "druhov_jedal": 7},
                        "2": {"vydaj_od": "11:00", "druhov_jedal": 7},
                        "3": {"vydaj_od": "14:30", "druhov_jedal": 7},
                    }
                }
            ),
        }
        result = EdupageScraper._build_jid_map([row], self.TARGET_DATE)
        self.assertEqual(result, {"1": "breakfast", "2": "lunch", "3": "olovrant"})

    def test_config_meal_hour_thresholds_splits_out_a_dedicated_snack_window(self):
        """British School (live mealsGuest 2026-09-07) má presne 4 okná/deň:
        08:30 raňajky (MŠ-only payer set), 10:05 desiata (~celá škola, iný typ
        jedla než náš interný olovrant/desiata koncept — user 4.9.2026), 11:25
        obed (21 druhov jedál), 14:30 olovrant (rovnaký MŠ-only payer set ako
        raňajky). Bez vlastných `meal_hour_thresholds` by desiata (hodina 10,
        nie < generický prah 10) spadla do rovnakého naivného košíka ako obed
        a olovrant a skončila zlúčená pod "breakfast" (rovnaký #British 885-hláv
        vzor ako `_build_jid_map`'s docstring, len pre 4. okno namiesto 3)."""
        row = {
            "setting": "vydaj_normal",
            "hodnota": json.dumps(
                {
                    "1": [
                        {"vydaj_od": "08:30", "vydaj_do": "10:00", "druhov_jedal": 1},
                        {"vydaj_od": "10:05", "vydaj_do": "10:30", "druhov_jedal": 1},
                        {"vydaj_od": "11:25", "vydaj_do": "14:00", "druhov_jedal": 21},
                        {"vydaj_od": "14:30", "vydaj_do": "15:30", "druhov_jedal": 1},
                    ]
                }
            ),
        }
        config = PrevadzkaConfig(
            subdomena="zdravyprojekt",
            ucty=("British School",),
            olovrant_mode=OlovrantMode.EDUPAGE,
            meal_hour_thresholds=((9, "breakfast"), (11, "desiata"), (15, "lunch")),
        )
        result = EdupageScraper._build_jid_map([row], self.TARGET_DATE, config=config)
        self.assertEqual(
            result,
            {"0": "breakfast", "1": "desiata", "2": "lunch", "3": "olovrant"},
        )

    def test_without_config_default_thresholds_still_apply(self):
        """Bez configu (alebo config bez `meal_hour_thresholds`) sa nič
        nemení pre ostatné školy — regresný test k `_MEAL_BY_HOUR`."""
        self.assertEqual(self._build("11:00")["2"], "lunch")

    def test_small_early_window_loses_to_the_real_lunch_and_falls_to_breakfast(self):
        """Desiata (10:05, 1 druh jedla) padne do rovnakého naivneho košíka
        ako skutočný obed (11:25, 21 druhov jedál) — obed vyhrá, desiata sa
        (keďže bola pred ním) preradí naspäť do raňajok, nie dopredu k
        olovrantu (#British School, 1.9.2026)."""
        row = {
            "setting": "vydaj_normal",
            "hodnota": json.dumps(
                {
                    "1": {
                        "0": {"vydaj_od": "08:30", "druhov_jedal": 1},
                        "1": {"vydaj_od": "10:05", "druhov_jedal": 1},
                        "2": {"vydaj_od": "11:25", "druhov_jedal": 21},
                        "3": {"vydaj_od": "14:30", "druhov_jedal": 1},
                    }
                }
            ),
        }
        result = EdupageScraper._build_jid_map([row], self.TARGET_DATE)
        self.assertEqual(
            result,
            {"0": "breakfast", "1": "breakfast", "2": "lunch", "3": "olovrant"},
        )

    def test_windows_as_a_plain_list_are_keyed_by_position(self):
        """British School nahlasuje okná ako list bez vlastného jid — pozícia
        v zozname JE jid použité v `prehlad`. Bez podpory tohto tvaru celý
        deň potichu preskočil a `jid_map` vyšla prázdna (#British School,
        1.9.2026 — 885 hláv skončilo pod jedným 'obedom')."""
        row = {
            "setting": "vydaj_normal",
            "hodnota": json.dumps(
                {
                    "1": [
                        {"vydaj_od": "08:30", "druhov_jedal": 1},
                        {"vydaj_od": "10:05", "druhov_jedal": 1},
                        {"vydaj_od": "11:25", "druhov_jedal": 21},
                        {"vydaj_od": "14:30", "druhov_jedal": 1},
                    ]
                }
            ),
        }
        result = EdupageScraper._build_jid_map([row], self.TARGET_DATE)
        self.assertEqual(
            result,
            {"0": "breakfast", "1": "breakfast", "2": "lunch", "3": "olovrant"},
        )


class TestBuildPayerMap(unittest.TestCase):
    TARGET_DATE = date(2026, 6, 17)

    def test_row_without_validity_dates_always_applies(self):
        typy = [
            {
                "setting": "typy_platitelov",
                "hodnota": {"1": {"nazov": "MŠ Klasik", "porcia": "0"}},
            }
        ]
        result = EdupageScraper._build_payer_map(typy, self.TARGET_DATE)
        self.assertEqual(result["1"]["portion"], "Škôlka")

    def test_row_outside_validity_window_is_ignored(self):
        """A payer-mapping row from a previous school year (already expired
        by plati_do) must not apply to a scrape for a later date - it may
        assign payer_ids to different diets/portions than the current row."""
        typy = [
            {
                "setting": "typy_platitelov",
                "plati_od": "2024-09-01",
                "plati_do": "2025-07-31",
                "hodnota": {"1": {"nazov": "MŠ Klasik", "porcia": "0"}},
            }
        ]
        result = EdupageScraper._build_payer_map(typy, self.TARGET_DATE)
        self.assertEqual(result, {})

    def test_only_row_valid_for_target_date_is_applied(self):
        """Two overlapping payer-mapping rows (e.g. reassigned payer_id
        across a school-year change) must not both merge in - only the one
        whose plati_od/plati_do actually covers target_date should apply."""
        old_row = {
            "setting": "typy_platitelov",
            "plati_od": "2024-09-01",
            "plati_do": "2025-07-31",
            "hodnota": {"14": {"nazov": "MŠ NoGluten", "porcia": "0"}},
        }
        new_row = {
            "setting": "typy_platitelov",
            "plati_od": "2025-09-01",
            "plati_do": "2026-07-31",
            "hodnota": {"14": {"nazov": "MŠ NoMilk", "porcia": "0"}},
        }
        result = EdupageScraper._build_payer_map([old_row, new_row], self.TARGET_DATE)
        self.assertEqual(result["14"]["diet"], "NO MILK")


class TestInjectDate(unittest.TestCase):
    def test_adds_date_when_missing(self):
        url = "https://zsivanka.edupage.org/menu/mealsGuest?id=x3StT4Z"
        result = EdupageScraper._inject_date(url, date(2026, 6, 17))
        self.assertIn("date=2026-06-17", result)
        self.assertIn("id=x3StT4Z", result)

    def test_replaces_existing_date(self):
        url = "https://school.edupage.org/menu/mealsGuest?id=ABC&date=2026-05-01"
        result = EdupageScraper._inject_date(url, date(2026, 6, 17))
        self.assertIn("date=2026-06-17", result)
        self.assertNotIn("2026-05-01", result)

    def test_preserves_id_param(self):
        url = "https://school.edupage.org/menu/mealsGuest?id=TOKEN123"
        result = EdupageScraper._inject_date(url, date(2026, 1, 1))
        self.assertIn("id=TOKEN123", result)


class TestParse(unittest.TestCase):
    TARGET_DATE = date(2026, 6, 17)
    DATE_STR = "2026-06-17"

    def _scrape_html(self, html: str, allowed_diets=None, config=None):
        scraper = EdupageScraper()
        return scraper._parse(
            html, self.TARGET_DATE, config=config, allowed_diets=allowed_diets
        )

    def _typy(self, items):
        return [
            {
                "setting": "typy_platitelov",
                "hodnota": {
                    str(payer_id): {
                        "nazov": name,
                        "porcia": portion_code,
                        "typ_platitela": payer_id,
                    }
                    for payer_id, name, portion_code in items
                },
            }
        ]

    def test_parse_full_html_lunch(self):
        prehlad = {
            "prehlad": {
                self.DATE_STR: {
                    "2": {
                        "A": {
                            "typ_platitela": {"6": {"o": 2}, "7": {"o": 1}},
                            "porcia": {},
                            "v_skupina": {},
                        },
                        "B": {
                            "typ_platitela": {"4": {"o": 5}},
                            "porcia": {},
                            "v_skupina": {},
                        },
                    }
                }
            },
            "mamUnknown": False,
            "unknownTypyIDS": [],
        }
        nazov_menu = {
            "A": {"nazov": "NoMilk", "skratka": "NM"},
            "B": {"nazov": "NoGluten", "skratka": "NG"},
        }
        nastavenia = [
            {
                "setting": "vydaj_normal",
                "hodnota": json.dumps(
                    {"1": {"2": {"vydaj_od": "11:00", "vydaj_do": "14:00"}}}
                ),
            }
        ]
        typy_platitelov = self._typy(
            [
                (4, "1.stupeň NoGluten", 1),
                (6, "MŠ NoMilk", 0),
                (7, "Dospelý NoMilk", 3),
            ]
        )
        html = _make_html(
            prehlad, nazov_menu, nastavenia, typy_platitelov, self.DATE_STR
        )
        result = self._scrape_html(html)

        self.assertIn("lunch", result.order_data)
        self.assertEqual(
            result.order_data["lunch"]["Škôlka"],
            {"menuCounts": {"A": 2}, "diets": {"NO MILK": 2}},
        )
        self.assertEqual(
            result.order_data["lunch"]["Dospelý (SŠ)"],
            {"menuCounts": {"A": 1}, "diets": {"NO MILK": 1}},
        )
        self.assertEqual(
            result.order_data["lunch"]["ZŠ 1.stupeň"],
            {"menuCounts": {"A": 5}, "diets": {"NO GLUTEN": 5}},
        )
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.unmapped_letters, [])

    def test_parse_breakfast_and_lunch(self):
        prehlad = {
            "prehlad": {
                self.DATE_STR: {
                    "1": {
                        "A": {
                            "typ_platitela": {"1": {"o": 20}},
                            "porcia": {},
                            "v_skupina": {},
                        }
                    },
                    "2": {
                        "A": {
                            "typ_platitela": {"1": {"o": 50}},
                            "porcia": {},
                            "v_skupina": {},
                        }
                    },
                }
            },
            "mamUnknown": False,
            "unknownTypyIDS": [],
        }
        nazov_menu = {"A": {"nazov": "menu A", "skratka": "A"}}
        nastavenia = [
            {
                "setting": "vydaj_normal",
                "hodnota": json.dumps(
                    {
                        "1": {
                            "1": {"vydaj_od": "07:30", "vydaj_do": "09:00"},
                            "2": {"vydaj_od": "11:30", "vydaj_do": "14:00"},
                        }
                    }
                ),
            }
        ]
        html = _make_html(
            prehlad,
            nazov_menu,
            nastavenia,
            self._typy([(1, "MŠ Klasik", 0)]),
            self.DATE_STR,
        )
        result = self._scrape_html(html)

        self.assertIn("breakfast", result.order_data)
        self.assertIn("lunch", result.order_data)
        self.assertEqual(
            result.order_data["breakfast"]["Škôlka"]["menuCounts"]["A"], 20
        )
        self.assertEqual(result.order_data["lunch"]["Škôlka"]["menuCounts"]["A"], 50)

    def test_parse_breakfast_lunch_and_olovrant(self):
        prehlad = {
            "prehlad": {
                self.DATE_STR: {
                    "1": {"A": {"typ_platitela": {"1": {"o": 7}}}},
                    "2": {"A": {"typ_platitela": {"1": {"o": 11}}}},
                    "3": {"A": {"typ_platitela": {"1": {"o": 5}}}},
                }
            },
            "mamUnknown": False,
            "unknownTypyIDS": [],
        }
        nazov_menu = {"A": {"nazov": "Klasik", "skratka": "A"}}
        nastavenia = [
            {
                "setting": "vydaj_normal",
                "hodnota": json.dumps(
                    {
                        "1": {
                            "1": {"vydaj_od": "08:00", "vydaj_do": "09:00"},
                            "2": {"vydaj_od": "12:00", "vydaj_do": "14:00"},
                            "3": {"vydaj_od": "15:30", "vydaj_do": "16:00"},
                        }
                    }
                ),
            }
        ]
        html = _make_html(
            prehlad,
            nazov_menu,
            nastavenia,
            self._typy([(1, "MŠ Klasik", 0)]),
            self.DATE_STR,
        )
        result = self._scrape_html(html)

        self.assertEqual(result.order_data["breakfast"]["Škôlka"]["menuCounts"]["A"], 7)
        self.assertEqual(result.order_data["lunch"]["Škôlka"]["menuCounts"]["A"], 11)
        self.assertEqual(result.order_data["olovrant"]["Škôlka"]["menuCounts"]["A"], 5)
        self.assertEqual(result.order_data["breakfast"]["Škôlka"]["diets"], {})
        self.assertEqual(result.order_data["lunch"]["Škôlka"]["diets"], {})
        self.assertEqual(result.order_data["olovrant"]["Škôlka"]["diets"], {})

    def test_parse_uses_per_jid_nazov_menu_override(self):
        """Regression test (zdravebrusko feed, 3.9.2026): EduPage môže tú istú
        písmenovú skratku na rôznych jidoch (raňajky/obed/olovrant) použiť pre
        úplne iný výber — `nazovMenu[letter]` nesie sploštený (skratka, nazov)
        pár PLUS voliteľný `jids` slovník s per-jid výnimkami. Písmeno "B" tu
        je na jid 1 (raňajky) "sšvA"/"Klasik" (SŠ Veterinárna klasik), ale na
        jid 2 (obed) "dsbNM"/"NoMilk" (Deutsche Schule diéta) — sploštený
        fallback vždy vrátil obedovú verziu, takže SŠ Veterinárna raňajky sa
        tíško vyhodnotili ako Deutsche Schule diéta a zmizli z prehľadu."""
        prehlad = {
            "prehlad": {
                self.DATE_STR: {
                    "1": {"B": {"typ_platitela": {"1": {"o": 8}}}},
                    "2": {"B": {"typ_platitela": {"1": {"o": 3}}}},
                }
            },
            "mamUnknown": False,
            "unknownTypyIDS": [],
        }
        nazov_menu = {
            "B": {
                # Sploštený fallback — reálne dáta ho nechávajú na poslednom
                # spracovanom jide (tu obed).
                "skratka": "dsbNM",
                "nazov": "NoMilk",
                "jids": {
                    "1": {"skratka": "sšvA", "nazov": "Klasik"},
                    "2": {"skratka": "dsbNM", "nazov": "NoMilk"},
                },
            }
        }
        nastavenia = [
            {
                "setting": "vydaj_normal",
                "hodnota": json.dumps(
                    {
                        "1": {
                            "1": {"vydaj_od": "07:30", "vydaj_do": "09:00"},
                            "2": {"vydaj_od": "11:30", "vydaj_do": "14:00"},
                        }
                    }
                ),
            }
        ]
        html = _make_html(
            prehlad,
            nazov_menu,
            nastavenia,
            self._typy([(1, "MŠ Klasik", 0)]),
            self.DATE_STR,
        )
        result = self._scrape_html(html, allowed_diets={"NO MILK"})

        # Raňajky: písmeno B je na jid 1 "Klasik" (menu, nie diéta) — musí
        # pristáť v menuCounts, nie v diets, a nesmie byť unmapped.
        self.assertEqual(
            result.order_data["breakfast"]["Škôlka"]["menuCounts"].get("A"), 8
        )
        self.assertEqual(result.order_data["breakfast"]["Škôlka"]["diets"], {})
        # Obed: to isté písmeno B je na jid 2 skutočne "NoMilk" diéta.
        self.assertEqual(
            result.order_data["lunch"]["Škôlka"]["diets"].get("NO MILK"), 3
        )
        self.assertEqual(result.unmapped_letters, [])

    def test_parse_late_olovrant_window_does_not_double_count_lunch(self):
        """Regression test for a real production discrepancy: an olovrant
        window starting at 14:30 has vydaj_od hour=14, same as an hour=14
        lunch window ending at 14:00 — both used to fall under the old
        "hour < 15" lunch bucket, silently summing two distinct real meals
        into one "lunch" count (e.g. 10 lunch + 10 olovrant reported as 20
        lunch, tripling the day's total with a 3rd breakfast window)."""
        prehlad = {
            "prehlad": {
                self.DATE_STR: {
                    "1": {"A": {"typ_platitela": {"1": {"o": 10}}}},
                    "2": {"A": {"typ_platitela": {"1": {"o": 10}}}},
                    "3": {"A": {"typ_platitela": {"1": {"o": 10}}}},
                }
            },
            "mamUnknown": False,
            "unknownTypyIDS": [],
        }
        nazov_menu = {"A": {"nazov": "Klasik", "skratka": "A"}}
        nastavenia = [
            {
                "setting": "vydaj_normal",
                "hodnota": json.dumps(
                    {
                        "1": {
                            "1": {"vydaj_od": "09:30", "vydaj_do": "10:30"},
                            "2": {"vydaj_od": "11:00", "vydaj_do": "14:00"},
                            "3": {"vydaj_od": "14:30", "vydaj_do": "15:30"},
                        }
                    }
                ),
            }
        ]
        html = _make_html(
            prehlad,
            nazov_menu,
            nastavenia,
            self._typy([(1, "MŠ Klasik", 0)]),
            self.DATE_STR,
        )
        result = self._scrape_html(html)

        self.assertEqual(
            result.order_data["breakfast"]["Škôlka"]["menuCounts"]["A"], 10
        )
        self.assertEqual(result.order_data["lunch"]["Škôlka"]["menuCounts"]["A"], 10)
        self.assertEqual(result.order_data["olovrant"]["Škôlka"]["menuCounts"]["A"], 10)

    def test_parse_menu_a_as_plain_menu_without_diet(self):
        prehlad = {
            "prehlad": {
                self.DATE_STR: {
                    "2": {"A": {"typ_platitela": {"1": {"o": 13}}}},
                }
            },
            "mamUnknown": False,
            "unknownTypyIDS": [],
        }
        nazov_menu = {"A": {"nazov": "Menu A", "skratka": "A"}}
        nastavenia = [
            {
                "setting": "vydaj_normal",
                "hodnota": json.dumps(
                    {"1": {"2": {"vydaj_od": "12:00", "vydaj_do": "14:00"}}}
                ),
            }
        ]
        html = _make_html(
            prehlad,
            nazov_menu,
            nastavenia,
            self._typy([(1, "ZŠ Klasik", 1)]),
            self.DATE_STR,
        )
        result = self._scrape_html(html)

        self.assertEqual(
            result.order_data["lunch"],
            {"ZŠ 1.stupeň": {"menuCounts": {"A": 13}, "diets": {}}},
        )

    def test_parse_payer_group_can_supply_clean_portion_without_forcing_a_diet(self):
        """SŠV payer group "SŠV žiak" is a plain portion label, not a diet.

        Live data (2.9.2026) confirmed SŠ Veterinárna's actual menu choice — Klasik
        (A) / Menu B / Vege — lives at the menu-letter level, not the payer group.
        A previous blanket "ssv in payer name → VEGGIE" rule forced every SŠV order
        to VEGGIE even when the letter picked was the plain Klasik menu (#557).
        """
        prehlad = {
            "prehlad": {
                self.DATE_STR: {
                    "2": {"A": {"typ_platitela": {"12": {"o": 4}}}},
                }
            },
            "mamUnknown": False,
            "unknownTypyIDS": [],
        }
        nazov_menu = {"A": {"nazov": "Klasik", "skratka": "sšvA"}}
        nastavenia = [
            {
                "setting": "vydaj_normal",
                "hodnota": json.dumps(
                    {"1": {"2": {"vydaj_od": "12:00", "vydaj_do": "14:00"}}}
                ),
            }
        ]
        html = _make_html(
            prehlad,
            nazov_menu,
            nastavenia,
            self._typy([(12, "SŠV žiak", 4)]),
            self.DATE_STR,
        )
        result = self._scrape_html(html)

        self.assertEqual(
            result.order_data["lunch"],
            {"Dospelý (SŠ)": {"menuCounts": {"A": 4}, "diets": {}}},
        )

    def test_parse_ssv_vege_letter_is_its_own_menu_not_a_diet_on_klasik(self):
        """ "sšvV" (Vege) je pre SŠ Veterinárnu samostatný MENU výber — ako
        "sšvA"/Klasik, "sšvB"/Menu B — nie dietná úprava Klasiku.

        Pôvodne namapované ako `LetterRule(diet="VEGGIE")` (#557) — keďže
        `_parse` diétu vždy sčíta aj do menuCounts.A (bežne JE úpravou
        Klasiku), toto duplicitne napočítalo vege objednávky aj do A (user
        3.9.2026: reálny obed mal byť A:18/B:4/V:2, appka ukazovala A:20).
        `LetterRule(menu="V")` počíta Vege do vlastného menuCounts.V."""
        prehlad = {
            "prehlad": {
                self.DATE_STR: {
                    "2": {
                        "A": {"typ_platitela": {"12": {"o": 18}}},
                        "I": {"typ_platitela": {"12": {"o": 2}}},
                    },
                }
            },
            "mamUnknown": False,
            "unknownTypyIDS": [],
        }
        nazov_menu = {
            "A": {"nazov": "Klasik", "skratka": "sšvA"},
            "I": {"nazov": "Vege", "skratka": "sšvV"},
        }
        nastavenia = [
            {
                "setting": "vydaj_normal",
                "hodnota": json.dumps(
                    {"1": {"2": {"vydaj_od": "12:00", "vydaj_do": "14:00"}}}
                ),
            }
        ]
        html = _make_html(
            prehlad,
            nazov_menu,
            nastavenia,
            self._typy([(12, "SŠV žiak", 4)]),
            self.DATE_STR,
        )
        config = PrevadzkaConfig(
            subdomena="zdravebrusko",
            ucty=("Ďumbierska", "Lamač", "Malý", "Heyrovského"),
            olovrant_mode=OlovrantMode.EDUPAGE,
            letter_hook=zdravebrusko_letter_hook,
        )
        result = self._scrape_html(html, config=config)

        self.assertEqual(
            result.order_data["lunch"],
            {
                "Dospelý (SŠ)": {
                    "menuCounts": {"A": 18, "V": 2},
                    "diets": {},
                }
            },
        )

    def test_parse_ssv_dospely_payer_group_is_flagged_pack_separately(self):
        """SŠV dospelí (zamestnanci) zdieľajú s "SŠV žiak" tú istú porciu
        ("Dospelý (SŠ)") — EduPage porcia kód ich nevie rozlíšiť, obaja
        spadajú pod strednú školu. Payer label "SŠV dospelý" je jediný
        spoľahlivý signál, appka ho preto automaticky označí packSeparately
        (user 4.9.2026) — na rozdiel od `adults_pack_separately_enabled`,
        ktorý by zabalil zvlášť aj žiakov zdieľajúcich tú istú porciu."""
        prehlad = {
            "prehlad": {
                self.DATE_STR: {
                    "2": {"A": {"typ_platitela": {"9": {"o": 3}, "12": {"o": 18}}}},
                }
            },
            "mamUnknown": False,
            "unknownTypyIDS": [],
        }
        nazov_menu = {"A": {"nazov": "Klasik", "skratka": "sšvA"}}
        nastavenia = [
            {
                "setting": "vydaj_normal",
                "hodnota": json.dumps(
                    {"1": {"2": {"vydaj_od": "12:00", "vydaj_do": "14:00"}}}
                ),
            }
        ]
        html = _make_html(
            prehlad,
            nazov_menu,
            nastavenia,
            self._typy([(9, "SŠV dospelý", 4), (12, "SŠV žiak", 4)]),
            self.DATE_STR,
        )
        config = PrevadzkaConfig(
            subdomena="zdravebrusko",
            ucty=("Ďumbierska", "Lamač", "Malý", "Heyrovského"),
            olovrant_mode=OlovrantMode.EDUPAGE,
            letter_hook=zdravebrusko_letter_hook,
            payer_hook=zdravebrusko_payer_hook,
        )
        result = self._scrape_html(html, config=config)

        self.assertEqual(
            result.order_data["lunch"],
            {
                "Dospelý (SŠ)": {
                    "menuCounts": {"A": 21},
                    "diets": {},
                    "packSeparately": {"menus": {"A": 3}, "diets": {}},
                }
            },
        )

    def test_nest_order_data_by_category_wraps_flat_meals(self):
        nested = nest_order_data_by_category(
            {
                "breakfast": {"menuCounts": {"A": 7}, "diets": {}},
                "lunch": {"menuCounts": {"A": 11}, "diets": {}},
            },
            "Edupage school",
        )

        self.assertEqual(
            nested,
            {
                "breakfast": {
                    "Edupage school": {
                        "menuCounts": {"A": 7},
                        "diets": {},
                    }
                },
                "lunch": {"Edupage school": {"menuCounts": {"A": 11}, "diets": {}}},
            },
        )

    def test_parse_empty_prehlad_for_date(self):
        prehlad = {"prehlad": {}, "mamUnknown": False, "unknownTypyIDS": []}
        html = _make_html(prehlad, {}, [], target_date=self.DATE_STR)
        result = self._scrape_html(html)

        self.assertEqual(result.order_data, {})

    def test_parse_empty_prehlad_list_is_not_error(self):
        prehlad = {"prehlad": [], "mamUnknown": False, "unknownTypyIDS": []}
        html = _make_html(prehlad, {}, [], target_date=self.DATE_STR)
        result = self._scrape_html(html)

        self.assertEqual(result.order_data, {})
        self.assertEqual(result.warnings, [])

    def test_parse_missing_prehlad_block(self):
        html = "<html><body>nothing here</body></html>"
        result = self._scrape_html(html)

        self.assertEqual(result.order_data, {})
        self.assertTrue(len(result.warnings) > 0)
        self.assertIn("prehlad", result.warnings[0])

    def test_parse_zero_orders_excluded(self):
        prehlad = {
            "prehlad": {
                self.DATE_STR: {
                    "2": {
                        "A": {
                            "typ_platitela": {"1": {"o": 0}},
                            "porcia": {},
                            "v_skupina": {},
                        },
                    }
                }
            },
            "mamUnknown": False,
            "unknownTypyIDS": [],
        }
        nazov_menu = {"A": {"nazov": "NoMilk", "skratka": "NM"}}
        nastavenia = [
            {
                "setting": "vydaj_normal",
                "hodnota": json.dumps(
                    {"1": {"2": {"vydaj_od": "11:00", "vydaj_do": "14:00"}}}
                ),
            }
        ]
        html = _make_html(
            prehlad,
            nazov_menu,
            nastavenia,
            self._typy([(1, "MŠ NoMilk", 0)]),
            self.DATE_STR,
        )
        result = self._scrape_html(html)

        # Zero-count entries should not appear in order_data
        self.assertEqual(result.order_data, {})

    def test_unknown_diet_is_counted_and_reported(self):
        prehlad = {
            "prehlad": {
                self.DATE_STR: {
                    "2": {
                        "Z": {
                            "typ_platitela": {"1": {"o": 3}},
                            "porcia": {},
                            "v_skupina": {},
                        },
                    }
                }
            },
            "mamUnknown": False,
            "unknownTypyIDS": [],
        }
        html = _make_html(
            prehlad,
            {},
            [],
            self._typy([(1, "MŠ Klasik", 0)]),
            self.DATE_STR,
        )
        result = self._scrape_html(html)

        # Neznáma diéta sa NEZAHADZUJE — porcie musia ostať v počte, inak
        # kuchyni chýbajú jedlá a nikto o tom nevie.
        self.assertEqual(
            result.order_data,
            {"lunch": {"Škôlka": {"menuCounts": {"A": 3}, "diets": {"Z": 3}}}},
        )
        self.assertIn("Z:Z", result.unmapped_letters)

    def test_diet_known_only_in_db_is_accepted(self):
        """Diéta založená v appke (nie v zabudovanom zozname) sa už nehlási ako
        neznáma — presne kvôli tomu, aby nová diéta školy nečakala na nasadenie."""
        prehlad = {
            "prehlad": {
                self.DATE_STR: {
                    "2": {
                        "N": {
                            "typ_platitela": {"1": {"o": 4}},
                            "porcia": {},
                            "v_skupina": {},
                        },
                    }
                }
            },
            "mamUnknown": False,
            "unknownTypyIDS": [],
        }
        nazov_menu = {"N": {"skratka": "NK", "nazov": "NO KAKAO"}}
        html = _make_html(
            prehlad,
            nazov_menu,
            [],
            self._typy([(1, "MŠ Klasik", 0)]),
            self.DATE_STR,
        )

        neznama = self._scrape_html(html)
        self.assertEqual(neznama.unmapped_letters, ["N:NO KAKAO"])

        znama = self._scrape_html(html, allowed_diets={"NO KAKAO"})
        self.assertEqual(znama.unmapped_letters, [])
        self.assertEqual(
            znama.order_data,
            {"lunch": {"Škôlka": {"menuCounts": {"A": 4}, "diets": {"NO KAKAO": 4}}}},
        )

    def test_fuzzy_matched_diet_is_uncertain_but_counted_normally(self):
        """#527: skratka mimo `_SKRATKA_MAP`, ktorá fuzzy-matchne na povolenú diétu,
        sa počíta rovnako ako doteraz (žiadny unmapped flag), ale appka si to
        poznamená ako neisté na kontrolu — namiesto tichej istoty."""
        prehlad = {
            "prehlad": {
                self.DATE_STR: {
                    "2": {
                        "Z": {
                            "typ_platitela": {"1": {"o": 2}},
                            "porcia": {},
                            "v_skupina": {},
                        },
                    }
                }
            },
            "mamUnknown": False,
            "unknownTypyIDS": [],
        }
        # "XYZ" nie je v `_SKRATKA_MAP`, ale nazov obsahuje "NoMilk" → fuzzy hit.
        nazov_menu = {"Z": {"skratka": "XYZ", "nazov": "NoMilk"}}
        html = _make_html(
            prehlad,
            nazov_menu,
            [],
            self._typy([(1, "MŠ Klasik", 0)]),
            self.DATE_STR,
        )
        result = self._scrape_html(html)

        self.assertEqual(result.unmapped_letters, [])
        self.assertEqual(result.uncertain_letters, ["Z:XYZ→NO MILK"])
        self.assertEqual(
            result.order_data,
            {"lunch": {"Škôlka": {"menuCounts": {"A": 2}, "diets": {"NO MILK": 2}}}},
        )

    def test_exact_skratka_match_is_not_uncertain(self):
        prehlad = {
            "prehlad": {
                self.DATE_STR: {
                    "2": {
                        "A": {
                            "typ_platitela": {"1": {"o": 2}},
                            "porcia": {},
                            "v_skupina": {},
                        },
                    }
                }
            },
            "mamUnknown": False,
            "unknownTypyIDS": [],
        }
        nazov_menu = {"A": {"skratka": "NM", "nazov": "NoMilk"}}
        html = _make_html(
            prehlad,
            nazov_menu,
            [],
            self._typy([(1, "MŠ Klasik", 0)]),
            self.DATE_STR,
        )
        result = self._scrape_html(html)
        self.assertEqual(result.uncertain_letters, [])


class TestFetchError(unittest.TestCase):
    def test_fetch_error_propagates(self):
        import requests as req_module

        scraper = EdupageScraper()
        with patch.object(
            scraper, "_fetch", side_effect=req_module.ConnectionError("timeout")
        ):
            with self.assertRaises(req_module.ConnectionError):
                scraper.scrape(
                    "https://school.edupage.org/menu/mealsGuest?id=X", date(2026, 6, 17)
                )

    def test_fetch_http_error_propagates(self):
        import requests as req_module

        scraper = EdupageScraper()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req_module.HTTPError("403")
        mock_resp.text = ""

        with patch("requests.get", return_value=mock_resp):
            with self.assertRaises(req_module.HTTPError):
                scraper.scrape(
                    "https://school.edupage.org/menu/mealsGuest?id=X", date(2026, 6, 17)
                )


if __name__ == "__main__":
    unittest.main()
