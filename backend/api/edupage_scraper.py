"""
Edupage mealsGuest HTML scraper.

Fetches the mealsGuest page for a school and extracts embedded order counts
(prehlad) from the server-rendered script tag. No headless browser needed —
the data is JSON embedded server-side on every page load.

Output format matches DailyOrder.data so imported orders look identical to
orders submitted through the UI.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

from api.edupage import PrevadzkaConfig, apply_config, config_pre_url

logger = logging.getLogger(__name__)

ALLOWED_DIET_NAMES = {
    "NO MILK",
    "NO GLUTEN",
    "NO MILK/NO GLUTEN",
    "NO MILK/NO EGG",
    "VEGGIE",
    "HISTAMIN",
    "NONONO",
    "NO ORECH",
    "NO PARADAJKA",
    "NO FISH",
    "NO EGG",
    "NO ZEMIAK",
    "NO SOJA",
    "NO ZELER",
    "DIA",
    "VEGAN",
    "NO BRAVCOVINA",
    "NO CERVENE MASO",
    "NO CUKOR",
    "NO CITRUS",
}


def allowed_diet_names() -> set[str]:
    """Povolené diéty = aktívne `Diet` z DB ∪ zabudovaný zoznam.

    Škola pridá do EduPage novú diétu kedykoľvek (Cvernička, 17. 8. 2026). Keby sa
    whitelist držal len v kóde, každá takáto diéta by čakala na nasadenie; takto ju
    stačí založiť v appke a najbližší scrape ju už pozná. Zabudovaný zoznam ostáva
    ako poistka, keby DB bola prázdna (testy, čerstvá inštalácia pred seedom).

    Import modelu je lokálny zámerne — modul sa načítava aj mimo Django kontextu
    (parser testy, skripty) a nesmie na import ťahať ORM.
    """
    from api.models import Diet

    names = set(ALLOWED_DIET_NAMES)
    names.update(Diet.objects.filter(is_active=True).values_list("name", flat=True))
    return names


DEFAULT_PORTION_NAME = "Škôlka"
PORTION_CODE_MAP = {
    "0": "Škôlka",
    "1": "ZŠ 1.stupeň",
    "2": "ZŠ 2.stupeň",
    "3": "Dospelý (SŠ)",
    "4": "Dospelý (SŠ)",
    # British School má pre učiteľov vlastný porcia kód (payer skupiny "Učiteľ
    # Klasik"/"Učiteľ VEGE") — bez tohto by neznámy kód spadol na
    # DEFAULT_PORTION_NAME ("Škôlka") a učitelia by dostávali MŠ porcie
    # namiesto dospelých (systémová kontrola 1.9.2026).
    "5": "Dospelý (SŠ)",
}

PREDSKOLAK_PORTION_NAME = "Predškolák"
# EduPage nemá pre predškoláka vlastný kód porcie — školy ho hlásia cez názov
# platiteľskej skupiny (`Klasik - predškoláci`). Rozlíšenie je potrebné, lebo
# `porcia=1` zlieva predškolákov s naozajstným 1. stupňom, no účtujú sa inak
# (Edulienka: predškolák 1,25 porcie, prvostupniar 1).
_PREDSKOLAK_KEY_FRAGMENTS = ("predskolac", "predskolak")
# Zámerne len pre `porcia=1`: Predškolák má rovnaký gramážový koeficient ako
# `ZŠ 1.stupeň`, takže gramy ostávajú identické — je to len rozpad tohto kódu.
# Libellus a Krásňanko hlásia predškolákov ako `porcia=0` (MŠ gramáž), tých by
# preznačenie posunulo z 200 g na 250 g, preto sa ich toto pravidlo netýka.
_PREDSKOLAK_PORTION_CODE = "1"

# ------------------------------------------------------------------
# Known mappings: Edupage abbreviation → our Diet.name
# ------------------------------------------------------------------

_SKRATKA_MAP: dict[str, str] = {
    "BG": "NO GLUTEN",
    "BH": "HISTAMIN",
    "BM": "NO MILK",
    "BMBG": "NO MILK/NO GLUTEN",
    "NM": "NO MILK",
    "NOM": "NO MILK",
    "NG": "NO GLUTEN",
    "NOG": "NO GLUTEN",
    "NOGLUTEN": "NO GLUTEN",  # MŠ Dobrého Pastiera píše skratku vypísanú celú
    "NGNM": "NO MILK/NO GLUTEN",
    "NMNG": "NO MILK/NO GLUTEN",
    "NMG": "NO MILK/NO GLUTEN",
    # ZŠ Ivanka pri Dunaji: "NMNGnORECH" — bez tejto zhody by substringový
    # heuristický fallback ("nmng" v compact_sk, viď nižšie) odrezal "orech" a
    # priradil len 2-zložkovú "NO MILK/NO GLUTEN" (potvrdené manuálne 2.9.2026,
    # kontrolou skutočného scrapu — appka reálne existujúcu 3-zložkovú diétu
    # "NO MILK – NO GLUTEN – NO ORECH" má, len ju táto skratka nenašla).
    "NMNGNORECH": "NO MILK – NO GLUTEN – NO ORECH",
    # MŠ Edulienka: "nGH" — bez tejto zhody končí na generickom "ngh" fallbacku
    # nižšie, ktorý vracia len "NO GLUTEN" a stráca histamín (potvrdené
    # manuálne 2.9.2026).
    "NGH": "HISTAMIN, NO GLUTEN",
    "NE": "NO EGG",
    "NENO": "NO EGG",
    "NS": "NO SOJA",
    "HIS": "HISTAMIN",
    "HISTAMIN": "HISTAMIN",
    "HIT": "HISTAMIN",
    "H": "HISTAMIN",
    "NNN": "NONONO",
    "NNNO": "NONONO",
    "NF": "NO FISH",
    "NGNF": "NO GLUTEN",
    "NN": "NO ORECH",  # British School: "nN" = noNuts (nie NONONO — kolízia s "nnn" substringom)
    # "NMNE"/"NMNEGG" = No Milk No Egg — bez tejto zhody padalo len na "NO MILK"
    # a strácalo sa vajíčko (rovnaký #527 vzor ako "dsbNMNE", opravené per-školu
    # cez letter_hook v zdravebrusko/ivanka/libellus). MŠ Naša Škola Poznania
    # skratku píše vypísanú celú ("nMnEgg") a nemá letter_hook, tak sa opravuje
    # tu v základnej mape (user-reported 2.9.2026, "H:nMnEgg→NO MILK").
    "NMNE": "NO MILK/NO EGG",
    "NMNEGG": "NO MILK/NO EGG",
    "NMNO": "NO MILK",
    "NMZ": "NO MILK",
    "NMZD": "NO MILK",
    "PNM": "NO MILK",  # MŠ Edulienka: "PnM" (Palisády no Milk)
    "V": "VEGGIE",
    "VEG": "VEGGIE",
    "VE": "VEGGIE",
    "VEGE": "VEGGIE",  # British School píše po anglicky "Vege"
    "PV": "VEGGIE",
    "SV": "VEGGIE",
    "VEGETAR": "VEGGIE",
    "DIA": "DIA",
    "VEGAN": "VEGAN",  # British School
    "NP": "NO BRAVCOVINA",  # British School: "nP" = noPork
    "NREDMEAT": "NO CERVENE MASO",  # British School: "nREDmeat"
    "NSUG": "NO CUKOR",  # British School: "nSUG" = noSugar
}

# Keyword fragments in nazov → our Diet.name (checked after stripping spaces/slashes)
_NAZOV_KEYWORD_MAP: dict[str, str] = {
    "nomilk": "NO MILK",
    "bezmliecne": "NO MILK",
    "bezmlieka": "NO MILK",
    "nogluten": "NO GLUTEN",
    "nog": "NO GLUTEN",
    "bezglutenove": "NO GLUTEN",
    "bezlep": "NO GLUTEN",
    "nomilknogluten": "NO MILK/NO GLUTEN",
    "noglutennomilk": "NO MILK/NO GLUTEN",
    "nomilknog": "NO MILK/NO GLUTEN",
    "nomno": "NO MILK/NO GLUTEN",
    "nmg": "NO MILK/NO GLUTEN",
    "nmn": "NO MILK/NO GLUTEN",
    # MŠ Naša Škola Poznania, raňajky/olovrant: payer label "1.-3.ročník
    # noMilk/noEgg" nemá vlastné menu-písmeno (tie majú len obed), diétu tu
    # rieši len fragment-match na payer nazov. Bez zloženej zhody vyhral prvý
    # (dlhší) samostatný fragment "nomilk" a "noEgg" sa ticho stratil (user
    # 3.9.2026, "nečíta dobre") — na obede rovnaký payer ide cez skratku
    # "nMnEgg" (`_SKRATKA_MAP`, opravené 2.9.2026) a je to tam OK, tak musí
    # byť aj tu.
    "nomilknoegg": "NO MILK/NO EGG",
    "noeggnomilk": "NO MILK/NO EGG",
    "bezmliecnebezglutenove": "NO MILK/NO GLUTEN",
    "noegg": "NO EGG",
    "bezvajec": "NO EGG",
    "bezvaj": "NO EGG",
    "nosoy": "NO SOJA",
    "nosoja": "NO SOJA",
    "bezsoje": "NO SOJA",
    "histamin": "HISTAMIN",
    "bezhistaminu": "HISTAMIN",
    "hit": "HISTAMIN",
    "nonono": "NONONO",
    "nnn": "NONONO",
    "nofish": "NO FISH",
    "bezryb": "NO FISH",
    "vegetar": "VEGGIE",
    "veggie": "VEGGIE",
    "vege": "VEGGIE",
    "nozeler": "NO ZELER",
    "noparadajka": "NO PARADAJKA",
    "noparadajky": "NO PARADAJKA",
    "noparadaj": "NO PARADAJKA",
    "noorech": "NO ORECH",
    "bezorech": "NO ORECH",
    "orech": "NO ORECH",
    "arasid": "NO ORECH",
    "nozemiak": "NO ZEMIAK",
    "horcica": "NO HORCICA",  # Cvernička "AnHorčica"/"Klasik/noHorčica"
    # MŠ Rozmanitá "Klasik bez citrus" — bez tohto fragmentu nemá "citrus" v
    # nazve žiadny diétny signál, takže by spadlo do resolve_menu_variant()
    # ako obyčajný Klasik (#Rozmanitá, 1.9.2026).
    "citrus": "NO CITRUS",
    "dia": "DIA",
    "diabet": "DIA",
    # British School (#531) hlási po anglicky — mapujeme na slovenské Diet.name.
    "vegan": "VEGAN",
    "nopork": "NO BRAVCOVINA",
    "noredmeat": "NO CERVENE MASO",
    "nosugar": "NO CUKOR",
}

# Meal category by service-hour range (vydaj_od hour)
_MEAL_BY_HOUR: list[tuple[int, str]] = [
    (10, "breakfast"),  # vydaj_od < 10:00
    (15, "lunch"),  # vydaj_od 10:00–14:59
]
_DEFAULT_MEAL = "olovrant"  # vydaj_od ≥ 15:00
_MENU_NAME_RE = re.compile(r"^(?:menu\s*)?([ABCD])$", re.IGNORECASE)
_PREFIXED_MENU_NAME_RE = re.compile(r"(?:^|\s)(?:menu\s*)?([ABCD])$", re.IGNORECASE)
_CLASSIC_MENU_NAMES = {
    "klasik",
    "classic",
    # Montessori labels its combined MŠ/ZŠ class this way instead of "Klasik";
    # real-table volumes confirm that it is a regular menu, not a diet.
    "mszsina",
}


def _normalise_key(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore")
    return re.sub(r"[\s/\-+.,_()]+", "", ascii_value.decode("ascii")).lower()


def _has_diet_signal(key: str) -> bool:
    return any(fragment in key for fragment in _NAZOV_KEYWORD_MAP)


def build_prevadzka_matches(prevadzky) -> dict[str, list[str]]:
    """{prefix: [názvy prevádzok]} pre `match_prevadzka`.

    Jedna prevádzka môže prispieť viacerými prefixami (`edupage_match` oddelený
    bodkočiarkami), preto sa mapa nedá postaviť ako `{p.edupage_match: p.nazov}` a jej
    veľkosť sa nesmie porovnávať s počtom prevádzok — na to je
    `prevadzky_without_match`.

    Hodnota je zoznam, lebo jeden prefix môže patriť viacerým prevádzkam: EduPage
    Zdravého Brúska zlučuje MŠ Malokarpatské a MŠ Heyrovského do jednej skratky
    (`mšMal,Hey`) pri desiate a olovrante. Rozpad na tie dve škôlky v dátach nie je,
    tak sa počet zapíše NAPLNO obom — dočasne, kým klient menu nerozdelí (viď
    feedback.md). Nadhodnocuje to fakturáciu oboch, ale je to vedomé.
    """
    matches: dict[str, list[str]] = {}
    for prevadzka in prevadzky:
        for prefix in prevadzka.edupage_prefixes():
            matches.setdefault(prefix, []).append(prevadzka.nazov)
    return matches


def prevadzky_without_match(prevadzky) -> list[str]:
    """Prevádzky bez použiteľného `edupage_match` — split by im nemal čo priradiť."""
    return [p.nazov for p in prevadzky if not p.edupage_prefixes()]


def match_prevadzka(
    matches: dict[str, list[str]],
    payer_name: str,
    menu_nazov: str,
    menu_skratka: str = "",
    only_payer: bool = False,
) -> list[str]:
    """Priraď EduPage riadok prevádzke podľa `edupage_match` prefixu.

    Prevádzka je zakódovaná ako PREFIX payer labelu (`J1 1.st. klasik`, `B - Les`),
    názvu menu (`Palisády nM`) alebo skratky menu (`dsbA`, `zšlaNM`). Skúšame všetky
    tri. Skratka je jediný spoľahlivý nosič tam, kde EduPage zastrešuje viac
    samostatných subjektov: Zdravé Brúsko vedie päť škôl a ich payer labely (`MŠ
    Klasik`, `MŠ Vege`) ani názvy menu (`Klasik`) školu neurčujú — skratka áno.

    Match je `startswith`, nie substring — inak by krátky `edupage_match` (napr. `Les`)
    chytil aj nesúvisiaci label, kde sa ten reťazec vyskytne v strede. Dlhšie prefixy
    majú prednosť, aby `J1` neprebilo špecifickejší match; vyhráva teda JEDEN prefix,
    a viac prevádzok vráti len vtedy, keď si ten istý prefix zdieľajú (`mšMal,Hey`).

    Vracia zoznam — prázdny znamená „nepriradené", nie „nič sa nedeje": volajúci to
    musí nahlásiť ako neúplný scrape, inak by porcie ticho zmizli.

    Skratka má PREDNOSŤ pred payer labelom, lebo je to zvyčajne spoľahlivejší nosič
    (napr. `dsbA` = Deutsche schule + Klasik). Výnimka je `only_payer=True`
    (`PayerRule.force_match`, viď `base.py`) — Zdravé Brúško raňajky/olovrant
    zdieľajú skratku `dsbNMNE` naprieč Deutsche Schule aj MŠ Malokarpatským/
    Heyrovského, ale payer label si so skratkou protirečí a je tu ten
    spoľahlivejší nosič: `payer='MŠ Mal. NoMilk'` so skratkou `dsbNMNE` musí byť
    porcia Malokarpatského, nie Deutsche schule (user 2.9.2026, potvrdené na live
    dátach — pôvodne to bolo naopak, viď git history).
    """
    kandidati = (
        (_normalise_key(payer_name),)
        if only_payer
        else (
            _normalise_key(menu_skratka),
            _normalise_key(payer_name),
            _normalise_key(menu_nazov),
        )
    )
    for key in kandidati:
        if not key:
            continue
        for prefix in sorted(matches, key=len, reverse=True):
            prefix_key = _normalise_key(prefix)
            if not prefix_key:
                continue
            if key.startswith(prefix_key):
                return list(matches[prefix])
    return []


# ------------------------------------------------------------------
# Public result type
# ------------------------------------------------------------------


@dataclass
class ScrapeResult:
    """Parsed order counts ready to be stored as DailyOrder.data."""

    date: date
    order_data: dict[str, Any]  # DailyOrder.data format (všetky prevádzky spolu)
    # {názov prevádzky: order_data} pri celkoch rozdelených na viac prevádzok.
    # Prázdne, ak sa split nerobil.
    order_data_by_prevadzka: dict[str, dict[str, Any]] = field(default_factory=dict)
    # EduPage riadky, ktoré nesadli na žiadnu prevádzku. Neprázdne = neúplný scrape.
    unmatched_prevadzka: list[str] = field(default_factory=list)
    # Diéty, ktoré appka nepozná. Porcie sa NEZAHADZUJÚ (celkový počet musí sedieť),
    # zapíšu sa pod názvom z EduPage a admin ich vidí ako upozornenie.
    unmapped_letters: list[str] = field(default_factory=list)
    # `unmapped_letters` rozpadnuté podľa prevádzky, do ktorej porcie padli.
    # Prázdne pri jedno-prevádzkovom scrape (vtedy platí `unmapped_letters`).
    unmapped_by_prevadzka: dict[str, list[str]] = field(default_factory=dict)
    # Diéty, ktoré appka rozpoznala len heuristikou (fuzzy suffix/keyword scan, nie
    # exaktnou skratkou zo `_SKRATKA_MAP`), aj keď výsledný názov je medzi povolenými.
    # Počty a priradenie sa NEMENIA — je to len signál pre admina na kontrolu, nie
    # signál zlyhania (nesmie sa miešať do `warnings`/`unmapped_letters`).
    uncertain_letters: list[str] = field(default_factory=list)
    # `uncertain_letters` rozpadnuté podľa prevádzky, analogicky k `unmapped_by_prevadzka`.
    uncertain_by_prevadzka: dict[str, list[str]] = field(default_factory=dict)
    # Scrape zlyhal štrukturálne — volajúci z toho robí "neimportuj nič".
    warnings: list[str] = field(default_factory=list)
    # Scrape prebehol, ale per-prevádzka config nesedí s realitou (škola zmenila
    # nastavenia). Diagnostika pre nás, NIE signál zlyhania — nesmie sa miešať
    # do `warnings`, inak by config drift zablokoval import platných objednávok.
    config_notes: list[str] = field(default_factory=list)
    # Písmená, ktoré `letter_hook` označil `skip=True` a appka ich vôbec nezarátala
    # (napr. Montessori: len 'Iná' sa počíta z EduPage, ostatné písmená sa ignorujú —
    # user 2.9.2026). Vedomé rozhodnutie, nie signál zlyhania.
    skipped_letters: list[str] = field(default_factory=list)
    # Písmená označené per-prevádzka hookom ako „skontroluj ručne" (napr. Krásňanko ZD).
    attention: list[str] = field(default_factory=list)
    # `attention` rozpadnuté podľa prevádzky, do ktorej porcie s daným flagom
    # reálne padli. Prázdne pri jedno-prevádzkovom scrape (vtedy platí `attention`).
    attention_by_prevadzka: dict[str, list[str]] = field(default_factory=dict)


# ------------------------------------------------------------------
# Core scraper
# ------------------------------------------------------------------


class EdupageScraper:
    TIMEOUT = 15

    def scrape(
        self,
        mealsguest_url: str,
        target_date: date,
        prevadzka_matches: dict[str, list[str]] | None = None,
        allowed_diets: set[str] | None = None,
    ) -> ScrapeResult:
        url = self._inject_date(mealsguest_url, target_date)
        html = self._fetch(url)
        config = config_pre_url(mealsguest_url)
        result = self._parse(
            html,
            target_date,
            config=config,
            prevadzka_matches=prevadzka_matches,
            allowed_diets=allowed_diets,
        )
        if config is not None:
            result = apply_config(result, config)
        return result

    # ------ HTTP ------

    def _fetch(self, url: str) -> str:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ZdravyProjektBot/1.0)"},
            timeout=self.TIMEOUT,
        )
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def _inject_date(url: str, target_date: date) -> str:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        qs["date"] = [target_date.isoformat()]
        new_query = urlencode({k: v[0] for k, v in qs.items()})
        return urlunparse(parsed._replace(query=new_query))

    # ------ JSON extraction from HTML ------

    @staticmethod
    def _extract_block(html: str, key: str) -> Any | None:
        """Pull a JS object/array assigned to `key :` inside the strava_numeri(…) call."""
        pattern = (
            rf"{re.escape(key)}\s*:\s*([{{\[].+?)(?=,\s*\n?\s*[a-zA-Z_]\w*\s*:|\);\s*$)"
        )
        m = re.search(pattern, html, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(1).rstrip(","))
        except json.JSONDecodeError as exc:
            logger.debug("JSON parse failed for key=%s: %s", key, exc)
            return None

    # ------ jid → meal_key ------

    @staticmethod
    def _parse_iso_date(value: str) -> date | None:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _parse_hm(value: str) -> tuple[int, int]:
        """Parse an "H:MM"/"HH:MM" time string into a (hour, minute) tuple."""
        hour_str, _, minute_str = value.partition(":")
        try:
            return int(hour_str), int(minute_str or 0)
        except ValueError:
            return 12, 0

    @staticmethod
    def _row_valid_for_date(row: dict, target_date: date) -> bool:
        """Return True unless `target_date` falls outside the row's plati_od/plati_do."""
        plati_od = row.get("plati_od")
        if plati_od:
            parsed = EdupageScraper._parse_iso_date(plati_od)
            if parsed and target_date < parsed:
                return False
        plati_do = row.get("plati_do")
        if plati_do:
            parsed = EdupageScraper._parse_iso_date(plati_do)
            if parsed and target_date > parsed:
                return False
        return True

    @staticmethod
    def _build_jid_map(
        nastavenia: list[dict],
        target_date: date,
        config: PrevadzkaConfig | None = None,
    ) -> dict[str, str]:
        """Return {jid_str: meal_key} using vydaj_od times from nastavenia.

        `config.meal_hour_thresholds`, keď je nastavený, nahradí generický
        `_MEAL_BY_HOUR` (viď `PrevadzkaConfig.meal_hour_thresholds` docstring) —
        celý zvyšok algoritmu (naivný košík podľa hodiny, "výherca" podľa
        `druhov_jedal`, posun kolidujúcich okien na najbližší voľný slot) ostáva
        nezmenený, len beží nad iným zoznamom prahov/meal_sequence.

        A school's olovrant (afternoon snack) window can start as early as
        14:30, which falls on the same side of the fixed hour thresholds as a
        lunch window ending at 14:00 (both have vydaj_od hour 14) — so two
        genuinely different service windows would resolve to the same
        meal_key and their headcounts would be summed together, silently
        doubling that meal's reported count. When more than one window in the
        same day resolves to the same naive meal, the window with the most
        menu variety (`druhov_jedal`) wins that meal — it is almost always
        the real lunch, not a small desiata/snack window landing in the same
        hour bucket by coincidence — and the rest are pushed to the nearest
        still-open slot on their own side (earlier windows toward breakfast,
        later ones toward olovrant), so each real window keeps its own
        bucket. Multiple jids legitimately sharing one bucket (e.g. a
        desiata window merged into "breakfast", which already covers
        raňajky+desiata as one reported meal) is fine — `_parse` sums counts
        across jids under the same meal_key regardless.

        Windows are normally keyed by jid directly (`{jid: {...}}`), but
        British School's `nastavenia` reports them as a plain list with no
        jid at all — list position IS the jid used elsewhere in `prehlad`
        (confirmed via the payer-type overlap between each window and its
        matching `prehlad` jid). Without this, the whole day was silently
        skipped (`isinstance(day_data, dict)` failed on a list), leaving
        `jid_map` empty — and every jid then fell through `_parse`'s
        single-jid-school fallback to "lunch", merging breakfast, desiata,
        the real lunch and olovrant into one inflated "lunch" count (#British
        School, 1.9.2026 — 885 heads under lunch, 0 under breakfast/olovrant).

        A `vydaj_normal` row is only valid while `target_date` falls within
        its own `plati_od`/`plati_do` range — a school that changed its
        serving schedule mid-year can have several such rows, and applying a
        row that isn't valid for the scraped date would silently attach the
        wrong (stale or not-yet-active) times to that day.
        """
        jid_map: dict[str, str] = {}
        meal_hour_thresholds = (
            config.meal_hour_thresholds
            if config is not None and config.meal_hour_thresholds is not None
            else _MEAL_BY_HOUR
        )
        # Single source of truth for meal ordering, shared with the hour
        # thresholds below - avoids a second, independently-maintained list.
        meal_sequence = [label for _, label in meal_hour_thresholds] + [_DEFAULT_MEAL]

        for row in nastavenia:
            if row.get("setting") != "vydaj_normal":
                continue
            if not EdupageScraper._row_valid_for_date(row, target_date):
                continue
            try:
                hodnota = (
                    json.loads(row["hodnota"])
                    if isinstance(row["hodnota"], str)
                    else row["hodnota"]
                )
            except (json.JSONDecodeError, KeyError):
                continue
            for day_data in hodnota.values():
                if isinstance(day_data, list):
                    day_data = {
                        str(index): entry for index, entry in enumerate(day_data)
                    }
                if not isinstance(day_data, dict):
                    continue

                unseen = [
                    (jid, times)
                    for jid, times in day_data.items()
                    if jid not in jid_map and isinstance(times, dict)
                ]
                if not unseen:
                    continue
                # Chronological within the day - parsed as (hour, minute) so
                # unpadded times (e.g. "9:30") still sort before "14:00"
                # instead of a lexicographic string compare misordering them.
                unseen.sort(
                    key=lambda pair: EdupageScraper._parse_hm(pair[1]["vydaj_od"])
                )

                order = [jid for jid, _ in unseen]
                by_bucket: dict[str, list[str]] = {}
                variety: dict[str, int] = {}
                for jid, times in unseen:
                    hour = EdupageScraper._parse_hm(times.get("vydaj_od", "12:00"))[0]
                    meal = _DEFAULT_MEAL
                    for threshold, label in meal_hour_thresholds:
                        if hour < threshold:
                            meal = label
                            break
                    by_bucket.setdefault(meal, []).append(jid)
                    try:
                        variety[jid] = int(times.get("druhov_jedal") or 1)
                    except (TypeError, ValueError):
                        variety[jid] = 1

                for meal, jids in by_bucket.items():
                    if len(jids) == 1:
                        jid_map[jids[0]] = meal
                        continue
                    winner = max(jids, key=lambda jid: variety[jid])
                    jid_map[winner] = meal
                    winner_index = order.index(winner)
                    start = meal_sequence.index(meal)
                    for jid in jids:
                        if jid == winner:
                            continue
                        if order.index(jid) < winner_index:
                            candidates = (
                                meal_sequence[start - 1 :: -1] if start > 0 else []
                            )
                        else:
                            candidates = meal_sequence[start + 1 :]
                        jid_map[jid] = candidates[0] if candidates else meal
        return jid_map

    @staticmethod
    def _build_payer_map(
        typy_platitelov: list[dict], target_date: date
    ) -> dict[str, dict[str, str]]:
        """Return {typ_platitela_id: cleaned portion/diet metadata}.

        Like `vydaj_normal`, a `typy_platitelov` row is only valid while
        `target_date` falls within its own `plati_od`/`plati_do` range - a
        school can redefine payer groups (e.g. reassign a payer_id to a
        different diet/portion) mid-year, leaving older rows in the data.
        Applying a row that isn't valid for the scraped date would silently
        misclassify counts under a stale or not-yet-active payer mapping.
        """
        payer_map: dict[str, dict[str, str]] = {}
        for row in typy_platitelov:
            if not isinstance(row, dict):
                continue
            if not EdupageScraper._row_valid_for_date(row, target_date):
                continue
            hodnota = row.get("hodnota", {})
            if isinstance(hodnota, str):
                try:
                    hodnota = json.loads(hodnota)
                except json.JSONDecodeError:
                    continue
            if not isinstance(hodnota, dict):
                continue

            for payer_id, payer_data in hodnota.items():
                if not isinstance(payer_data, dict):
                    continue
                name = str(payer_data.get("nazov", "")).strip()
                portion_code = str(payer_data.get("porcia", "")).strip()
                payer_map[str(payer_id)] = {
                    "name": name,
                    "portion": EdupageScraper.resolve_payer_portion_name(
                        name, portion_code
                    ),
                    "diet": EdupageScraper.resolve_payer_diet_name(name) or "",
                }
        return payer_map

    # ------ diet name auto-match ------

    @staticmethod
    def resolve_diet_name(skratka: str, nazov: str) -> str:
        """
        Map an Edupage diet abbreviation/name to our Diet.name.

        Priority:
        1. Known skratka (abbreviation) exact match
        2. Keyword scan on normalised nazov
        3. Fallback: return nazov as-is (stored under that name in diets)

        Tenký wrapper nad `_resolve_diet_name_with_confidence` — vracia len názov,
        bez confidence flagu. Signatúra/návratový typ zostávajú nezmenené zámerne,
        volá sa priamo z testov (`TestResolveDietName`).
        """
        name, _ = EdupageScraper._resolve_diet_name_with_confidence(skratka, nazov)
        return name

    @staticmethod
    def _resolve_diet_name_with_confidence(
        skratka: str, nazov: str
    ) -> tuple[str, bool]:
        """Ako `resolve_diet_name`, ale aj s flagom, či sme si istí.

        `is_exact=True` len pre presnú zhodu v `_SKRATKA_MAP` — všetko ostatné (suffix
        heuristiky, keyword scan, fallback echo) je fuzzy odhad. `is_exact=False`
        neznamená, že výsledok je zlý (fuzzy matching bežne funguje správne), len že
        appka si nie je istá a admin by ho mal vedieť skontrolovať (viď #527: nová/
        nezvyčajná diéta môže zdieľať fragment s existujúcou skratkou a tíško sa
        priradiť nesprávne).
        """
        sk = skratka.strip().upper()
        if sk in _SKRATKA_MAP:
            return _SKRATKA_MAP[sk], True

        compact_sk = _normalise_key(skratka)
        if any(fragment in compact_sk for fragment in ("nmng", "ngnm", "bmbg")):
            return "NO MILK/NO GLUTEN", False
        if compact_sk.endswith("nmg") or compact_sk.endswith("ngm"):
            return "NO MILK/NO GLUTEN", False
        if compact_sk.endswith("ngh"):
            return "NO GLUTEN", False
        if compact_sk.endswith("nnn") or "nonono" in compact_sk:
            return "NONONO", False
        if compact_sk.endswith("hit") or compact_sk.endswith("his"):
            return "HISTAMIN", False
        if compact_sk.endswith("ng") or compact_sk.endswith("nog"):
            return "NO GLUTEN", False
        if compact_sk.endswith("nm") or compact_sk.endswith("nom"):
            return "NO MILK", False
        if compact_sk.endswith("nomo"):
            return "NO MILK", False
        if compact_sk.endswith("ne") or compact_sk.startswith("ne"):
            return "NO EGG", False
        if compact_sk.endswith("h") and re.search(r"(?:^|\s)H\s*$", nazov):
            return "HISTAMIN", False

        key = _normalise_key(f"{skratka} {nazov}")

        if sk.endswith("V") and re.search(r"(?:^|\s)V\s*$", nazov, re.IGNORECASE):
            return "VEGGIE", False

        for fragment, diet_name in sorted(
            _NAZOV_KEYWORD_MAP.items(), key=lambda item: len(item[0]), reverse=True
        ):
            if fragment in key:
                return diet_name, False

        return nazov.strip() or skratka.strip(), False

    @staticmethod
    def resolve_payer_portion_name(nazov: str, portion_code: str) -> str:
        """Map an Edupage payer group to our PortionType.name.

        Splits `porcia=1` into `Predškolák` / `ZŠ 1.stupeň` by group label — the
        two share a portion code but not a billing coefficient.
        """
        key = _normalise_key(nazov)
        if portion_code == _PREDSKOLAK_PORTION_CODE and any(
            fragment in key for fragment in _PREDSKOLAK_KEY_FRAGMENTS
        ):
            return PREDSKOLAK_PORTION_NAME
        return PORTION_CODE_MAP.get(portion_code, DEFAULT_PORTION_NAME)

    @staticmethod
    def resolve_payer_diet_name(nazov: str) -> str | None:
        """Map an Edupage payer group label to one of our Diet.name values.

        Do NOT special-case "SŠV" here: live data (2.9.2026) shows SŠ Veterinárna
        payer groups are "SŠV Žiak"/"SŠV dospelý" — plain portion labels, not diets.
        Their actual menu choice (Klasik/Menu B/Vege) lives at the menu-letter level
        (skratka "sšvA"/"sšvB"/"sšvV") and is resolved there. A previous blanket
        "ssv in key → VEGGIE" rule forced every SŠV order to VEGGIE regardless of
        the letter they actually picked (user-reported 2.9.2026).
        """
        key = _normalise_key(nazov)

        for fragment, diet_name in sorted(
            _NAZOV_KEYWORD_MAP.items(), key=lambda item: len(item[0]), reverse=True
        ):
            if fragment in key and diet_name in ALLOWED_DIET_NAMES:
                return diet_name

        return None

    @staticmethod
    def resolve_menu_variant(skratka: str, nazov: str) -> str | None:
        """Return a menu variant for non-diet Edupage entries."""
        sk = skratka.strip().upper()
        nazov_clean = nazov.strip()
        key = _normalise_key(nazov_clean)
        combined_key = _normalise_key(f"{skratka} {nazov_clean}")

        if _has_diet_signal(combined_key):
            return None

        # Písmeno na konci názvu (napr. "Klasik B") má prednosť pred paušálnym
        # "klasik"/"classic" → A nižšie — inak škola s dvoma klasickými
        # variantmi ("Klasik A", "Klasik B") dostane obe spočítané pod A a
        # variant B sa v appke nikdy neobjaví (#Naša Škola Poznania, dom B).
        for value in (nazov_clean, sk):
            match = _MENU_NAME_RE.match(value)
            if match:
                return match.group(1).upper()

        match = _PREFIXED_MENU_NAME_RE.search(nazov_clean)
        if match:
            return match.group(1).upper()

        if key in _CLASSIC_MENU_NAMES or "klasik" in key or "classic" in key:
            return "A"

        return None

    # ------ aggregation ------

    def _parse(
        self,
        html: str,
        target_date: date,
        config: PrevadzkaConfig | None = None,
        prevadzka_matches: dict[str, list[str]] | None = None,
        allowed_diets: set[str] | None = None,
    ) -> ScrapeResult:
        prehlad_raw = self._extract_block(html, "prehlad")
        nazov_menu_raw = self._extract_block(html, "nazovMenu")
        nastavenia_raw = self._extract_block(html, "nastavenia")
        typy_platitelov_raw = self._extract_block(html, "typy_platitelov")

        warnings: list[str] = []
        unmapped: list[str] = []
        uncertain: list[str] = []
        attention: list[str] = []
        skipped_letters: list[str] = []
        # Normalizovaný index, aby `no milk` z EduPage sadlo na našu `NO MILK` a
        # nezaložilo druhú, len inak písanú diétu.
        allowed_by_key = {
            _normalise_key(name): name for name in (allowed_diets or ALLOWED_DIET_NAMES)
        }
        letter_hook = config.letter_hook if config is not None else None
        payer_hook = config.payer_hook if config is not None else None

        if not prehlad_raw:
            warnings.append("prehlad block not found in HTML")
            return ScrapeResult(date=target_date, order_data={}, warnings=warnings)

        prehlad = prehlad_raw.get("prehlad", {})
        if isinstance(prehlad, list):
            prehlad = {}
        if not isinstance(prehlad, dict):
            warnings.append("prehlad block has unexpected format")
            return ScrapeResult(date=target_date, order_data={}, warnings=warnings)

        nazov_menu: dict = nazov_menu_raw or {}
        nastavenia: list = nastavenia_raw or []
        typy_platitelov: list = typy_platitelov_raw or []

        jid_map = self._build_jid_map(nastavenia, target_date, config=config)
        payer_map = self._build_payer_map(typy_platitelov, target_date)

        # prevádzka ("" = nerozdelené) -> meal -> porcia -> menu/diet counts.
        # Posledná úroveň je `Any`, nie `dict[str, int]` — okrem "menuCounts"/
        # "diets" (letter → int) sem pribúda aj "packSeparately"
        # ({"menus"/"diets": letter → int}), o úroveň hlbšie.
        counts: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
        matches = prevadzka_matches or {}
        unmatched: list[str] = []
        # bucket (názov prevádzky) -> flagy, ktoré do neho reálne padli
        attention_buckets: dict[str, set[str]] = {}
        # to isté pre neznáme diéty (`unmapped`)
        unmapped_buckets: dict[str, set[str]] = {}
        # to isté pre neisto (fuzzy) namatchnuté diéty (`uncertain`)
        uncertain_buckets: dict[str, set[str]] = {}

        date_key = target_date.isoformat()
        day_data = prehlad.get(date_key, {})

        for jid, jid_data in day_data.items():
            meal_key = jid_map.get(jid)
            if not meal_key:
                # Fallback: single-jid schools are almost always lunch
                meal_key = "lunch"
                if len(jid_map) == 0:
                    warnings.append(
                        f"nastavenia missing – defaulting jid={jid} → lunch"
                    )

            for letter, letter_data in jid_data.items():
                if not isinstance(letter_data, dict):
                    continue

                nm_entry = nazov_menu.get(letter, {})
                # `nazovMenu[letter]` je sploštená na jeden (skratka, nazov) pár,
                # ale EduPage vie tú istú písmenovú skratku na rôznych jidoch
                # (raňajky/obed/olovrant) použiť pre úplne iný výber — potvrdené
                # na zdravebrusko feede (3.9.2026): písmeno "B" je na jid 1/3
                # (raňajky/olovrant) "sšvA"/"Klasik" (SŠ Veterinárna), ale na
                # jid 2 (obed) "dsbNM"/"NoMilk" (Deutsche Schule diéta). Sploštený
                # fallback vždy vrátil ten istý (posledný spracovaný) jid — SŠV
                # raňajky/olovrant sa tak tíško vyhodnotili ako Deutsche Schule
                # No Milk diéta namiesto Klasik menu, a zmizli z prehľadu úplne.
                # `jids[jid]`, keď existuje, je autoritatívny pre tento konkrétny jid.
                jid_entry = nm_entry.get("jids", {}).get(jid, nm_entry)
                skratka = jid_entry.get("skratka", letter)
                nazov = jid_entry.get("nazov", letter)

                rule = letter_hook(letter, skratka, nazov) if letter_hook else None
                if rule is not None and rule.skip:
                    skipped_letters.append(f"{letter}:{skratka}")
                    continue
                portion_override = rule.portion if rule else None

                flag_label: str | None = None
                unmapped_label: str | None = None
                uncertain_label: str | None = None
                if rule is not None and (rule.menu or rule.diet):
                    menu_variant = rule.menu
                    diet_name = rule.diet
                    if rule.flag:
                        flag_label = f"{letter}:{skratka}{rule.flag}"
                        attention.append(flag_label)
                else:
                    menu_variant = self.resolve_menu_variant(skratka, nazov)
                    diet_name = None
                    if menu_variant is None:
                        diet_name, diet_is_exact = (
                            self._resolve_diet_name_with_confidence(skratka, nazov)
                        )
                        canonical = allowed_by_key.get(_normalise_key(diet_name))
                        if canonical is not None:
                            diet_name = canonical
                            if diet_name == letter and letter not in nazov_menu:
                                unmapped_label = letter
                            elif not diet_is_exact:
                                # Fuzzy match (nie exaktná skratka) padol medzi povolené
                                # diéty — počty ostávajú, ale appka si nie je istá, tak
                                # to nahlási na kontrolu namiesto tichej istoty (#527).
                                uncertain_label = f"{letter}:{skratka}→{diet_name}"
                        else:
                            # Neznámu diétu NEZAHADZUJEME: skorší `continue` tu zmazal
                            # celý riadok vrátane počtu porcií, takže kuchyni chýbali
                            # jedlá a nikde to nebolo vidno (Cvernička, 17. 8. 2026).
                            # Radšej ju zapíšeme pod názvom z EduPage a nahlásime —
                            # admin ju založí v appke a od ďalšieho behu je známa.
                            unmapped_label = f"{letter}:{diet_name}"
                        if unmapped_label is not None:
                            unmapped.append(unmapped_label)
                        if uncertain_label is not None:
                            uncertain.append(uncertain_label)

                tp = letter_data.get("typ_platitela", {})
                if not isinstance(tp, dict):
                    continue

                for payer_id, payer_counts in tp.items():
                    if not isinstance(payer_counts, dict):
                        continue
                    try:
                        total = int(payer_counts.get("o", 0) or 0)
                    except (TypeError, ValueError):
                        total = 0
                    if total <= 0:
                        continue

                    payer_info = payer_map.get(str(payer_id), {})
                    payer_name = payer_info.get("name", "")
                    payer_rule = payer_hook(payer_name) if payer_hook else None
                    match_name = (
                        payer_rule.match_name
                        if payer_rule and payer_rule.match_name is not None
                        else payer_name
                    )
                    portion_name = (
                        portion_override
                        or (payer_rule.portion if payer_rule else None)
                        or payer_info.get("portion")
                        or DEFAULT_PORTION_NAME
                    )
                    payer_diet = (
                        (payer_rule.diet if payer_rule else None)
                        or payer_info.get("diet")
                        or None
                    )
                    # `force_match` znamená, že payer label je pre TENTO riadok
                    # spoľahlivejší než zdieľané menu písmeno (viď `match_prevadzka`)
                    # — potom musí vyhrať aj jeho diéta, inak by sa prevádzka opravila
                    # správne, ale diéta zostala z cudzieho (zdieľaného) písmena.
                    forced_diet = (
                        payer_rule.diet
                        if payer_rule and payer_rule.force_match
                        else None
                    )
                    effective_diet = forced_diet or diet_name or payer_diet
                    effective_menu = "A" if effective_diet else (menu_variant or "A")

                    if matches:
                        buckets = match_prevadzka(
                            matches,
                            match_name,
                            nazov,
                            skratka,
                            only_payer=bool(payer_rule and payer_rule.force_match),
                        )
                        if not buckets:
                            # Radšej nahlás neúplný scrape, než ticho zahodiť porcie.
                            unmatched.append(
                                f"{letter}:{skratka}/{payer_info.get('name', payer_id)}"
                            )
                            continue
                    else:
                        buckets = [""]

                    # Zdieľaná skratka (`mšMal,Hey`) padne viacerým prevádzkam naraz —
                    # celý počet každej z nich, nie delený. Viď `build_prevadzka_matches`.
                    for bucket in buckets:
                        if flag_label is not None:
                            attention_buckets.setdefault(bucket, set()).add(flag_label)
                        if unmapped_label is not None:
                            unmapped_buckets.setdefault(bucket, set()).add(
                                unmapped_label
                            )
                        if uncertain_label is not None:
                            uncertain_buckets.setdefault(bucket, set()).add(
                                uncertain_label
                            )

                        counts_by_meal = counts.setdefault(bucket, {})
                        meal_counts = counts_by_meal.setdefault(meal_key, {})
                        portion_counts = meal_counts.setdefault(
                            portion_name, {"menuCounts": {}, "diets": {}}
                        )
                        menu_counts = portion_counts["menuCounts"]
                        diet_counts = portion_counts["diets"]
                        menu_counts[effective_menu] = (
                            menu_counts.get(effective_menu, 0) + total
                        )
                        if effective_diet:
                            diet_counts[effective_diet] = (
                                diet_counts.get(effective_diet, 0) + total
                            )
                        if payer_rule and payer_rule.pack_separately:
                            # Napr. SŠV dospelý: payer label je jediný signál,
                            # že tento riadok treba zabaliť zvlášť, hoci
                            # porcia je zdieľaná s inou (nezabalenou) skupinou
                            # — viď `PayerRule.pack_separately` docstring.
                            pack = portion_counts.setdefault(
                                "packSeparately", {"menus": {}, "diets": {}}
                            )
                            pack["menus"][effective_menu] = (
                                pack["menus"].get(effective_menu, 0) + total
                            )
                            if effective_diet:
                                pack["diets"][effective_diet] = (
                                    pack["diets"].get(effective_diet, 0) + total
                                )

        def _clean(counts_by_meal: dict) -> dict[str, Any]:
            return {
                meal_key: meal_counts
                for meal_key, meal_counts in counts_by_meal.items()
                if meal_counts
            }

        by_prevadzka = {
            bucket: cleaned
            for bucket, counts_by_meal in counts.items()
            if bucket and (cleaned := _clean(counts_by_meal))
        }

        if matches:
            # Zlúčený pohľad pre volajúcich, ktorí split neriešia (napr. preview).
            order_data = _merge_meal_counts(by_prevadzka.values())
        else:
            order_data = _clean(counts.get("", {}))

        if unmatched:
            warnings.append(
                f"EduPage riadky bez prevádzky (nezapočítané): {sorted(set(unmatched))}"
            )

        return ScrapeResult(
            date=target_date,
            order_data=order_data,
            order_data_by_prevadzka=by_prevadzka,
            unmatched_prevadzka=sorted(set(unmatched)),
            unmapped_letters=sorted(set(unmapped)),
            unmapped_by_prevadzka={
                bucket: sorted(labels)
                for bucket, labels in unmapped_buckets.items()
                if bucket and labels
            },
            uncertain_letters=sorted(set(uncertain)),
            uncertain_by_prevadzka={
                bucket: sorted(labels)
                for bucket, labels in uncertain_buckets.items()
                if bucket and labels
            },
            warnings=warnings,
            skipped_letters=sorted(set(skipped_letters)),
            attention=sorted(set(attention)),
            attention_by_prevadzka={
                bucket: sorted(flags)
                for bucket, flags in attention_buckets.items()
                if bucket and flags
            },
        )


def _merge_meal_counts(order_datas) -> dict[str, Any]:
    """Sčítaj viac order_data (jedna na prevádzku) do jedného zlúčeného pohľadu."""
    merged: dict[str, Any] = {}
    for order_data in order_datas:
        for meal_key, portions in order_data.items():
            meal = merged.setdefault(meal_key, {})
            for portion, details in portions.items():
                target = meal.setdefault(portion, {"menuCounts": {}, "diets": {}})
                for group in ("menuCounts", "diets"):
                    for key, count in details.get(group, {}).items():
                        target[group][key] = target[group].get(key, 0) + count
                src_pack = details.get("packSeparately")
                if isinstance(src_pack, dict):
                    tgt_pack = target.setdefault(
                        "packSeparately", {"menus": {}, "diets": {}}
                    )
                    for sub in ("menus", "diets"):
                        for key, count in (src_pack.get(sub) or {}).items():
                            tgt_pack[sub][key] = tgt_pack[sub].get(key, 0) + count
    return merged


def nest_order_data_by_category(
    order_data: dict[str, Any], category_name: str
) -> dict[str, Any]:
    """Wrap flat Edupage meal data under the operation/category name."""
    category = category_name.strip() or "EduPage"
    nested: dict[str, Any] = {}

    for meal_key, meal_data in (order_data or {}).items():
        if not isinstance(meal_data, dict) or not meal_data:
            continue

        if "menuCounts" in meal_data or "diets" in meal_data:
            nested[meal_key] = {category: dict(meal_data)}
        else:
            # Already normalized by our internal categories/portion types.
            nested[meal_key] = meal_data

    return nested
