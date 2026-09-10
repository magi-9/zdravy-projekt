"""Spec → HTML. Druhý z dvoch hlúpych rendererov (prvý je GramageTable.tsx).

Nesmie tu padnúť žiadne rozhodnutie o vzhľade — poradie riadkov, texty, čísla
aj CSS triedy prichádzajú hotové z `gramage_table_spec.build_table_spec()`.
Ak sa niečo má zobraziť inak, patrí to do spec-u, nie sem; inak sa obrazovka
a tlač znova rozídu.
"""

from __future__ import annotations

import pathlib
from html import escape

ASSETS = pathlib.Path(__file__).parent / "assets"

# Slovenské názvy dní a mesiacov — `strftime` ich dá v locale kontajnera (C).
_DAYS = [
    "Pondelok",
    "Utorok",
    "Streda",
    "Štvrtok",
    "Piatok",
    "Sobota",
    "Nedeľa",
]
_MONTHS = [
    "januára",
    "februára",
    "marca",
    "apríla",
    "mája",
    "júna",
    "júla",
    "augusta",
    "septembra",
    "októbra",
    "novembra",
    "decembra",
]


def _stylesheet() -> str:
    """Najprv spoločná tabuľka, až potom papier.

    `gramage-pdf.css` je vrstva navrch: dopĺňa premenné a prepisuje to, čo je
    na obrazovke inak (šírky stĺpcov, veľkosti písma, pruhy). Pri opačnom poradí
    ju screen pravidlá s rovnakou špecificitou prebijú a tlač ostane pri
    rozmeroch monitora.
    """
    table = (ASSETS / "gramage-table.css").read_text(encoding="utf-8")
    page = (ASSETS / "gramage-pdf.css").read_text(encoding="utf-8")
    return f"{table}\n{page}"


def format_date(iso_date: str) -> str:
    import datetime

    try:
        value = datetime.date.fromisoformat(str(iso_date))
    except (TypeError, ValueError):
        return str(iso_date or "")
    return (
        f"{_DAYS[value.weekday()]} {value.day}. {_MONTHS[value.month - 1]} {value.year}"
    )


def _attrs(**pairs) -> str:
    parts = []
    for name, value in pairs.items():
        if value in (None, "", 0):
            continue
        parts.append(f' {name}="{escape(str(value), quote=True)}"')
    return "".join(parts)


def _swatch(swatch: dict) -> str:
    """Farebná bodka pred názvom diéty; viac farieb = koláč, ako na obrazovke."""
    colors = [c for c in (swatch.get("base_colors") or []) if c]
    if not colors:
        background = escape(str(swatch.get("color") or "#FDE68A"), quote=True)
    elif len(colors) == 1:
        background = escape(colors[0], quote=True)
    else:
        step = 100 / len(colors)
        stops = ", ".join(
            f"{escape(color, quote=True)} {index * step:.0f}% {(index + 1) * step:.0f}%"
            for index, color in enumerate(colors)
        )
        background = f"conic-gradient({stops})"
    return f'<span class="diet-dot" style="background: {background}"></span>'


def _cell(cell: dict) -> str:
    attrs = _attrs(**{"class": cell.get("css"), "colspan": cell.get("colspan")})
    text = escape(str(cell.get("text") or ""))
    corner_count = cell.get("corner_count")
    corner = (
        f'<span class="corner-count">{escape(str(corner_count))}</span>'
        if corner_count is not None
        else ""
    )

    if cell.get("count") is not None:
        inner = text
        if cell.get("swatch"):
            inner = _swatch(cell["swatch"]) + inner
        count = escape(str(cell["count"]))
        # "S"/"Z" (10.9.2026, #568 nadväzba) — vedľa count-badge, nie v mene
        # diéty (viď `_diet_pack_badge`). Oranžová, akonáhle je v odznaku
        # čo i len jedno "Z" (aj composite "Z + S + Z").
        pack_badge = str(cell.get("pack_badge") or "")
        badge_html = (
            (
                f'<span class="pack-badge{" pack-badge--z" if "Z" in pack_badge else ""}">'
                f"{escape(pack_badge)}</span>"
            )
            if pack_badge
            else ""
        )
        body = corner + (
            f'<span class="lbl-line"><span>{inner}</span>'
            f'<span class="count-badge">{count}</span>{badge_html}</span>'
        )
    else:
        body = corner + text
    return f"<td{attrs}>{body}</td>"


def _row(row: dict) -> str:
    kind = row.get("kind")
    cells = row.get("cells") or []
    style_parts = []
    if row.get("color"):
        style_parts.append(f"color: {escape(str(row['color']), quote=True)}")
    if row.get("background"):
        style_parts.append(
            f"background-color: {escape(str(row['background']), quote=True)}"
        )
    style = f' style="{"; ".join(style_parts)}"' if style_parts else ""
    attrs = _attrs(**{"class": row.get("css")})

    if kind == "client":
        cell = cells[0]
        # Poznámka prevádzky (#513) ide rovno za názov a počtami (nie do
        # samostatného stĺpca — ten bol zrušený), oddelená lomítkom, nech je
        # vidno hneď vedľa toho, čoho sa týka.
        note = cell.get("note")
        note_span = (
            f' / <span class="client-note-inline">{escape(str(note))}</span>'
            if note
            else ""
        )
        return (
            f"<tr{attrs}><td{_attrs(colspan=cell.get('colspan'))}>"
            f'<span class="client-toggle"><span>{escape(str(cell.get("text") or ""))}'
            f'<span class="meta">{escape(str(cell.get("meta") or ""))}</span>{note_span}</span>'
            f'<span class="meta">{escape(str(cell.get("meta_right") or ""))}</span>'
            f"</span></td></tr>"
        )

    if kind == "route":
        cell = cells[0]
        sub = cell.get("sub")
        sub_html = f"<small>{escape(str(sub))}</small>" if sub else ""
        return (
            f"<tr{attrs}><td{_attrs(colspan=cell.get('colspan'))}>"
            f'<span class="route-pill"><span>{escape(str(cell.get("text") or ""))}</span>'
            f"{sub_html}</span></td></tr>"
        )

    if kind in ("note-admin", "note-delivery", "total-ms-porcie", "cluster-ms-row"):
        cell = cells[0]
        return (
            f"<tr{attrs}><td{_attrs(colspan=cell.get('colspan'))}>"
            f"<strong>{escape(str(cell.get('label') or ''))}</strong> "
            f"{escape(str(cell.get('text') or ''))}</td></tr>"
        )

    return f"<tr{attrs}{style}>" + "".join(_cell(cell) for cell in cells) + "</tr>"


def _tbody_chunks(rows: list[dict]) -> list[list[dict]]:
    """Zoskupí riadky jednej prevádzky do vlastného `<tbody>` (#527).

    Riadky klienta (`kind == "client"`, jeho sub-riadky a poznámky) nesú
    rovnaký `group_id` — kým sú v jednom `<tbody>`, prehliadač aj WeasyPrint
    ho vedia zalomiť ako celok (`break-inside: avoid` v `gramage-pdf.css`),
    takže sa škôlka na papieri nepretrhne v polovici. Riadky bez `group_id`
    (trasa, pás výdaja, súhrny) idú každý do vlastného `<tbody>` — netreba im
    brániť v zalomení, sú to jednotlivé riadky.
    """
    chunks: list[list[dict]] = []
    for row in rows:
        group_id = row.get("group_id")
        if group_id and chunks and chunks[-1][0].get("group_id") == group_id:
            chunks[-1].append(row)
        else:
            chunks.append([row])
    return chunks


def _tbody(rows_chunk: list[dict]) -> str:
    cls = ' class="client-group"' if rows_chunk[0].get("group_id") else ""
    return f"<tbody{cls}>" + "".join(_row(row) for row in rows_chunk) + "</tbody>"


def render_table(spec: dict) -> str:
    header = spec.get("header") or {}
    groups = "".join(
        f"<th{_attrs(**{'class': group.get('css'), 'colspan': group.get('colspan')})}>"
        f"{escape(str(group.get('text') or ''))}<small>{escape(str(group.get('sub') or ''))}</small></th>"
        for group in header.get("groups") or []
    )
    components = "".join(
        f"<th{_attrs(**{'class': component.get('css')})}>"
        f"{escape(str(component.get('text') or ''))}"
        f"<small>{escape(str(component.get('sub') or ''))}</small></th>"
        for component in header.get("components") or []
    )
    meals = "".join(
        f"<th{_attrs(**{'class': band.get('css'), 'colspan': band.get('colspan')})}>"
        f"{escape(str(band.get('text') or ''))}</th>"
        for band in header.get("meals") or []
    )
    body = "".join(_tbody(chunk) for chunk in _tbody_chunks(spec.get("rows") or []))
    footer = "".join(_row(row) for row in spec.get("footer") or [])

    # Hlavička má tri poschodia (jedlo → stĺpcová skupina → zložka). Rohová bunka
    # ich preklenie všetky, preto sa `rowspan` odvíja od toho, či spec pás jedál
    # nesie — bez neho ostáva hlavička dvojposchodová.
    corner = (
        f'<th class="corner" rowspan="{3 if meals else 2}">'
        f"{escape(str(header.get('corner') or ''))}</th>"
    )
    head_rows = ([f"<tr>{corner}{meals}</tr>"] if meals else []) + [
        f"<tr>{groups}</tr>" if meals else f"<tr>{corner}{groups}</tr>",
        f"<tr>{components}</tr>",
    ]
    return (
        '<table class="zpa-gram">'
        f"<thead>{''.join(head_rows)}</thead>"
        f"{body}"
        f"<tfoot>{footer}</tfoot>"
        "</table>"
    )


def render_document(spec: dict, title: str = "Gramáž jedál") -> str:
    """Celá stránka vrátane štýlov — vstup pre WeasyPrint.

    ``title`` mení len nadpis strany; tabuľka je pre stiahnutie z admina aj pre
    denný report tá istá.
    """
    date_text = format_date(spec.get("date") or "")
    return (
        "<!DOCTYPE html><html lang='sk'><head><meta charset='utf-8'>"
        f"<title>{escape(title)} — {escape(str(spec.get('date') or ''))}</title>"
        f"<style>{_stylesheet()}</style></head><body>"
        f"<h1>{escape(title)}<small>{escape(date_text)}</small></h1>"
        f"{render_table(spec)}"
        "</body></html>"
    )
