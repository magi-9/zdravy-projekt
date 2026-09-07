from django.core import management
from django.core.management.base import BaseCommand

from api.management.commands.deploy_bootstrap import deploy_bootstrap_lock


class Command(BaseCommand):
    help = (
        "Run the data seed commands (school/prevádzka onboarding data) manually. "
        "Not run automatically on deploy — run this by hand after adding/editing "
        "operations in the seed source files."
    )

    def handle(self, *args, **options):
        with deploy_bootstrap_lock():
            # The production guards on these two commands are bypassed intentionally:
            # this wrapper is the explicit, manually invoked production seed workflow.
            management.call_command(
                "real_initial_seed_prevadzky",
                "--allow-prod",
                verbosity=options.get("verbosity", 1),
            )
            # Poradie je dôležité: splity (Jolly 1/2/3, Škôlka MS) musia byť skôr než
            # `seed_real_delivery_layout`, ktorý existujúce prevádzky iba doplní o
            # rozvoz (a nepresúva ich medzi celkami — inak by narazil na
            # unique(celok, nazov)).
            management.call_command(
                "seed_prevadzky_edupage", verbosity=options.get("verbosity", 1)
            )
            management.call_command(
                "seed_zdrave_brusko", verbosity=options.get("verbosity", 1)
            )
            management.call_command(
                "seed_real_delivery_layout",
                "--allow-prod",
                verbosity=options.get("verbosity", 1),
            )
            # Zlúčenie samostatných celkov jednej školy do jedného celku s N prevádzkami
            # (Bystrá, Dubáčik, …). Musí bežať PO delivery layoute, ktorý app-celky
            # vytvára; opravený `_upsert_prevadzka` ich potom už nerecykluje.
            management.call_command(
                "seed_merge_celky", verbosity=options.get("verbosity", 1)
            )
            management.call_command(
                "seed_bystra_breakfast_from_lunch",
                verbosity=options.get("verbosity", 1),
            )
            management.call_command(
                "seed_new_edupage_2026_08", verbosity=options.get("verbosity", 1)
            )
            management.call_command(
                "seed_british_school_2026_08", verbosity=options.get("verbosity", 1)
            )
            management.call_command(
                "seed_cms_pezinok_2026_08", verbosity=options.get("verbosity", 1)
            )
            management.call_command(
                "seed_skolicka_zs_2026_09", verbosity=options.get("verbosity", 1)
            )
            management.call_command(
                "seed_rozmanita_split_2026_09", verbosity=options.get("verbosity", 1)
            )
            management.call_command(
                "seed_nasa_skola_poznania_split_2026_09",
                verbosity=options.get("verbosity", 1),
            )
            management.call_command(
                "clear_confirmed_edupage_uncertain_flags",
                verbosity=options.get("verbosity", 1),
            )
