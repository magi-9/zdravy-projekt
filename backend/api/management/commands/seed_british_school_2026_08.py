"""Naseeduj onboarding British School na EduPage (GH #531).

Na rozdiel od `seed_new_edupage_2026_08` celok a prevádzka British School ešte
neexistujú — tento seed ich vytvorí a rovno prepojí na EduPage guest link
dodaný priamo v zadaní issue.

Rozvozová trasa: podľa spätnej väzby (26. 8. 2026) je jedno, či British School
ide pod nový Cluster C alebo pod existujúci blok "Trasa extra" — dôležité je
len mať trasu priradenú. Ideme na Cluster C, prvé reálne použitie `Vydaj.C`
(#531 pôvodne vzniklo presne kvôli tomuto), v rámci existujúceho bloku
"Trasa extra" (nezakladáme nový blok).

    python manage.py seed_british_school_2026_08
    python manage.py seed_british_school_2026_08 --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import (
    Celok,
    DeliveryBlock,
    DeliveryRoute,
    Diet,
    EdupageConnection,
    Prevadzka,
    Vydaj,
)

BRITISH_SCHOOL_URL = "https://zdravyprojekt.edupage.org/menu/mealsGuest?id=Dr8kS45"
BRITISH_SCHOOL_NAME = "British School"
BRITISH_SCHOOL_ROUTE_BLOCK = "Trasa extra"
# Vlastný scrape crontab (deň vopred, Ne–Št, cieli na nasledujúci pracovný
# deň) namiesto zdieľaných GlobalSettings deadlinov — viď
# `EdupageConnection.dedicated_scrape_hour/minute` a
# `api.signals._sync_dedicated_connection_scrape_schedules`.
BRITISH_SCHOOL_SCRAPE_HOUR = 12
BRITISH_SCHOOL_SCRAPE_MINUTE = 15
# Anglické EduPage diéty (Vegan/noPork/noRedMeat/noSugar), preložené do
# slovenských Diet.name (edupage_scraper._NAZOV_KEYWORD_MAP) — nie sú
# default-visible pre každú prevádzku (reference_data.OPERATION_SPECIFIC_DIETS),
# tak ich British School potrebuje zapnuté explicitne, aby ich admin/klient
# reálne videl v appke.
# Nie v `DEFAULT_VISIBLE_MENUS` (api/default_visibility.py) — British je jediná
# prevádzka, ktorá ich má vidieť (Cluster C, kusový sumár, žiadna gramáž).
BRITISH_SCHOOL_EXTRA_MENUS = ["D", "VEGE1"]

BRITISH_SCHOOL_DIET_NAMES = [
    "VEGAN",
    "NO BRAVCOVINA",
    "NO CERVENE MASO",
    "NO CUKOR",
]


class Command(BaseCommand):
    help = "Naseeduje onboarding British School na EduPage (GH #531)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        connection, connection_created = EdupageConnection.objects.get_or_create(
            mealsguest_url=BRITISH_SCHOOL_URL,
            defaults={
                "name": BRITISH_SCHOOL_NAME,
                "dedicated_scrape_hour": BRITISH_SCHOOL_SCRAPE_HOUR,
                "dedicated_scrape_minute": BRITISH_SCHOOL_SCRAPE_MINUTE,
            },
        )
        connection_update_fields = []
        if connection.dedicated_scrape_hour != BRITISH_SCHOOL_SCRAPE_HOUR:
            connection.dedicated_scrape_hour = BRITISH_SCHOOL_SCRAPE_HOUR
            connection_update_fields.append("dedicated_scrape_hour")
        if connection.dedicated_scrape_minute != BRITISH_SCHOOL_SCRAPE_MINUTE:
            connection.dedicated_scrape_minute = BRITISH_SCHOOL_SCRAPE_MINUTE
            connection_update_fields.append("dedicated_scrape_minute")
        if connection_update_fields:
            connection.save(update_fields=connection_update_fields)
        self.stdout.write(
            "  British School: EduPage spojenie "
            f"{'vytvorené' if connection_created else 'už existuje'}"
        )

        celok, celok_created = Celok.objects.get_or_create(
            nazov=BRITISH_SCHOOL_NAME,
            defaults={"zdroj_objednavok": Celok.ZdrojObjednavok.EDUPAGE},
        )
        if celok.zdroj_objednavok != Celok.ZdrojObjednavok.EDUPAGE:
            celok.zdroj_objednavok = Celok.ZdrojObjednavok.EDUPAGE
            celok.save(update_fields=["zdroj_objednavok"])

        prevadzka, prevadzka_created = Prevadzka.objects.get_or_create(
            celok=celok, nazov=BRITISH_SCHOOL_NAME
        )
        update_fields = []
        if prevadzka.edupage_connection_id != connection.pk:
            prevadzka.edupage_connection = connection
            update_fields.append("edupage_connection")
        if prevadzka.edupage_match != "":
            prevadzka.edupage_match = ""
            update_fields.append("edupage_match")
        # Menu D a VEGE1 (4. obedové menu, Cluster C sumár, žiadna gramáž) sú
        # British School špecifiká — nie sú v `DEFAULT_VISIBLE_MENUS` (migrácia
        # 0097 ich zo všetkých ostatných prevádzok odstránila), takže British
        # ich musí mať zapnuté explicitne tu.
        missing_menus = [
            m for m in BRITISH_SCHOOL_EXTRA_MENUS if m not in prevadzka.visible_menus
        ]
        if missing_menus:
            prevadzka.visible_menus = [*prevadzka.visible_menus, *missing_menus]
            update_fields.append("visible_menus")
        # British nemá gramážové menu-šablóny — Cluster C sumár (kusy + MŠ
        # prepočet) sa počíta priamo z EduPage počtov, mimo bežnej mriežky.
        if not prevadzka.gramage_summary_only:
            prevadzka.gramage_summary_only = True
            update_fields.append("gramage_summary_only")
        if update_fields:
            prevadzka.save(update_fields=update_fields)

        self.stdout.write(
            "  British School: celok "
            f"{'vytvorený' if celok_created else 'už existuje'}, prevádzka "
            f"{'vytvorená' if prevadzka_created else 'už existuje'}, "
            "pripojené na EduPage"
        )

        diets = Diet.objects.filter(name__in=BRITISH_SCHOOL_DIET_NAMES)
        found_names = set(diets.values_list("name", flat=True))
        missing_names = set(BRITISH_SCHOOL_DIET_NAMES) - found_names
        if missing_names:
            self.stdout.write(
                self.style.WARNING(
                    "  British School: diéty "
                    f"{sorted(missing_names)} v DB chýbajú (spusti "
                    "init_reference_data skôr) — visible_diets nedopĺňam."
                )
            )
        else:
            prevadzka.visible_diets.add(*diets)
            self.stdout.write(
                "  British School: diéty "
                f"{sorted(found_names)} zapnuté (visible_diets)"
            )

        block = DeliveryBlock.objects.filter(name=BRITISH_SCHOOL_ROUTE_BLOCK).first()
        if block is None:
            self.stdout.write(
                self.style.WARNING(
                    f"  British School: blok '{BRITISH_SCHOOL_ROUTE_BLOCK}' "
                    "neexistuje (spusti seed_real_delivery_layout skôr) — "
                    "trasu priraď ručne cez admin Rozvoz."
                )
            )
        else:
            route, route_created = DeliveryRoute.objects.get_or_create(
                name=BRITISH_SCHOOL_NAME,
                defaults={
                    "block": block,
                    "vydaj": Vydaj.C,
                    "sort_order": 99,
                    "is_active": True,
                },
            )
            if prevadzka.delivery_route_id != route.pk:
                prevadzka.delivery_route = route
                prevadzka.save(update_fields=["delivery_route"])
            self.stdout.write(
                "  British School: trasa "
                f"{'vytvorená' if route_created else 'už existuje'} "
                f"(Cluster C, blok '{BRITISH_SCHOOL_ROUTE_BLOCK}'), priradená prevádzke"
            )

        self.stdout.write(
            self.style.WARNING(
                "  British School: po prvom live scrape over edupage_match "
                "a potvrď počty s kontaktnou osobou."
            )
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run — rollback"))
            transaction.set_rollback(True)
        else:
            self.stdout.write(self.style.SUCCESS("Hotovo."))
