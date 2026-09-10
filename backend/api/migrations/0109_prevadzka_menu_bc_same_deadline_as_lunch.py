from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0108_diet_component_merge_flip_semantics"),
    ]

    operations = [
        migrations.AddField(
            model_name="prevadzka",
            name="menu_bc_same_deadline_as_lunch",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Keď je zapnuté, na Menu B/C tejto prevádzky sa NEVZŤAHUJE "
                    "prísny globálny 2-dňový termín nárastu "
                    "(`GlobalSettings.deadline_menu_bc`) — platí preň rovnaký "
                    "termín ako na Menu A (bežná uzávierka daného jedla). "
                    "Určené pre školy, kde je Menu B/C pevná, vopred známa "
                    "voľba (napr. len v piatok cez `menu_day_restrictions`), "
                    "nie narýchlo dokupovaná porcia (user 10.9.2026: Múdre "
                    "hranie Škola, Benjamin Pezinok, Benjamin Senec, "
                    "Pinocchio)."
                ),
            ),
        ),
    ]
