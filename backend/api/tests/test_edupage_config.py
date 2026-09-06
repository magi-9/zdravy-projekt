"""Testy per-prevádzka configu EduPage scrapingu (api.edupage)."""

import json
import unittest
from datetime import date

from api.edupage import (
    LetterRule,
    OlovrantMode,
    PayerRule,
    PrevadzkaConfig,
    apply_config,
    config_pre_url,
    subdomena_z_url,
)
from api.edupage.overrides.britishschool import (
    british_school_letter_hook,
    british_school_payer_hook,
)
from api.edupage.overrides.cmspezinok import cmspezinok_letter_hook
from api.edupage.overrides.cvernicka import cvernicka_letter_hook
from api.edupage.overrides.dobrodruzstvo import dobrodruzstvo_payer_hook
from api.edupage.overrides.fantasticka import (
    fantasticka_letter_hook,
    fantasticka_payer_hook,
    fantastickaskolka_letter_hook,
)
from api.edupage.overrides.felixkarloveska import felixkarloveska_letter_hook
from api.edupage.overrides.filipaneriho import filipaneriho_letter_hook
from api.edupage.overrides.ivanka import ivanka_letter_hook
from api.edupage.overrides.krasnanko import krasnanko_letter_hook
from api.edupage.overrides.libellus import libellus_letter_hook
from api.edupage.overrides.montessori import montessori_letter_hook
from api.edupage.overrides.rozmanita import rozmanita_letter_hook
from api.edupage.overrides.skolicka import skolicka_zs_payer_hook
from api.edupage.overrides.skolickams import (
    skolickams_letter_hook,
    skolickams_payer_hook,
)
from api.edupage.overrides.strecnianska import strecnianska_letter_hook
from api.edupage.overrides.zdravebrusko import (
    zdravebrusko_letter_hook,
    zdravebrusko_payer_hook,
)
from api.edupage_scraper import (
    EdupageScraper,
    ScrapeResult,
    build_prevadzka_matches,
    match_prevadzka,
    prevadzky_without_match,
)

TARGET = date(2026, 6, 17)


def _make_html(prehlad, nazov_menu, nastavenia, typy_platitelov=None):
    def _js(obj):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

    js_call = (
        f"strava_numeri({{"
        f"odkedy:'{TARGET.isoformat()}',"
        f"dokedy:'{TARGET.isoformat()}',"
        f"prehlad:{_js(prehlad)},"
        f'prehladNG:{{"prehlad":{{}}}},'
        f"typy_platitelov:{_js(typy_platitelov or [])},"
        f"nazovMenu:{_js(nazov_menu)},"
        f"nastavenia:{_js(nastavenia)},"
        f"odhlasovania2:[]"
        f"}});"
    )
    return f"<script>{js_call}</script>"


def _result(order_data) -> ScrapeResult:
    return ScrapeResult(date=TARGET, order_data=order_data)


def _cfg(mode, **kw) -> PrevadzkaConfig:
    return PrevadzkaConfig(subdomena="test", ucty=("Test",), olovrant_mode=mode, **kw)


LUNCH_DATA = {"Škôlka": {"menuCounts": {"A": 10}, "diets": {"NO MILK": 2}}}


class TestSubdomenaZUrl(unittest.TestCase):
    def test_extracts_subdomain(self):
        url = "https://krasnanko.edupage.org/menu/mealsGuest?id=x"
        self.assertEqual(subdomena_z_url(url), "krasnanko")

    def test_non_edupage_host_returns_none(self):
        self.assertIsNone(subdomena_z_url("https://example.com/menu"))

    def test_bare_edupage_domain_returns_none(self):
        self.assertIsNone(subdomena_z_url("https://edupage.org/menu"))


class TestConfigPreUrl(unittest.TestCase):
    def test_known_school(self):
        cfg = config_pre_url("https://skolkapramienok.edupage.org/menu/mealsGuest?id=x")
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.olovrant_mode, OlovrantMode.ODVODIT_Z_OBEDU)
        self.assertTrue(cfg.ranajky_z_obedu)

    def test_unknown_school_returns_none_not_raises(self):
        """Nová škola bez riadku v tabuľke sa musí odscrapovať generickým spôsobom."""
        self.assertIsNone(config_pre_url("https://novaskolka.edupage.org/menu?id=x"))

    def test_krasnanko_has_letter_hook(self):
        cfg = config_pre_url("https://krasnanko.edupage.org/menu/mealsGuest?id=x")
        self.assertIsNotNone(cfg.letter_hook)

    def test_skolickams_has_payer_hook(self):
        cfg = config_pre_url("https://skolickams.edupage.org/menu/mealsGuest?id=x")
        self.assertIsNotNone(cfg.payer_hook)

    def test_cvernicka_has_letter_hook(self):
        cfg = config_pre_url("https://skolkacvernicka.edupage.org/menu/mealsGuest?id=x")
        self.assertIsNotNone(cfg.letter_hook)

    def test_felixkarloveska_has_letter_hook(self):
        cfg = config_pre_url(
            "https://msfelixkarloveska.edupage.org/menu/mealsGuest?id=x"
        )
        self.assertIsNotNone(cfg.letter_hook)

    def test_zdravebrusko_has_letter_hook(self):
        cfg = config_pre_url("https://zdravebrusko.edupage.org/menu/mealsGuest?id=x")
        self.assertIsNotNone(cfg.letter_hook)

    def test_british_school_has_letter_and_payer_hook(self):
        cfg = config_pre_url("https://zdravyprojekt.edupage.org/menu/mealsGuest?id=x")
        self.assertIsNotNone(cfg)
        self.assertIsNotNone(cfg.letter_hook)
        self.assertIsNotNone(cfg.payer_hook)

    def test_british_school_has_dedicated_desiata_meal_hour_thresholds(self):
        """Živé dáta (2026-09-07): 4 okná/deň, desiata potrebuje vlastný
        meal_key "desiata" (NIE "snack" — ten je legacy alias pre Olovrant),
        nie zlúčenie do "breakfast" — viď
        `TestBuildJidMap.test_config_meal_hour_thresholds_splits_out_a_dedicated_snack_window`.
        """
        cfg = config_pre_url("https://zdravyprojekt.edupage.org/menu/mealsGuest?id=x")
        self.assertEqual(
            cfg.meal_hour_thresholds,
            ((9, "breakfast"), (11, "desiata"), (15, "lunch")),
        )

    def test_british_school_olovrant_mode_is_edupage(self):
        """Potvrdené na živom mealsGuest (2026-09-07) — olovrant okno reálne
        existuje (14:30-15:30, rovnaký MŠ-only payer set ako raňajky), takže
        `olovrant_mode` už nie je NEZNAMY."""
        cfg = config_pre_url("https://zdravyprojekt.edupage.org/menu/mealsGuest?id=x")
        self.assertEqual(cfg.olovrant_mode, OlovrantMode.EDUPAGE)

    def test_fantasticka_ms_and_zs_are_separate(self):
        ms = config_pre_url("https://fantastickaskolka.edupage.org/menu?id=x")
        zs = config_pre_url("https://szsfan.edupage.org/menu?id=x")
        self.assertNotEqual(ms.ucty, zs.ucty)

    def test_fantastickaskolka_has_its_own_letter_hook(self):
        cfg = config_pre_url("https://fantastickaskolka.edupage.org/menu?id=x")
        self.assertIsNotNone(cfg.letter_hook)

    def test_szsfan_has_letter_hook(self):
        cfg = config_pre_url("https://szsfan.edupage.org/menu/mealsGuest?id=x")
        self.assertIsNotNone(cfg.letter_hook)

    def test_zsivanka_has_letter_hook(self):
        cfg = config_pre_url("https://zsivanka.edupage.org/menu/mealsGuest?id=x")
        self.assertIsNotNone(cfg.letter_hook)

    def test_mslibellus_has_letter_hook(self):
        cfg = config_pre_url("https://mslibellus.edupage.org/menu/mealsGuest?id=x")
        self.assertIsNotNone(cfg.letter_hook)

    def test_montessorisk_has_letter_hook(self):
        cfg = config_pre_url("https://montessorisk.edupage.org/menu/mealsGuest?id=x")
        self.assertIsNotNone(cfg.letter_hook)
        self.assertTrue(cfg.ranajky_z_obedu)

    def test_cmspezinok_has_letter_hook(self):
        cfg = config_pre_url("https://cmspezinok.edupage.org/menu/mealsGuest?id=x")
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.olovrant_mode, OlovrantMode.EDUPAGE)
        self.assertIsNotNone(cfg.letter_hook)


class TestApplyConfigOlovrant(unittest.TestCase):
    def test_odvodit_z_obedu_copies_lunch(self):
        res = _result({"lunch": LUNCH_DATA})
        apply_config(res, _cfg(OlovrantMode.ODVODIT_Z_OBEDU))
        self.assertEqual(res.order_data["olovrant"], LUNCH_DATA)

    def test_odvodit_z_obedu_deep_copies(self):
        """Mutácia olovrantu nesmie tichým aliasom zmeniť obed."""
        res = _result({"lunch": LUNCH_DATA})
        apply_config(res, _cfg(OlovrantMode.ODVODIT_Z_OBEDU))
        res.order_data["olovrant"]["Škôlka"]["menuCounts"]["A"] = 999
        self.assertEqual(res.order_data["lunch"]["Škôlka"]["menuCounts"]["A"], 10)

    def test_odvodit_z_obedu_uses_each_prevadzka_own_lunch(self):
        first_lunch = {"Škôlka": {"menuCounts": {"A": 3}, "diets": {}}}
        second_lunch = {"Škôlka": {"menuCounts": {"A": 7}, "diets": {}}}
        res = ScrapeResult(
            date=TARGET,
            order_data={"lunch": LUNCH_DATA},
            order_data_by_prevadzka={
                "Prvá": {"lunch": first_lunch},
                "Druhá": {"lunch": second_lunch},
            },
        )

        apply_config(res, _cfg(OlovrantMode.ODVODIT_Z_OBEDU))

        self.assertEqual(res.order_data_by_prevadzka["Prvá"]["olovrant"], first_lunch)
        self.assertEqual(res.order_data_by_prevadzka["Druhá"]["olovrant"], second_lunch)
        self.assertNotEqual(
            res.order_data_by_prevadzka["Prvá"]["olovrant"],
            res.order_data_by_prevadzka["Druhá"]["olovrant"],
        )

    def test_odvodit_z_obedu_empty_day_stays_empty(self):
        """Zatvorená škola = prázdny deň, nie chyba — nedopočítavame nič."""
        res = _result({})
        apply_config(res, _cfg(OlovrantMode.ODVODIT_Z_OBEDU))
        self.assertNotIn("olovrant", res.order_data)
        self.assertEqual(res.warnings, [])

    def test_odvodit_z_obedu_warns_if_edupage_suddenly_has_olovrant(self):
        res = _result({"lunch": LUNCH_DATA, "olovrant": LUNCH_DATA})
        apply_config(res, _cfg(OlovrantMode.ODVODIT_Z_OBEDU))
        self.assertTrue(any("over config" in n for n in res.config_notes))
        self.assertEqual(res.order_data["olovrant"], LUNCH_DATA)
        self.assertEqual(res.warnings, [])

    def test_mimo_appky_drops_and_warns(self):
        res = _result({"lunch": LUNCH_DATA, "olovrant": LUNCH_DATA})
        apply_config(res, _cfg(OlovrantMode.MIMO_APPKY))
        self.assertNotIn("olovrant", res.order_data)
        self.assertTrue(res.config_notes)
        self.assertEqual(res.warnings, [])

    def test_mimo_appky_silent_when_absent(self):
        res = _result({"lunch": LUNCH_DATA})
        apply_config(res, _cfg(OlovrantMode.MIMO_APPKY))
        self.assertEqual(res.config_notes, [])

    def test_edupage_warns_when_olovrant_missing_but_lunch_present(self):
        res = _result({"lunch": LUNCH_DATA})
        apply_config(res, _cfg(OlovrantMode.EDUPAGE))
        self.assertTrue(res.config_notes)
        self.assertEqual(res.warnings, [])

    def test_edupage_silent_when_olovrant_present(self):
        res = _result({"lunch": LUNCH_DATA, "olovrant": LUNCH_DATA})
        apply_config(res, _cfg(OlovrantMode.EDUPAGE))
        self.assertEqual(res.config_notes, [])

    def test_olovrant_missing_ok_suppresses_the_note_for_named_prevadzka(self):
        """ZŠ Malokarpatská (zdravebrusko) reálne nikdy nemá olovrant/raňajky
        v tomto EduPage feede — starší žiaci si ich cez appku neobjednávajú,
        na rozdiel od MŠ na tom istom feede. Živý raw scrape (3.9.2026)
        potvrdzuje: žiadny payer s menom školy sa v blokoch raňajok/olovrantu
        vôbec nevyskytuje — nie je to config drift, je to štrukturálny fakt.
        `olovrant_missing_ok` musí notu pre TÚTO prevádzku umlčať, ale nie
        pre ostatné na tej istej connection (napr. Deutsche Schule, ktorá
        olovrant reálne má a mala by byť nahlásená, keby jej zrazu chýbal)."""
        res = ScrapeResult(
            date=TARGET,
            order_data={"lunch": LUNCH_DATA},
            order_data_by_prevadzka={
                "ZŠ Malokarpatská": {"lunch": LUNCH_DATA},
                "Deutsche schule": {"lunch": LUNCH_DATA},
            },
        )

        apply_config(
            res,
            _cfg(
                OlovrantMode.EDUPAGE,
                olovrant_missing_ok=frozenset({"ZŠ Malokarpatská"}),
            ),
        )

        self.assertFalse(
            any("ZŠ Malokarpatská" in n for n in res.config_notes),
            res.config_notes,
        )
        self.assertTrue(
            any("Deutsche schule" in n and "olovrant" in n for n in res.config_notes)
        )

    def test_neznamy_does_not_guess(self):
        """Ivanka: kým nemáme dáta, radšej warning než tichý odhad."""
        res = _result({"lunch": LUNCH_DATA})
        apply_config(res, _cfg(OlovrantMode.NEZNAMY))
        self.assertNotIn("olovrant", res.order_data)
        self.assertTrue(res.config_notes)
        self.assertEqual(
            res.warnings, [], "config drift nesmie vyzerať ako zlyhanie scrapu"
        )


class TestApplyConfigRanajky(unittest.TestCase):
    """`ranajky_z_obedu` — celodenná dochádzka, raňajky = obed (user 2.9.2026,
    Pramienok a Montessori Borínska MŠ)."""

    def test_off_by_default_does_not_add_breakfast(self):
        res = _result({"lunch": LUNCH_DATA})
        apply_config(res, _cfg(OlovrantMode.EDUPAGE))
        self.assertNotIn("breakfast", res.order_data)

    def test_copies_lunch_into_breakfast(self):
        res = _result({"lunch": LUNCH_DATA})
        apply_config(res, _cfg(OlovrantMode.EDUPAGE, ranajky_z_obedu=True))
        self.assertEqual(res.order_data["breakfast"], LUNCH_DATA)

    def test_deep_copies(self):
        res = _result({"lunch": LUNCH_DATA})
        apply_config(res, _cfg(OlovrantMode.EDUPAGE, ranajky_z_obedu=True))
        res.order_data["breakfast"]["Škôlka"]["menuCounts"]["A"] = 999
        self.assertEqual(res.order_data["lunch"]["Škôlka"]["menuCounts"]["A"], 10)

    def test_empty_day_stays_empty(self):
        res = _result({})
        apply_config(res, _cfg(OlovrantMode.EDUPAGE, ranajky_z_obedu=True))
        self.assertNotIn("breakfast", res.order_data)
        self.assertEqual(res.config_notes, [])

    def test_warns_if_edupage_suddenly_has_breakfast(self):
        res = _result({"lunch": LUNCH_DATA, "breakfast": LUNCH_DATA})
        apply_config(res, _cfg(OlovrantMode.EDUPAGE, ranajky_z_obedu=True))
        self.assertTrue(any("over config" in n for n in res.config_notes))
        self.assertEqual(res.order_data["breakfast"], LUNCH_DATA)
        self.assertEqual(res.warnings, [])

    def test_uses_each_prevadzka_own_lunch(self):
        first_lunch = {"Škôlka": {"menuCounts": {"A": 3}, "diets": {}}}
        second_lunch = {"Škôlka": {"menuCounts": {"A": 7}, "diets": {}}}
        res = ScrapeResult(
            date=TARGET,
            order_data={"lunch": LUNCH_DATA},
            order_data_by_prevadzka={
                "Prvá": {"lunch": first_lunch},
                "Druhá": {"lunch": second_lunch},
            },
        )

        apply_config(res, _cfg(OlovrantMode.EDUPAGE, ranajky_z_obedu=True))

        self.assertEqual(res.order_data_by_prevadzka["Prvá"]["breakfast"], first_lunch)
        self.assertEqual(
            res.order_data_by_prevadzka["Druhá"]["breakfast"], second_lunch
        )


class TestApplyConfigPerPrevadzkaDrift(unittest.TestCase):
    """Zdravé Brúško 2.9.2026: merged (celok-wide) pohľad drift skryje, ak čo i
    len jedna z viacerých prevádzok zdieľanej connection má olovrant/raňajky —
    per-prevádzka notes s labelom to musia odhaliť (user: "zle ich čítalo,
    treba preveriť")."""

    def test_merged_view_hides_missing_olovrant_for_one_of_several_prevadzky(self):
        res = ScrapeResult(
            date=TARGET,
            order_data={"lunch": LUNCH_DATA, "olovrant": LUNCH_DATA},
            order_data_by_prevadzka={
                "Deutsche schule": {"lunch": LUNCH_DATA, "olovrant": LUNCH_DATA},
                "MŠ Heyrovského 4": {"lunch": LUNCH_DATA},
            },
        )

        apply_config(res, _cfg(OlovrantMode.EDUPAGE))

        # Merged pohľad sám osebe nič nenahlási — olovrant tam je (z Deutsche
        # schule) — preto potrebujeme per-prevádzka notes s labelom.
        self.assertTrue(
            any("MŠ Heyrovského 4" in n and "olovrant" in n for n in res.config_notes)
        )
        self.assertFalse(any("Deutsche schule" in n for n in res.config_notes))


class TestKrasnankoLetterHook(unittest.TestCase):
    def _rule(self, skratka) -> LetterRule:
        return krasnanko_letter_hook("X", skratka, "")

    def test_klasik_is_child_portion(self):
        self.assertEqual(self._rule("K").portion, "Škôlka")
        self.assertEqual(self._rule("K").menu, "A")

    def test_kd_klasik_domov_is_child_portion(self):
        """`K-D` sa volá „Klasik domov", ale je to detská porcia."""
        self.assertEqual(self._rule("K-D").portion, "Škôlka")
        self.assertEqual(self._rule("K-D").menu, "A")

    def test_kz_employee_adult_is_adult_portion(self):
        self.assertEqual(self._rule("KZ").portion, "Dospelý (SŠ)")

    def test_nmz_employee_adult_keeps_diet(self):
        rule = self._rule("NMZ")
        self.assertEqual(rule.portion, "Dospelý (SŠ)")
        self.assertEqual(rule.diet, "NO MILK")

    def test_kzd_is_plain_klasik_child_portion_no_flag(self):
        # KZD = Klasik detská porcia, berieme ju tak; žiadny attention flag (user 7/13).
        rule = self._rule("KZD")
        self.assertEqual(rule.portion, "Škôlka")
        self.assertEqual(rule.menu, "A")
        self.assertIsNone(rule.flag)

    def test_nmzd_child_portion_diet_no_flag(self):
        rule = self._rule("NMZD")
        self.assertEqual(rule.portion, "Škôlka")
        self.assertEqual(rule.diet, "NO MILK")
        self.assertIsNone(rule.flag)

    def test_dia(self):
        self.assertEqual(self._rule("DIA").diet, "DIA")

    def test_dnm_is_now_dieta_no_milk_not_dospely(self):
        """Škola 3.9.2026 premenovala celú skratkovú schému na EduPage strane
        (živý guest dump: nazovMenu už posiela DK/DNM/DNG pre deti, ZK/ZNM/ZNG
        pre dospelých, PDK/PDNM/PDNG pre predškolákov, namiesto pôvodných
        K/NM/NG a KZ/NMZ) — 'DNM' teraz znamená 'Dieťa no milk' (D = Dieťa),
        NIE 'Dospelý' ako predtým (1.9.2026 vysvetlenie Stana Šulca už
        neplatí, kolidovalo by to s dnešným 'D' = dieťa a ticho by zamiešalo
        detské NO MILK do dospelej porcie). Nahlásené userom 3.9.2026 ('ZK
        dospelý - 1 je 2' — dospelá porcia bola nesprávne napočítaná)."""
        rule = self._rule("DNM")
        self.assertEqual(rule.portion, "Škôlka")
        self.assertEqual(rule.diet, "NO MILK")

    def test_dk_is_child_klasik(self):
        rule = self._rule("DK")
        self.assertEqual(rule.portion, "Škôlka")
        self.assertEqual(rule.menu, "A")

    def test_dng_is_child_no_gluten(self):
        rule = self._rule("DNG")
        self.assertEqual(rule.portion, "Škôlka")
        self.assertEqual(rule.diet, "NO GLUTEN")

    def test_zk_is_adult_klasik(self):
        """Nová skratka pre dospelého klasik (nahrádza pôvodné 'KZ')."""
        rule = self._rule("ZK")
        self.assertEqual(rule.portion, "Dospelý (SŠ)")
        self.assertEqual(rule.menu, "A")

    def test_znm_is_adult_no_milk(self):
        """Nová skratka pre dospelého no milk (nahrádza pôvodné 'NMZ')."""
        rule = self._rule("ZNM")
        self.assertEqual(rule.portion, "Dospelý (SŠ)")
        self.assertEqual(rule.diet, "NO MILK")

    def test_zng_is_adult_no_gluten(self):
        rule = self._rule("ZNG")
        self.assertEqual(rule.portion, "Dospelý (SŠ)")
        self.assertEqual(rule.diet, "NO GLUTEN")

    def test_pdk_is_predskolak_klasik(self):
        rule = self._rule("PDK")
        self.assertEqual(rule.portion, "Predškolák")
        self.assertEqual(rule.menu, "A")

    def test_pdng_is_predskolak_no_gluten(self):
        rule = self._rule("PDNG")
        self.assertEqual(rule.portion, "Predškolák")
        self.assertEqual(rule.diet, "NO GLUTEN")

    def test_z_half_k_is_child_portion_not_adult(self):
        """'Z1/2K' — rovnaká výnimka ako 'Z1/2NM': porcia MŠ, hoci obsahuje 'Z'."""
        rule = self._rule("Z1/2K")
        self.assertEqual(rule.portion, "Škôlka")
        self.assertEqual(rule.menu, "A")

    def test_pdnm_is_predskolak_no_milk(self):
        """'PD' = Predškolák."""
        rule = self._rule("PDNM")
        self.assertEqual(rule.portion, "Predškolák")
        self.assertEqual(rule.diet, "NO MILK")

    def test_z_half_nm_is_child_portion_not_adult(self):
        """'Z1/2' = Dospelý 1/2 (zamestnanec, ale porcia MŠ) — na rozdiel od
        KZ/NMZ toto NIE JE dospelá porcia, hoci obsahuje 'Z'."""
        rule = self._rule("Z1/2NM")
        self.assertEqual(rule.portion, "Škôlka")
        self.assertEqual(rule.diet, "NO MILK")

    def test_unknown_skratka_falls_through_to_engine(self):
        self.assertIsNone(self._rule("QQQ"))


class TestLetterHookInParse(unittest.TestCase):
    """Hook musí prebiť `porcia` kód payera — to je dôvod, prečo existuje."""

    NASTAVENIA = [
        {
            "nazov": "vydaj_normal",
            "hodnota": json.dumps({"2": {"vydaj_od": "11:00", "vydaj_do": "13:00"}}),
        }
    ]
    # Payer tvrdí porcia=0 (Škôlka), hoci skratka KZ znamená dospelého.
    TYPY = [{"hodnota": json.dumps({"18": {"nazov": "Klasik Z", "porcia": "0"}})}]
    NAZOV_MENU = {"E": {"skratka": "KZ", "nazov": "Klasik dospelý Z"}}
    PREHLAD = {
        "prehlad": {
            TARGET.isoformat(): {"2": {"E": {"typ_platitela": {"18": {"o": 4}}}}}
        }
    }

    def _parse(self, config):
        html = _make_html(self.PREHLAD, self.NAZOV_MENU, self.NASTAVENIA, self.TYPY)
        return EdupageScraper()._parse(html, TARGET, config=config)

    def test_without_hook_payer_porcia_wins(self):
        res = self._parse(config=None)
        self.assertIn("Škôlka", res.order_data["lunch"])

    def test_hook_portion_overrides_payer_porcia(self):
        cfg = _cfg(OlovrantMode.EDUPAGE, letter_hook=krasnanko_letter_hook)
        res = self._parse(config=cfg)
        lunch = res.order_data["lunch"]
        self.assertIn("Dospelý (SŠ)", lunch)
        self.assertNotIn("Škôlka", lunch)
        self.assertEqual(lunch["Dospelý (SŠ)"]["menuCounts"]["A"], 4)

    def test_flag_surfaces_in_attention(self):
        # `LetterRule.flag` je všeobecný mechanizmus; testujeme ho syntetickým hookom
        # (žiadne reálne Krásňanko pravidlo dnes flag nenesie).
        def flag_hook(letter, skratka, nazov):
            return LetterRule(portion="Škôlka", menu="A", flag="!")

        nazov_menu = {"G": {"skratka": "XY", "nazov": "Čokoľvek"}}
        prehlad = {
            "prehlad": {
                TARGET.isoformat(): {"2": {"G": {"typ_platitela": {"18": {"o": 3}}}}}
            }
        }
        html = _make_html(prehlad, nazov_menu, self.NASTAVENIA, self.TYPY)
        cfg = _cfg(OlovrantMode.EDUPAGE, letter_hook=flag_hook)
        res = EdupageScraper()._parse(html, TARGET, config=cfg)
        self.assertEqual(res.attention, ["G:XY!"])
        self.assertEqual(res.order_data["lunch"]["Škôlka"]["menuCounts"]["A"], 3)


class TestCvernickaLetterHook(unittest.TestCase):
    """#527: obe skratky sa predtým fuzzy-matchovali len na NO MILK/NO GLUTEN,
    hoci lepok sa v nich vôbec nevyskytuje (EduPage `nazov` to potvrdzuje)."""

    def _rule(self, skratka) -> LetterRule:
        return cvernicka_letter_hook("X", skratka, "")

    def test_nmncnj_full_combo(self):
        self.assertEqual(self._rule("nMnČnJ").diet, "NO MILK/NO KAKAO/NO JAHODA")

    def test_seven_way_combo(self):
        self.assertEqual(
            self._rule("nMnOnJnPnČnŠnZEL").diet,
            "NO MILK/NO ORECH/NO PARADAJKA/NO JAHODA/NO KAKAO/NO SKORICA/NO ZELER",
        )

    def test_horcica(self):
        # Bez tohto pravidla `resolve_menu_variant` skratku potichu absorbuje
        # do Menu A, lebo nazov obsahuje "Klasik" — žiadny unmapped/uncertain
        # flag, diéta zmizne úplne (nájdené 27.8.2026 v Hárok1).
        self.assertEqual(self._rule("AnHorčica").diet, "NO HORCICA")

    def test_unknown_skratka_falls_through_to_engine(self):
        self.assertIsNone(self._rule("nM"))


class TestFelixKarloveskaLetterHook(unittest.TestCase):
    """#527: 'NE bez O,A,S,S' sa fuzzy-matchovalo len na NO EGG — reálna
    tabuľka (Felix/IUVENTA) má tento riadok ako EpiPen-úroveň alergiu."""

    def _rule(self, skratka) -> LetterRule:
        return felixkarloveska_letter_hook("X", skratka, "")

    def test_epipen_combo(self):
        self.assertEqual(
            self._rule("NE bez O,A,S,S").diet,
            "NO EGG/NO ORECH/NO ARASIDY/NO SOJA/NO SEZAM",
        )

    def test_case_insensitive(self):
        self.assertEqual(
            self._rule("ne bez o,a,s,s").diet,
            "NO EGG/NO ORECH/NO ARASIDY/NO SOJA/NO SEZAM",
        )

    def test_nmno_confirmed_certain(self):
        """'NMNO'/'NoMilk no orech' fuzzy-matchovalo len na NO MILK, orech sa
        strácal — potvrdené na existujúcu diétu pk 121 (user 1.9.2026)."""
        self.assertEqual(self._rule("NMNO").diet, "NO MILK – NO ORECH")

    def test_plain_ne_falls_through_to_engine(self):
        self.assertIsNone(self._rule("NE"))


class TestZdravebruskoLetterHook(unittest.TestCase):
    """#527: 'dsbNMNE' sa fuzzy-matchovalo len na NO EGG (endswith('ne') beží
    skôr, než si engine všimne 'nm') — EduPage nazov='NoMilk/NoEgg' potvrdzuje
    plnú kombináciu."""

    def _rule(self, skratka) -> LetterRule:
        return zdravebrusko_letter_hook("X", skratka, "")

    def test_dsbnmne_full_combo(self):
        self.assertEqual(self._rule("dsbNMNE").diet, "NO MILK/NO EGG")

    def test_dsbnm_is_certain_no_milk(self):
        """Fuzzy engine už tipovalo správne (NO MILK), ale ako 'uncertain' —
        letter_hook to teraz potvrdzuje na isté (user 1.9.2026)."""
        self.assertEqual(self._rule("dsbNM").diet, "NO MILK")

    def test_dsbngnm_is_certain_milk_gluten_combo(self):
        self.assertEqual(self._rule("dsbNGNM").diet, "NO MILK – NO GLUTEN")

    def test_dsbno_is_certain_no_orech(self):
        self.assertEqual(self._rule("dsbNO").diet, "NO ORECH")

    def test_dsb_triple_combo_confirmed(self):
        """'dsbNNN SJ' bol uncertain fuzzy match (len NO SOJA) — potvrdené na
        plnú kombináciu (user 1.9.2026)."""
        self.assertEqual(self._rule("dsbNNN SJ").diet, "NONONO – NO SOJA")

    def test_heyrovskeho_gluten_confirmed(self):
        self.assertEqual(self._rule("mšHey. NG").diet, "NO GLUTEN")

    def test_malokarpatke_namestie_confirmed(self):
        self.assertEqual(self._rule("mšMal. NM").diet, "NO MILK")
        self.assertEqual(self._rule("mšMal. NG").diet, "NO GLUTEN")

    def test_zs_malokarpatska_gluten_confirmed(self):
        self.assertEqual(self._rule("zšlaNG").diet, "NO GLUTEN")

    def test_zs_malokarpatska_quad_combo_confirmed(self):
        """Posledné písmeno skratky (jahoda/jablko) bolo pôvodne neisté — user
        potvrdil jablko, nie jahodu (1.9.2026), flag na kontrolu už netreba."""
        rule = self._rule("zšlaNMnEnOnJ")
        self.assertEqual(rule.diet, "NO MILK – NO EGG – NO ORECH – NO JABLKO")
        self.assertIsNone(rule.flag)

    def test_zs_malokarpatska_milk_only_confirmed(self):
        """'zšlaNM' (len mlieko, bez ďalších obmedzení) bol uncertain fuzzy
        match — potvrdené na isté (user 2.9.2026)."""
        self.assertEqual(self._rule("zšlaNM").diet, "NO MILK")

    def test_ss_veterinarna_vege_is_own_menu_not_a_diet(self):
        """'sšvV' (SŠ Veterinárna Vege) bol pôvodne namapovaný ako diéta
        VEGGIE (user 2.9.2026) — user 3.9.2026 opravil: je to pre SŠV
        samostatný MENU výber (ako 'sšvA'/Klasik, 'sšvB'/Menu B), nie dietná
        úprava Klasiku. Diéta by sa v `_parse` vždy sčítala aj do
        menuCounts.A (bežne JE úpravou Klasiku) — pri SŠV to duplicitne
        napočítalo vege objednávky aj do A (obed ukazoval A:20 namiesto
        správnych 18)."""
        rule = self._rule("sšvV")
        self.assertEqual(rule.menu, "V")
        self.assertIsNone(rule.diet)

    def test_unknown_skratka_falls_through_to_engine(self):
        self.assertIsNone(self._rule("something else entirely"))


class TestZdravebruskoPayerHook(unittest.TestCase):
    """Raňajky/olovrant: MŠ Mal./Hey. zdieľajú písmeno dsbNMNE s Deutsche Schule
    — payer_hook musí vrátiť správnu prevádzku (force_match) aj vlastnú diétu,
    nie tú z cudzieho zdieľaného písmena (user 2.9.2026, live dáta)."""

    def test_malokarpatske_no_milk(self):
        rule = zdravebrusko_payer_hook("MŠ Mal. NoMilk")
        self.assertEqual(rule.match_name, "mšMal")
        self.assertEqual(rule.diet, "NO MILK")
        self.assertTrue(rule.force_match)

    def test_malokarpatske_no_gluten(self):
        rule = zdravebrusko_payer_hook("MŠ Mal. NoGluten")
        self.assertEqual(rule.match_name, "mšMal")
        self.assertEqual(rule.diet, "NO GLUTEN")

    def test_heyrovskeho_no_gluten(self):
        rule = zdravebrusko_payer_hook("MŠ Hey. NoGluten")
        self.assertEqual(rule.match_name, "mšHey")
        self.assertEqual(rule.diet, "NO GLUTEN")
        self.assertTrue(rule.force_match)

    def test_combo_is_no_milk_no_gluten(self):
        rule = zdravebrusko_payer_hook("MŠ Mal. NoMilk/NoGluten")
        self.assertEqual(rule.diet, "NO MILK/NO GLUTEN")

    def test_no_banan_combo_keeps_both_restrictions(self):
        """'MŠ Mal. NoMilk/NoBanán' (nový payer, 0 objednávok 3.9.2026, ale
        potenciálna alergia) — starý kód poznal len milk/gluten fragmenty,
        takže 'NoBanán' sa ticho stratilo a diéta vyšla len 'NO MILK' (rovnaký
        vzor ako predtým opravené NO MILK/NO EGG pre Naša škola poznania).
        Keďže `force_match=True` a diéta z hooku nie je None, `forced_diet`
        prebije aj zdieľané písmeno — banán sa preto MUSÍ zachovať už tu."""
        rule = zdravebrusko_payer_hook("MŠ Mal. NoMilk/NoBanán")
        self.assertEqual(rule.match_name, "mšMal")
        self.assertTrue(rule.force_match)
        self.assertEqual(rule.diet, "NO MILK/NO BANÁN")

    def test_no_banan_alone_is_recognised(self):
        rule = zdravebrusko_payer_hook("MŠ Hey. NoBanán")
        self.assertEqual(rule.diet, "NO BANÁN")

    def test_deutsche_schule_payer_untouched(self):
        self.assertIsNone(zdravebrusko_payer_hook("MŠ Klasik"))

    def test_unrelated_payer_untouched(self):
        self.assertIsNone(zdravebrusko_payer_hook("1.stupeň Lamač"))

    def test_ssv_dospely_flagged_pack_separately(self):
        """SŠV dospelí (zamestnanci) zdieľajú s "SŠV žiak" tú istú porciu
        "Dospelý (SŠ)" — porcia kód ich nevie rozlíšiť. Payer label je jediný
        spoľahlivý signál, appka ho preto vždy automaticky zabalí zvlášť
        (user 4.9.2026)."""
        rule = zdravebrusko_payer_hook("SŠV dospelý")
        self.assertTrue(rule.pack_separately)
        self.assertIsNone(rule.match_name)
        self.assertIsNone(rule.diet)
        self.assertIsNone(rule.portion)
        self.assertFalse(rule.force_match)

    def test_ssv_ziak_untouched(self):
        """Žiaci zostávajú v normálnej porcii bez packSeparately príznaku."""
        self.assertIsNone(zdravebrusko_payer_hook("SŠV žiak"))


class TestFantastickaLetterHook(unittest.TestCase):
    """#527: 'HITNMNGnSnKnFC' sa fuzzy-matchovalo len na NO MILK/NO GLUTEN —
    EduPage nazov="HITnomilk/noGlu/noSoja/noKuk/noRafcukor" potvrdzuje plnú
    6-násobnú kombináciu (nahlásené Stanom 31.8.2026)."""

    def _rule(self, skratka) -> LetterRule:
        return fantasticka_letter_hook("X", skratka, "")

    def test_six_way_combo(self):
        self.assertEqual(
            self._rule("HITNMNGnSnKnFC").diet,
            "NO MILK – NO GLUTEN – HISTAMIN – NO SOJA – NO CUKOR – NO KUKURICA",
        )

    def test_unknown_skratka_falls_through_to_engine(self):
        self.assertIsNone(self._rule("NM"))


class TestFantastickaPayerHook(unittest.TestCase):
    """Payer skupina '2.stupeň DIABETI' (typ_platitela 16) má v EduPage
    nastavení `porcia=1` napriek vlastnému názvu — potvrdené user 3.9.2026
    (appka priradila diabetika do ZŠ 1.stupeň namiesto 2.stupňa)."""

    def _rule(self, payer_name) -> PayerRule | None:
        return fantasticka_payer_hook(payer_name)

    def test_diabeti_payer_forced_to_2_stupen(self):
        self.assertEqual(self._rule("2.stupeň DIABETI").portion, "ZŠ 2.stupeň")

    def test_plain_2_stupen_untouched(self):
        # Normálne 2.stupňové skupiny majú porcia kód správne — netreba zásah.
        self.assertIsNone(self._rule("2.stupeň"))
        self.assertIsNone(self._rule("2.stupeň NoMilk"))

    def test_1_stupen_untouched(self):
        self.assertIsNone(self._rule("1.stupeň"))

    def test_unrelated_payer_untouched(self):
        self.assertIsNone(self._rule("dospelý klasik"))


class TestDobrodruzstvoPayerHook(unittest.TestCase):
    """4 z 5 "1. stupeň" payer skupín majú v EduPage nastavení `porcia=2`
    namiesto správnej `1` — appka väčšinu 1. stupňa počítala do ZŠ 2.stupeň
    (user 3.9.2026: 'spojilo 1. a 2. stupeň'). Diéta 'bezlak' (bez laktózy)
    tiež chýbala v generickom keyword mape (prázdna diéta)."""

    def _rule(self, payer_name) -> PayerRule | None:
        return dobrodruzstvo_payer_hook(payer_name)

    def test_1_stupen_variants_forced_to_1_stupen(self):
        for name in ("1.st.", "1.st. ŠD", "1.st. ŠD vege", "1. st. ŠD bezlak"):
            with self.subTest(name=name):
                self.assertEqual(self._rule(name).portion, "ZŠ 1.stupeň")

    def test_2_stupen_variants_forced_to_2_stupen(self):
        for name in ("2.st.", "2. st. ŠD", "2. st. bezlep", "2.st ŠD bezlak"):
            with self.subTest(name=name):
                self.assertEqual(self._rule(name).portion, "ZŠ 2.stupeň")

    def test_bezlak_resolves_to_no_milk(self):
        self.assertEqual(self._rule("1. st. ŠD bezlak").diet, "NO MILK")
        self.assertEqual(self._rule("2.st ŠD bezlak").diet, "NO MILK")

    def test_ms_and_dospely_untouched(self):
        self.assertIsNone(self._rule("MŠ klasik"))
        self.assertIsNone(self._rule("MŠ Vege"))
        self.assertIsNone(self._rule("Dospelý"))


class TestFantastickaSkolkaLetterHook(unittest.TestCase):
    """Samostatné EduPage pripojenie od Fantastickej Školy vyššie (iný
    subdomain, iný feed) — 'B' (riadok 'MŠ nM/nG') bol uncertain fuzzy match,
    potvrdené na isté (user 2.9.2026)."""

    def _rule(self, skratka) -> LetterRule:
        return fantastickaskolka_letter_hook("X", skratka, "")

    def test_b_no_milk_no_gluten_confirmed(self):
        self.assertEqual(self._rule("B").diet, "NO MILK/NO GLUTEN")

    def test_unknown_skratka_falls_through_to_engine(self):
        self.assertIsNone(self._rule("A"))


class TestIvankaLetterHook(unittest.TestCase):
    """#527: NGNF/NMNE/'MŠ NMNG bez ARAS' fuzzy-matchovali len na jedno
    obmedzenie z viacerých — EduPage nazov potvrdzuje plné kombinácie
    (nahlásené Stanom 31.8.2026)."""

    def _rule(self, skratka, nazov="") -> LetterRule:
        return ivanka_letter_hook("X", skratka, nazov)

    def test_ngnf_full_combo(self):
        self.assertEqual(self._rule("NGNF").diet, "NO GLUTEN – NO FISH")

    def test_nmne_full_combo(self):
        self.assertEqual(self._rule("NMNE").diet, "NO MILK/NO EGG")

    def test_ms_nmng_bez_aras_full_combo(self):
        self.assertEqual(
            self._rule("MŠ NMNG bez ARAS").diet, "NO MILK – NO GLUTEN – NO ARASIDY"
        )

    def test_ng_olo_confirmed_certain(self):
        """Bol uncertain fuzzy match (NO GLUTEN) — potvrdené na isté
        (user 1.9.2026)."""
        self.assertEqual(self._rule("Ng+Olo").diet, "NO GLUTEN")

    def test_unknown_skratka_falls_through_to_engine(self):
        self.assertIsNone(self._rule("NG"))

    def test_nmngnorech_with_orech_in_nazov_is_full_combo(self):
        """Letter N: skratka 'NMNGnORECH', nazov 'NoMilk/NoGluten/NoOrech' —
        potvrdené na existujúcu diétu pk 132 (user 1.9.2026)."""
        self.assertEqual(
            self._rule("NMNGnORECH", "NoMilk/NoGluten/NoOrech").diet,
            "NO MILK – NO GLUTEN – NO ORECH",
        )

    def test_nmngnorech_without_orech_in_nazov_falls_through(self):
        """Rovnaká skratka sa na tejto škole recykluje aj pre letter A, kde
        nazov orech vôbec nespomína ('NoMilk/NoGluten') — nesmie dostať plnú
        trojkombináciu, necháva sa na engine (fuzzy NO MILK/NO GLUTEN)."""
        self.assertIsNone(self._rule("NMNGnORECH", "NoMilk/NoGluten"))


class TestLibellusLetterHook(unittest.TestCase):
    """#527: NENO/NMNE fuzzy-matchovali len na jedno obmedzenie z dvoch —
    EduPage nazov potvrdzuje plné kombinácie (nahlásené Stanom 31.8.2026)."""

    def _rule(self, skratka) -> LetterRule:
        return libellus_letter_hook("X", skratka, "")

    def test_neno_full_combo(self):
        self.assertEqual(self._rule("NENO").diet, "NO EGG – NO ORECH")

    def test_nmne_full_combo(self):
        self.assertEqual(self._rule("NMNE").diet, "NO MILK/NO EGG")

    def test_neno_par_mak_full_combo(self):
        """'NENOnPARnMAK' bol uncertain fuzzy match (len NO EGG) — potvrdené
        na plnú 4-kombináciu (user 1.9.2026)."""
        self.assertEqual(
            self._rule("NENOnPARnMAK").diet,
            "NO EGG – NO PARADAJKA – NO ORECH – NO MAK",
        )

    def test_unknown_skratka_falls_through_to_engine(self):
        self.assertIsNone(self._rule("NE"))

    def test_sa_stromcek_skipped(self):
        """`sA` (nazov "Stomček Klasik") patrí Stromčeku, nie Libellusu — obe
        zdieľajú jeden EduPage feed, ale Stromček objednáva cez appku
        (`zdroj_objednavok=app`). Bez skip by substring "klasik" v nazve
        skratku tíško zlúčil do Libellusovho vlastného Klasik/A počtu
        (nahlásené 3.9.2026, živý porovnávací scrape: Škôlka A o 4 vyššie
        než uložená objednávka na obede aj raňajkách)."""
        self.assertTrue(self._rule("sA").skip)


class TestMontessoriLetterHook(unittest.TestCase):
    """#527: 'Iná..NmNgNe' sa fuzzy-matchovalo len na NO MILK/NO GLUTEN —
    EduPage nazov="Iná NmNgNe..." potvrdzuje plnú kombináciu (nahlásené
    Stanom 31.8.2026)."""

    def _rule(self, skratka) -> LetterRule:
        return montessori_letter_hook("X", skratka, "")

    def test_full_combo(self):
        self.assertEqual(self._rule("Iná..NmNgNe").diet, "NO MILK – NO GLUTEN – NO EGG")

    def test_full_combo_bounding_dots_variant(self):
        """Škola posiela aj tvar '.Iná NmNgNe.' (bodky na okrajoch, medzera
        namiesto vnútornej bodky) — nahlásené 1.9.2026, kľúč založený len na
        'Iná..NmNgNe' ho nechytil a E sa tíško zlúčilo s D pod NO MILK/NO
        GLUTEN bez vajec."""
        self.assertEqual(
            self._rule(".Iná NmNgNe.").diet, "NO MILK – NO GLUTEN – NO EGG"
        )

    def test_nmng_no_egg_confirmed_certain(self):
        """'Iná NmNg' (bez vajec, na rozdiel od 'Iná..NmNgNe' vyššie) bol
        uncertain fuzzy match (NO MILK/NO GLUTEN) — letter_hook to potvrdzuje
        na isté (user 2.9.2026)."""
        self.assertEqual(self._rule("Iná NmNg").diet, "NO MILK/NO GLUTEN")

    def test_unknown_skratka_falls_through_to_engine(self):
        self.assertIsNone(self._rule("Iná ZZZ"))

    def test_non_ina_letters_are_skipped(self):
        """User 2.9.2026: appka má z EduPage rátať VÝHRADNE 'Iná' skupinu —
        bežné MŠ/ZŠ menu aj zamestnanecké porcie sa majú ignorovať celkom."""
        for skratka in ("MŠ", "ZŠ", "ZŠ 1.", "ZŠ FK 2.", "ZŠ zam.", "FK zam.", ".."):
            rule = self._rule(skratka)
            self.assertTrue(rule.skip, msg=skratka)

    def test_ina_group_is_not_skipped(self):
        """'Iná' (A) aj 'Iná NmNo' (D) ostávajú v hre — len ostatné písmená
        sa preskakujú."""
        for skratka in ("Iná", "Iná NmNo"):
            rule = self._rule(skratka)
            self.assertIsNone(rule, msg=skratka)  # necháva sa na engine


class TestCmsPezinokLetterHook(unittest.TestCase):
    """'H'/'Hlavná budova' je administratívna skupina, nie diéta HISTAMIN —
    bez tohto hooku by exaktný `_SKRATKA_MAP['H']` ju tíško zaradil ako diétu
    (user 2.9.2026: má sa úplne preskočiť)."""

    def _rule(self, skratka) -> LetterRule | None:
        return cmspezinok_letter_hook("X", skratka, "Hlavná budova")

    def test_h_is_skipped(self):
        rule = self._rule("H")
        self.assertIsNotNone(rule)
        self.assertTrue(rule.skip)

    def test_other_letters_fall_through_to_engine(self):
        self.assertIsNone(self._rule("NG"))


class TestFilipanerihoLetterHook(unittest.TestCase):
    """Uncertain fuzzy matche potvrdené na isté diéty (user 1.9.2026)."""

    def _rule(self, skratka) -> LetterRule:
        return filipaneriho_letter_hook("X", skratka, "")

    def test_med_mak_orech_uses_existing_comma_diet(self):
        # Existujúca diéta pk 56 (čiarkový formát) - nie novo založená.
        self.assertEqual(self._rule("No med,mak,orechy").diet, "NO MED, MAK, ORECH")

    def test_no_zemiak(self):
        self.assertEqual(self._rule("No zemiak").diet, "NO ZEMIAK")

    def test_no_orech(self):
        self.assertEqual(self._rule("No orech").diet, "NO ORECH")

    def test_ng_hrib_confirmed_certain(self):
        """'NG hríb'/'NoGlutenNoHríb' bolo uncertain fuzzy match (len NO
        GLUTEN), hríb sa strácal — potvrdené na existujúcu diétu pk 58
        (user 1.9.2026)."""
        self.assertEqual(self._rule("NG hríb").diet, "NO GLUTEN, HRÍBY")

    def test_nnno_confirmed_certain(self):
        """'NNNO'/'NoNoNo orech' — rovnaký vzor ako Rozmanitá, orech sa
        strácal (0 detí v čase nálezu, doplnené preventívne, user 1.9.2026)."""
        self.assertEqual(self._rule("NNNO").diet, "NONONO, NO ORECH")

    def test_unknown_skratka_falls_through_to_engine(self):
        self.assertIsNone(self._rule("niečo iné"))


class TestRozmanitaLetterHook(unittest.TestCase):
    def _rule(self, skratka) -> LetterRule:
        return rozmanita_letter_hook("X", skratka, "")

    def test_nomo_confirmed_certain(self):
        """Bol uncertain fuzzy match (len NO MILK) — potvrdené na NO MILK –
        NO ORECH (user 1.9.2026)."""
        self.assertEqual(self._rule("NoMO").diet, "NO MILK – NO ORECH")

    def test_nnno_confirmed_certain(self):
        """'NNNO'/'NoNoNo bezO' fuzzy-matchovalo len na NONONO, orech sa
        strácal — potvrdené na existujúcu diétu pk 67 (user 1.9.2026)."""
        self.assertEqual(self._rule("NNNO").diet, "NONONO, NO ORECH")

    def test_unknown_skratka_falls_through_to_engine(self):
        self.assertIsNone(self._rule("niečo iné"))


class TestStrecnianskaLetterHook(unittest.TestCase):
    def _rule(self, skratka) -> LetterRule:
        return strecnianska_letter_hook("X", skratka, "")

    def test_ngns_confirmed_certain(self):
        """Bol uncertain fuzzy match (len NO GLUTEN) — potvrdené na NO GLUTEN
        – NO SOJA (user 1.9.2026)."""
        self.assertEqual(self._rule("nGnS").diet, "NO GLUTEN – NO SOJA")

    def test_unknown_skratka_falls_through_to_engine(self):
        self.assertIsNone(self._rule("niečo iné"))


class TestFixedLetterHooksInParse(unittest.TestCase):
    """Integračný test: letter_hook beží pred fuzzy engine, takže tieto
    skratky teraz idú priamo na plný názov a NEobjavia sa v `uncertain_letters`
    (na rozdiel od fuzzy matchov, letter_hook je deklarovaná istota, nie odhad)."""

    NASTAVENIA = [
        {
            "nazov": "vydaj_normal",
            "hodnota": json.dumps({"2": {"vydaj_od": "11:00", "vydaj_do": "13:00"}}),
        }
    ]
    TYPY = [{"hodnota": json.dumps({"18": {"nazov": "Klasik", "porcia": "0"}})}]

    def _parse(self, skratka, config):
        nazov_menu = {"E": {"skratka": skratka, "nazov": skratka}}
        prehlad = {
            "prehlad": {
                TARGET.isoformat(): {"2": {"E": {"typ_platitela": {"18": {"o": 1}}}}}
            }
        }
        html = _make_html(prehlad, nazov_menu, self.NASTAVENIA, self.TYPY)
        return EdupageScraper()._parse(html, TARGET, config=config)

    def test_cvernicka_skratka_resolves_and_is_not_uncertain(self):
        cfg = _cfg(OlovrantMode.EDUPAGE, letter_hook=cvernicka_letter_hook)
        res = self._parse("nMnČnJ", cfg)
        self.assertEqual(
            res.order_data["lunch"]["Škôlka"]["diets"],
            {"NO MILK/NO KAKAO/NO JAHODA": 1},
        )
        self.assertEqual(res.uncertain_letters, [])
        self.assertEqual(res.unmapped_letters, [])

    def test_cvernicka_horcica_resolves_as_diet_not_menu_a(self):
        cfg = _cfg(OlovrantMode.EDUPAGE, letter_hook=cvernicka_letter_hook)
        res = self._parse("AnHorčica", cfg)
        self.assertEqual(res.order_data["lunch"]["Škôlka"]["diets"], {"NO HORCICA": 1})
        self.assertEqual(res.uncertain_letters, [])
        self.assertEqual(res.unmapped_letters, [])

    def test_felixkarloveska_skratka_resolves_and_is_not_uncertain(self):
        cfg = _cfg(OlovrantMode.EDUPAGE, letter_hook=felixkarloveska_letter_hook)
        res = self._parse("NE bez O,A,S,S", cfg)
        self.assertEqual(
            res.order_data["lunch"]["Škôlka"]["diets"],
            {"NO EGG/NO ORECH/NO ARASIDY/NO SOJA/NO SEZAM": 1},
        )
        self.assertEqual(res.uncertain_letters, [])
        self.assertEqual(res.unmapped_letters, [])

    def test_zdravebrusko_skratka_resolves_and_is_not_uncertain(self):
        cfg = _cfg(OlovrantMode.EDUPAGE, letter_hook=zdravebrusko_letter_hook)
        res = self._parse("dsbNMNE", cfg)
        self.assertEqual(
            res.order_data["lunch"]["Škôlka"]["diets"], {"NO MILK/NO EGG": 1}
        )
        self.assertEqual(res.uncertain_letters, [])
        self.assertEqual(res.unmapped_letters, [])

    def test_fantasticka_skratka_resolves_and_is_not_uncertain(self):
        cfg = _cfg(OlovrantMode.EDUPAGE, letter_hook=fantasticka_letter_hook)
        res = self._parse("HITNMNGnSnKnFC", cfg)
        self.assertEqual(
            res.order_data["lunch"]["Škôlka"]["diets"],
            {"NO MILK – NO GLUTEN – HISTAMIN – NO SOJA – NO CUKOR – NO KUKURICA": 1},
        )
        self.assertEqual(res.uncertain_letters, [])
        self.assertEqual(res.unmapped_letters, [])

    def test_ivanka_skratka_resolves_and_is_not_uncertain(self):
        cfg = _cfg(OlovrantMode.EDUPAGE, letter_hook=ivanka_letter_hook)
        res = self._parse("MŠ NMNG bez ARAS", cfg)
        self.assertEqual(
            res.order_data["lunch"]["Škôlka"]["diets"],
            {"NO MILK – NO GLUTEN – NO ARASIDY": 1},
        )
        self.assertEqual(res.uncertain_letters, [])
        self.assertEqual(res.unmapped_letters, [])

    def test_libellus_skratka_resolves_and_is_not_uncertain(self):
        cfg = _cfg(OlovrantMode.EDUPAGE, letter_hook=libellus_letter_hook)
        res = self._parse("NENO", cfg)
        self.assertEqual(
            res.order_data["lunch"]["Škôlka"]["diets"], {"NO EGG – NO ORECH": 1}
        )
        self.assertEqual(res.uncertain_letters, [])
        self.assertEqual(res.unmapped_letters, [])

    def test_montessori_skratka_resolves_and_is_not_uncertain(self):
        cfg = _cfg(OlovrantMode.EDUPAGE, letter_hook=montessori_letter_hook)
        res = self._parse("Iná..NmNgNe", cfg)
        self.assertEqual(
            res.order_data["lunch"]["Škôlka"]["diets"],
            {"NO MILK – NO GLUTEN – NO EGG": 1},
        )
        self.assertEqual(res.uncertain_letters, [])
        self.assertEqual(res.unmapped_letters, [])

    def test_montessori_zs_bezna_is_skipped_entirely(self):
        """User 2.9.2026: appka počíta z Montessori EduPage výhradne 'Iná' —
        bežné 'ZŠ' menu sa má úplne vynechať, nie počítať ako menu A."""
        cfg = _cfg(OlovrantMode.EDUPAGE, letter_hook=montessori_letter_hook)
        res = self._parse("ZŠ", cfg)
        self.assertEqual(res.order_data, {})
        self.assertEqual(res.skipped_letters, ["E:ZŠ"])
        self.assertEqual(res.uncertain_letters, [])
        self.assertEqual(res.unmapped_letters, [])


class TestBritishSchoolHooks(unittest.TestCase):
    """#527: skratky s koncovým '+' zdieľajú viaceré deti s navzájom
    odlišnými kombináciami — letter_hook necháva diétu na payer_hook."""

    def test_letter_hook_suppresses_diet_for_plus_skratky(self):
        rule = british_school_letter_hook("H", "nM+", "noMilk+")
        self.assertIsNotNone(rule)
        self.assertIsNone(rule.diet)
        self.assertEqual(rule.menu, "A")

    def test_letter_hook_falls_through_for_plain_skratky(self):
        self.assertIsNone(british_school_letter_hook("G", "nM", "noMilk"))

    def test_payer_hook_known_combinations(self):
        cases = [
            ("1.st. noMushroom", "NO HUBY"),
            ("1.st. noMilk+reflux", "NO MILK/REFLUX"),
            ("MŠ noMilk+reflux", "NO MILK/REFLUX"),
            ("Učiteľ noMilk/VEGE", "NO MILK/VEGGIE"),
            ("1.st. noNuts/noFish", "NO ORECH/NO FISH"),
            ("1.st. noNuts/noKiwi", "NO ORECH/NO KIWI"),
            ("2.st. noNuts/noAPP/noStr", "NO ORECH/NO JABLKO/NO JAHODA"),
            ("3.st. noNuts/sezam", "NO ORECH/NO SEZAM"),
            ("MŠ nonono+pork+berr", "NONONO/NO BRAVCOVINA/NO BOBULE"),
            ("MŠ nonononANAnLEG HIT", "NONONO/NO ANANAS/NO STRUKOVINY/HISTAMIN"),
        ]
        for payer_name, expected in cases:
            with self.subTest(payer_name=payer_name):
                rule = british_school_payer_hook(payer_name)
                self.assertIsNotNone(rule)
                self.assertEqual(rule.diet, expected)

    def test_payer_hook_unknown_falls_through_to_engine(self):
        self.assertIsNone(british_school_payer_hook("2.st. noNuts/noBanana"))

    def test_letter_hook_recognizes_vege1_as_own_menu_variant(self):
        """VEGE1 je vlastné menu, nie diéta VEGGIE — bez tohto pravidla by
        substring "vege" v `_has_diet_signal` skratku tíško vyhodnotil ako
        diétu VEGGIE (rovnaký fragment ako plain "Vege"), hoci ide o úplne
        iné menu (British škola, 4.9.2026)."""
        rule = british_school_letter_hook("E", "VEGE1", "Vege 1")
        self.assertIsNotNone(rule)
        self.assertEqual(rule.menu, "VEGE1")
        self.assertIsNone(rule.diet)

    def test_letter_hook_plain_vege_still_falls_through_to_diet_engine(self):
        """Plain "Vege"/"VEGGIE" ostáva diéta — len VEGE1 je nové menu."""
        self.assertIsNone(british_school_letter_hook("V", "Vege", "Vege"))


class TestBritishSchoolHooksInParse(unittest.TestCase):
    """Rovnaká skratka `nN+`, 4 rôzne deti (payer) → 4 rôzne diéty naraz —
    presne dôvod, prečo tu letter_hook sám nestačí."""

    NASTAVENIA = [
        {
            "nazov": "vydaj_normal",
            "hodnota": json.dumps({"2": {"vydaj_od": "11:00", "vydaj_do": "13:00"}}),
        }
    ]

    def _cfg(self):
        return _cfg(
            OlovrantMode.NEZNAMY,
            letter_hook=british_school_letter_hook,
            payer_hook=british_school_payer_hook,
        )

    def test_same_letter_different_payers_resolve_to_different_diets(self):
        nazov_menu = {"N": {"skratka": "nN+", "nazov": "noNuts+"}}
        typy = [
            {
                "hodnota": json.dumps(
                    {
                        "72": {"nazov": "1.st. noNuts/noKiwi", "porcia": "0"},
                        "73": {"nazov": "1.st. noNuts/noFish", "porcia": "0"},
                    }
                )
            }
        ]
        prehlad = {
            "prehlad": {
                TARGET.isoformat(): {
                    "2": {
                        "N": {
                            "typ_platitela": {
                                "72": {"o": 1},
                                "73": {"o": 1},
                            }
                        }
                    }
                }
            }
        }
        html = _make_html(prehlad, nazov_menu, self.NASTAVENIA, typy)
        res = EdupageScraper()._parse(html, TARGET, config=self._cfg())
        diets = res.order_data["lunch"]["Škôlka"]["diets"]
        self.assertEqual(diets.get("NO ORECH/NO KIWI"), 1)
        self.assertEqual(diets.get("NO ORECH/NO FISH"), 1)
        self.assertEqual(res.uncertain_letters, [])
        self.assertEqual(res.unmapped_letters, [])

    def test_unknown_payer_on_plus_letter_keeps_the_count(self):
        # Payer_hook nepozná kombináciu → diet_name aj payer_diet ostanú None,
        # takže sa diéta nepriradí, ale PORCIA sa nestratí (padne pod Menu A) —
        # bezpečnejšie ako appke spadnúť alebo si niečo vymyslieť.
        nazov_menu = {"N": {"skratka": "nN+", "nazov": "noNuts+"}}
        typy = [
            {
                "hodnota": json.dumps(
                    {"99": {"nazov": "4.st. noNuts/noBanana", "porcia": "0"}}
                )
            }
        ]
        prehlad = {
            "prehlad": {
                TARGET.isoformat(): {"2": {"N": {"typ_platitela": {"99": {"o": 1}}}}}
            }
        }
        html = _make_html(prehlad, nazov_menu, self.NASTAVENIA, typy)
        res = EdupageScraper()._parse(html, TARGET, config=self._cfg())
        self.assertEqual(res.order_data["lunch"]["Škôlka"]["menuCounts"]["A"], 1)


class TestSkolickamsPayerHook(unittest.TestCase):
    """Prefix B/BM = dodávateľ (Bruško/BruškoMilk), nie výdajňa — strip + BM→NO MILK."""

    def test_b_prefix_stripped_no_diet(self):
        rule = skolickams_payer_hook("B - Les")
        self.assertEqual(rule.match_name, "Les")
        self.assertIsNone(rule.diet)

    def test_bm_prefix_is_no_milk(self):
        rule = skolickams_payer_hook("BM - Lúka sd")
        self.assertEqual(rule.match_name, "Lúka sd")
        self.assertEqual(rule.diet, "NO MILK")

    def test_en_dash_and_spacing_tolerated(self):
        rule = skolickams_payer_hook("B–Les")
        self.assertEqual(rule.match_name, "Les")

    def test_case_insensitive_supplier_token(self):
        rule = skolickams_payer_hook("bm - Les")
        self.assertEqual(rule.diet, "NO MILK")

    def test_host_is_routed_to_luka(self):
        rule = skolickams_payer_hook("Hosť")
        self.assertEqual(rule.match_name, "Lúka")
        self.assertIsNone(rule.diet)

    def test_host_matched_ascii_folded(self):
        # diakritika/veľkosť nesmie rozhodnúť: "HOSŤ" / "host" tiež → Lúka
        for variant in ("HOSŤ", "host", " Hosť "):
            self.assertEqual(skolickams_payer_hook(variant).match_name, "Lúka")

    def test_nm_prefix_is_also_no_milk(self):
        """Škola premenovala dodávateľský prefix `BM`→`nM` (živý guest dump
        3.9.2026: typ_platitela 5/6/10/12 = "nM - Lúka sd"/"nM - Les"/
        "nM - Lúka učiteľ"/"nM - Les sd") — starý `BM`-only regex tento
        payer vôbec nerozpoznal, takže NO MILK objednávka (raňajky, obed aj
        olovrant, každý deň rovnaký 1 kus) sa ticho stratila (user 3.9.2026:
        "Lúka na raňajky nenačítalo NM z Edupage")."""
        rule = skolickams_payer_hook("nM - Lúka učiteľ")
        self.assertEqual(rule.match_name, "Lúka učiteľ")
        self.assertEqual(rule.diet, "NO MILK")

    def test_nm_prefix_case_insensitive(self):
        rule = skolickams_payer_hook("NM - Les")
        self.assertEqual(rule.match_name, "Les")
        self.assertEqual(rule.diet, "NO MILK")

    def test_label_without_supplier_prefix_falls_through(self):
        self.assertIsNone(skolickams_payer_hook("učiteľ Lúka"))

    def test_bare_b_word_not_treated_as_prefix(self):
        # bez oddeľovača "-" to nie je dodávateľský prefix
        self.assertIsNone(skolickams_payer_hook("Bratislava"))

    def test_speci_luka_gets_full_diet_and_child_portion(self):
        """'ŠPECI - Lúka' (payer type 13, live 2.9.2026) — nahlásené rodičom
        a potvrdené p. Kohútom 1.9.2026. Payer porcia=3 by inak dala inú
        porciu než ostatní v triede — hook ju pribíja na detskú."""
        rule = skolickams_payer_hook("ŠPECI - Lúka")
        self.assertEqual(rule.match_name, "Lúka")
        self.assertEqual(
            rule.diet,
            "NO GLUTEN – NO ORECH – NO STRUKOVINY – NO PARADAJKA – NO PAPRIKA – "
            "NO POHANKA – NO SOJA – NO QUINOA",
        )
        self.assertEqual(rule.portion, "Škôlka")

    def test_speci_ascii_s_tolerated(self):
        # EduPage môže poslať aj bez mäkčeňa ("SPECI").
        rule = skolickams_payer_hook("SPECI - Lúka")
        self.assertEqual(rule.match_name, "Lúka")
        self.assertIsNotNone(rule.diet)


class TestSkolickaZsPayerHook(unittest.TestCase):
    """Školička ZŠ: 'X.stupeň - variant' — variant B/N+M/G → diéta, 'H' → Histamín."""

    def test_klasik_has_no_diet(self):
        self.assertIsNone(skolicka_zs_payer_hook("1.stupeň - klasik"))

    def test_bm_is_no_milk(self):
        rule = skolicka_zs_payer_hook("1.stupeň - BM")
        self.assertEqual(rule.diet, "NO MILK")

    def test_nm_is_also_no_milk(self):
        """'N' aj 'B' znamenajú "no"/"bez" — prvé písmeno sa ignoruje (user 2.9.2026)."""
        rule = skolicka_zs_payer_hook("2.stupeň - NM")
        self.assertEqual(rule.diet, "NO MILK")

    def test_bg_is_no_gluten(self):
        rule = skolicka_zs_payer_hook("1.stupeň - BG")
        self.assertEqual(rule.diet, "NO GLUTEN")

    def test_comma_combo_is_no_milk_no_gluten(self):
        rule = skolicka_zs_payer_hook("1.stupeň - BM,BG")
        self.assertEqual(rule.diet, "NO MILK/NO GLUTEN")

    def test_concatenated_combo_is_no_milk_no_gluten(self):
        rule = skolicka_zs_payer_hook("2.stupeň - BMBG")
        self.assertEqual(rule.diet, "NO MILK/NO GLUTEN")

    def test_mixed_prefix_combo_is_no_milk_no_gluten(self):
        rule = skolicka_zs_payer_hook("2.stupeň - nMnG")
        self.assertEqual(rule.diet, "NO MILK/NO GLUTEN")

    def test_bare_h_is_histamin(self):
        rule = skolicka_zs_payer_hook("učiteľ - H")
        self.assertEqual(rule.diet, "HISTAMIN")

    def test_full_word_vege_falls_through_to_generic(self):
        # "vege"/"histamín" celým slovom necháme na generický engine
        self.assertIsNone(skolicka_zs_payer_hook("1.stupeň - vege"))

    def test_full_word_histamin_falls_through_to_generic(self):
        self.assertIsNone(skolicka_zs_payer_hook("2.stupeň - histamín"))

    def test_match_name_left_untouched(self):
        """Hook rieši len diétu — prevádzku priraďuje `edupage_match` prefix."""
        rule = skolicka_zs_payer_hook("1.stupeň - BM")
        self.assertIsNone(rule.match_name)


class TestSkolickamsLetterHook(unittest.TestCase):
    """Reálny guest dump (1.9.2026): `ŠPECI` chodí aj ako menu písmeno (skratka
    `ŠPECI`, nazov "noGLUT ORECH STRUK PARAD PAPRIKA POH SOJA QUINOA"), nie len
    ako payer label — bez tohto hooku by engine fuzzy-matchol len na NO ORECH."""

    def test_speci_letter_gets_full_diet(self):
        rule = skolickams_letter_hook(
            "D", "ŠPECI", "noGLUT ORECH STRUK PARAD PAPRIKA POH SOJA QUINOA"
        )
        self.assertEqual(
            rule.diet,
            "NO GLUTEN – NO ORECH – NO STRUKOVINY – NO PARADAJKA – NO PAPRIKA – "
            "NO POHANKA – NO SOJA – NO QUINOA",
        )

    def test_speci_letter_ascii_s_tolerated(self):
        rule = skolickams_letter_hook("D", "SPECI", "cokolvek")
        self.assertIsNotNone(rule.diet)

    def test_other_letters_fall_through(self):
        self.assertIsNone(skolickams_letter_hook("A", "B", "Bruško klasik"))


class TestPayerHookInParse(unittest.TestCase):
    """payer_hook strip prefixu umožní match na čistý `Les`/`Lúka` a odvodí NO MILK."""

    NASTAVENIA = [
        {
            "nazov": "vydaj_normal",
            "hodnota": json.dumps({"2": {"vydaj_od": "11:00", "vydaj_do": "13:00"}}),
        }
    ]
    TYPY = [
        {
            "hodnota": json.dumps(
                {
                    "1": {"nazov": "B - Les", "porcia": "0"},
                    "2": {"nazov": "BM - Lúka sd", "porcia": "0"},
                }
            )
        }
    ]
    NAZOV_MENU = {"A": {"skratka": "A", "nazov": "klasik A"}}

    def _parse(self, matches, config):
        prehlad = {
            "prehlad": {
                TARGET.isoformat(): {
                    "2": {"A": {"typ_platitela": {"1": {"o": 6}, "2": {"o": 4}}}}
                }
            }
        }
        html = _make_html(prehlad, self.NAZOV_MENU, self.NASTAVENIA, self.TYPY)
        return EdupageScraper()._parse(
            html, TARGET, config=config, prevadzka_matches=matches
        )

    def test_supplier_prefix_stripped_lets_clean_match_win(self):
        cfg = _cfg(OlovrantMode.EDUPAGE, payer_hook=skolickams_payer_hook)
        res = self._parse({"Les": ["Les"], "Lúka": ["Lúka"]}, cfg)
        by = res.order_data_by_prevadzka
        self.assertEqual(by["Les"]["lunch"]["Škôlka"]["menuCounts"]["A"], 6)
        self.assertEqual(by["Lúka"]["lunch"]["Škôlka"]["menuCounts"]["A"], 4)

    def test_bm_becomes_no_milk_diet(self):
        cfg = _cfg(OlovrantMode.EDUPAGE, payer_hook=skolickams_payer_hook)
        res = self._parse({"Les": ["Les"], "Lúka": ["Lúka"]}, cfg)
        luka = res.order_data_by_prevadzka["Lúka"]["lunch"]["Škôlka"]
        self.assertEqual(luka["diets"]["NO MILK"], 4)
        les = res.order_data_by_prevadzka["Les"]["lunch"]["Škôlka"]
        self.assertNotIn("NO MILK", les["diets"])

    def test_without_hook_supplier_prefix_breaks_clean_match(self):
        # bez hooku `B - Les` prefixovo nesadne na čisté `Les` → unmatched
        res = self._parse({"Les": ["Les"], "Lúka": ["Lúka"]}, config=None)
        self.assertTrue(res.unmatched_prevadzka)


class TestMatchPrevadzka(unittest.TestCase):
    MATCHES = {"J1": ["Jolly 1"], "J2": ["Jolly 2"], "Palisády": ["Palisády"]}

    def test_matches_payer_label_prefix(self):
        self.assertEqual(
            match_prevadzka(self.MATCHES, "J1 1.st. klasik", "klasik A"), ["Jolly 1"]
        )

    def test_matches_menu_nazov(self):
        self.assertEqual(
            match_prevadzka(self.MATCHES, "Klasik - MŠ", "Palisády nM"), ["Palisády"]
        )

    def test_diacritics_and_spaces_ignored(self):
        self.assertEqual(match_prevadzka({"B - Les": ["Les"]}, "B-Les sd", ""), ["Les"])

    def test_no_match_returns_empty(self):
        self.assertEqual(match_prevadzka(self.MATCHES, "J9 klasik", "menu A"), [])

    def test_longer_prefix_wins(self):
        matches = {"J1": ["Jolly 1"], "J1 2.st": ["Jolly 1 druhy stupen"]}
        self.assertEqual(
            match_prevadzka(matches, "J1 2.st klasik", ""), ["Jolly 1 druhy stupen"]
        )

    def test_matches_menu_skratka(self):
        """Skratka nesie celok v prefixe (`dsbA` = Deutsche schule + Klasik).

        Pri Zdravom Brúsku je to jediný rozlišovač: payer label je pre všetky školy
        `MŠ ...` a názov menu je `Klasik`.
        """
        matches = {"dsb": ["Deutsche schule"], "sšv": ["SŠ VETERINÁRNA"]}
        self.assertEqual(
            match_prevadzka(matches, "MŠ Klasik", "Klasik", "dsbA"), ["Deutsche schule"]
        )
        self.assertEqual(
            match_prevadzka(matches, "MŠ Klasik", "Klasik", "sšvA"), ["SŠ VETERINÁRNA"]
        )

    def test_skratka_beats_conflicting_payer(self):
        """Payer label si so skratkou vie protirečiť — vyhrať musí skratka.

        `MŠ Mal. NoMilk` so skratkou `dsbNMNE` je porcia Deutsche schule; keby vyhral
        payer, fakturovala by sa Malokarpatskému.
        """
        matches = {"dsb": ["Deutsche schule"], "mšMal": ["MŠ Malokarpatké námestie 6"]}
        self.assertEqual(
            match_prevadzka(matches, "MŠ Mal. NoMilk", "NoMilk/NoEgg", "dsbNMNE"),
            ["Deutsche schule"],
        )

    def test_only_payer_ignores_conflicting_skratka(self):
        """`only_payer=True` (Zdravé Brúško raňajky/olovrant, #564-Mal/Hey) obráti
        prioritu — payer_hook vie, že skratka je pre tento riadok cudzia."""
        matches = {"dsb": ["Deutsche schule"], "mšMal": ["MŠ Malokarpatké námestie 6"]}
        self.assertEqual(
            match_prevadzka(
                matches, "mšMal", "NoMilk/NoEgg", "dsbNMNE", only_payer=True
            ),
            ["MŠ Malokarpatké námestie 6"],
        )

    def test_shared_skratka_hits_both_prevadzky(self):
        """`mšMal,Hey` je jedna skratka pre dve škôlky — počet padne naplno obom."""
        matches = {
            "mšMal": ["MŠ Malokarpatké námestie 6"],
            "mšHey": ["MŠ Heyrovského 4"],
            "mšMal,Hey": ["MŠ Heyrovského 4", "MŠ Malokarpatké námestie 6"],
        }
        self.assertEqual(
            match_prevadzka(matches, "MŠ Diéta", "Diéta Lamač", "mšMal,Hey"),
            ["MŠ Heyrovského 4", "MŠ Malokarpatké námestie 6"],
        )


class _FakePrevadzka:
    """Len to, čo `build_prevadzka_matches` potrebuje — bez DB."""

    def __init__(self, nazov, edupage_match):
        self.nazov = nazov
        self.edupage_match = edupage_match

    def edupage_prefixes(self):
        return [p.strip() for p in self.edupage_match.split(";") if p.strip()]


class TestBuildPrevadzkaMatches(unittest.TestCase):
    """Dobrodružstvo: škola nemá spoločný prefix → `edupage_match` s bodkočiarkami."""

    DOBRODRUZSTVO = [
        _FakePrevadzka("MŠ Dobrodružstvo", "MŠ"),
        _FakePrevadzka("ZŠ Dobrodružstvo", "1.st; 2.st; Dospelý"),
    ]

    def test_each_prefix_maps_to_its_prevadzka(self):
        self.assertEqual(
            build_prevadzka_matches(self.DOBRODRUZSTVO),
            {
                "MŠ": ["MŠ Dobrodružstvo"],
                "1.st": ["ZŠ Dobrodružstvo"],
                "2.st": ["ZŠ Dobrodružstvo"],
                "Dospelý": ["ZŠ Dobrodružstvo"],
            },
        )

    def test_live_payer_groups_all_land(self):
        """Všetkých 14 skupín z živého EduPage (17.7.2026) musí sadnúť.

        Nezaradený riadok = neúplný scrape → celý celok sa zahodí.
        """
        matches = build_prevadzka_matches(self.DOBRODRUZSTVO)
        skolka = ["MŠ klasik", "MŠ Vege", "MŠ His", "MŠ No paradaj."]
        skola = [
            "1.st.",
            "1.st. ŠD",
            "2.st.",
            "Dospelý",
            "2. st. ŠD",
            "2. st. bezlep",
            "1.st. ŠD vege",
            "1. st. ŠD bezlak",
            "2.st ŠD bezlak",
            "1.st His ŠD",
        ]
        for nazov in skolka:
            self.assertEqual(
                match_prevadzka(matches, nazov, ""), ["MŠ Dobrodružstvo"], nazov
            )
        for nazov in skola:
            self.assertEqual(
                match_prevadzka(matches, nazov, ""), ["ZŠ Dobrodružstvo"], nazov
            )

    def test_single_prefix_still_works(self):
        self.assertEqual(
            build_prevadzka_matches([_FakePrevadzka("Jolly 1", "J1")]),
            {"J1": ["Jolly 1"]},
        )

    def test_prevadzka_without_match_is_reported(self):
        prevadzky = [_FakePrevadzka("Lúka", "Lúka"), _FakePrevadzka("Hosť", "  ")]
        self.assertEqual(prevadzky_without_match(prevadzky), ["Hosť"])

    def test_all_matched_reports_nothing(self):
        self.assertEqual(prevadzky_without_match(self.DOBRODRUZSTVO), [])


class TestParseSplit(unittest.TestCase):
    """Split podľa edupage_match: objem sa rozdelí, nič sa nestratí ticho."""

    NASTAVENIA = [
        {
            "nazov": "vydaj_normal",
            "hodnota": json.dumps({"2": {"vydaj_od": "11:00", "vydaj_do": "13:00"}}),
        }
    ]
    TYPY = [
        {
            "hodnota": json.dumps(
                {
                    "1": {"nazov": "J1 1.st. klasik", "porcia": "1"},
                    "2": {"nazov": "J2 1.st. klasik", "porcia": "1"},
                    "9": {"nazov": "J9 neznama", "porcia": "1"},
                }
            )
        }
    ]
    NAZOV_MENU = {"A": {"skratka": "A", "nazov": "klasik A"}}

    def _parse(self, payers, matches):
        prehlad = {
            "prehlad": {
                TARGET.isoformat(): {
                    "2": {"A": {"typ_platitela": {k: {"o": v} for k, v in payers}}}
                }
            }
        }
        html = _make_html(prehlad, self.NAZOV_MENU, self.NASTAVENIA, self.TYPY)
        return EdupageScraper()._parse(html, TARGET, prevadzka_matches=matches)

    def test_counts_split_between_prevadzky(self):
        res = self._parse([("1", 5), ("2", 3)], {"J1": ["Jolly 1"], "J2": ["Jolly 2"]})
        by = res.order_data_by_prevadzka
        self.assertEqual(by["Jolly 1"]["lunch"]["ZŠ 1.stupeň"]["menuCounts"]["A"], 5)
        self.assertEqual(by["Jolly 2"]["lunch"]["ZŠ 1.stupeň"]["menuCounts"]["A"], 3)

    def test_merged_order_data_is_the_sum(self):
        res = self._parse([("1", 5), ("2", 3)], {"J1": ["Jolly 1"], "J2": ["Jolly 2"]})
        self.assertEqual(res.order_data["lunch"]["ZŠ 1.stupeň"]["menuCounts"]["A"], 8)

    def test_unmatched_row_is_reported_not_silently_dropped(self):
        res = self._parse([("1", 5), ("9", 4)], {"J1": ["Jolly 1"]})
        self.assertEqual(res.order_data["lunch"]["ZŠ 1.stupeň"]["menuCounts"]["A"], 5)
        self.assertTrue(res.unmatched_prevadzka)
        self.assertTrue(res.warnings, "nezaradený riadok musí byť scrape failure")

    def test_no_matches_means_no_split(self):
        res = self._parse([("1", 5)], None)
        self.assertEqual(res.order_data_by_prevadzka, {})
        self.assertEqual(res.order_data["lunch"]["ZŠ 1.stupeň"]["menuCounts"]["A"], 5)


class TestMatchPrevadzkaPrefixOnly(unittest.TestCase):
    """Regresia #4: match je prefix, nie substring."""

    def test_substring_in_middle_does_not_match(self):
        # "Les" sa vyskytuje v strede, nie ako prefix → nesmie matchnúť.
        self.assertEqual(
            match_prevadzka({"Les": ["Školička Les"]}, "Bez Lesných plodov", ""), []
        )

    def test_prefix_matches(self):
        self.assertEqual(
            match_prevadzka({"Les": ["Školička Les"]}, "Les učiteľ", ""),
            ["Školička Les"],
        )
