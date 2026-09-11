import datetime

import pytest
from django.contrib.auth.models import User

from api.models import (
    Celok,
    DailyMealPlan,
    DailyOrder,
    DeliveryBlock,
    DeliveryRoute,
    MealPlanItem,
    MealTemplate,
    PortionType,
    Prevadzka,
)
from api.services.meal_plan_service import MealPlanService

pytestmark = pytest.mark.django_db


def _prevadzka(nazov, *, route=None, order=0):
    """Prevádzka s obedovou trasou — testy v tomto súbore riešia len obed."""
    celok, _ = Celok.objects.get_or_create(nazov=f"Celok {nazov}")
    return Prevadzka.objects.create(
        celok=celok,
        nazov=nazov,
        delivery_route_lunch=route,
        delivery_sort_order_lunch=order,
    )


def test_delivery_layout_endpoint_returns_blocks_routes_and_unassigned(
    admin_authenticated_client,
):
    block = DeliveryBlock.objects.create(name="Bežné trasy", sort_order=1)
    route = DeliveryRoute.objects.create(block=block, name="Trasa 1", sort_order=1)
    assigned = _prevadzka("Jolly 1", route=route, order=1)
    unassigned = _prevadzka("Jolly 2")

    response = admin_authenticated_client.get(
        "/api/admin/delivery-blocks/layout/?meal_type=lunch"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["blocks"][0]["name"] == "Bežné trasy"
    assert payload["blocks"][0]["routes"][0]["name"] == "Trasa 1"
    assert payload["blocks"][0]["routes"][0]["prevadzky"][0]["id"] == assigned.id
    assert [row["id"] for row in payload["unassigned_prevadzky"]] == [unassigned.id]


def test_delivery_layout_reorder_moves_prevadzky_between_routes(
    admin_authenticated_client,
):
    block = DeliveryBlock.objects.create(name="Bežné trasy", sort_order=1)
    route_a = DeliveryRoute.objects.create(block=block, name="Trasa A", sort_order=1)
    route_b = DeliveryRoute.objects.create(block=block, name="Trasa B", sort_order=2)
    first = _prevadzka("Prvá", route=route_a, order=1)
    second = _prevadzka("Druhá", route=route_a, order=2)

    response = admin_authenticated_client.post(
        "/api/admin/delivery-blocks/reorder/",
        {
            "meal_type": "lunch",
            "blocks": [
                {
                    "id": block.id,
                    "routes": [
                        {"id": route_a.id, "prevadzky": [{"id": second.id}]},
                        {"id": route_b.id, "prevadzky": [{"id": first.id}]},
                    ],
                }
            ],
            "unassigned_prevadzky": [],
        },
        format="json",
    )

    assert response.status_code == 200
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.delivery_route_lunch_id == route_b.id
    assert first.delivery_sort_order_lunch == 1
    assert second.delivery_route_lunch_id == route_a.id
    assert second.delivery_sort_order_lunch == 1


def test_delivery_routes_cannot_be_assigned_to_the_wrong_meal_type(
    admin_authenticated_client,
):
    """Každé pole prevádzky má vlastnú trasu, ale len rovnakého typu jedla."""
    lunch_block = DeliveryBlock.objects.create(name="Obed", meal_type="lunch")
    breakfast_block = DeliveryBlock.objects.create(
        name="Raňajky", meal_type="breakfast"
    )
    breakfast_route = DeliveryRoute.objects.create(
        block=breakfast_block, name="Ranná trasa"
    )
    lunch_route = DeliveryRoute.objects.create(block=lunch_block, name="Obedová trasa")
    prevadzka = _prevadzka("Správne priradenie")

    patch_response = admin_authenticated_client.patch(
        f"/api/admin/prevadzky-delivery/{prevadzka.id}/",
        {"delivery_route_lunch": breakfast_route.id},
        format="json",
    )
    reorder_response = admin_authenticated_client.post(
        "/api/admin/delivery-blocks/reorder/",
        {
            "meal_type": "lunch",
            "blocks": [
                {
                    "id": lunch_block.id,
                    "routes": [
                        {"id": breakfast_route.id, "prevadzky": [{"id": prevadzka.id}]}
                    ],
                }
            ],
        },
        format="json",
    )
    route_move_response = admin_authenticated_client.patch(
        f"/api/admin/delivery-routes/{lunch_route.id}/",
        {"block": breakfast_block.id},
        format="json",
    )

    assert patch_response.status_code == 400
    assert reorder_response.status_code == 400
    assert route_move_response.status_code == 400
    prevadzka.refresh_from_db()
    assert prevadzka.delivery_route_lunch_id is None
    lunch_route.refresh_from_db()
    assert lunch_route.block_id == lunch_block.id


def test_route_vydaj_can_be_switched(admin_authenticated_client):
    """Výdaj sa prepína na trase — je to jediné miesto, kde sa nastavuje."""
    block = DeliveryBlock.objects.create(name="Bežné trasy", sort_order=1)
    route = DeliveryRoute.objects.create(block=block, name="Trasa 1", sort_order=1)
    assert route.vydaj == "A"

    response = admin_authenticated_client.patch(
        f"/api/admin/delivery-routes/{route.id}/",
        {"vydaj": "D"},
        format="json",
    )

    assert response.status_code == 200
    route.refresh_from_db()
    assert route.vydaj == "D"


def test_route_can_be_moved_to_another_block(admin_authenticated_client):
    """Blok = výdajný bod kuchyne; trasa sa medzi bodmi musí dať presunúť."""
    bezne = DeliveryBlock.objects.create(name="Bežné trasy", sort_order=1)
    extra = DeliveryBlock.objects.create(name="Trasa extra", sort_order=2)
    route = DeliveryRoute.objects.create(block=bezne, name="Trasa 1", sort_order=1)

    response = admin_authenticated_client.patch(
        f"/api/admin/delivery-routes/{route.id}/",
        {"block": extra.id, "sort_order": 1},
        format="json",
    )

    assert response.status_code == 200
    route.refresh_from_db()
    assert route.block_id == extra.id


def test_block_can_be_renamed(admin_authenticated_client):
    """Prevádzka si bloky pomenúva sama (napr. Cluster 1 / Cluster 2)."""
    block = DeliveryBlock.objects.create(name="Bežné trasy", sort_order=1)

    response = admin_authenticated_client.patch(
        f"/api/admin/delivery-blocks/{block.id}/",
        {"name": "Cluster 1"},
        format="json",
    )

    assert response.status_code == 200
    block.refresh_from_db()
    assert block.name == "Cluster 1"


def test_gramage_dashboard_splits_table_by_route_vydaj():
    """Tabuľku riadia trasy: trasa výdaja A tvorí tabuľku A, trasa B tabuľku B.

    Prevádzka nemá vlastný výdaj — patrí do toho, v ktorého trase stojí.
    """
    block = DeliveryBlock.objects.create(name="Bežné trasy", sort_order=1)
    route_a = DeliveryRoute.objects.create(
        block=block, name="Trasa A", sort_order=1, vydaj="A"
    )
    route_b = DeliveryRoute.objects.create(
        block=block, name="Trasa B", sort_order=2, vydaj="B"
    )
    v_a = _prevadzka("A prevádzka", route=route_a, order=1)
    v_b = _prevadzka("B prevádzka", route=route_b, order=1)

    user = User.objects.create_user(
        username="vydaj@example.com", email="vydaj@example.com"
    )
    PortionType.objects.create(name="Škôlka", coefficient="1.0000", sort_order=1)
    template = MealTemplate.objects.create(
        category="main_course",
        name="Rizoto",
        weight_label="200g",
        base_weight_grams="200.00",
        components=[{"label": "Hlavná zložka", "grams": "200", "unit": "g"}],
    )
    plan = DailyMealPlan.objects.create(
        date=datetime.date(2026, 7, 20), created_by=user
    )
    MealPlanItem.objects.create(
        meal_plan=plan, template=template, category="main_course"
    )
    for prevadzka in (v_a, v_b):
        DailyOrder.objects.create(
            user=user,
            prevadzka=prevadzka,
            date=plan.date,
            data={"lunch": {"Škôlka": {"menuCounts": {"A": 1}, "diets": {}}}},
        )

    data = MealPlanService.gramage_dashboard(plan.date.isoformat())

    assert [vydaj["key"] for vydaj in data["vydaje_by_meal"]["lunch"]] == ["A", "B"]
    for vydaj, expected_route, expected_client in zip(
        data["vydaje_by_meal"]["lunch"],
        ["Trasa A", "Trasa B"],
        ["A prevádzka", "B prevádzka"],
    ):
        assert [route["name"] for route in vydaj["routes"]] == [expected_route]
        assert [row["client"] for row in vydaj["routes"][0]["rows"]] == [
            expected_client
        ]


def test_gramage_dashboard_groups_rows_by_delivery_layout_order():
    block = DeliveryBlock.objects.create(name="Extra", sort_order=2)
    route = DeliveryRoute.objects.create(block=block, name="TRASA EXTRA", sort_order=3)
    later = _prevadzka("B prevádzka", route=route, order=2)
    earlier = _prevadzka("A prevádzka", route=route, order=1)

    user = User.objects.create_user(
        username="admin@example.com", email="admin@example.com"
    )
    PortionType.objects.create(name="Škôlka", coefficient="1.0000", sort_order=1)
    template = MealTemplate.objects.create(
        category="main_course",
        name="Rizoto",
        weight_label="200g",
        base_weight_grams="200.00",
        components=[{"label": "Hlavná zložka", "grams": "200", "unit": "g"}],
    )
    plan = DailyMealPlan.objects.create(
        date=datetime.date(2026, 7, 17), created_by=user
    )
    MealPlanItem.objects.create(
        meal_plan=plan, template=template, category="main_course"
    )

    for prevadzka in (later, earlier):
        DailyOrder.objects.create(
            user=user,
            prevadzka=prevadzka,
            date=plan.date,
            data={
                "lunch": {
                    "Škôlka": {"menuCounts": {"A": 1}, "diets": {}},
                }
            },
        )

    data = MealPlanService.gramage_dashboard(plan.date.isoformat())

    assert [row["client"] for row in data["rows"]] == ["A prevádzka", "B prevádzka"]
    # Najvyššia úroveň tabuľky je výdajný bod prevádzky (default „Cluster A"),
    # poradie vnútri neho ostáva rozvozové.
    assert data["vydaje_by_meal"]["lunch"][0]["name"] == "Cluster A"
    assert data["vydaje_by_meal"]["lunch"][0]["routes"][0]["name"] == "TRASA EXTRA"
    assert [
        row["client"] for row in data["vydaje_by_meal"]["lunch"][0]["routes"][0]["rows"]
    ] == [
        "A prevádzka",
        "B prevádzka",
    ]
