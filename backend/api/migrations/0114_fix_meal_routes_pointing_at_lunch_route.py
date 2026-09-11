"""Fix 0113's mistake: point breakfast/olovrant at real, own routes.

`0113_backfill_per_meal_routes_from_lunch` set
`delivery_route_breakfast_id = delivery_route_lunch_id` — i.e. the exact
same `DeliveryRoute` row whose `block.meal_type` is `"lunch"`. A facility in
that state disappeared from the raňajky/olovrant admin screen entirely: it
isn't in any breakfast/olovrant block (the route belongs to lunch), and it
isn't in "Nepriradené" either (the field isn't NULL) (11.9.2026 incident).

This migration re-points every facility caught by 0113's bug onto a real
breakfast/olovrant route, cloned from its lunch route (same name/driver/
departure time, so the driver/route identity survives) but placed under a
dedicated breakfast/olovrant block. Per a deliberate simplification decided
alongside this fix, raňajky/olovrant don't need the Cluster (`vydaj`) split
lunch has (kitchen serves lunch from two points at once; breakfast/olovrant
don't) — every new route is forced onto a single `vydaj="A"`, and the admin
UI hides the Cluster picker for those two tabs, so the table never splits.

Facilities whose breakfast/olovrant route is already something other than
the lunch route (a real, distinct assignment) are left untouched. Multiple
facilities sharing the same broken lunch route land on the same new route
(`get_or_create`), not a duplicate each.
"""

from django.db import migrations


def _fix_meal(apps, meal_type):
    Prevadzka = apps.get_model("api", "Prevadzka")
    DeliveryBlock = apps.get_model("api", "DeliveryBlock")
    DeliveryRoute = apps.get_model("api", "DeliveryRoute")

    route_field = f"delivery_route_{meal_type}_id"

    block = DeliveryBlock.objects.filter(meal_type=meal_type).order_by("id").first()
    if block is None:
        block = DeliveryBlock.objects.create(
            meal_type=meal_type,
            name={"breakfast": "Raňajky", "olovrant": "Olovrant"}[meal_type],
            sort_order=1,
        )

    # Presne stav, ktorý spôsobila 0113: pole ukazuje na TÚ ISTÚ trasu ako obed.
    broken = Prevadzka.objects.filter(**{f"{route_field}__isnull": False}).exclude(
        **{route_field: None}
    )
    broken = [
        p
        for p in broken.select_related("delivery_route_lunch")
        if getattr(p, route_field) == p.delivery_route_lunch_id
    ]

    new_route_by_lunch_route: dict[int, int] = {}
    for prevadzka in broken:
        lunch_route_id = prevadzka.delivery_route_lunch_id
        new_route_id = new_route_by_lunch_route.get(lunch_route_id)
        if new_route_id is None:
            lunch_route = prevadzka.delivery_route_lunch
            new_route, _ = DeliveryRoute.objects.get_or_create(
                block=block,
                name=lunch_route.name,
                defaults={
                    "vydaj": "A",
                    "driver": lunch_route.driver,
                    "departure_time": lunch_route.departure_time,
                    "sort_order": lunch_route.sort_order,
                },
            )
            new_route_id = new_route.id
            new_route_by_lunch_route[lunch_route_id] = new_route_id
        setattr(prevadzka, route_field, new_route_id)
        prevadzka.save(update_fields=[route_field])


def repoint_meal_routes_off_the_lunch_route(apps, schema_editor):
    _fix_meal(apps, "breakfast")
    _fix_meal(apps, "olovrant")


class Migration(migrations.Migration):
    dependencies = [("api", "0113_backfill_per_meal_routes_from_lunch")]

    operations = [
        migrations.RunPython(
            repoint_meal_routes_off_the_lunch_route, migrations.RunPython.noop
        )
    ]
