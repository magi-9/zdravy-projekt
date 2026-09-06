from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0097_remove_menu_d_from_default_visible_menus"),
    ]

    operations = [
        migrations.AddField(
            model_name="prevadzka",
            name="gramage_summary_only",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Prevádzka nemá gramážové menu-šablóny (British School, "
                    "Cluster C, #531) — objednávky sa v gramážnej tabuľke/PDF "
                    "vôbec nevykazujú cez bežnú per-klientsku mriežku s "
                    "gramami, len ako samostatný kusový sumár (+ prepočet na "
                    "MŠ porcie) v `MealPlanService."
                    "_build_gramage_summary_only_cluster`."
                ),
            ),
        ),
    ]
