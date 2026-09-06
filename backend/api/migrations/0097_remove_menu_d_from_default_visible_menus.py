from django.db import migrations

# `D` bolo v `DEFAULT_VISIBLE_MENUS`/`_default_visible_menus()` (api/default_visibility.py,
# api/models.py) od začiatku ako univerzálna voľba pre KAŽDÚ prevádzku — reálne ho
# ale používa len British School (Cluster C, #531). Kód default zmenil, táto migrácia
# odstráni "D" z už uložených `visible_menus` všade okrem British School, ktorej ho
# (a nový "VEGE1") explicitne pridá `seed_british_school_2026_08` (user 4.9.2026: má
# byť "disabled teda neviditeľná inak pre british úplne rovnako ako menu Vege 1").
BRITISH_SCHOOL_NAME = "British School"


def strip_menu_d_except_british(apps, schema_editor):
    Prevadzka = apps.get_model("api", "Prevadzka")
    for prevadzka in Prevadzka.objects.exclude(nazov=BRITISH_SCHOOL_NAME).iterator():
        visible_menus = prevadzka.visible_menus or []
        if "D" in visible_menus:
            prevadzka.visible_menus = [m for m in visible_menus if m != "D"]
            prevadzka.save(update_fields=["visible_menus"])


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0096_drop_orphaned_prevadzka_visible_diets_table"),
    ]

    operations = [
        migrations.RunPython(strip_menu_d_except_british, migrations.RunPython.noop),
    ]
