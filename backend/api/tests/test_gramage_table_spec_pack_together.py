"""„Zabaliť spolu:" — nový súhrnný riadok na konci trasy (9.9.2026).

Default je "spolu": diétne porcie klienta sa sčítajú do jedného riadku na
konci trasy, okrem tých, čo sú buď (a) globálne pre daný deň označené ako
"zabaliť zvlášť" (`diet_packing`, plošne naprieč prevádzkami — kombinovaná
diéta zdedí zvlášť od základnej), alebo (b) klient si ich sám označil ako
"zabaliť zvlášť"/"zvlášť do GN" (`sub_row.type in ("zvlast", "zvlast_gn")`).
Nič z existujúcich riadkov sa tým nemení ani nemaže.
"""

from decimal import Decimal

from api.exporters.gramage_table_spec import build_table_spec

GRAMS = {"label": "Mäso", "base_grams": "300", "unit": "g"}


def _col_groups():
    return [
        {
            "key": "main_course_A",
            "meal": "main_course",
            "variant": "A",
            "label": "Obed",
            "template_name": "Kuracie",
            "components": [GRAMS],
        },
    ]


def _diet_sub_row(diet_name, count, row_type="diet", grams="200.00"):
    return {
        "type": row_type,
        "meal": "main_course",
        "portion_name": "Škôlka",
        "diet_name": diet_name,
        "label": f"Škôlka - {diet_name}",
        "diet_color": "#F59E0B",
        "count": count,
        "_heads": count,
        "_ms_recalc": Decimal(count),
        "col_grams": [[grams]],
    }


def _standard_sub_row(count=5, grams="1000.00"):
    return {
        "type": "standard",
        "meal": "main_course",
        "variant": "A",
        "portion_name": "Škôlka",
        "label": "Škôlka - Obed Menu A",
        "count": count,
        "_heads": count,
        "_ms_recalc": Decimal(count),
        "col_grams": [[grams]],
    }


def _client_row(name, sub_rows, client_id=1):
    return {
        "client": name,
        "client_id": client_id,
        "total_count": sum(sr["count"] for sr in sub_rows),
        "standard_total_count": 0,
        "standard_col_grams": [[]],
        "diet_summary_rows": [],
        "sub_rows": sub_rows,
    }


def _payload(route_rows, **overrides):
    data = {
        "date": "2026-09-10",
        "col_groups": _col_groups(),
        "rows": [],
        "totals": [[]],
        "count_summary": [],
        "vydaje_by_meal": {
            "lunch": [
                {
                    "key": "A",
                    "name": "Cluster A",
                    "routes": [{"id": 1, "name": "Trasa 1", "rows": route_rows}],
                }
            ]
        },
    }
    data.update(overrides)
    return data


def _pack_together_rows(spec):
    return [r for r in spec["rows"] if r["kind"] == "pack-together"]


def test_pack_together_row_sums_diet_portions_at_the_end_of_the_route():
    rows = [_client_row("MŠ A", [_diet_sub_row("No Milk", 3)])]
    spec = build_table_spec(_payload(rows))

    pack_rows = _pack_together_rows(spec)
    assert len(pack_rows) == 1
    assert pack_rows[0]["cells"][0]["text"] == "Zabaliť spolu:"
    assert pack_rows[0]["cells"][0]["count"] == "3"


def test_pack_together_row_comes_right_before_the_next_route():
    rows_a = [_client_row("MŠ A", [_diet_sub_row("No Milk", 3)])]
    rows_b = [_client_row("MŠ B", [_diet_sub_row("No Milk", 1)], client_id=2)]
    payload = _payload(
        rows_a,
        vydaje_by_meal={
            "lunch": [
                {
                    "key": "A",
                    "name": "Cluster A",
                    "routes": [
                        {"id": 1, "name": "Trasa 1", "rows": rows_a},
                        {"id": 2, "name": "Trasa 2", "rows": rows_b},
                    ],
                }
            ]
        },
    )
    spec = build_table_spec(payload)
    kinds = [r["kind"] for r in spec["rows"]]

    route_indices = [i for i, k in enumerate(kinds) if k == "route"]
    pack_indices = [i for i, k in enumerate(kinds) if k == "pack-together"]
    assert len(route_indices) == 2
    assert len(pack_indices) == 2
    # Prvý "Zabaliť spolu:" je hneď PRED druhou trasou.
    assert pack_indices[0] == route_indices[1] - 1
    # Druhý je hneď po poslednom klientskom riadku druhej trasy, pred
    # akýmkoľvek nasledujúcim klastrovým súhrnom (mimo tejto trasy).
    assert kinds[pack_indices[1] - 1] == "sub-row"
    assert kinds[pack_indices[1] + 1] != "client"


def test_manually_pack_separately_diet_portions_are_excluded():
    rows = [
        _client_row(
            "MŠ A",
            [
                _diet_sub_row("No Milk", 3),
                _diet_sub_row("No Milk", 2, row_type="zvlast"),
                _diet_sub_row("No Milk", 1, row_type="zvlast_gn"),
            ],
        )
    ]
    spec = build_table_spec(_payload(rows))

    pack_rows = _pack_together_rows(spec)
    assert pack_rows[0]["cells"][0]["count"] == "3"


def test_globally_flagged_diet_is_excluded_from_pack_together():
    rows = [_client_row("MŠ A", [_diet_sub_row("No Milk", 3)])]
    spec = build_table_spec(_payload(rows), diet_packing={"No Milk": True})

    assert _pack_together_rows(spec) == []


def test_globally_flagged_diet_does_not_touch_other_diets():
    rows = [
        _client_row(
            "MŠ A",
            [_diet_sub_row("No Milk", 3), _diet_sub_row("No Gluten", 2)],
        )
    ]
    spec = build_table_spec(_payload(rows), diet_packing={"No Milk": True})

    pack_rows = _pack_together_rows(spec)
    assert len(pack_rows) == 1
    assert pack_rows[0]["cells"][0]["count"] == "2"


def test_route_without_diet_portions_gets_no_pack_together_row():
    rows = [_client_row("MŠ A", [_standard_sub_row(5)])]
    spec = build_table_spec(_payload(rows))

    assert _pack_together_rows(spec) == []


def test_existing_rows_are_untouched_by_the_new_row():
    """Zásadná zmena (9.9.2026): žiadny existujúci riadok sa nemaže ani
    nemení, len pribúda nový na konci trasy."""
    rows = [_client_row("MŠ A", [_diet_sub_row("No Milk", 3)])]
    spec = build_table_spec(_payload(rows))

    kinds = [r["kind"] for r in spec["rows"]]
    assert "client" in kinds
    assert "sub-row" in kinds
    assert kinds.count("pack-together") == 1
