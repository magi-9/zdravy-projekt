from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0110_alter_diet_name_max_length"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailyorder",
            name="touched_meals",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
