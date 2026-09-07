"""Clear historical uncertain-diet flags for confirmed EduPage feeds.

The listed feeds previously used fuzzy diet matching. Their current explicit
EduPage hooks handle the confirmed labels, so past ``uncertain_diets`` flags
are no longer actionable. Other scrape flags and all other EduPage feeds stay
unchanged.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import DailyOrder


class Command(BaseCommand):
    help = "Odstráni historické neisté diétne príznaky z potvrdených EduPage feedov."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        orders = DailyOrder.objects.filter(
            prevadzka__edupage_connection__mealsguest_url__regex=(
                r"https?://(rozmanita|dobrodruzstvo|szsfan|fantastickaskolka|skolickams)\."
            ),
            scrape_flags__has_key="uncertain_diets",
        )
        cleared = 0
        for order in orders.iterator():
            flags = dict(order.scrape_flags or {})
            if not flags.get("uncertain_diets"):
                continue
            flags.pop("uncertain_diets", None)
            cleared += 1
            if not options["dry_run"]:
                order.scrape_flags = flags
                order.save(update_fields=["scrape_flags", "updated_at"])

        verb = "by sa odstránil" if options["dry_run"] else "odstránený"
        self.stdout.write(f"{verb} neistý príznak z {cleared} objednávok.")
        if options["dry_run"]:
            transaction.set_rollback(True)
