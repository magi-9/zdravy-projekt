"""`gramage_table_html._row` prekladá spec do značiek — testy zamykajú, že farba
textu a podfarbenie diétneho riadku (#536) obe skončia v jednom `style` atribúte,
nie že sa navzájom prepíšu."""

from api.exporters.gramage_table_html import _row, render_document


def test_row_renders_both_colour_and_background():
    html = _row(
        {
            "kind": "sub-row",
            "css": "sub-row diet",
            "color": "#966107",
            "background": "#FDF0D9",
            "cells": [{"text": "No Milk"}],
        }
    )
    assert 'style="color: #966107; background-color: #FDF0D9"' in html


def test_row_without_background_only_sets_colour():
    html = _row(
        {
            "kind": "sub-row",
            "css": "sub-row",
            "color": "#425422",
            "cells": [{"text": "Menu A"}],
        }
    )
    assert 'style="color: #425422"' in html
    assert "background-color" not in html


def test_row_without_colour_or_background_has_no_style_attribute():
    html = _row({"kind": "sub-row", "css": "sub-row", "cells": [{"text": "Menu A"}]})
    assert " style=" not in html


def _minimal_spec(meal_type: str) -> dict:
    return {
        "date": "2026-09-11",
        "meal_type": meal_type,
        "total_columns": 1,
        "header": {"corner": "Prevádzka / Riadok", "groups": [], "components": []},
        "rows": [],
        "footer": [],
    }


def test_breakfast_pdf_page_is_portrait():
    """Raňajky/olovrant majú málo stĺpcov — na výšku (A4 portrait) sa
    neroztiahnu naprázdno, na rozdiel od obeda (užívateľ 11.9.2026)."""
    html = render_document(_minimal_spec("breakfast"))
    assert "size: A4 portrait" in html


def test_olovrant_pdf_page_is_portrait():
    html = render_document(_minimal_spec("olovrant"))
    assert "size: A4 portrait" in html


def test_lunch_pdf_page_stays_landscape():
    html = render_document(_minimal_spec("lunch"))
    assert "size: A4 landscape" in html
    assert "size: A4 portrait" not in html
