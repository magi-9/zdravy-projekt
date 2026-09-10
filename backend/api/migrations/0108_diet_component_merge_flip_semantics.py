# Generated manually 10.9.2026 — flip DietComponentMerge sémantiky (#568
# nadväzba): riadok teraz znamená "zvlášť" namiesto "spolu", default sa
# otočil z "zvlášť" na "spolu". Staré riadky ("spolu" výnimky) by pod novou
# logikou znamenali presný opak ("zvlášť" výnimky) — nedajú sa bezpečne
# preložiť (chýba nám univerzum všetkých vtedy platných buniek), preto sa
# jednoducho zmažú. Krátkodobé prevádzkové dáta (šéfkuchár si ich nastavuje
# priebežne, max 7 dní dopredu) — nie je čo zachraňovať.

from django.db import migrations


def clear_diet_component_merges(apps, schema_editor):
    DietComponentMerge = apps.get_model("api", "DietComponentMerge")
    DietComponentMerge.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0107_restore_shared_delivery_route"),
    ]

    operations = [
        migrations.RunPython(clear_diet_component_merges, migrations.RunPython.noop),
    ]
