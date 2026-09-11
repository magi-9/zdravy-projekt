"""Assign live-confirmed canonical EduPage diets to their prevádzky.

The ledger contains only targets from the approved September deduplication map
which were returned by the read-only EduPage audit for 2026-09-14. It never
creates diets, removes assignments, or touches historical orders.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import Diet, Prevadzka, PrevadzkaDiet

# (celok, prevádzka, canonical diet). Excludes unconfirmed/unknown live inputs.
ASSIGNMENTS = (
    (
        "British School",
        "British School",
        "NO MILK – NO GLUTEN – NO EGG – HISTAMIN – NO STRUKOVINY – NO ANANÁS",
    ),
    (
        "British School",
        "British School",
        "NO MILK – NO GLUTEN – NO EGG – NO BOBULE – NO BRAVCOVINA",
    ),
    ("British School", "British School", "NO MILK – REFLUX"),
    ("British School", "British School", "NO ORECH – NO JABLKO – NO JAHODA"),
    ("British School", "British School", "NO ORECH – NO KIWI"),
    ("Montesori škôlka", "Montesori škôlka", "NO MILK – NO GLUTEN"),
    ("Montesori škola", "montesori škola", "NO MILK – NO GLUTEN"),
    ("MŠ Edulienka", "MŠ Edulienka", "NO MILK – NO GLUTEN"),
    ("Rozmanitá", "Rozmanita Škola", "NO MILK – NO GLUTEN"),
    ("Naša Škola Poznania", "Naša škola poznania - Dom A", "NO MILK – NO EGG"),
    ("Školička ZŠ", "Školička 1.stupeň", "NO MILK – NO GLUTEN"),
    ("Školička ZŠ", "Školička 2. stupeň", "NO MILK – NO GLUTEN"),
)


class Command(BaseCommand):
    help = "Dry-run/apply viditeľných diét potvrdených EduPage auditom 2026-09-14."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Zapíše chýbajúce viditeľné priradenia po čistom preflight-e.",
        )

    @staticmethod
    def _resolve(celok_name: str, prevadzka_name: str, diet_name: str):
        prevadzka = (
            Prevadzka.objects.select_for_update()
            .filter(celok__nazov=celok_name, nazov=prevadzka_name)
            .first()
        )
        if prevadzka is None:
            raise CommandError(
                f"Prevádzka chýba: celok={celok_name!r}, prevádzka={prevadzka_name!r}"
            )
        diets = list(Diet.objects.select_for_update().filter(name__iexact=diet_name))
        if len(diets) != 1:
            raise CommandError(f"Diéta chýba alebo nie je jednoznačná: {diet_name!r}")
        return prevadzka, diets[0]

    def handle(self, *args, **options):
        apply = options["apply"]
        if not apply:
            self.stdout.write(
                self.style.WARNING(
                    "DRY-RUN: nič sa nezapíše. Pre zápis pridaj --apply."
                )
            )

        with transaction.atomic():
            resolved = [self._resolve(*assignment) for assignment in ASSIGNMENTS]
            missing = [
                (prevadzka, diet)
                for prevadzka, diet in resolved
                if not PrevadzkaDiet.objects.filter(
                    prevadzka=prevadzka, diet=diet
                ).exists()
            ]
            for prevadzka, diet in resolved:
                status = "pridá sa" if (prevadzka, diet) in missing else "už priradená"
                self.stdout.write(
                    f"{prevadzka.celok.nazov}/{prevadzka.nazov}: {diet.name} ({status})"
                )

            if not apply:
                transaction.set_rollback(True)
                return

            PrevadzkaDiet.objects.bulk_create(
                [
                    PrevadzkaDiet(prevadzka=prevadzka, diet=diet)
                    for prevadzka, diet in missing
                ]
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Pridaných {len(missing)} potvrdených viditeľných priradení; nič nebolo odstránené."
                )
            )
