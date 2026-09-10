"""Odznak "S"/"Z" pri KAŽDOM riadku s diétou (10.9.2026, #568 nadväzba).

"S" (spolu, default) alebo "Z" (zvlášť) — stav z diet-component-merge
boardu pre daný deň a jedlo (`data["diet_pack_state"]`). Ide ako samostatný
`cell["pack_badge"]`, vedľa count-badge ("1 + x + y") — NIE vpletený do mena
diéty ani do poznámky (`cell["text"]` ostáva čisté meno). Pri riadku, čo
zlučuje viac jedál naprieč raňajky/obed/olovrant (composite), sa odznaky
spoja "+" v chronologickom poradí, jeden za KAŽDÉ jedlo, ktoré tá diéta v
danom riadku reálne má."""

from api.exporters.gramage_table_spec import build_table_spec

GRAMS = {"label": "Mäso", "base_grams": "300", "unit": "g"}


def _payload(diet_pack_state=None, **overrides):
    data = {
        "date": "2026-07-28",
        "col_groups": [
            {
                "key": "main_course_A",
                "meal": "main_course",
                "variant": "A",
                "label": "Obed",
                "template_name": "Kuracie",
                "components": [GRAMS],
            },
        ],
        "rows": [
            {
                "client": "MŠ Testovacia",
                "client_id": 1,
                "total_count": 10,
                "standard_total_count": 8,
                "standard_col_grams": [["1600.00"]],
                "diet_summary_rows": [
                    {
                        "name": "No Milk",
                        "count": 2,
                        "color": "#F59E0B",
                        "col_grams": [["400.00"]],
                        "meal_counts": {"main_course": 2},
                    }
                ],
                "sub_rows": [
                    {
                        "type": "standard",
                        "meal": "main_course",
                        "variant": "A",
                        "portion_name": "Škôlka",
                        "label": "Škôlka - Obed Menu A",
                        "count": 8,
                        "col_grams": [["1600.00"]],
                    },
                    {
                        "type": "diet",
                        "meal": "main_course",
                        "portion_name": "Škôlka",
                        "label": "No Milk",
                        "diet_name": "No Milk",
                        "diet_color": "#F59E0B",
                        "count": 2,
                        "col_grams": [["400.00"]],
                    },
                ],
            }
        ],
        "totals": [["1600.00"]],
        "count_summary": [],
        "diet_pack_state": diet_pack_state or {},
    }
    data.update(overrides)
    return data


def _sub_row_cell(spec):
    return next(
        r["cells"][0]
        for r in spec["rows"]
        if r["kind"] == "sub-row" and "diet" in r["css"]
    )


def _summary_diet_cell(spec):
    return next(r["cells"][0] for r in spec["rows"] if r["kind"] == "summary-diet")


def test_badge_defaults_to_S_with_no_board_state():
    spec = build_table_spec(_payload())

    sub_cell = _sub_row_cell(spec)
    assert sub_cell["text"] == "↳ No Milk"
    assert sub_cell["pack_badge"] == "S"
    summary_cell = _summary_diet_cell(spec)
    assert summary_cell["text"] == "No Milk"
    assert summary_cell["pack_badge"] == "S"


def test_badge_shows_Z_when_the_board_marks_the_diet_separate():
    payload = _payload(diet_pack_state={"main_course": {"No Milk": "Z"}})

    spec = build_table_spec(payload)

    assert _sub_row_cell(spec)["pack_badge"] == "Z"
    assert _summary_diet_cell(spec)["pack_badge"] == "Z"
    # Meno diéty ostáva čisté — odznak nejde do textu.
    assert _sub_row_cell(spec)["text"] == "↳ No Milk"


def test_badge_is_per_diet_other_diets_stay_unaffected():
    payload = _payload(diet_pack_state={"main_course": {"Bez lepku": "Z"}})

    spec = build_table_spec(payload)

    # "No Milk" nemá v `diet_pack_state` zápis → default "S".
    assert _sub_row_cell(spec)["pack_badge"] == "S"


def test_composite_badge_joins_S_and_Z_across_meal_bands_in_order():
    """Rovnaká diéta na obede (spolu) aj olovrante (zvlášť) — zlúčený riadok
    (#527) dostane "S + Z", v poradí obed → olovrant, nie v poradí, ako
    prišli v `sub_rows`.

    Len tieto dva pásy sa dajú spojiť v JEDNEJ tabuľke
    (#dashboard-per-meal-routes, 10.9.2026): raňajky majú vlastnú
    samostatnú trasu/tabuľku vždy, olovrant len vtedy, keď prevádzka NEMÁ
    "olovrant s obedom" (`snack_with_lunch`) — vtedy sa spája s obedom."""
    payload = _payload(
        diet_pack_state={
            "main_course": {"No Milk": "S"},
            "afternoon_snack": {"No Milk": "Z"},
        }
    )
    payload["col_groups"] = [
        payload["col_groups"][0],
        {
            "key": "afternoon_snack",
            "meal": "afternoon_snack",
            "variant": "",
            "label": "Olovrant",
            "template_name": "Jogurt",
            "components": [GRAMS],
        },
    ]
    row = payload["rows"][0]
    # Obedová tabuľka pridá olovrantový stĺpec navyše, len keď má aspoň
    # jednu takú prevádzku (`_has_snack_with_lunch_rows`).
    row["snack_with_lunch"] = True
    row["standard_col_grams"] = [["1600.00"], ["1600.00"]]
    row["diet_summary_rows"][0]["col_grams"] = [["400.00"], ["400.00"]]
    for sub_row in row["sub_rows"]:
        sub_row["col_grams"] = [sub_row["col_grams"][0], []]
    row["sub_rows"].append(
        {
            "type": "diet",
            "meal": "afternoon_snack",
            "portion_name": "Škôlka",
            "label": "No Milk",
            "diet_name": "No Milk",
            "diet_color": "#F59E0B",
            "count": 1,
            "col_grams": [[], ["100.00"]],
        }
    )
    payload["totals"] = [["1600.00"], ["1600.00"]]

    spec = build_table_spec(payload)

    assert _sub_row_cell(spec)["pack_badge"] == "S + Z"
    assert _sub_row_cell(spec)["text"] == "↳ No Milk"


def test_badge_appears_in_the_cluster_footer_summary_too():
    payload = _payload(diet_pack_state={"main_course": {"No Milk": "Z"}})
    payload["vydaje"] = [
        {
            "key": "A",
            "name": "Vydaj A",
            "routes": [{"id": 1, "name": "Trasa 1", "rows": payload["rows"]}],
        }
    ]

    spec = build_table_spec(payload)

    footer_diet = next(r for r in spec["footer"] if r["kind"] == "summary-diet")
    assert footer_diet["cells"][0]["text"] == "No Milk"
    assert footer_diet["cells"][0]["pack_badge"] == "Z"
