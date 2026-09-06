"""British School — skratky s koncovým "+" sú len prvá diéta, zvyšok je v payer mene.

Na rozdiel od Cvernička/Felix Karlovská/Zdravé Brúško (jedna skratka = jedna
neúplná diéta pre všetky deti na nej), tu jednu skratku zdieľajú viaceré deti s
NAVZÁJOM ODLIŠNÝMI kombináciami — napr. `nN+` má na jeden deň naraz 4 rôzne
deti so 4 rôznymi kombináciami (noNuts/noFish, noNuts/noKiwi, noNuts/noAPP/
noStr, noNuts/sezam). `letter_hook` (jeden názov na skratku) by to nevedel
rozlíšiť — preto tu beží `payer_hook`, ktorý vidí presné meno platiteľskej
skupiny (kde je celá kombinácia vypísaná).

Mechanizmus: `letter_hook` pre skratky končiace na "+" vráti `LetterRule(menu="A")`
bez `diet` — to necháva `diet_name=None` na úrovni písmena, takže `_parse`
(`effective_diet = diet_name or payer_diet`) nechá rozhodnúť `payer_hook`
namiesto generického fuzzy enginu. `menu="A"` je len placeholder — keď
`payer_diet` napokon vyhrá, `effective_menu` sa aj tak prepíše na "A".

Živé payer labely (over_edupage 26.–27.8.2026, stabilné 2 dni po sebe):

    HIT+  → "1.st. noMushroom"                    → NO HUBY
    nM+   → "1.st. noMilk+reflux"                  → NO MILK/REFLUX
            "MŠ noMilk+reflux"                     → NO MILK/REFLUX
            "Učiteľ noMilk/VEGE"                   → NO MILK/VEGGIE
    nN+   → "1.st. noNuts/noFish"                  → NO ORECH/NO FISH
            "1.st. noNuts/noKiwi"                  → NO ORECH/NO KIWI
            "2.st. noNuts/noAPP/noStr"              → NO ORECH/NO JABLKO/NO JAHODA
            "3.st. noNuts/sezam"                   → NO ORECH/NO SEZAM
    NNN+  → "MŠ nonono+pork+berr"                  → NONONO/NO BRAVCOVINA/NO BOBULE
            "MŠ nonononANAnLEG HIT"                → NONONO/NO ANANAS/NO STRUKOVINY/HISTAMIN

Payer meno, ktoré tu nie je (napr. nová kombinácia na `nP+`, dosiaľ bez dát),
necháme cez `payer_diet = None` padnúť na engine (echo raw skratky) — appka to
nahlási cez `unmapped_diets`, nie ticho zle priradí.
"""

from __future__ import annotations

import re

from ..base import LetterRule, PayerRule

_PAYER_RULES: dict[str, str] = {
    "1.ST. NOMUSHROOM": "NO HUBY",
    "1.ST. NOMILK+REFLUX": "NO MILK/REFLUX",
    "MŠ NOMILK+REFLUX": "NO MILK/REFLUX",
    "UČITEĽ NOMILK/VEGE": "NO MILK/VEGGIE",
    "1.ST. NONUTS/NOFISH": "NO ORECH/NO FISH",
    "1.ST. NONUTS/NOKIWI": "NO ORECH/NO KIWI",
    "2.ST. NONUTS/NOAPP/NOSTR": "NO ORECH/NO JABLKO/NO JAHODA",
    "3.ST. NONUTS/SEZAM": "NO ORECH/NO SEZAM",
    "MŠ NONONO+PORK+BERR": "NONONO/NO BRAVCOVINA/NO BOBULE",
    "MŠ NONONONANANLEG HIT": "NONONO/NO ANANAS/NO STRUKOVINY/HISTAMIN",
}


def _kluc(value: str) -> str:
    return (value or "").strip().upper()


def _je_vege1(skratka: str, nazov: str) -> bool:
    """VEGE1 je samostatné menu (obed), nie diéta VEGGIE — obe zdieľajú
    substring "vege", takže bez explicitnej zhody by generický
    `resolve_menu_variant`/`resolve_diet_name` skratku tíško vyhodnotil ako
    diétu VEGGIE (4.9.2026, user: "VEGE a VEGE1 sú dve iné menu")."""
    normalised = re.sub(r"[\s\-_.]+", "", (skratka or nazov or "")).upper()
    return normalised == "VEGE1"


def british_school_letter_hook(
    letter: str, skratka: str, nazov: str
) -> LetterRule | None:
    """Skratky končiace na "+" necháme bez diéty — rozhodne `payer_hook`.

    VEGE1 (4. obedové menu, popri Klasik/B/C) sa musí vyhodnotiť ako menu
    variant, nie ako fuzzy-matchnutá diéta VEGGIE."""
    if _je_vege1(skratka, nazov):
        return LetterRule(menu="VEGE1")
    if _kluc(skratka).endswith("+"):
        return LetterRule(menu="A")
    return None


def british_school_payer_hook(payer_name: str) -> PayerRule | None:
    """Priraď presnú kombináciu podľa mena platiteľskej skupiny."""
    diet = _PAYER_RULES.get(_kluc(payer_name))
    if diet is None:
        return None
    return PayerRule(diet=diet)
