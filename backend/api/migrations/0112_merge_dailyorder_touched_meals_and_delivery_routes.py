# Generated manually to join independently merged feature branches.  The
# operations from both parents are already represented by their migrations;
# this node only gives Django a single current migration leaf.
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0109_reapply_split_delivery_routes_by_meal_type"),
        ("api", "0111_dailyorder_touched_meals"),
    ]

    operations = []
