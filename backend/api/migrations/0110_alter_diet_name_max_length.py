from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0109_prevadzka_menu_bc_same_deadline_as_lunch"),
    ]

    operations = [
        migrations.AlterField(
            model_name="diet",
            name="name",
            field=models.CharField(max_length=255, unique=True),
        ),
    ]
