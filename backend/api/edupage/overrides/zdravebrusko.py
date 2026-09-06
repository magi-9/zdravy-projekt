"""Zdravé Brúško — skratka "dsbNMNE" sa fuzzy-matchovala len na NO EGG.

`compact_sk.endswith("ne")` pravidlo v generickom engine chytí "no egg" skôr,
než si všimne, že skratka obsahuje aj "nm" (no milk) — "no milk" časť sa
tíško stratí. EduPage vlastný `nazov` to tentoraz vypíše priamo a
jednoznačne: `nazov="NoMilk/NoEgg"`. Rovnaká kombinácia (samostatná diéta
"No Milk NO EGG") existuje aj u MŠ Libellus v tej istej reálnej tabuľke —
nejde o výmysel, je to bežná kombinácia.

Zdieľaný feed pre 5 celkov (Deutsche Schule "dsb", MŠ Heyrovského 4 "mšHey.",
MŠ Malokarpatké nám. 6 "mšMal.", ZŠ Malokarpatská "zšla" — rozdelené cez
`edupage_match`, viď CLAUDE.md). Potvrdené s userom 1.9.2026, doplnené z
"uncertain" fuzzy matchov na isté pravidlá:
- `dsbNNN SJ` = mlieko+lepok+vajcia+sója → "NONONO – NO SOJA" (pk 125)
- `dsbNGNM` = mlieko+lepok → "NO MILK – NO GLUTEN" (pk 84)
- `zšlaNMnEnOnJ` = mlieko+vajcia+orechy+jablko → nová kombinácia (posledné
  písmeno "J" bolo pôvodne neisté, `flag="!"` žiadal manuálnu kontrolu; user
  1.9.2026 potvrdil jablko, nie jahodu — flag odstránený, diéta je istá).

User 2.9.2026 potvrdil ďalšie dve "uncertain" fuzzy matche:
- `sšvV` = SŠ Veterinárna Vege. PÔVODNE namapované ako diéta VEGGIE (poznámka
  na `PrevadzkaConfig` v `registry.py`) — user 3.9.2026 opravil: Vege je pre
  SŠV samostatný MENU výber (ako `sšvA`/Klasik, `sšvB`/Menu B), nie dietná
  úprava Klasiku. `LetterRule(diet=...)` núti `effective_menu = "A"`
  (`_parse`: diéta sa vždy sčíta aj do menuCounts.A, lebo bežne JE úpravou
  Klasiku) — pri SŠV to duplicitne napočítalo 2 vege objednávky aj do A
  (obed ukazoval A:20 namiesto správnych 18). `LetterRule(menu="V")` počíta
  Vege do vlastného menuCounts.V, bez dotyku na A.
- `zšlaNM` = ZŠ Malokarpatská, len mlieko (bez ďalších obmedzení, na rozdiel
  od `zšlaNMnEnOnJ` vyššie) → NO MILK.

`zdravebrusko_payer_hook` — raňajky/olovrant (live 2.9.2026): diétne portie MŠ
Malokarpatského aj MŠ Heyrovského tam zdieľajú menu písmeno `dsbNMNE` (Deutsche
Schule) s Deutsche Schule, lebo tento feed pre ne pri raňajkách/olovrante nemá
vlastné písmeno (na rozdiel od obeda, kde vlastné písmená majú — `MŠMAL. NM`
atď. vyššie). Bez zásahu by `match_prevadzka` tieto porcie (aj ich diétu)
pripísal Deutsche Schule, hoci payer label jasne hovorí `MŠ Mal.`/`MŠ Hey.`
(user 2.9.2026, potvrdené priamo na live dátach — `force_match=True`, viď
`PayerRule`/`match_prevadzka` docstringy).
"""

from __future__ import annotations

import unicodedata

from ..base import LetterRule, PayerRule

_RULES: dict[str, LetterRule] = {
    "DSBNMNE": LetterRule(diet="NO MILK/NO EGG"),
    "DSBNM": LetterRule(diet="NO MILK"),
    "DSBNNN SJ": LetterRule(diet="NONONO – NO SOJA"),
    "DSBNGNM": LetterRule(diet="NO MILK – NO GLUTEN"),
    "DSBNO": LetterRule(diet="NO ORECH"),
    "MŠHEY. NG": LetterRule(diet="NO GLUTEN"),
    "MŠMAL. NM": LetterRule(diet="NO MILK"),
    "MŠMAL. NG": LetterRule(diet="NO GLUTEN"),
    "ZŠLANG": LetterRule(diet="NO GLUTEN"),
    "ZŠLANMNENONJ": LetterRule(diet="NO MILK – NO EGG – NO ORECH – NO JABLKO"),
    "ZŠLANM": LetterRule(diet="NO MILK"),
    "SŠVV": LetterRule(menu="V"),
}


def _kluc(skratka: str) -> str:
    return skratka.strip().upper()


def zdravebrusko_letter_hook(
    letter: str, skratka: str, nazov: str
) -> LetterRule | None:
    """Vráť pravidlo pre menu písmeno, alebo None → nech rozhodne engine."""
    return _RULES.get(_kluc(skratka))


def _fold_letters(value: str) -> str:
    """ASCII-fold + len písmená veľkými (diakritika/interpunkcia nerozhoduje)."""
    decomposed = unicodedata.normalize("NFKD", (value or "").casefold())
    return "".join(ch for ch in decomposed if ch.isalpha()).upper()


def zdravebrusko_payer_hook(payer_name: str) -> PayerRule | None:
    """`MŠ Mal.`/`MŠ Hey.` payer label prebíja zdieľané písmeno pri raňajkách/
    olovrante (viď modul docstring) — `force_match=True` aj vlastná diéta
    odvodená z payera, nie zo zdieľaného písmena."""
    key = _fold_letters(payer_name)
    if key.startswith("MSMAL"):
        match_name = "mšMal"
    elif key.startswith("MSHEY"):
        match_name = "mšHey"
    elif "SSVDOSPEL" in key:
        # SŠV (SŠ Veterinárna) dospelí (zamestnanci) zdieľajú s "SŠV žiak" tú
        # istú porciu "Dospelý (SŠ)" — EduPage porcia kód ich nevie rozlíšiť,
        # obaja spadajú pod strednú školu. Payer label je jediný spoľahlivý
        # signál, tak ho appka vždy automaticky zabalí zvlášť — na rozdiel od
        # `Prevadzka.adults_pack_separately_enabled`, ktorý by zabalil zvlášť
        # aj žiakov zdieľajúcich tú istú porciu (user 4.9.2026).
        return PayerRule(pack_separately=True)
    else:
        return None

    parts = []
    if "NOMILK" in key:
        parts.append("NO MILK")
    if "NOGLUTEN" in key:
        parts.append("NO GLUTEN")
    # "NoBanán" (nový payer, 3.9.2026) — bez tejto zhody has_milk/has_gluten
    # jediné dve rozpoznané frázy ticho zahodili zvyšok kombinácie (napr.
    # "NoMilk/NoBanán" → len "NO MILK", banán zmizol). `force_match=True` +
    # nenulová diéta z hooku prebije aj zdieľané písmeno (`forced_diet`),
    # takže presnosť tu musí byť úplná, nie čiastočná.
    if "NOBANAN" in key:
        parts.append("NO BANÁN")
    diet = "/".join(parts) if parts else None

    return PayerRule(match_name=match_name, diet=diet, force_match=True)
