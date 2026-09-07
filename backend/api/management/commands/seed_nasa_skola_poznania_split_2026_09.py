"""Rozdeľ EduPage objednávky Našej školy poznania medzi dom A a dom B.

EduPage platiteľov označuje ročníkom: 1.–3. ročník patrí do domu A, 4. ročník
do domu B. Oba domy preto musia zdieľať to isté EduPage pripojenie a mať
jednoznačný ``edupage_match`` prefix.

    python manage.py seed_nasa_skola_poznania_split_2026_09
    python manage.py seed_nasa_skola_poznania_split_2026_09 --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import Celok, Prevadzka

CELOK_NAZOV = "Naša škola poznania"
DOM_A = "Naša škola poznania A"
DOM_B = "Naša škola poznania B"
DOM_A_MATCH = "1.-3.ročník"
DOM_B_MATCH = "4. ročník"


class Command(BaseCommand):
    help = "Napoj domy Našej školy poznania na EduPage a rozdeľ ich podľa ročníka."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        celok = Celok.objects.filter(nazov=CELOK_NAZOV).first()
        if celok is None:
            self.stdout.write(
                self.style.WARNING(f"  {CELOK_NAZOV}: celok neexistuje, preskakujem")
            )
            if dry_run:
                transaction.set_rollback(True)
            return

        dom_a = Prevadzka.objects.filter(celok=celok, nazov=DOM_A).first()
        if dom_a is None or dom_a.edupage_connection_id is None:
            self.stdout.write(
                self.style.WARNING(
                    f"  {DOM_A}: prevádzka alebo EduPage spojenie chýba, preskakujem"
                )
            )
            if dry_run:
                transaction.set_rollback(True)
            return

        if dom_a.edupage_match != DOM_A_MATCH:
            dom_a.edupage_match = DOM_A_MATCH
            dom_a.save(update_fields=["edupage_match"])
        self.stdout.write(f"  {DOM_A}: edupage_match = '{DOM_A_MATCH}'")

        dom_b = Prevadzka.objects.filter(celok=celok, nazov=DOM_B).first()
        if dom_b is None:
            self.stdout.write(
                self.style.WARNING(f"  {DOM_B}: prevádzka neexistuje, preskakujem")
            )
        else:
            update_fields = []
            if dom_b.edupage_connection_id != dom_a.edupage_connection_id:
                dom_b.edupage_connection = dom_a.edupage_connection
                update_fields.append("edupage_connection")
            if dom_b.edupage_match != DOM_B_MATCH:
                dom_b.edupage_match = DOM_B_MATCH
                update_fields.append("edupage_match")
            if update_fields:
                dom_b.save(update_fields=update_fields)
            self.stdout.write(f"  {DOM_B}: pripojené na EduPage ({DOM_B_MATCH})")

        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run — rollback"))
            transaction.set_rollback(True)
        else:
            self.stdout.write(self.style.SUCCESS("Hotovo."))
