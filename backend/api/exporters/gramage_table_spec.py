"""Jediný zdroj pravdy o tom, ako vyzerá tabuľka „Gramáž jedál".

Tabuľka sa vykresľuje na dvoch miestach — na obrazovke (React) a v PDF (HTML →
WeasyPrint). Kým každé z nich rozhodovalo samo, výstupy sa rozišli v desiatkach
detailov (stĺpec navyše, `0` namiesto `—`, iné poradie poznámok, iné farby pásov).

Tento modul preto robí **všetky** rozhodnutia: ktoré riadky existujú, v akom
poradí, s akým textom, číslom a CSS triedou. Renderery už len prekladajú spec do
značiek a nemajú čo rozhodnúť, takže sa nemajú ako rozísť.

Referenciou je obrazovka — spec reprodukuje jej správanie, nie správanie starých
exportérov.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from ..utils import ADULT_PORTION_TYPE_NAME
from .gramage_dashboard_export import (
    blend_with_white,
    component_subtitle,
    diet_color,
    group_label,
    meal_hue,
    portion_summary,
    readable_text_color,
)

EMPTY = "—"

# Podfarbenie riadku, keď je diéta zložená z 3+ diét naraz (#536) — v takom
# prípade podfarbenie podľa jednej konkrétnej zložky pôsobilo náhodne, tak má
# pevnú, na kombinácii nezávislú farbu. Text riadku ostáva farbou prvej diéty.
COMBO_DIET_FALLBACK_BACKGROUND = "F97316"

# Ktoré stĺpcové skupiny patria pod ktoré jedlo. Kuchyňa čítala tabuľku ako jeden
# pás stĺpcov a hľadala, kde končia raňajky a začína obed — hlavička preto nesie
# ešte jednu, nadradenú úroveň s názvom jedla.
_MEAL_BANDS: dict[str, str] = {
    "breakfast_snack": "Raňajky / desiata",
    "soup": "Obed",
    "main_course": "Obed",
    "afternoon_snack": "Olovrant",
}
_MEAL_BAND_CSS: dict[str, str] = {
    "Raňajky / desiata": "mb-break",
    "Obed": "mb-lunch",
    "Olovrant": "mb-snack",
}

# Skratky dlhých názvov porcií (#528) — v úzkom stĺpci na papieri "ZŠ
# 1.stupeň" naťahovalo riadok, kuchyňa aj tak porcii hovorí skratkou. Mení sa
# len text v tejto tabuľke (obrazovka aj PDF), nie `PortionType.name` v DB —
# ten nesie aj EduPage mapovanie a fakturačné koeficienty.
_PORTION_ABBREVIATIONS: dict[str, str] = {
    "ZŠ 1.stupeň": "1.st",
    "ZŠ 2.stupeň": "2.st",
}


def _abbreviate_label(label: str) -> str:
    """Nahradí dlhý názov porcie skratkou, nech je kdekoľvek v texte labelu."""
    for full, short in _PORTION_ABBREVIATIONS.items():
        label = label.replace(full, short)
    return label


def _decimal_text(value: Decimal) -> str:
    """Číslo do bunky: bez chvostových núl, s desatinnou čiarkou.

    Zámerne bez `normalize()` — tá zo `2000.00` spraví `2E+3`, čo je v tabuľke
    nezmysel (rovnaká pasca ako v `_tidy_count`). Celé hodnoty preto idú cez
    `int`, zvyšku sa chvostové nuly odrežú ručne.
    """
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rounded == rounded.to_integral_value():
        return str(int(rounded))
    return format(rounded, "f").rstrip("0").rstrip(".").replace(".", ",")


def format_gram(raw: object) -> str | None:
    """Gramáž do bunky — alebo None, keď sa má zobraziť „—".

    Desatiny sa zobrazujú (`2000,5`), lebo kuchyňa ich potrebuje vidieť; celé
    hodnoty zostávajú bez chvosta (`2000`). Nula a menej sa nezobrazuje vôbec —
    tabuľka má byť riedka, nie stena núl.
    """
    if raw is None or raw == "":
        return None
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return _decimal_text(value)


def format_count(count: object) -> str:
    """Počet porcií do odznaku; „—" keď je nulový."""
    try:
        value = Decimal(str(count or 0))
    except (InvalidOperation, TypeError, ValueError):
        return EMPTY
    if value <= 0:
        return EMPTY
    return _decimal_text(value)


def _filter_col_groups(col_groups: list[dict], sections: list[str] | None) -> list[int]:
    """Indexy stĺpcových skupín, ktoré sa majú vykresliť.

    Sekcia je kľúč stĺpcovej skupiny (`breakfast_snack`, `soup`,
    `main_course_A`, `afternoon_snack` …). `sections=None` znamená kompletnú
    tabuľku; inak sa vykreslí presne to, čo si používateľ vybral — polievka
    ani menu sa navzájom nedoťahujú, každý prepínač platí sám za seba.

    Neznáme kľúče sa ignorujú a prázdny výber padne späť na kompletnú tabuľku,
    aby sa preklep v URL neprejavil prázdnou stranou.
    """
    if not sections:
        return list(range(len(col_groups)))
    wanted = {str(section) for section in sections}
    keep = [
        index
        for index, group in enumerate(col_groups)
        if str(group.get("key") or "") in wanted
    ]
    return keep or list(range(len(col_groups)))


def _gram_cells(
    col_grams: list,
    groups: list[dict],
    hues: list[str],
    snack_with_lunch: bool = False,
) -> list[dict]:
    """Bunky s gramážou pre jeden riadok, vrátane oddeľovača medzi jedlami.

    `snack_with_lunch` je `Prevadzka.olovrant_s_obedom` prevzatý z riadku
    klienta — olovrant tejto prevádzky nejde s popoludňajším rozvozom ako
    ostatné, takže namiesto bežného tónovania „Olovrant" dostane vlastnú
    (žltú) farbu, nech ho kuchyňa naloží spolu s obedom.
    """
    cells = []
    for position, (group_index, group) in enumerate(groups):
        grams = []
        if group_index < len(col_grams):
            grams = col_grams[group_index] or []
        hue = hues[position]
        if snack_with_lunch and group.get("meal") == "afternoon_snack":
            hue = "snacklunch"
        for component_index, component in enumerate(group.get("components") or []):
            raw = grams[component_index] if component_index < len(grams) else None
            text = format_gram(raw)
            separator = " meal-sep" if position > 0 and component_index == 0 else ""
            if text is None:
                cells.append({"text": EMPTY, "css": f"cell-empty{separator}"})
            else:
                cells.append(
                    {
                        "text": text,
                        "css": f"cell-num mh-{hue}-cell{separator}",
                    }
                )
    return cells


def _as_decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _sum_counts(sub_rows) -> Decimal:
    return sum((_as_decimal(sr.get("count")) for sr in sub_rows), Decimal("0"))


def _label_cell(text: str, count: object, css: str = "lbl", **extra) -> dict:
    cell = {"text": text, "css": css, "count": format_count(count)}
    cell.update(extra)
    return cell


def _diet_text_and_background(data: dict, row_like: dict) -> tuple[str, str]:
    """Farba textu a podfarbenie riadku diéty (#536).

    Jedna diéta: obe farbou tej diéty. Kombinácia dvoch: text hlavnej
    (prvej), podfarbenie sekundárnej. Kombinácia troch a viac: text prvej,
    podfarbenie pevnou oranžovou — farba jednej z troch a viac zložiek by
    pôsobila náhodne, nič konkrétne by neoznačovala.
    """
    base_colors = [
        str(color).lstrip("#").upper()
        for color in (
            row_like.get("diet_base_colors") or row_like.get("base_colors") or []
        )
        if color
    ]
    if len(base_colors) >= 3:
        return base_colors[0], COMBO_DIET_FALLBACK_BACKGROUND
    if len(base_colors) == 2:
        return base_colors[0], base_colors[1]
    own = diet_color(data, row_like)
    return own, own


def _explicit_diet_color(
    data: dict, row_like: dict, keys: tuple[str, str], data_key: str
) -> str:
    """HEX hodnota admin-om vybranej farby (`Diet.text_color`/`background_color`),
    normalizovaná bez „#“, alebo „“ keď nie je nastavená.

    `keys` pokrýva obe konvencie použité v `MealPlanService` payloade — riadok
    diéty jedného klienta nesie `diet_text_color`/`diet_background_color`,
    agregovaný súhrnný riadok nesie `text_color`/`background_color`. Keď
    riadok vlastnú hodnotu nenesie, padá sa na dátovú mapu podľa mena diéty
    (rovnaký vzor ako `diet_color`).
    """
    value = row_like.get(keys[0]) or row_like.get(keys[1])
    if not value:
        name = (
            row_like.get("name") or row_like.get("diet_name") or row_like.get("label")
        )
        value = (data.get(data_key) or {}).get(name)
    normalized = str(value or "").lstrip("#").upper()
    return normalized if len(normalized) == 6 else ""


def _diet_style(data: dict, row_like: dict) -> tuple[str, str]:
    """Finálna, hotová farba textu a podfarbenia riadku diéty pre CSS/PDF.

    Keď má diéta (jednoduchá aj kombinovaná) explicitne nastavenú vlastnú
    farbu textu AJ pozadia (`Diet.text_color`/`background_color`), použije sa
    presne táto dvojica — bez stmavovania/blendovania, ktoré rieši len
    čitateľnosť automaticky odvodenej predvolenej palety. Iba jedna z dvoch
    nastavená sa ignoruje (nekonzistentná kombinácia by mohla byť nečitateľná)
    a spadne sa na pôvodnú logiku (`_diet_text_and_background`).
    """
    explicit_text = _explicit_diet_color(
        data, row_like, ("diet_text_color", "text_color"), "diet_text_colors"
    )
    explicit_background = _explicit_diet_color(
        data,
        row_like,
        ("diet_background_color", "background_color"),
        "diet_background_colors",
    )
    if explicit_text and explicit_background:
        return explicit_text, explicit_background

    text_hex, background_hex = _diet_text_and_background(data, row_like)
    return readable_text_color(text_hex), blend_with_white(background_hex)


def _filter_vydaje(all_vydaje: list[dict], selected: list[str] | None) -> list[int]:
    """Indexy výdajných bodov, ktoré sa majú vykresliť.

    Výdaj sa vyberá kľúčom (`A`, `B` …), nie názvom — názov je len popiska a môže
    sa zmeniť. Prázdny výber aj neznámy kľúč padnú späť na celú tabuľku (rovnako
    ako filter sekcií), aby preklep v URL nevrátil prázdnu stranu.
    """
    if not selected:
        return list(range(len(all_vydaje)))
    wanted = {str(key) for key in selected}
    keep = [
        index
        for index, vydaj in enumerate(all_vydaje)
        if str(vydaj.get("key") or "") in wanted
    ]
    return keep or list(range(len(all_vydaje)))


def _totals_from_summary(summary: list[dict]) -> list[list]:
    """Riadok CELKOM z už spočítaného súhrnu porcií.

    `data["totals"]` platí pre celý deň. Keď sa tlačí len jeden výdajný bod, sedeli
    by v pätke gramáže druhého bodu — preto sa pri filtrovaní celkom počíta z tých
    istých riadkov, z ktorých sa počítal súhrn (`portion_summary(data, rows)`
    plní gramáž do stĺpca vlastnej skupiny, viď `portion_summary`).
    """
    return [
        (
            (item.get("col_grams") or [])[index]
            if index < len(item.get("col_grams") or [])
            else []
        )
        for index, item in enumerate(summary)
    ]


def _sum_col_grams(left: list, right: list) -> list:
    """Sčíta dve serializované gramážové mriežky (list skupín × komponentov).

    Rovnaká logika ako `MealPlanService._sum_col_grams` (delenie polievky) —
    kopíruje sa sem, aby si tento modul nemusel ťahať závislosť na
    `meal_plan_service` len kvôli jednej pomocnej funkcii.
    """
    result = []
    for left_group, right_group in zip(left, right):
        if not left_group:
            result.append(right_group)
        elif not right_group:
            result.append(left_group)
        else:
            result.append(
                [
                    str((Decimal(a) + Decimal(b)).quantize(Decimal("0.01")))
                    for a, b in zip(left_group, right_group)
                ]
            )
    return result


def _composite_meal_count_text(
    meal_counts: dict[str, object], visible_bands: tuple[tuple[str, ...], ...]
) -> str:
    """„0 + 11 + 8" — jedno číslo za KAŽDÝ pás jedla, ktorý má tabuľka ako
    stĺpec (`visible_bands`), nie len tie, čo tento riadok reálne má —
    chýbajúci pás dostane „0", nie medzeru, nech je vidno, že tabuľka
    raňajky/olovrant má, len ich tento riadok neobjednal. Bez R/Ob/Ol
    skratky pred číslom — len duplikovala stĺpec, pod ktorým číslo aj tak
    stálo.
    """
    parts = []
    for keys in visible_bands:
        total = sum((_as_decimal(meal_counts.get(key)) for key in keys), Decimal("0"))
        parts.append(_decimal_text(total))
    return " + ".join(parts) if parts else EMPTY


def _visible_meal_bands(groups: list) -> tuple[tuple[str, ...], ...]:
    """Ktoré z troch pásiem jedla (`_CLUSTER_SUMMARY_MEAL_BANDS`) má TÁTO
    tabuľka reálne ako stĺpce — po filtri sekcií (`sections`), nie fixne
    všetky tri. `_composite_meal_count_text` chýbajúci pás nemá vypisovať
    ako „0", lebo by fabrikoval jedlo, ktoré tabuľka vôbec nezobrazuje
    (napr. tlač len obeda).
    """
    present = {str(group.get("meal") or "") for _, group in groups}
    return tuple(keys for keys, _ in _CLUSTER_SUMMARY_MEAL_BANDS if present & set(keys))


def _merge_sub_rows_across_meals(sub_rows: list[dict]) -> list[dict]:
    """Zlúči „štandard"/„diéta" riadky tej istej porcie naprieč jedlami (#527).

    Predtým mala jedna porcia až tri riadky (raňajky/obed/olovrant) s
    rovnakým menom, len iným počtom a gramážou — teraz je to jeden riadok,
    počet nesie rozpis `R 12 + Ob 12 + Ol 10` (`_composite_meal_count_text`)
    a gramáž sa spojí, keďže patrí do disjunktných stĺpcov (jeden riadok má
    dáta len vo „svojich" stĺpcoch, inde prázdno — viď `_col_grams` v
    `MealPlanService`, odtiaľ táto štruktúra pochádza).

    "zvlast"/"zvlast_gn" riadky (balenie zvlášť) majú v labeli vlastný odkaz
    na konkrétne jedlo ("... - zvlášť") a zlúčenie by muselo prepisovať aj
    text, nie len počet — ostávajú preto nezlúčené, jeden riadok na jedlo,
    presne ako doteraz.

    "Dospelý (SŠ)" má na rozdiel od ostatných porcií viac menu variantov,
    ktoré kuchyňa chce vidieť oddelene (klasik/vege...) — pre túto porciu sa
    preto zlučuje len naprieč jedlami (rovnaký variant), nie naprieč
    variantmi (viď `variant` v kľúči nižšie a `base_label` v `_client_rows`).
    """
    merged: dict[tuple, dict] = {}
    out: list[dict] = []
    for sub_row in sub_rows:
        if sub_row.get("type") not in ("standard", "diet"):
            out.append(sub_row)
            continue
        portion_name = sub_row.get("portion_name", "")
        key = (
            sub_row["type"],
            portion_name,
            sub_row.get("diet_name", ""),
            (
                sub_row.get("variant", "")
                if portion_name == ADULT_PORTION_TYPE_NAME
                else ""
            ),
        )
        existing = merged.get(key)
        if existing is None:
            clone = dict(sub_row)
            clone["_meal_counts"] = {sub_row.get("meal"): sub_row.get("count")}
            merged[key] = clone
            out.append(clone)
            continue
        existing["col_grams"] = _sum_col_grams(
            existing["col_grams"], sub_row["col_grams"]
        )
        existing["count"] = _as_decimal(existing["count"]) + _as_decimal(
            sub_row.get("count")
        )
        # Viac variantov toho istého jedla (Menu B + Menu C obeda) musí
        # sčítať, nie prepísať — inak "Ob" v rozpise ukáže len posledný
        # variant a stratí zvyšok (3.9.2026: Little Big Dospelý SŠ mal
        # v tabuľke "Ob 6" namiesto "Ob 12" pri B:6 + C:6).
        meal = sub_row.get("meal")
        existing["_meal_counts"][meal] = _as_decimal(
            existing["_meal_counts"].get(meal, 0)
        ) + _as_decimal(sub_row.get("count"))
    return out


def _aggregate_diet_summary(rows_for_summary: list[dict]) -> list[dict]:
    """Diétny súhrn naprieč viacerými klientskymi riadkami (pre Sumár X/dokopy).

    Každý klientský riadok už nesie vlastný `diet_summary_rows` (count +
    col_grams per diéta v tom riadku) — táto funkcia ich len sčíta naprieč
    zadanou skupinou, rovnako ako sa per-klient diéty sčítavajú vnútri
    jedného riadku.
    """
    totals: dict[str, dict] = {}
    order: list[str] = []
    for row in rows_for_summary:
        for diet in row.get("diet_summary_rows") or []:
            name = str(diet.get("name") or "")
            if not name:
                continue
            if name not in totals:
                totals[name] = {
                    "name": name,
                    "color": diet.get("color"),
                    "base_colors": diet.get("base_colors") or [],
                    "text_color": diet.get("text_color"),
                    "background_color": diet.get("background_color"),
                    "count": Decimal("0"),
                    "col_grams": [[] for _ in (diet.get("col_grams") or [])],
                    # Rozpis podľa jedla (#560) — `count` je plochý súčet cez
                    # raňajky/obed/olovrant, ktorý by rovnaké dieťa objednané na
                    # viac jedál rátal viackrát; zobrazenie použije radšej tento
                    # rozpis, viď `_diet_name_rows`.
                    "meal_counts": {},
                }
                order.append(name)
            entry = totals[name]
            entry["count"] += _as_decimal(diet.get("count"))
            entry["col_grams"] = _sum_col_grams(
                entry["col_grams"], diet.get("col_grams") or []
            )
            for meal, count in (diet.get("meal_counts") or {}).items():
                entry["meal_counts"][meal] = _as_decimal(
                    entry["meal_counts"].get(meal, 0)
                ) + _as_decimal(count)
    return [totals[name] for name in order]


def _diet_name_rows(
    rows_for_summary: list[dict],
    data: dict,
    groups: list[dict],
    hues: list[str],
) -> list[dict]:
    """Rozpad „koľko z ktorej diéty" naprieč danou skupinou klientov —
    doplnkový detail pod riadkami sekcie SUMÁR DIÉTY (#532), po mene diéty
    namiesto po stĺpcovej skupine.

    Vizuálne totožné s per-klientským diétnym súhrnom (`summary-diet`), len
    sčítané naprieč všetkými klientmi v danej skupine — admin/kuchyňa vidí
    diétny rozpad aj na úrovni celého klastra/dňa, nielen jedného klienta.
    """
    visible_bands = _visible_meal_bands(groups)
    diet_rows: list[dict] = []
    for diet in _aggregate_diet_summary(rows_for_summary):
        if not diet["count"]:
            continue
        text_hex, background_hex = _diet_style(data, diet)
        label_cell = _label_cell(
            diet["name"],
            diet["count"],
            swatch={
                "color": f"#{diet_color(data, diet)}",
                "base_colors": diet.get("base_colors") or [],
            },
        )
        # Viac ako jeden pás jedla v tabuľke (#560) — plochý `count` by rátal
        # to isté dieťa na raňajkách/obede/olovrante viackrát, rozpis
        # "0 + x + y" ukáže reálny počet za každý pás zvlášť (aj nulový,
        # keď ho tabuľka má, len táto diéta ho neobjednala).
        meal_counts = diet.get("meal_counts") or {}
        if len(visible_bands) > 1:
            label_cell["count"] = _composite_meal_count_text(meal_counts, visible_bands)
        diet_rows.append(
            {
                "kind": "summary-diet",
                "css": "summ-diet",
                "color": f"#{text_hex}",
                "background": f"#{background_hex}",
                "cells": [label_cell]
                + _gram_cells(diet.get("col_grams") or [], groups, hues),
            }
        )
    return diet_rows


def build_table_spec(
    data: dict,
    sections: list[str] | None = None,
    vydaje: list[str] | None = None,
    include_summary_rows: bool = True,
    show_empty: bool = False,
    show_cluster_summary: bool = True,
    diet_clusters: list[str] | None = None,
) -> dict:
    """Prevedie payload z `gramage_dashboard()` na hotový popis tabuľky.

    `include_summary_rows=False` vynechá per-klientske "Súčet bez diét" a
    diétne súhrnné riadky (`summary-std`/`summary-diet`). Na obrazovke majú
    zmysel len pri zbalenom klientovi (#510) — v statickom PDF exporte sú
    sub-riadky vždy "rozbalené" a súhrny by len duplikovali čísla o riadok
    vyššie, takže PDF volajúci túto funkciu volajú s `False`.

    `show_empty=True` (nastavenia tabuľky, 2.9.2026) vykreslí aj trasy bez
    jedinej objednávky — inak sa v pôvodnom (default) správaní ticho
    preskočia (#464-466 nižšie), čo pri chýbajúcich dátach vyzerá ako "trasa
    neexistuje", nie "trasa je prázdna".

    `show_cluster_summary=False` vynechá pásy "SUMÁR CLUSTER ... S DIÉTAMI
    MŠ" (per-cluster, kombinovaný aj celkový v pätke) — nedotýka sa
    "CELKOM (g/ml)" ani "SUM TOTAL OBED MŠ", tie sú iný typ súčtu.

    `diet_clusters` (zoznam `vydaj["key"]`, napr. `["A", "C"]`) obmedzí
    diétny rozpis v cluster summary blokoch len na vymenované clustre —
    `None` (default) = diéty vo všetkých zobrazených clustroch, tak ako
    doteraz. Kombinovaný súhrn (prvé dva/celkový v pätke) diéty ukáže, ak ich
    má zapnutý aspoň jeden z clustrov, ktoré do neho patria.
    """
    diet_cluster_keys = None if diet_clusters is None else set(diet_clusters)

    def _cluster_shows_diets(*keys: str) -> bool:
        if diet_cluster_keys is None:
            return True
        return any(key in diet_cluster_keys for key in keys)

    all_groups = data.get("col_groups") or []
    keep = _filter_col_groups(all_groups, sections)
    groups = [(index, all_groups[index]) for index in keep]
    hues = [meal_hue(g.get("meal"), g.get("variant")) for _, g in groups]

    total_components = sum(len(g.get("components") or []) for _, g in groups)
    # 1 = názov prevádzky/riadku.
    total_columns = 1 + total_components

    header = _build_header(groups, hues)
    rows: list[dict] = []

    all_vydaje = data.get("vydaje") or []
    keep_vydaje = _filter_vydaje(all_vydaje, vydaje)
    shown_vydaje = [all_vydaje[index] for index in keep_vydaje]
    # Filter na konkrétny výdajný bod je „vytlač túto tabuľku" — nepriradené
    # prevádzky doň nepatria a v celej tabuľke sa aj tak ukážu.
    filtered = len(shown_vydaje) != len(all_vydaje)
    if shown_vydaje:
        # Klastre 1 a 2 (spravidla Vydaj A a B) chcú navyše spoločný medzisúčet
        # — kým klaster 3 (British School, #531) je nová, samostatná trasa.
        # Viazané na POZÍCIU v `shown_vydaje`, nie na Vydaj.key: pri filtrovanej
        # tlači je poradie stále "prvý zobrazený, druhý zobrazený", takže sa to
        # správa rozumne aj keď sa niekedy vynechá stredný klaster z výberu.
        first_two_rows: list[dict] = []
        first_two_names: list[str] = []
        first_two_keys: list[str] = []
        for position, vydaj in enumerate(shown_vydaje):
            # Výdajný bod je najvyššia úroveň tabuľky — v tlači ide každý na
            # vlastný list, nech si ho jeho obsluha vezme celý.
            rows.append(
                _band(
                    "block-band",
                    vydaj.get("name") or "",
                    total_columns,
                    css="band block-band" + (" page-break" if position else ""),
                )
            )
            first_route_in_block = True
            for route in vydaj.get("routes") or []:
                route_rows = route.get("rows") or []
                # Prázdne trasy sa v default móde preskakujú (`show_empty`
                # ich vie ukázať — 2.9.2026).
                if not route_rows and not show_empty:
                    continue
                # Každá trasa na vlastný list — okrem prvej v bloku, tá už má
                # nový list od `block-band` vyššie (inak by ostal prázdny
                # list len s hlavičkou výdajného bodu).
                rows.append(
                    _route_row(
                        route, total_columns, page_break=not first_route_in_block
                    )
                )
                first_route_in_block = False
                for client_row in route_rows:
                    rows.extend(
                        _client_rows(
                            client_row,
                            data,
                            groups,
                            hues,
                            total_columns,
                            include_summary_rows,
                        )
                    )
            vydaj_rows = [
                r
                for route in vydaj.get("routes") or []
                for r in route.get("rows") or []
            ]
            cluster_name = vydaj.get("name") or ""
            cluster_key = str(vydaj.get("key") or "")
            # `summary_only` klastre (British School, Cluster C, #531) nemajú
            # per-klientske riadky (žiadne menu-šablóny, žiadna gramáž) — ich
            # kusový/MŠ sumár je postavený inak (`british_cluster_summary`) a
            # nesmie sa miešať do "Cluster A + B" medzisúčtu, ten počíta s
            # rovnakým (gram-plánovým) zdrojom dát ako jeho zložky.
            if vydaj.get("summary_only"):
                rows.extend(
                    _british_summary_rows(
                        [cluster_name],
                        vydaj.get("british_summary") or [],
                        total_columns,
                    )
                )
                continue
            if position < 2:
                first_two_rows.extend(vydaj_rows)
                first_two_names.append(cluster_name)
                first_two_keys.append(cluster_key)
            if show_cluster_summary:
                rows.extend(
                    _cluster_summary_rows(
                        [cluster_name],
                        vydaj_rows,
                        data,
                        groups,
                        hues,
                        total_columns,
                        include_diets=_cluster_shows_diets(cluster_key),
                    )
                )
            # Presne 2 zobrazené klastre: kombinovaný súhrn by bol identický
            # s celkovým — zbytočná duplicita pre bežný prípad (Vydaj A/B bez
            # tretieho klastra). Zmysel má, až keď je aj tretí (British
            # School), voči ktorému sa medzisúčet prvých dvoch odlišuje.
            if position == 1 and len(shown_vydaje) > 2 and show_cluster_summary:
                rows.extend(
                    _cluster_summary_rows(
                        first_two_names,
                        first_two_rows,
                        data,
                        groups,
                        hues,
                        total_columns,
                        include_diets=_cluster_shows_diets(*first_two_keys),
                    )
                )
        unassigned = [] if filtered else (data.get("unassigned_rows") or [])
        if unassigned:
            rows.append(
                _band(
                    "block-band",
                    "Nepriradené prevádzky",
                    total_columns,
                    css="band block-band page-break",
                )
            )
            for client_row in unassigned:
                rows.extend(
                    _client_rows(
                        client_row,
                        data,
                        groups,
                        hues,
                        total_columns,
                        include_summary_rows,
                    )
                )
    else:
        for client_row in data.get("rows") or []:
            rows.extend(
                _client_rows(
                    client_row, data, groups, hues, total_columns, include_summary_rows
                )
            )

    if filtered:
        visible_rows = [
            row
            for vydaj in shown_vydaje
            for route in vydaj.get("routes") or []
            for row in route.get("rows") or []
        ]
        totals_summary = portion_summary(data, visible_rows)
        footer_totals = _totals_from_summary(totals_summary)
        footer_rows = visible_rows
    else:
        totals_summary = portion_summary(data)
        footer_totals = data.get("totals") or []
        footer_rows = data.get("rows") or []
    # Počty na CELKOM riadok (#totals-row-count) — vždy z `portion_summary`,
    # aj v nefiltrovanej vetve, kde sa gramáž berie priamo z `data["totals"]`
    # (rovnaký denný súhrn, len sa preň netreba znova prechádzať cez rows).
    footer_counts = [item.get("count") or 0 for item in totals_summary]

    # `summary_only` klastre (British School) nemajú čo prispieť do tohto
    # gram-plánového kombinovaného súčtu (žiadne sub_rows/col_grams) — ich
    # meno by tam len klamlivo viselo bez zodpovedajúcich čísel.
    _footer_vydaje = [v for v in shown_vydaje if not v.get("summary_only")]
    footer_names = [v.get("name") or "" for v in _footer_vydaje]
    footer_keys = [str(v.get("key") or "") for v in _footer_vydaje]
    footer: list[dict] = (
        _cluster_summary_rows(
            footer_names,
            footer_rows,
            data,
            groups,
            hues,
            total_columns,
            include_diets=_cluster_shows_diets(*footer_keys),
        )
        if show_cluster_summary
        else []
    )
    footer.append(_totals_row(footer_totals, footer_counts, keep, groups, hues))
    # Posledný riadok pätky: súčet OBEDA (polievka + hlavné jedlo) na MŠ
    # porcie naprieč VŠETKÝMI zobrazenými klastrami (Cluster A+B+C) —
    # rovnaký prepočet cez katalógový `PortionType.coefficient`, aký má
    # každý jednotlivý klastrový súhrn (`_cluster_ms_totals`), len sčítaný
    # dokopy. Nie fakturačný `billing_portion_coefficients` súčet naprieč
    # všetkými jedlami (predošlé „Spolu prepočítané na MŠ porcie").
    obed_total = next(
        (
            item["total"]
            for item in _cluster_ms_totals(footer_rows, groups)
            if item["label"] == "Obed"
        ),
        Decimal("0"),
    )
    footer.append(
        {
            "kind": "total-ms-porcie",
            "css": "total-ms-porcie",
            "cells": [
                {
                    "label": "SUM TOTAL OBED MŠ",
                    "text": format_count(obed_total),
                    "colspan": total_columns,
                }
            ],
        }
    )

    return {
        "date": data.get("date"),
        "total_columns": total_columns,
        "header": header,
        "rows": rows,
        "footer": footer,
        # Prepínače pre UI — zo VŠETKÝCH skupín, nie z filtrovaných, inak by
        # sa odškrtnutá sekcia už nedala zapnúť späť.
        "sections": [
            {
                "key": str(group.get("key") or ""),
                "label": group_label(group),
                "selected": index in set(keep),
            }
            for index, group in enumerate(all_groups)
        ],
        # Prepínače výdajných bodov — tiež zo VŠETKÝCH, nech sa odfiltrovaný dá
        # zapnúť späť.
        "vydaje": [
            {
                "key": str(vydaj.get("key") or ""),
                "name": str(vydaj.get("name") or ""),
                "selected": index in set(keep_vydaje),
            }
            for index, vydaj in enumerate(all_vydaje)
        ],
    }


def _meal_band_cells(groups: list[dict]) -> list[dict]:
    """Nadradený pás hlavičky: Raňajky / Obed / Olovrant.

    Susedné stĺpcové skupiny toho istého jedla sa zlejú do jednej bunky (polievka
    a všetky menu tvoria jeden „Obed"), takže hranica medzi jedlami je vidieť ako
    jeden švík, nie ako séria malých nadpisov.
    """
    cells: list[dict] = []
    for _, group in groups:
        span = len(group.get("components") or [])
        if not span:
            continue
        label = _MEAL_BANDS.get(str(group.get("meal") or ""), "Ostatné")
        if cells and cells[-1]["text"] == label:
            cells[-1]["colspan"] += span
            continue
        css = _MEAL_BAND_CSS.get(label, "mb-other")
        separator = " meal-sep" if cells else ""
        cells.append(
            {"text": label, "css": f"mealband {css}{separator}", "colspan": span}
        )
    return cells


def _build_header(groups: list[dict], hues: list[str]) -> dict:
    group_cells = []
    component_cells = []
    for position, (_, group) in enumerate(groups):
        components = group.get("components") or []
        separator = " meal-sep" if position > 0 else ""
        group_cells.append(
            {
                "text": group_label(group),
                "sub": group.get("template_name") or "",
                "css": f"grp mh-{hues[position]}-1{separator}",
                "colspan": len(components),
            }
        )
        for component_index, component in enumerate(components):
            component_separator = (
                " meal-sep" if position > 0 and component_index == 0 else ""
            )
            component_cells.append(
                {
                    "text": component.get("label") or "",
                    "sub": component_subtitle(component),
                    "css": f"comp mh-{hues[position]}-2{component_separator}",
                }
            )
    return {
        "corner": "Prevádzka / Riadok",
        "meals": _meal_band_cells(groups),
        "groups": group_cells,
        "components": component_cells,
    }


def _band(kind: str, text: str, total_columns: int, css: str = "band") -> dict:
    return {
        "kind": kind,
        "css": css,
        "cells": [{"text": text, "colspan": total_columns}],
    }


def _route_row(route: dict, total_columns: int, page_break: bool = False) -> dict:
    meta = [
        (route.get("departure_time") or "")[:5],
        route.get("driver") or "",
    ]
    return {
        "kind": "route",
        "css": "route-row" + (" page-break" if page_break else ""),
        "cells": [
            {
                "text": route.get("name") or "",
                "sub": " / ".join(part for part in meta if part),
                "colspan": total_columns,
            }
        ],
    }


def _client_rows(
    row: dict,
    data: dict,
    groups: list[dict],
    hues: list[str],
    total_columns: int,
    include_summary_rows: bool = True,
) -> list[dict]:
    """Klientsky pás, jeho podriadky, poznámky a medzisúčty — v poradí obrazovky.

    `include_summary_rows=False` (PDF, #510) vynecháva medzisúčty na konci —
    v statickom exporte sú sub-riadky vždy rozbalené, takže by len duplikovali
    čísla, ktoré sú už vypísané vyššie.
    """
    key = str(row.get("row_key") or row.get("client_id") or row.get("client") or "")
    snack_with_lunch = bool(row.get("snack_with_lunch"))
    # Pásy jedla (Raňajky/Obed/Olovrant), ktoré má TÁTO tabuľka ako stĺpce —
    # `_composite_meal_count_text` nižšie ním zaplní aj pásy, ktoré tento
    # riadok/klient nemá, nulou (nie medzerou), presne raz na klienta.
    visible_bands = _visible_meal_bands(groups)

    # Zlúčenie musí ísť pred filtrom viditeľnosti — potrebuje plné pole
    # `col_grams` (všetky jedlá), nie len tie, čo prežili výber sekcií nižšie.
    merged_sub_rows = _merge_sub_rows_across_meals(row.get("sub_rows") or [])

    # Počty sa sčítavajú z riadkov, ktoré filter naozaj nechal — inak by na
    # obedovom hárku svietil súčet vrátane raňajok a olovrantu.
    visible: list[tuple[dict, list[dict]]] = []
    for sub_row in merged_sub_rows:
        gram_cells = _gram_cells(
            sub_row.get("col_grams") or [], groups, hues, snack_with_lunch
        )
        # Riadok bez jediného čísla vo viditeľných stĺpcoch nemá čo povedať.
        if any("cell-num" in cell["css"] for cell in gram_cells):
            visible.append((sub_row, gram_cells))

    # "zvlast"/"zvlast_gn" riadky sú komplementárna podmnožina toho istého
    # "standard"/"diet" riadku (súčet je celkový počet - viď MealPlanService,
    # kde sa "zabaliť zvlášť" počty odpočítavajú z "čistého" riadku), preto sa
    # tu rátajú spolu s ním podľa toho, či majú `diet_name`, nie podľa `type`,
    # inak by "spolu porcií" nižšie ukazovalo menej ľudí, než reálne objednalo.
    standard_count = _sum_counts(
        sub_row for sub_row, _ in visible if not sub_row.get("diet_name")
    )
    # Rozpis štandardného počtu podľa jedla — rovnaký princíp ako
    # `diet_meal_counts` nižšie, len bez diét. „Súčet bez diét" ho použije
    # namiesto plochého čísla, nech je hneď vidno "0 + 12 + 8", nie len "20".
    standard_meal_counts: dict[str, Decimal] = {}
    for sub_row, _ in visible:
        if sub_row.get("diet_name"):
            continue
        meal_counts = sub_row.get("_meal_counts") or {
            sub_row.get("meal"): sub_row.get("count")
        }
        for meal, count in meal_counts.items():
            if not meal:
                continue
            standard_meal_counts[meal] = standard_meal_counts.get(
                meal, Decimal("0")
            ) + _as_decimal(count)
    diet_counts: dict[str, Decimal] = {}
    # Rozpis diétneho počtu podľa jedla (#560) — `_meal_counts` na zlúčenom
    # sub-riadku (viď `_merge_sub_rows_across_meals`) drží, koľko z tejto
    # diéty patrí raňajkám/obedu/olovrantu zvlášť. `diet_counts` nižšie ostáva
    # plochý súčet pre "spolu porcií" (to je reálny počet pripravovaných
    # porcií, sčítanie je tam správne) — rozpis sa použije len na zobrazenie
    # riadku diéty, nech sa jedno dieťa na troch jedlách nepočíta 3×.
    diet_meal_counts: dict[str, dict[str, Decimal]] = {}
    for sub_row, _ in visible:
        if not sub_row.get("diet_name"):
            continue
        name = str(sub_row.get("diet_name") or "")
        diet_counts[name] = diet_counts.get(name, Decimal("0")) + _as_decimal(
            sub_row.get("count")
        )
        meal_counts = sub_row.get("_meal_counts") or {
            sub_row.get("meal"): sub_row.get("count")
        }
        bucket = diet_meal_counts.setdefault(name, {})
        for meal, count in meal_counts.items():
            if not meal:
                continue
            bucket[meal] = bucket.get(meal, Decimal("0")) + _as_decimal(count)
    diet_total = sum(diet_counts.values(), Decimal("0"))

    meta = f"štandard {format_count(standard_count)}"
    if diet_total:
        meta += f", diéty {format_count(diet_total)}"

    # #513 — poznámka prevádzky (nastavenie „Poznámka k objednávke") je vidno
    # hneď na zbalenom riadku klienta. Predtým žila len v `collapsible`
    # sub-riadku, takže kým sa klient nerozbalil, admin o nej nevedel; ten
    # sub-riadok už nie je, aby text nebol v tabuľke dvakrát. Pôvodne šla do
    # samostatného úzkeho stĺpca Poznámka — dlhší text tam ale zalamoval
    # a naťahoval riadok na viacero riadkov (klient hlásenie), preto ide
    # rovno za názov prevádzky; samostatný stĺpec Poznámka je odvtedy zbytočný
    # a bol zrušený.
    admin_order_note = str(row.get("admin_order_note") or "").strip()
    # Poznámka k „Špeciálnej" diéte — kuchyňa inak nemá odkiaľ vedieť, čo pre
    # dieťa nabrať (samotný názov diéty „Špeciálna" nič nehovorí). Ide do tej
    # istej bunky ako admin_order_note, nech je vidno hneď na zbalenom riadku.
    special_diet_note = str(row.get("special_diet_note") or "").strip()
    note_parts = []
    if special_diet_note:
        note_parts.append(f"Špeciálna diéta: {special_diet_note}")
    if admin_order_note:
        note_parts.append(admin_order_note)
    combined_note = " · ".join(note_parts)

    out: list[dict] = [
        {
            "kind": "client",
            "css": "client-row",
            "group_id": key,
            # Kuchyňa vešia na klientsky riadok odklikávanie naloženia (#487),
            # a potrebuje k tomu prevádzku ako číslo — nie parsovanie `group_id`.
            "prevadzka_id": row.get("prevadzka_id"),
            "cells": [
                {
                    "text": row.get("client") or "",
                    "note": combined_note or None,
                    "meta": meta,
                    "meta_right": (
                        f"spolu porcií {format_count(standard_count + diet_total)}"
                    ),
                    "colspan": total_columns,
                },
            ],
        }
    ]

    # Každý druhý podriadok dostane pruh (`zebra`) — na papieri je tabuľka
    # široká a oko bez neho stráca riadok. Parita sa počíta v rámci jednej
    # prevádzky, aby pruhy nezáviseli od toho, koľko riadkov mala tá nad ňou.
    for position, (sub_row, gram_cells) in enumerate(visible):
        row_type = sub_row.get("type")
        is_diet = row_type == "diet"
        zebra = " zebra" if position % 2 else ""
        # Zlúčený „štandard" riadok (#527) už nepatrí jednému jedlu — meno
        # jedla z pôvodného labelu ("Dospelý - Obed") nahrádza čisté meno
        # porcie, rozpis na jedlá nesie počet nižšie. "zvlast"/"zvlast_gn" sa
        # nezlučujú, ich label si drží meno jedla ako doteraz.
        #
        # "Dospelý (SŠ)" je výnimka — zlučuje sa len naprieč jedlami, nie
        # naprieč menu variantmi (viď `_merge_sub_rows_across_meals`), takže
        # si variant musí niesť ďalej v labeli, inak by "Menu A" a "Menu B"
        # riadky vyzerali identicky.
        portion_name = sub_row.get("portion_name") or ""
        variant = sub_row.get("variant") or ""
        if (
            row_type == "standard"
            and portion_name == ADULT_PORTION_TYPE_NAME
            and variant
        ):
            base_label = f"{portion_name} - Menu {variant}"
        elif row_type == "standard":
            base_label = portion_name or sub_row.get("label") or ""
        else:
            base_label = sub_row.get("label") or ""
        label = _abbreviate_label(base_label)
        # Interná poznámka k dvojici (prevádzka, diéta) — nastavená v detaile
        # prevádzky (tab Diéty) — ide rovno za názov diéty, nech ju kuchyňa
        # vidí aj v statickom PDF (tam sú tieto sub-riadky vždy rozbalené).
        diet_note = str(sub_row.get("diet_note") or "").strip() if is_diet else ""
        display_label = f"↳ {label}" if is_diet else label
        if diet_note:
            display_label = f"{display_label} — {diet_note}"
        cell = _label_cell(
            display_label,
            sub_row.get("count"),
        )
        # "zvlast"/"zvlast_gn" riadky sa naprieč jedlami nikdy nezlučujú (viď
        # `_merge_sub_rows_across_meals`) — nemajú preto `_meal_counts`, len
        # svoje vlastné (jedno) jedlo. Bez tohto fallbacku by composite text
        # počítal z prázdneho slovníka a reálny počet nahradil samými nulami.
        meal_counts = sub_row.get("_meal_counts") or {
            sub_row.get("meal"): sub_row.get("count")
        }
        if len(visible_bands) > 1:
            cell["count"] = _composite_meal_count_text(meal_counts, visible_bands)
        text_hex = background_hex = None
        if is_diet:
            text_hex, background_hex = _diet_style(data, sub_row)
            cell["swatch"] = {
                "color": f"#{diet_color(data, sub_row)}",
                "base_colors": sub_row.get("diet_base_colors") or [],
            }
        out.append(
            {
                "kind": "sub-row",
                "css": ("sub-row diet" if is_diet else "sub-row") + zebra,
                "group_id": key,
                "collapsible": True,
                "color": f"#{text_hex}" if is_diet else None,
                "background": f"#{background_hex}" if is_diet else None,
                "cells": [cell] + gram_cells,
            }
        )

    # Poznámky idú PRED medzisúčty — tak ich má obrazovka. `note-admin` sa už
    # nevypisuje: odkedy má klientsky riadok vlastný stĺpec Poznámka (#513),
    # bol by ten istý text v tabuľke dvakrát.
    for kind, label, note in (("note-delivery", "Rozvoz:", row.get("delivery_note")),):
        if note and str(note).strip():
            out.append(
                {
                    "kind": kind,
                    "css": kind,
                    "group_id": key,
                    "collapsible": True,
                    "cells": [
                        {
                            "text": str(note).strip(),
                            "label": label,
                            "colspan": total_columns,
                        }
                    ],
                }
            )

    if include_summary_rows and standard_count:
        std_label_cell = _label_cell("Súčet bez diét", standard_count)
        # "0 + 12 + 8" namiesto plochých "20" — kuchyňa vidí rozpad po pásoch
        # jedla hneď na tomto (vždy viditeľnom, aj zbalenom) riadku klienta,
        # rovnaký princíp ako composite count nižšie na sub-riadkoch/diétach.
        if len(visible_bands) > 1:
            std_label_cell["count"] = _composite_meal_count_text(
                standard_meal_counts, visible_bands
            )
        out.append(
            {
                "kind": "summary-std",
                "css": "summ-std",
                "cells": [std_label_cell]
                + _gram_cells(
                    row.get("standard_col_grams") or [], groups, hues, snack_with_lunch
                ),
            }
        )
    diet_summary_rows = (
        row.get("diet_summary_rows") or [] if include_summary_rows else []
    )
    for diet in diet_summary_rows:
        name = str(diet.get("name") or "")
        # Diéta, ktorá vo viditeľných jedlách nie je, nemá čo sumarizovať.
        if name not in diet_counts:
            continue
        hex_color = diet_color(data, diet)
        text_hex, background_hex = _diet_style(data, diet)
        # Interná poznámka k dvojici (prevádzka, diéta) — pozri komentár pri
        # sub-riadku vyššie; tu ide na medzisúčtový riadok tej istej diéty.
        diet_note = str(diet.get("note") or "").strip()
        label_cell = _label_cell(
            f"{name} — {diet_note}" if diet_note else name,
            diet_counts[name],
            swatch={
                "color": f"#{hex_color}",
                "base_colors": diet.get("base_colors") or [],
            },
        )
        # Viac ako jeden pás jedla v tabuľke (#560) — plochý súčet by rátal
        # to isté dieťa na raňajkách/obede/olovrante viackrát, rozpis
        # "0 + x + y" ukáže reálny počet za každý pás zvlášť.
        meal_counts = diet_meal_counts.get(name) or {}
        if len(visible_bands) > 1:
            label_cell["count"] = _composite_meal_count_text(meal_counts, visible_bands)
        out.append(
            {
                "kind": "summary-diet",
                "css": "summ-diet",
                "color": f"#{text_hex}",
                "background": f"#{background_hex}",
                "cells": [label_cell]
                + _gram_cells(
                    diet.get("col_grams") or [], groups, hues, snack_with_lunch
                ),
            }
        )
    return out


# Jedlá zoskupené do troch pásiem pre klastrový súhrn (#532) — polievka a
# hlavné jedlo sú jeden údaj „Obed", presne ako v hlavičke tabuľky
# (`_MEAL_BANDS`). Poradie je chronologické (raňajky → obed → olovrant),
# nezávisle od poradia stĺpcov v tabuľke.
_CLUSTER_SUMMARY_MEAL_BANDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("breakfast_snack",), "Raňajky"),
    (("soup", "main_course"), "Obed"),
    (("afternoon_snack",), "Olovrant"),
)


def _cluster_short_label(name: str) -> str:
    """ "Cluster A" → "A" — krátky názov pre kombinovaný nadpis súhrnu
    ("SUMÁR CLUSTER A + B S DIÉTAMI MŠ")."""
    stripped = str(name or "").strip()
    prefix = "cluster "
    if stripped.lower().startswith(prefix):
        return stripped[len(prefix) :].strip()
    return stripped


def _cluster_summary_title(names: list[str]) -> str:
    if not names:
        return "SUMÁR S DIÉTAMI MŠ"
    if len(names) == 1:
        return f"SUMÁR {names[0].upper()} S DIÉTAMI MŠ"
    combined = " + ".join(_cluster_short_label(name) for name in names)
    return f"SUMÁR CLUSTER {combined} S DIÉTAMI MŠ"


def _cluster_diety_title(names: list[str]) -> str:
    if not names:
        return "DIÉTY"
    if len(names) == 1:
        return f"{names[0].upper()} DIÉTY"
    combined = " + ".join(_cluster_short_label(name) for name in names)
    return f"CLUSTER {combined} DIÉTY"


def _cluster_ms_totals(rows_for_summary: list[dict], groups: list[dict]) -> list[dict]:
    """Jeden riadok na jedlo (Raňajky/Obed/Olovrant), len tie, ktoré sú v
    tabuľke naozaj vidno — a súčet je `_ms_recalc` (surové hlavy × katalógový
    `PortionType.coefficient`, MealPlanService), nie fakturačný
    `billing_portion_coefficients` (#532: „ak mám porciu MŠ tak +1, ak
    dospelý +2, ak 1.st +1,25 — presne podľa toho, ako to je v katalógu
    jedál"). Sčítava štandard, diétu aj „zvlášť"/„zvlášť do GN" — tie sú
    komplementárnou podmnožinou toho istého jedla, nie navyše.

    Popri prepočítanom `total` (MŠ) nesie každý riadok aj surové `heads"
    (kusovo — koľko sa reálne objednávok/hláv za tým skrýva, pred
    prepočtom cez koeficient) — kuchyňa chcela vidieť oboje, nielen
    prepočítané číslo. Riadok „Obed" navyše dostáva rozpis `menus` po
    stĺpcových skupinách main_course s vyplneným variantom (Menu A/B/C…),
    v poradí, v akom sú v tabuľke — polievka aj menu bez variantu (žiadne
    triedenie) idú len do súčtu, nie do vlastného menu riadku.
    """
    present_meals = {group.get("meal") for _, group in groups}
    # Poradie menu variantov podľa stĺpcov tabuľky, bez duplicít — len
    # main_course skupiny s vyplneným variantom.
    menu_variants: list[str] = []
    seen_variants: set[str] = set()
    for _, group in groups:
        if group.get("meal") != "main_course":
            continue
        variant = str(group.get("variant") or "")
        if not variant or variant in seen_variants:
            continue
        seen_variants.add(variant)
        menu_variants.append(variant)

    # Objednávka môže obsahovať variant, pre ktorý sa v dennom pláne ešte
    # nenachádza gramážový stĺpec. Kusový sumár ho napriek tomu nesmie potichu
    # zahodiť (najmä Menu V) — poradie plánových stĺpcov ostáva zachované a
    # dodatočné varianty pridáme za ne v bežnom poradí menu.
    actual_variants = {
        str(sub_row.get("variant") or "")
        for row in rows_for_summary
        for sub_row in (row.get("sub_rows") or [])
        if sub_row.get("type") in ("standard", "zvlast", "zvlast_gn")
        and sub_row.get("meal") == "main_course"
        and str(sub_row.get("variant") or "")
    }
    variant_order = ("A", "B", "C", "D", "V")
    for variant in sorted(
        actual_variants - seen_variants,
        key=lambda value: (
            (
                variant_order.index(value)
                if value in variant_order
                else len(variant_order)
            ),
            value,
        ),
    ):
        seen_variants.add(variant)
        menu_variants.append(variant)

    out: list[dict] = []
    for meal_keys, label in _CLUSTER_SUMMARY_MEAL_BANDS:
        if not present_meals & set(meal_keys):
            continue
        total = Decimal("0")
        heads = Decimal("0")
        diet_heads = Decimal("0")
        diet_total = Decimal("0")
        menu_totals: dict[str, tuple[Decimal, Decimal]] = {}
        for row in rows_for_summary:
            for sub_row in row.get("sub_rows") or []:
                if sub_row.get("meal") not in meal_keys:
                    continue
                if sub_row.get("type") not in (
                    "standard",
                    "diet",
                    "zvlast",
                    "zvlast_gn",
                ):
                    continue
                sub_heads = _as_decimal(sub_row.get("_heads"))
                sub_ms = _as_decimal(sub_row.get("_ms_recalc"))
                heads += sub_heads
                total += sub_ms
                if sub_row.get("type") == "diet":
                    diet_heads += sub_heads
                    diet_total += sub_ms
                    # EduPage parser zapisuje diétu ako podmnožinu Menu A
                    # (`effective_menu = "A"`), preto patrí jej drill-down
                    # práve sem, nie navyše do celkového Obeda.
                    if sub_row.get("meal") == "main_course":
                        prev_heads, prev_ms = menu_totals.get(
                            "A", (Decimal("0"), Decimal("0"))
                        )
                        menu_totals["A"] = (
                            prev_heads + sub_heads,
                            prev_ms + sub_ms,
                        )
                    continue
                variant = str(sub_row.get("variant") or "")
                if sub_row.get("meal") == "main_course" and variant in seen_variants:
                    prev_heads, prev_ms = menu_totals.get(
                        variant, (Decimal("0"), Decimal("0"))
                    )
                    menu_totals[variant] = (prev_heads + sub_heads, prev_ms + sub_ms)
        item = {"label": label, "heads": heads, "total": total}
        if diet_heads:
            item["diets"] = {"heads": diet_heads, "total": diet_total}
        # Jediný variant by len duplikoval riadok "Obed:" priamo nad sebou —
        # rozpis má zmysel až od dvoch variantov vyššie.
        if len(menu_variants) > 1 and "main_course" in meal_keys:
            item["menus"] = [
                {
                    "label": f"Menu {variant.upper()}",
                    "heads": menu_totals.get(variant, (Decimal("0"), Decimal("0")))[0],
                    "total": menu_totals.get(variant, (Decimal("0"), Decimal("0")))[1],
                }
                for variant in menu_variants
            ]
        out.append(item)
    return out


def _british_summary_rows(
    names: list[str], meal_items: list[dict], total_columns: int
) -> list[dict]:
    """Kusový sumár pre `summary_only` klastre (British School, Cluster C,
    #531) — rovnaký vizuálny formát ako `_cluster_summary_rows`
    ("Obed: N ks / N MŠ" + rozpis Menu variantov), len `meal_items` prichádza
    už hotové z `british_cluster_summary.build_gramage_summary_only_clusters`
    (priamo z `DailyOrder.data`), nie z `_cluster_ms_totals` (ktorá číta
    `col_groups`/`sub_rows` — British nemá menu-šablóny, takže by boli
    prázdne). Žiadny diétny rozpis — ten pre Cluster C nateraz nie je
    súčasťou zadania.
    """
    rows: list[dict] = [
        _band(
            "portion-band",
            _cluster_summary_title(names),
            total_columns,
            css="portion-summary-band",
        )
    ]
    for item in meal_items:
        rows.append(
            {
                "kind": "cluster-ms-row",
                "css": "cluster-ms-row",
                "cells": [
                    {
                        "label": f"{item['label']}:",
                        "text": (
                            f"{format_count(item['heads'])} ks / "
                            f"{format_count(item['total'])} MŠ"
                        ),
                        "colspan": total_columns,
                    }
                ],
            }
        )
        for menu in item.get("menus") or []:
            rows.append(
                {
                    "kind": "cluster-ms-row",
                    "css": "cluster-ms-row cluster-ms-menu-row",
                    "cells": [
                        {
                            "label": f"{menu['label']}:",
                            "text": (
                                f"{format_count(menu['heads'])} ks / "
                                f"{format_count(menu['total'])} MŠ"
                            ),
                            "colspan": total_columns,
                        }
                    ],
                }
            )
    return rows


def _cluster_diet_count_row(diets: dict, total_columns: int) -> dict:
    """Riadok „z toho diéty" je drill-down, nie ďalšia porcia."""
    return {
        "kind": "cluster-ms-row",
        "css": "cluster-ms-row cluster-ms-diet-count-row",
        "cells": [
            {
                "label": "z toho diéty:",
                "text": (
                    f"{format_count(diets['heads'])} ks / "
                    f"{format_count(diets['total'])} MŠ"
                ),
                "colspan": total_columns,
            }
        ],
    }


def _cluster_summary_rows(
    names: list[str],
    rows_for_summary: list[dict],
    data: dict,
    groups: list[dict],
    hues: list[str],
    total_columns: int,
    include_diets: bool = True,
) -> list[dict]:
    """Celý súhrn jedného klastra (alebo kombinácie klastrov) — #532:

    „SUMÁR CLUSTER A S DIÉTAMI MŠ" a pod ním 1–3 riadky (len prítomné
    jedlá), každý ako „Obed: 3345 MŠ" — jedno číslo, štandard aj diéty
    spolu, prepočítané cez `PortionType.coefficient`. Hneď pod tým, ak sú v
    skupine nejaké diéty, „CLUSTER A DIÉTY" s rozpadom podľa mena diéty
    (`_diet_name_rows`), rovnaký ako per-klientský súhrn.

    `include_diets=False` (nastavenia tabuľky, per-cluster checkbox) vynechá
    len tento diétny rozpis — riadky "Obed:"/"Raňajky:"/"Olovrant:" ostávajú.
    """
    rows: list[dict] = [
        _band(
            "portion-band",
            _cluster_summary_title(names),
            total_columns,
            css="portion-summary-band",
        )
    ]
    for item in _cluster_ms_totals(rows_for_summary, groups):
        rows.append(
            {
                "kind": "cluster-ms-row",
                "css": "cluster-ms-row",
                "cells": [
                    {
                        "label": f"{item['label']}:",
                        "text": (
                            f"{format_count(item['heads'])} ks / "
                            f"{format_count(item['total'])} MŠ"
                        ),
                        "colspan": total_columns,
                    }
                ],
            }
        )
        diets = item.get("diets")
        diet_rendered = False
        # Pri raňajkách a olovrante patrí pod priamo pod jedlo. Pri obede sa
        # vloží až pod Menu A nižšie, kam EduPage parser diéty zaraďuje.
        if diets and not item.get("menus"):
            rows.append(_cluster_diet_count_row(diets, total_columns))
            diet_rendered = True
        # Rozpis Obedu po menu variantoch (Menu A/B/C…), odsadený pod ním —
        # kuchyňa chcela vidieť, koľko z celkového obedu pripadá na ktorý
        # variant, rovnaký kusovo/MŠ formát ako riadok vyššie.
        for menu in item.get("menus") or []:
            rows.append(
                {
                    "kind": "cluster-ms-row",
                    "css": "cluster-ms-row cluster-ms-menu-row",
                    "cells": [
                        {
                            "label": f"{menu['label']}:",
                            "text": (
                                f"{format_count(menu['heads'])} ks / "
                                f"{format_count(menu['total'])} MŠ"
                            ),
                            "colspan": total_columns,
                        }
                    ],
                }
            )
            if diets and menu["label"] == "Menu A":
                rows.append(_cluster_diet_count_row(diets, total_columns))
                diet_rendered = True
        # Fallback pre neštandardný import bez Menu A: diétu nestratíme, len
        # ju nevieme pravdivo priradiť ku konkrétnemu variantu.
        if diets and not diet_rendered:
            rows.append(_cluster_diet_count_row(diets, total_columns))
    diet_rows = (
        _diet_name_rows(rows_for_summary, data, groups, hues) if include_diets else []
    )
    if diet_rows:
        rows.append(
            _band(
                "portion-band",
                _cluster_diety_title(names),
                total_columns,
                css="portion-summary-band",
            )
        )
        rows.extend(diet_rows)
    return rows


def _totals_row(
    totals: list, counts: list, keep: list[int], groups: list[dict], hues: list[str]
) -> dict:
    cells = []
    for position, (group_index, group) in enumerate(groups):
        values = totals[group_index] if group_index < len(totals) else []
        group_count = counts[group_index] if group_index < len(counts) else None
        for component_index, component in enumerate(group.get("components") or []):
            raw = values[component_index] if component_index < len(values) else None
            text = format_gram(raw)
            separator = " meal-sep" if position > 0 and component_index == 0 else ""
            cell = {"text": text or EMPTY, "css": separator.strip()}
            # Počet porcií patrí len do prvej (ľavej) bunky zložky danej
            # skupiny — kuchyňa tak hneď vidí "koľko sa toho varí" pri vstupe
            # do stĺpcov daného jedla/menu, nemusí si to prepočítavať naspäť
            # z gramáže. Opakovať ho na každej zložke by len duplikovalo
            # rovnaké číslo naprieč riadkom.
            if component_index == 0 and group_count:
                cell["count"] = format_count(group_count)
            cells.append(cell)
    return {
        "kind": "total",
        "css": "total",
        "cells": [{"text": "CELKOM (g / ml)", "css": "corner"}] + cells,
    }
