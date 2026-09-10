# Núdzová oprava (9.9.2026 večer / 10.9.2026): "samostatné trasy per jedlo"
# (#613) sa nasadilo na produkciu ako v3.2.0 a hneď zas revertlo kódovo
# (v3.2.1) — ale migrácia `0103_split_delivery_routes_by_meal_type`, ktorá
# rozdelila `delivery_route`/`delivery_sort_order` na tri (breakfast/lunch/
# olovrant) a STARÉ polia úplne zmazala (RemoveField), sa pri code-revert
# nedala vziať späť — jej súbor v reverte zmizol, takže Django nemal ako
# spustiť jej `backwards()`. DB tak ostala v "post-3.2.0" stave, kým kód
# (v3.2.1) číta staré `delivery_route` — ten stĺpec už neexistoval, celý
# rozvoz (a teda aj raňajky/olovrant v tabuľke) bol rozbitý.
#
# Táto migrácia je skutočný, ručne napísaný reverz: vráti späť
# `delivery_route`/`delivery_sort_order`, naplní ich z `delivery_route_lunch`/
# `delivery_sort_order_lunch` (tam sa pôvodné hodnoty skopírovali a odvtedy
# sa nemenili — #613 sa live nikdy nepoužívalo dosť dlho na to, aby niekto
# nastavil samostatné raňajkové/olovrantové trasy), a zmaže tri nové FK aj
# `DeliveryBlock.meal_type`/jeho constraint, späť na pôvodnú schému.
import django.db.models.deletion
from django.db import migrations, models


def copy_lunch_to_shared_delivery_route(apps, schema_editor):
    Prevadzka = apps.get_model("api", "Prevadzka")
    Prevadzka.objects.exclude(delivery_route_lunch__isnull=True).update(
        delivery_route=models.F("delivery_route_lunch"),
        delivery_sort_order=models.F("delivery_sort_order_lunch"),
    )


def copy_shared_delivery_route_to_lunch(apps, schema_editor):
    Prevadzka = apps.get_model("api", "Prevadzka")
    Prevadzka.objects.exclude(delivery_route__isnull=True).update(
        delivery_route_lunch=models.F("delivery_route"),
        delivery_sort_order_lunch=models.F("delivery_sort_order"),
    )


class Migration(migrations.Migration):

    dependencies = [
        # Merge dvoch nezávislých vetiev (#568 diet-component-merge a
        # #613 samostatné trasy per jedlo) — obe vychádzali z 0102.
        ("api", "0103_split_delivery_routes_by_meal_type"),
        ("api", "0106_alter_dailyorder_attention_dismissed"),
    ]

    operations = [
        migrations.AddField(
            model_name="prevadzka",
            name="delivery_route",
            field=models.ForeignKey(
                blank=True,
                help_text="Rozvozová trasa používaná v admin Prehľade.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="prevadzky",
                to="api.deliveryroute",
            ),
        ),
        migrations.AddField(
            model_name="prevadzka",
            name="delivery_sort_order",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Poradie prevádzky v rámci rozvozovej trasy.",
            ),
        ),
        migrations.RunPython(
            copy_lunch_to_shared_delivery_route,
            copy_shared_delivery_route_to_lunch,
        ),
        migrations.RemoveField(
            model_name="prevadzka",
            name="delivery_route_breakfast",
        ),
        migrations.RemoveField(
            model_name="prevadzka",
            name="delivery_route_lunch",
        ),
        migrations.RemoveField(
            model_name="prevadzka",
            name="delivery_route_olovrant",
        ),
        migrations.RemoveField(
            model_name="prevadzka",
            name="delivery_sort_order_breakfast",
        ),
        migrations.RemoveField(
            model_name="prevadzka",
            name="delivery_sort_order_lunch",
        ),
        migrations.RemoveField(
            model_name="prevadzka",
            name="delivery_sort_order_olovrant",
        ),
        migrations.RemoveConstraint(
            model_name="deliveryblock",
            name="unique_delivery_block_name_per_meal",
        ),
        migrations.RemoveField(
            model_name="deliveryblock",
            name="meal_type",
        ),
        migrations.AlterField(
            model_name="deliveryblock",
            name="name",
            field=models.CharField(max_length=120, unique=True),
        ),
    ]
