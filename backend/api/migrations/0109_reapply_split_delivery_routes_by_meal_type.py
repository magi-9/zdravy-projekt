# Znovu-zavedenie #613 "samostatné trasy per jedlo" (10.9.2026), tentokrát
# poriadne: NIE znova použitá stará `0103_split_delivery_routes_by_meal_type`
# (tá je už aplikovaná, história ju nedovolí zopakovať) a NIE zmazanie
# `0107_restore_shared_delivery_route` (tá je tiež už aplikovaná na
# produkcii aj develop — zmazanie súboru by zopakovalo presne tú istú
# chybu, čo spôsobila incident 9.-10.9.2026, viď komentár v 0107).
#
# Táto migrácia preto robí to isté, čo pôvodná 0103_split, len ako NOVÝ
# krok navrchu 0107/0108: rozdelí `delivery_route`/`delivery_sort_order`
# na `_breakfast`/`_lunch`/`_olovrant`, skopíruje aktuálnu zdieľanú trasu do
# `_lunch` (rovnaký predpoklad ako predtým — doteraz sa reálne používala
# ako obedová) a staré zdieľané polia zmaže.
import django.db.models.deletion
from django.db import migrations, models


def copy_shared_delivery_route_to_lunch(apps, schema_editor):
    Prevadzka = apps.get_model("api", "Prevadzka")
    Prevadzka.objects.exclude(delivery_route__isnull=True).update(
        delivery_route_lunch=models.F("delivery_route"),
        delivery_sort_order_lunch=models.F("delivery_sort_order"),
    )


def copy_lunch_to_shared_delivery_route(apps, schema_editor):
    Prevadzka = apps.get_model("api", "Prevadzka")
    Prevadzka.objects.exclude(delivery_route_lunch__isnull=True).update(
        delivery_route=models.F("delivery_route_lunch"),
        delivery_sort_order=models.F("delivery_sort_order_lunch"),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0108_diet_component_merge_flip_semantics"),
    ]

    operations = [
        migrations.AddField(
            model_name="deliveryblock",
            name="meal_type",
            field=models.CharField(
                choices=[
                    ("breakfast", "Raňajky"),
                    ("lunch", "Obed"),
                    ("olovrant", "Olovrant"),
                ],
                db_index=True,
                default="lunch",
                help_text="Jedlo, ktorému blok patrí — raňajky/obed/olovrant majú vlastné stromy blokov.",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="deliveryblock",
            name="name",
            field=models.CharField(max_length=120),
        ),
        migrations.AddConstraint(
            model_name="deliveryblock",
            constraint=models.UniqueConstraint(
                fields=("meal_type", "name"), name="unique_delivery_block_name_per_meal"
            ),
        ),
        migrations.AddField(
            model_name="prevadzka",
            name="delivery_route_breakfast",
            field=models.ForeignKey(
                blank=True,
                help_text="Rozvozová trasa pre raňajky, používaná v admin Prehľade.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="prevadzky_breakfast",
                to="api.deliveryroute",
            ),
        ),
        migrations.AddField(
            model_name="prevadzka",
            name="delivery_route_lunch",
            field=models.ForeignKey(
                blank=True,
                help_text="Rozvozová trasa pre obed, používaná v admin Prehľade.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="prevadzky_lunch",
                to="api.deliveryroute",
            ),
        ),
        migrations.AddField(
            model_name="prevadzka",
            name="delivery_route_olovrant",
            field=models.ForeignKey(
                blank=True,
                help_text="Rozvozová trasa pre olovrant, používaná v admin Prehľade.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="prevadzky_olovrant",
                to="api.deliveryroute",
            ),
        ),
        migrations.AddField(
            model_name="prevadzka",
            name="delivery_sort_order_breakfast",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Poradie prevádzky v rámci raňajkovej rozvozovej trasy.",
            ),
        ),
        migrations.AddField(
            model_name="prevadzka",
            name="delivery_sort_order_lunch",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Poradie prevádzky v rámci obedovej rozvozovej trasy.",
            ),
        ),
        migrations.AddField(
            model_name="prevadzka",
            name="delivery_sort_order_olovrant",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Poradie prevádzky v rámci olovrantovej rozvozovej trasy.",
            ),
        ),
        migrations.RunPython(
            copy_shared_delivery_route_to_lunch,
            copy_lunch_to_shared_delivery_route,
        ),
        migrations.RemoveField(
            model_name="prevadzka",
            name="delivery_route",
        ),
        migrations.RemoveField(
            model_name="prevadzka",
            name="delivery_sort_order",
        ),
    ]
