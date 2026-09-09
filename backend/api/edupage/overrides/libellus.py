"""MŠ Libellus — dve skratky, kde fuzzy vrstva orezáva kombinovanú diétu na
jedno obmedzenie.

EduPage vlastný `nazov` vypisuje celý obsah jednoznačne:

    NENO   nazov="NoEgg/NoOrech" → engine chytí len "no egg" a orechy stratí
    NMNE   nazov="NoMilk/NoEgg"  → rovnaký #527 vzor ako "dsbNMNE" (zdravebrusko)
                                    a ZŠ Ivanka pri Dunaji — engine skratku chytí
                                    ako "no egg" a stratí mlieko

Nahlásené Stanom 31.8.2026. `NO EGG – NO ORECH` založené v appke 31.8.2026
(pk 124) — nezamieňať s existujúcim `NO MILK – NO ORECH`, pk 121, ktoré je
iná diéta pre iné dieťa.

`NENOnPARnMAK` (bez vajec, paradajok, orechov, maku) fuzzy-matchovala tiež
len na jedno obmedzenie — potvrdené s userom 1.9.2026, `NO EGG – NO PARADAJKA
– NO ORECH – NO MAK` (pk 127).

`sA` nazov="Stomček Klasik" (preklep za "Stromček" v EduPage) — Libellus a
Stromček zdieľajú jeden EduPage feed. Bez pravidla by `resolve_menu_variant`
chytil substring "klasik" v nazve a skratku `sA` tíško zlúčil do Libellusovho
vlastného "Klasik"/A počtu — nahlásené 3.9.2026 (živý porovnávací scrape
ukázal Škôlka A o 4 vyššie než uložená objednávka: 37 vs 33 na obede, 38 vs
34 na raňajkách).

Skôr sa `sA` presmerúval na samostatný celok Stromček (`redirect_prevadzka`,
appkový zdroj objednávok) — ukázalo sa to nespoľahlivé (appkové a EduPage
počty sa opakovane rozišli, user 9.9.2026). Namiesto presmerovania sa `sA`
teraz zapíše priamo ako diéta "Klasik STROMČEK" v rámci Libellusu — Stromček
si svoje objednávky rieši výhradne cez appku.
"""

from __future__ import annotations

from ..base import LetterRule

_RULES: dict[str, LetterRule] = {
    "NENO": LetterRule(diet="NO EGG – NO ORECH"),
    "NMNE": LetterRule(diet="NO MILK/NO EGG"),
    "NENONPARNMAK": LetterRule(diet="NO EGG – NO PARADAJKA – NO ORECH – NO MAK"),
    "SA": LetterRule(diet="Klasik STROMČEK"),
}


def _kluc(skratka: str) -> str:
    return skratka.strip().upper()


def libellus_letter_hook(letter: str, skratka: str, nazov: str) -> LetterRule | None:
    """Vráť pravidlo pre menu písmeno, alebo None → nech rozhodne engine."""
    return _RULES.get(_kluc(skratka))
