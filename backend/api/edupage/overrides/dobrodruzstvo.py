"""MŠ/ZŠ Dobrodružstvo — porcia kód pre "1. stupeň" payer skupiny je v EduPage
nastavení väčšinou zle nastavený.

4 z 5 "1. stupeň" platiteľských skupín (typ_platitela 3/4/9/11: "1.st.",
"1.st. ŠD", "1.st. ŠD vege", "1. st. ŠD bezlak") majú `porcia=2` namiesto
správnej `1` — len "1.st His ŠD" (typ_platitela 14) má kód správny. Appka tak
väčšinu 1. stupňa počítala do ZŠ 2.stupeň (user 3.9.2026: "spojilo 1. a 2.
stupeň"). `dobrodruzstvo_payer_hook` prepíše porciu podľa spoľahlivého
payer labelu namiesto nespoľahlivého EduPage kódu.

Zároveň diéta "bezlak" (bez laktózy) nebola v generickom keyword mape vôbec
namapovaná (registry.py poznamka: "bezlak→NO MILK, doplniť keyword mapu") —
"1. st. ŠD bezlak"/"2.st ŠD bezlak" mali prázdnu diétu. Hook to dopĺňa.

`nPAR` bol uncertain fuzzy match — potvrdené na isté, NO PARADAJKA (user
9.9.2026).
"""

from __future__ import annotations

import unicodedata

from ..base import LetterRule, PayerRule

_ZS_1_STUPEN = "ZŠ 1.stupeň"
_ZS_2_STUPEN = "ZŠ 2.stupeň"

_LETTER_RULES: dict[str, LetterRule] = {
    "NPAR": LetterRule(diet="NO PARADAJKA"),
}


def _fold(value: str) -> str:
    """ASCII-fold + len písmená a číslice veľkými (diakritika/interpunkcia
    nerozhoduje, ale číslo stupňa musí ostať zachované)."""
    decomposed = unicodedata.normalize("NFKD", (value or "").casefold())
    return "".join(ch for ch in decomposed if ch.isalnum()).upper()


def dobrodruzstvo_payer_hook(payer_name: str) -> PayerRule | None:
    """Prepíš porciu podľa payer labelu (spoľahlivý), nie podľa EduPage
    `porcia` kódu (nespoľahlivý pre "1. stupeň" na tomto feede) — a doplň
    diétu pre "bezlak" (bez laktózy), ktorú generický engine nepozná."""
    key = _fold(payer_name)

    portion: str | None = None
    if key.startswith("1ST"):
        portion = _ZS_1_STUPEN
    elif key.startswith("2ST"):
        portion = _ZS_2_STUPEN

    diet = "NO MILK" if "BEZLAK" in key else None

    if portion is None and diet is None:
        return None
    return PayerRule(portion=portion, diet=diet)


def dobrodruzstvo_letter_hook(
    letter: str, skratka: str, nazov: str
) -> LetterRule | None:
    """Vráť pravidlo pre menu písmeno, alebo None → nech rozhodne engine."""
    return _LETTER_RULES.get(_fold(skratka))
