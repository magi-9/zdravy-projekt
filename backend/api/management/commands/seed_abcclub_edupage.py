"""Prepoj existujúcu prevádzku ABC na jej EduPage objednávky.

python manage.py seed_abcclub_edupage
python manage.py seed_abcclub_edupage --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import Celok, EdupageConnection, Prevadzka

ABCCLUB_URL = "https://abcclub.edupage.org/menu/mealsGuest?id=RV2L4bx"


class Command(BaseCommand):
    help = "Prepojí ABC na EduPage mealsGuest feed."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        celok = Celok.objects.filter(nazov="ABC").first()
        if celok is None:
            self.stdout.write(
                self.style.WARNING("  ABC: celok neexistuje, preskakujem")
            )
            return

        prevadzka = Prevadzka.objects.filter(celok=celok, nazov="ABC").first()
        if prevadzka is None:
            self.stdout.write(
                self.style.WARNING("  ABC: prevádzka neexistuje, preskakujem")
            )
            return

        connection, created = EdupageConnection.objects.get_or_create(
            mealsguest_url=ABCCLUB_URL,
            defaults={"name": "ABC"},
        )
        changed = created
        update_fields = []
        if celok.zdroj_objednavok != Celok.ZdrojObjednavok.EDUPAGE:
            celok.zdroj_objednavok = Celok.ZdrojObjednavok.EDUPAGE
            update_fields.append("zdroj_objednavok")
        if update_fields:
            celok.save(update_fields=update_fields)
            changed = True

        update_fields = []
        if prevadzka.edupage_connection_id != connection.pk:
            prevadzka.edupage_connection = connection
            update_fields.append("edupage_connection")
        if prevadzka.edupage_match:
            prevadzka.edupage_match = ""
            update_fields.append("edupage_match")
        if update_fields:
            prevadzka.save(update_fields=update_fields)
            changed = True

        state = "prepojené" if changed else "už prepojené"
        self.stdout.write(f"  ABC: {state} na EduPage")
        if options["dry_run"]:
            transaction.set_rollback(True)
            self.stdout.write(self.style.WARNING("dry-run — rollback"))
