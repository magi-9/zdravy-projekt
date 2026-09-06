"""Per-prevádzka konfigurácia EduPage scrapingu.

Engine (`api.edupage_scraper`) parsuje HTML rovnako pre všetky školy. Rozdiely medzi
prevádzkami sú *dáta*, nie *kód* — držíme ich tu ako deklaratívny config a aplikujeme
až na výsledok parsovania.

Výnimka: `override_hook` pre prevádzky, kde config nestačí (Krásňanko).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from api.edupage_scraper import ScrapeResult

BREAKFAST = "breakfast"
LUNCH = "lunch"
OLOVRANT = "olovrant"


@dataclass(frozen=True)
class LetterRule:
    """Ako vyhodnotiť jedno menu písmeno, keď engine sám nestačí.

    `None` v poli = nechaj engine rozhodnúť. `portion` prebíja `porcia` kód payera —
    práve preto tento hook existuje: niektoré školy nesú porciu v menu skratke
    (Krásňanko `KZ` = dospelý), nie v payer configu.

    `skip=True` = riadok tohto písmena sa vôbec nezaráta (napr. Montessori: appka má
    počítať len 'Iná', ostatné písmená z EduPage ignorovať — user 2.9.2026). Na rozdiel
    od neznámej diéty (ktorá sa zapíše a nahlási) sa skip riadok tíško vynechá — je to
    vedomé rozhodnutie, nie chýbajúci mapping.
    """

    portion: str | None = None
    menu: str | None = None
    diet: str | None = None
    flag: str | None = None  # napr. "!" — vyžaduje manuálnu kontrolu
    skip: bool = False


# Hook beží pri parsovaní, na každé menu písmeno pred agregáciou.
LetterHook = Callable[[str, str, str], LetterRule | None]  # (letter, skratka, nazov)


@dataclass(frozen=True)
class PayerRule:
    """Ako upraviť jeden payer label, keď engine sám nestačí.

    Na rozdiel od `LetterRule` (rieši menu písmeno) beží na payer LABELI. Existuje pre
    školy, kde je v labeli zakódované niečo, čo kazí buď matching prevádzky, alebo diétu —
    typicky Školička, kde prefix `B `/`BM ` je DODÁVATEĽ (Bruško / Bruško Milk), nie
    súčasť názvu výdajne. `match_name` sa použije na priradenie prevádzky namiesto surového
    labelu; `None` polia = nechaj engine/config rozhodnúť.
    """

    match_name: str | None = (
        None  # názov pre match_prevadzka (bez dodávateľského prefixu)
    )
    diet: str | None = None
    portion: str | None = None
    # Vynúti packSeparately na riadkoch tohto payera (viď `_parse` v
    # `edupage_scraper.py`). Existuje pre skupiny, ktoré zdieľajú porciu s inou
    # skupinou (SŠV dospelý/žiak majú obaja "Dospelý (SŠ)"), takže
    # `Prevadzka.adults_pack_separately_enabled` (celoportionový prepínač) by
    # zabalil zvlášť aj tú druhú skupinu — payer label je tu jediný spoľahlivý
    # signál (user 4.9.2026).
    pack_separately: bool = False
    # `match_prevadzka` bežne uprednostní skratku menu pred payer labelom (je to
    # spoľahlivejší nosič — viď jej docstring). Zdravé Brúško raňajky/olovrant ale
    # zdieľajú skratku `dsbNMNE` (Deutsche Schule) naprieč MŠ Malokarpatským aj MŠ
    # Heyrovského — payer label pritom jednoznačne hovorí, ktorej škole riadok
    # patrí (`MŠ Mal. NoMilk` vs `MŠ Hey. NoGluten`). `force_match=True` prikáže
    # `match_prevadzka` ignorovať skratku/menu názov a matchovať LEN na
    # `match_name` (user 2.9.2026, potvrdené na live dátach).
    force_match: bool = False


# Hook beží na každý payer label pred agregáciou.
PayerHook = Callable[[str], PayerRule | None]  # (payer_name)


class OlovrantMode(StrEnum):
    """Odkiaľ berieme olovrant pre danú prevádzku.

    Viď test/data/output/olovrant_klasifikacia_2026-07-09.md — tri kategórie.
    """

    EDUPAGE = "edupage"  # C: olovrant má vlastný jid, berieme priamo
    ODVODIT_Z_OBEDU = "odvodit_z_obedu"  # A: škola olovrant neobjednáva, = obed
    MIMO_APPKY = "mimo_appky"  # B: olovrant sa účtuje iným kanálom
    NEZNAMY = "neznamy"  # zatiaľ nepotvrdené — nehádame, hlásime warning


@dataclass(frozen=True)
class PrevadzkaConfig:
    subdomena: str
    ucty: tuple[str, ...]  # účtovné názvy (1..N — split prevádzky majú viac)
    olovrant_mode: OlovrantMode
    poznamka: str = ""
    letter_hook: LetterHook | None = None
    payer_hook: PayerHook | None = None
    # Škola má "celodennú" dochádzku — raňajky sa neobjednávajú samostatne cez
    # EduPage, majú byť rovnaké ako obed (rovnaký princíp ako
    # OlovrantMode.ODVODIT_Z_OBEDU, len pre raňajky — user 2.9.2026, Pramienok
    # a Montessori Borínska MŠ).
    ranajky_z_obedu: bool = False
    # Mená prevádzok (per-prevádzka `label`, viď `_apply_olovrant_config`), pre
    # ktoré je chýbajúci olovrant pri `OlovrantMode.EDUPAGE` ŠTRUKTURÁLNY fakt,
    # nie config drift — napr. zdieľaná connection, kde len časť prevádzok
    # (MŠ) olovrant reálne objednáva a iné (ZŠ, starší žiaci) nikdy nie (user
    # 3.9.2026: ZŠ Malokarpatská, žiadny payer pre ňu sa v EduPage bloku
    # raňajok/olovrantu vôbec nevyskytuje). Bez tejto výnimky by
    # `olovrant_mode` musel platiť rovnako pre celú connection, hoci realita
    # je per-prevádzka iná.
    olovrant_missing_ok: frozenset[str] = frozenset()
    # Nahradí generický `_MEAL_BY_HOUR` (breakfast<10, lunch<15, inak olovrant)
    # pre túto prevádzku — školy s vlastnou dedikovanou EduPage connection (jedna
    # HTML stránka = jeden subjekt) môžu mať iný počet/usporiadanie denných okien.
    # British School (#British Cluster C) má 4: raňajky, desiata (nový meal_key
    # "desiata" — NIE "snack", ten string je už obsadený ako legacy alias pre
    # Olovrant, viď `_EXTRA_MEAL_KEYS` v `tasks.py`; počíta sa kusovo, rovnaká
    # pre všetkých), obed, olovrant — bez vlastných prahov by desiata
    # (hodina 10, generický prah "breakfast" je < 10) spadla do rovnakého
    # naivného košíka ako obed/olovrant a zlúčila sa pod "breakfast" (potvrdené
    # na živom mealsGuest 2026-09-07, viď `TestBuildJidMap`). `None` = použi
    # `_MEAL_BY_HOUR` (nezmenené správanie pre všetky ostatné školy).
    meal_hour_thresholds: tuple[tuple[int, str], ...] | None = None


def _apply_olovrant_config(
    order_data: dict,
    config: PrevadzkaConfig,
    config_notes: list[str] | None = None,
    label: str | None = None,
) -> dict:
    """Aplikuj olovrant config na jeden order_data slovník.

    `label` (napr. názov konkrétnej prevádzky pri viac-prevádzkovej connection) sa
    pridá do config_notes textu, aby drift bolo vidno aj vtedy, keď sa v merged
    (celok-wide) pohľade stratí — napr. Zdravé Brúško: Deutsche Schule má olovrant,
    Heyrovského/Malokarpatská ho nemajú, ale merged pohľad to prekryje (user
    2.9.2026: "zle ich čítalo, treba preveriť").
    """
    lunch = order_data.get(LUNCH)
    has_olovrant = bool(order_data.get(OLOVRANT))
    kde = f"{config.subdomena}/{label}" if label else config.subdomena

    match config.olovrant_mode:
        case OlovrantMode.ODVODIT_Z_OBEDU:
            if has_olovrant and config_notes is not None:
                # Škola začala olovrant objednávať cez EduPage → config je zastaraný.
                config_notes.append(
                    f"{kde}: olovrant_mode=odvodit_z_obedu, "
                    f"ale EduPage olovrant reálne obsahuje — over config"
                )
            if lunch:
                order_data[OLOVRANT] = copy.deepcopy(lunch)

        case OlovrantMode.MIMO_APPKY:
            if has_olovrant:
                if config_notes is not None:
                    config_notes.append(
                        f"{kde}: olovrant_mode=mimo_appky, "
                        f"ale EduPage olovrant obsahuje — over config"
                    )
                order_data.pop(OLOVRANT, None)

        case OlovrantMode.EDUPAGE:
            if (
                lunch
                and not has_olovrant
                and config_notes is not None
                and label not in config.olovrant_missing_ok
            ):
                config_notes.append(
                    f"{kde}: očakávaný olovrant z EduPage chýba (obed prítomný)"
                )

        case OlovrantMode.NEZNAMY:
            if lunch and not has_olovrant and config_notes is not None:
                config_notes.append(
                    f"{kde}: olovrant_mode nepotvrdený a olovrant chýba "
                    f"— netipujeme, treba doplniť config"
                )

    return order_data


def _apply_ranajky_config(
    order_data: dict,
    config: PrevadzkaConfig,
    config_notes: list[str] | None = None,
    label: str | None = None,
) -> dict:
    """Aplikuj `ranajky_z_obedu` na jeden order_data slovník.

    Rovnaká logika ako `_apply_olovrant_config`/`ODVODIT_Z_OBEDU`, len pre raňajky —
    škola má celodennú dochádzku, raňajky sa neobjednávajú cez EduPage samostatne.
    `label` — viď `_apply_olovrant_config`.
    """
    if not config.ranajky_z_obedu:
        return order_data

    lunch = order_data.get(LUNCH)
    has_breakfast = bool(order_data.get(BREAKFAST))
    kde = f"{config.subdomena}/{label}" if label else config.subdomena

    if has_breakfast and config_notes is not None:
        # Škola začala raňajky objednávať cez EduPage → config je zastaraný.
        config_notes.append(
            f"{kde}: ranajky_z_obedu=True, ale EduPage raňajky "
            f"reálne obsahuje — over config"
        )
    if lunch:
        order_data[BREAKFAST] = copy.deepcopy(lunch)

    return order_data


def apply_config(result: ScrapeResult, config: PrevadzkaConfig) -> ScrapeResult:
    """Aplikuj per-prevádzka pravidlá na výsledok scrapingu.

    Mutuje a vracia `result`. Prázdny deň (žiadny obed) nechávame tak — škola bola
    zatvorená, nie je to chyba.

    Nezhody configu s realitou idú do `config_notes`, nie do `warnings`: `warnings`
    znamená „scrape zlyhal, neimportuj nič" (viď `tasks.py`), a config drift takým
    zlyhaním nie je.
    """
    _apply_olovrant_config(result.order_data, config, result.config_notes)
    _apply_ranajky_config(result.order_data, config, result.config_notes)
    # Per-prevádzka drift (napr. len niektoré prevádzky viac-prevádzkovej connection
    # majú EduPage olovrant/raňajky chýbajúce) by v merged pohľade vyššie zmizlo, ak
    # čo i len jedna prevádzka dané jedlo má — preto ho hlásime aj tu, s labelom.
    for nazov, order_data in result.order_data_by_prevadzka.items():
        _apply_olovrant_config(order_data, config, result.config_notes, label=nazov)
        _apply_ranajky_config(order_data, config, result.config_notes, label=nazov)

    return result
