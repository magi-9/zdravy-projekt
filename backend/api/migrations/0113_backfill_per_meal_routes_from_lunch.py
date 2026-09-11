"""Seed new breakfast/snack routes from the pre-split lunch layout.

The original split migration deliberately carried the legacy shared route only
to lunch.  In the deployed layout that leaves every eligible breakfast and
standalone afternoon snack unassigned, even though the lunch route is the
best available starting layout.  This migration is intentionally additive:
manual per-meal assignments always win.
"""

from django.db import migrations


def copy_lunch_route_to_eligible_meals(apps, schema_editor):
    Prevadzka = apps.get_model("api", "Prevadzka")

    for prevadzka in Prevadzka.objects.exclude(
        delivery_route_lunch__isnull=True
    ).iterator():
        visible_meals = set(prevadzka.visible_meals or [])
        update_fields = []

        if (
            "breakfast" in visible_meals
            and prevadzka.delivery_route_breakfast_id is None
        ):
            prevadzka.delivery_route_breakfast_id = prevadzka.delivery_route_lunch_id
            prevadzka.delivery_sort_order_breakfast = (
                prevadzka.delivery_sort_order_lunch
            )
            update_fields.extend(
                ["delivery_route_breakfast", "delivery_sort_order_breakfast"]
            )

        # Yellow snack-with-lunch facilities remain on the lunch route/table;
        # assigning a standalone snack route would make them appear twice.
        if (
            "olovrant" in visible_meals
            and not prevadzka.olovrant_s_obedom
            and prevadzka.delivery_route_olovrant_id is None
        ):
            prevadzka.delivery_route_olovrant_id = prevadzka.delivery_route_lunch_id
            prevadzka.delivery_sort_order_olovrant = prevadzka.delivery_sort_order_lunch
            update_fields.extend(
                ["delivery_route_olovrant", "delivery_sort_order_olovrant"]
            )

        if update_fields:
            prevadzka.save(update_fields=update_fields)


class Migration(migrations.Migration):
    dependencies = [("api", "0112_merge_dailyorder_touched_meals_and_delivery_routes")]

    operations = [
        migrations.RunPython(
            copy_lunch_route_to_eligible_meals, migrations.RunPython.noop
        )
    ]
