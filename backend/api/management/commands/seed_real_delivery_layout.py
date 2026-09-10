"""Seed the real delivery layout used by the local dev overview.

The source is the Week 29/2026 real production workbook in ``test/data/real``.
The dev Docker container does not mount ``test/``, so the parsed route layout is
kept here as an idempotent seed command.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import Celok, DeliveryBlock, DeliveryRoute, Diet, Prevadzka, Vydaj


@dataclass(frozen=True)
class DeliverySeedRow:
    route: str
    name: str
    alias: str = ""
    address: str = ""
    note: str = ""
    canonical_name: str = ""
    match_names: tuple[str, ...] = ()
    is_edupage: bool = False
    login_name: str = ""

    @property
    def prevadzka_name(self) -> str:
        return (self.canonical_name or self.name).strip()


DIET_COLORS = {
    "NO MILK": "#9A3412",
    "NO GLUTEN": "#2563EB",
    "NO MILK/NO GLUTEN": "#DC2626",
    "VEGGIE": "#16A34A",
    "HISTAMIN": "#9333EA",
    "NONONO": "#BE123C",
    "NO ORECH": "#B91C1C",
    "NO PARADAJKA": "#EF4444",
    "NO FISH": "#0EA5E9",
    "NO EGG": "#C026D3",
    "NO ZEMIAK": "#F59E0B",
    "NO SOJA": "#0284C7",
    "NO ZELER": "#64748B",
    "DIA": "#0F766E",
}

BLOCKS = [
    ("Bežné trasy", 1, True, False),
    ("Trasa extra", 2, False, True),
]

ROUTES = [
    ("Bežné trasy", "1.Trasa - Pezinská - Heňo/Ivan", 1),
    ("Bežné trasy", "trasa 2 - 9:25 - Ivan/Heňo", 2),
    ("Bežné trasy", "TRASA 3 - Jaro", 3),
    ("Bežné trasy", "TRASA 4 - MIŇO - 10:00", 4),
    ("Bežné trasy", "trasa 5 - RADKO - 10:00", 5),
    ("Trasa extra", "TRASA EXTRA 1 - RENÉ - 9:00", 1),
    ("Trasa extra", "TRASA EXTRA 2 - MIŠO a IGOR 9:15", 2),
    ("Trasa extra", "TRASA EXTRA 3 - DUŠAN - 9:45", 3),
    ("Trasa extra", "TRASA 4 - MAJO - 10:00", 4),
    ("Trasa extra", "TRASA EXTRA ZABALENÉ ZVLÁŠŤ - do 11:00 MAJO", 5),
]

DELIVERY_ROWS = [
    DeliverySeedRow("1.Trasa - Pezinská - Heňo/Ivan", "Jolly 3", is_edupage=True),
    DeliverySeedRow(
        "1.Trasa - Pezinská - Heňo/Ivan", "LILLIUM GARDEN", address="Štúrova 61, Modra"
    ),
    DeliverySeedRow(
        "1.Trasa - Pezinská - Heňo/Ivan",
        "Šenkvice Smart Child",
        address="Trlínská 81, Šenkvice",
    ),
    DeliverySeedRow(
        "1.Trasa - Pezinská - Heňo/Ivan",
        "benjamín senec",
        address="Tulipánová 7, Senec",
    ),
    DeliverySeedRow(
        "1.Trasa - Pezinská - Heňo/Ivan",
        "Ivanka",
        alias="Ivanka",
        address="SNP",
        canonical_name="ZŠ Ivanka pri Dunaji",
        match_names=("ivánka", "Ivanka pri Dunaji"),
    ),
    DeliverySeedRow("1.Trasa - Pezinská - Heňo/Ivan", "Jolly 1", is_edupage=True),
    DeliverySeedRow("1.Trasa - Pezinská - Heňo/Ivan", "Jolly 2", is_edupage=True),
    DeliverySeedRow(
        "1.Trasa - Pezinská - Heňo/Ivan",
        "benjamín pezinok",
        address="Trnavská 4, Pezinok",
    ),
    DeliverySeedRow("1.Trasa - Pezinská - Heňo/Ivan", "Múdre Hlavičky Nová"),
    DeliverySeedRow("1.Trasa - Pezinská - Heňo/Ivan", "Múdre Hlavičky Stará"),
    DeliverySeedRow(
        "1.Trasa - Pezinská - Heňo/Ivan", "ABC", address="SNP 1/124, Svätý Jur"
    ),
    DeliverySeedRow("1.Trasa - Pezinská - Heňo/Ivan", "pinocchio"),
    DeliverySeedRow("1.Trasa - Pezinská - Heňo/Ivan", "Záhradka"),
    DeliverySeedRow("1.Trasa - Pezinská - Heňo/Ivan", "Mimi&Monty"),
    DeliverySeedRow("1.Trasa - Pezinská - Heňo/Ivan", "Chrobáčikovo"),
    DeliverySeedRow(
        "trasa 2 - 9:25 - Ivan/Heňo", "Nova Tulipa", address="Orgovánová 3, Kvetoslavov"
    ),
    DeliverySeedRow(
        "trasa 2 - 9:25 - Ivan/Heňo",
        "Škôlkáreň - Kvetoslavov",
        login_name="Škôlkáreň",
    ),
    DeliverySeedRow("trasa 2 - 9:25 - Ivan/Heňo", "Hugáčik"),
    DeliverySeedRow(
        "trasa 2 - 9:25 - Ivan/Heňo",
        "Hravou Formou bez raňajok",
        address="Krátka 7, Dunajská Lužná",
    ),
    DeliverySeedRow("trasa 2 - 9:25 - Ivan/Heňo", "DupiDupi"),
    DeliverySeedRow(
        "trasa 2 - 9:25 - Ivan/Heňo",
        "Motýlik a Včielka",
        address="Sadová 10, Dunajská Lužná",
        login_name="Zvlášť!!! Motýlik a Včielka",
    ),
    DeliverySeedRow("trasa 2 - 9:25 - Ivan/Heňo", "pohodička 1"),
    DeliverySeedRow("trasa 2 - 9:25 - Ivan/Heňo", "pohodička 2"),
    DeliverySeedRow(
        "trasa 2 - 9:25 - Ivan/Heňo",
        "Nezbedná stonožka",
        address="Staré Grunty 324/A, BA",
    ),
    DeliverySeedRow(
        "trasa 2 - 9:25 - Ivan/Heňo",
        "Naše Jasličky Svetielko",
        address="Ľ. Fullu 12, Bratislava",
    ),
    DeliverySeedRow("trasa 2 - 9:25 - Ivan/Heňo", "STEAMTECH Dospelá spolu"),
    DeliverySeedRow("trasa 2 - 9:25 - Ivan/Heňo", "Dudvažská"),
    DeliverySeedRow(
        "TRASA 3 - Jaro", "InŠkôlka Slnečnice", address="Zuzany Chalupovej 15a"
    ),
    DeliverySeedRow("TRASA 3 - Jaro", "BYSTRÁ 1 Slnečnice", address="Žltá 2A, BA"),
    DeliverySeedRow("TRASA 3 - Jaro", "BYSTRÁ 2 Slnečnice", address="Žltá 2A, BA"),
    DeliverySeedRow("TRASA 3 - Jaro", "BYSTRÁ JASLE", address="Žltá 13/A"),
    DeliverySeedRow("TRASA 3 - Jaro", "VČIELKA RUSOVCE"),
    DeliverySeedRow("TRASA 3 - Jaro", "EMŠ STREČNIANSKA 15"),
    DeliverySeedRow(
        "TRASA 3 - Jaro",
        "Do Sveta",
        login_name="Do Sveta (nemajú raňajky)",
    ),
    DeliverySeedRow("TRASA 3 - Jaro", "KIDSPARADISE", address="Vyšehradská 18, BA"),
    DeliverySeedRow("TRASA 3 - Jaro", "JPND", address="Žehrianska 6, BA"),
    DeliverySeedRow("TRASA 3 - Jaro", "Korálky", address="Žehrianska 6, BA"),
    DeliverySeedRow(
        "TRASA 3 - Jaro", "MŠ Prameň", alias="Pramienok", address="Gercenova 10, BA"
    ),
    DeliverySeedRow("TRASA 3 - Jaro", "Little Dreamer"),
    DeliverySeedRow("TRASA 3 - Jaro", "Hajanka"),
    DeliverySeedRow("TRASA 3 - Jaro", "MŠ Turnianska 6"),
    DeliverySeedRow(
        "TRASA 4 - MIŇO - 10:00",
        "Zvlášť!!! Tábor Omnibus",
        address="Kvetná 2, Bratislava",
    ),
    DeliverySeedRow("TRASA 4 - MIŇO - 10:00", "InŠkôlka", address="Cintorínska 14, BA"),
    DeliverySeedRow("TRASA 4 - MIŇO - 10:00", "Monte Minds"),
    DeliverySeedRow("TRASA 4 - MIŇO - 10:00", "Kidsparadise 1"),
    DeliverySeedRow("TRASA 4 - MIŇO - 10:00", "Kidsparadise 2"),
    DeliverySeedRow("TRASA 4 - MIŇO - 10:00", "little monkey"),
    DeliverySeedRow("TRASA 4 - MIŇO - 10:00", "Bystrá Skypark"),
    DeliverySeedRow("TRASA 4 - MIŇO - 10:00", "Štvorlístok škôlka"),
    DeliverySeedRow("TRASA 4 - MIŇO - 10:00", "Štvorlístok škola"),
    DeliverySeedRow("TRASA 4 - MIŇO - 10:00", "M16"),
    DeliverySeedRow(
        "TRASA 4 - MIŇO - 10:00", "JARABINKA /M16 Jasle", address="Miletičova 16, BA"
    ),
    DeliverySeedRow("trasa 5 - RADKO - 10:00", "Zahrajda", address="Hummelova 12"),
    DeliverySeedRow(
        "trasa 5 - RADKO - 10:00", "MŠ Dobrodružstvo", alias="dobrodružstvo"
    ),
    DeliverySeedRow(
        "trasa 5 - RADKO - 10:00", "ZŠ Dobrodružstvo", alias="DOBRODRUŽSTVO Škola"
    ),
    DeliverySeedRow("trasa 5 - RADKO - 10:00", "Koliba", address="Desiata ulica, BA"),
    DeliverySeedRow("trasa 5 - RADKO - 10:00", "dragon kids 1"),
    DeliverySeedRow("trasa 5 - RADKO - 10:00", "mozart", address="Hrebendova 9"),
    DeliverySeedRow(
        "trasa 5 - RADKO - 10:00",
        "SZŠ FAN",
        alias="Fantastická škola",
        match_names=(
            "Fantastická Škola",
            "SZŠ Fantastická",
            "Súkromná základná škola Fantastická",
        ),
    ),
    DeliverySeedRow("trasa 5 - RADKO - 10:00", "Ostravská"),
    DeliverySeedRow("trasa 5 - RADKO - 10:00", "Stromček"),
    DeliverySeedRow("trasa 5 - RADKO - 10:00", "Naša škola poznania A"),
    DeliverySeedRow("trasa 5 - RADKO - 10:00", "Naša škola poznania B"),
    DeliverySeedRow(
        "trasa 5 - RADKO - 10:00",
        "Zvlášť!!! Tábor Lab Café",
        address="Námestie SNP 484, Bratislava",
    ),
    DeliverySeedRow(
        "TRASA EXTRA 1 - RENÉ - 9:00", "Múdre Včielky", address="Detvianska 27, Rača"
    ),
    DeliverySeedRow("TRASA EXTRA 1 - RENÉ - 9:00", "Grobček"),
    DeliverySeedRow("TRASA EXTRA 1 - RENÉ - 9:00", "Dubáčik 4"),
    DeliverySeedRow("TRASA EXTRA 1 - RENÉ - 9:00", "Dubáčik 3"),
    DeliverySeedRow("TRASA EXTRA 1 - RENÉ - 9:00", "Dubáčik 1"),
    DeliverySeedRow(
        "TRASA EXTRA 1 - RENÉ - 9:00", "Cvernička", address="Nová Cvernovka"
    ),
    DeliverySeedRow("TRASA EXTRA 1 - RENÉ - 9:00", "Bystrá Krasňany"),
    DeliverySeedRow("TRASA EXTRA 1 - RENÉ - 9:00", "PEKNÁ CESTIČKA"),
    DeliverySeedRow(
        "TRASA EXTRA 1 - RENÉ - 9:00",
        "MŠ Krásnanko",
        alias="Krasňanko",
        address="Hrušková 2D, BA",
    ),
    DeliverySeedRow(
        "TRASA EXTRA 1 - RENÉ - 9:00", "detský domček", address="Rostovská 13, BA"
    ),
    DeliverySeedRow("TRASA EXTRA 1 - RENÉ - 9:00", "Emjoy", address="Sliačska 1E"),
    DeliverySeedRow("TRASA EXTRA 1 - RENÉ - 9:00", "Jasle v Domčeku"),
    DeliverySeedRow(
        "TRASA EXTRA 1 - RENÉ - 9:00",
        "MŠ Dobrého Pastiera",
        alias="Klubík - MŠ Dobrého Pastiera",
    ),
    DeliverySeedRow(
        "TRASA EXTRA 2 - MIŠO a IGOR 9:15",
        "MŠ Libellus",
        alias="Libellus",
        address="Mokrohájska 3",
    ),
    DeliverySeedRow(
        "TRASA EXTRA 2 - MIŠO a IGOR 9:15",
        "Les",
        alias="Školička les",
        is_edupage=True,
    ),
    DeliverySeedRow(
        "TRASA EXTRA 2 - MIŠO a IGOR 9:15",
        "Lúka",
        alias="Školička lúka",
        is_edupage=True,
    ),
    DeliverySeedRow(
        "TRASA EXTRA 2 - MIŠO a IGOR 9:15",
        "Školička 1.stupeň",
        address="Panenská 4, BA",
    ),
    DeliverySeedRow(
        "TRASA EXTRA 2 - MIŠO a IGOR 9:15",
        "Školička 2. stupeň",
        address="Panenská 4, BA",
    ),
    # MŠ Edulienka splits into Palisády/Stupava sub-prevádzky (see
    # seed_prevadzky_edupage.SPLITS) — target them directly, same as the
    # Jolly Homeschool / Škôlka MS multi-prevádzka rows above/below.
    # Targeting the pre-split default name here would resurrect it
    # (is_active=True) every time this command reseeds, undoing the split.
    DeliverySeedRow(
        "TRASA EXTRA 2 - MIŠO a IGOR 9:15",
        "Palisády",
        alias="Edulienka - Palisády",
        is_edupage=True,
    ),
    DeliverySeedRow(
        "TRASA EXTRA 2 - MIŠO a IGOR 9:15",
        "Stupava",
        alias="Edulienka - Stupava",
        is_edupage=True,
    ),
    DeliverySeedRow(
        "TRASA EXTRA 2 - MIŠO a IGOR 9:15",
        "Deutsche schule",
        address="Bárdošova 33, Bratislava",
    ),
    DeliverySeedRow(
        "TRASA EXTRA 2 - MIŠO a IGOR 9:15",
        "Little Big",
        address="Ďumbierska 3G, BA",
    ),
    DeliverySeedRow(
        "TRASA EXTRA 2 - MIŠO a IGOR 9:15",
        "Škôlkáreň - Mokrohájska",
        login_name="Škôlkáreň",
    ),
    DeliverySeedRow(
        "TRASA EXTRA 2 - MIŠO a IGOR 9:15",
        "Múdre Hranie Škôlka",
        address="Pod Klepáčom 8, BA",
    ),
    DeliverySeedRow(
        "TRASA EXTRA 2 - MIŠO a IGOR 9:15",
        "Múdre Hranie Škola",
        address="Pod Klepáčom 8, BA",
    ),
    DeliverySeedRow(
        "TRASA EXTRA 2 - MIŠO a IGOR 9:15",
        "Múdre hranie JASLE",
        address="Pod Klepáčom 8, BA",
    ),
    DeliverySeedRow("TRASA EXTRA 2 - MIŠO a IGOR 9:15", "Krok za krokom"),
    DeliverySeedRow("TRASA EXTRA 3 - DUŠAN - 9:45", "Zvlášť!!! Tábor VEVE 2"),
    DeliverySeedRow(
        "TRASA EXTRA 3 - DUŠAN - 9:45", "Veselý Úľ 1", address="Stalicova 2"
    ),
    DeliverySeedRow(
        "TRASA EXTRA 3 - DUŠAN - 9:45", "Veselý Úľ 2", address="Stalicova 2"
    ),
    DeliverySeedRow("TRASA EXTRA 3 - DUŠAN - 9:45", "Šidielko"),
    DeliverySeedRow("TRASA EXTRA 3 - DUŠAN - 9:45", "tulipánik"),
    DeliverySeedRow("TRASA EXTRA 3 - DUŠAN - 9:45", "tučniačik"),
    DeliverySeedRow("TRASA EXTRA 3 - DUŠAN - 9:45", "Medulienka"),
    DeliverySeedRow(
        "TRASA EXTRA 3 - DUŠAN - 9:45", "MŠ Rozmanitá", alias="Rozmanita Škôlka"
    ),
    DeliverySeedRow(
        "TRASA EXTRA 3 - DUŠAN - 9:45", "Rozmanita Škola", address="Svidnická 4, BA"
    ),
    DeliverySeedRow("TRASA EXTRA 3 - DUŠAN - 9:45", "Včielka"),
    DeliverySeedRow("TRASA EXTRA 3 - DUŠAN - 9:45", "Malí šampióni"),
    DeliverySeedRow(
        "TRASA 4 - MAJO - 10:00", "Dobré Jasle", address="Nejedlého 73, Bratislava"
    ),
    DeliverySeedRow(
        "TRASA 4 - MAJO - 10:00", "MŠ Felix Karlovská", alias="Felix", address="IUVENTA"
    ),
    DeliverySeedRow(
        "TRASA 4 - MAJO - 10:00",
        "Simon Drgo MŠ Milana Marečka 20, DNV",
    ),
    DeliverySeedRow("TRASA 4 - MAJO - 10:00", "MŠ Filipáneriho", alias="Filipa Nériho"),
    DeliverySeedRow("TRASA 4 - MAJO - 10:00", "MŠ Malokarpatké námestie 6"),
    DeliverySeedRow("TRASA 4 - MAJO - 10:00", "MŠ Heyrovského 4"),
    DeliverySeedRow("TRASA 4 - MAJO - 10:00", "Montesori škôlka"),
    DeliverySeedRow("TRASA 4 - MAJO - 10:00", "montesori škola"),
    DeliverySeedRow(
        "TRASA EXTRA ZABALENÉ ZVLÁŠŤ - do 11:00 MAJO",
        "SŠ VETERINÁRNA",
        alias="SŠ VETERINÁRNA Pod brehmi 6",
        address="Pod brehmi 6, Bratislava",
        match_names=("SŠ VETERINÁRNA Pod brehmi 6",),
    ),
    DeliverySeedRow(
        "TRASA EXTRA ZABALENÉ ZVLÁŠŤ - do 11:00 MAJO",
        "Waldorf Kukučínova",
        # Reálna prevádzka v DB sa volá skrátene "Waldorf" (celok "Waldom") — bez
        # tohto by _find_existing_prevadzka exact-matchol na "Waldorf Kukučínova"
        # a založil TRETÍ, prázdny duplicitný celok popri "Waldom"/"Walldom".
        match_names=("Waldorf",),
    ),
    DeliverySeedRow("TRASA EXTRA ZABALENÉ ZVLÁŠŤ - do 11:00 MAJO", "ZŠ Malokarpatská"),
    DeliverySeedRow(
        "TRASA EXTRA ZABALENÉ ZVLÁŠŤ - do 11:00 MAJO",
        "Malokarpatské námestie 2, Lamač",
    ),
    DeliverySeedRow(
        "TRASA EXTRA ZABALENÉ ZVLÁŠŤ - do 11:00 MAJO",
        "Zvlášť!!! Tábor Big Hug Gym",
        address="Hodonínska 7/A",
    ),
    DeliverySeedRow(
        "TRASA EXTRA ZABALENÉ ZVLÁŠŤ - do 11:00 MAJO", "Zvlášť!!! Tábor Warrior"
    ),
    DeliverySeedRow("TRASA EXTRA ZABALENÉ ZVLÁŠŤ - do 11:00 MAJO", "Hodonínska 27"),
    DeliverySeedRow(
        "TRASA EXTRA ZABALENÉ ZVLÁŠŤ - do 11:00 MAJO",
        "Zvlášť!!! Futbalový Tábor",
        address="Športová 450, Šamorín",
    ),
    DeliverySeedRow(
        "TRASA EXTRA ZABALENÉ ZVLÁŠŤ - do 11:00 MAJO",
        "Športová 450, Šamorín",
        address="Športová 450, Šamorín",
    ),
    DeliverySeedRow(
        "TRASA EXTRA ZABALENÉ ZVLÁŠŤ - do 11:00 MAJO",
        "Zvlášť!!! Tábor Paint People",
        address="Steinov dvor 2, Bratislava",
    ),
    DeliverySeedRow(
        "TRASA EXTRA ZABALENÉ ZVLÁŠŤ - do 11:00 MAJO",
        "Steinov dvor 2, Bratislava",
        address="Steinov dvor 2, Bratislava",
    ),
    DeliverySeedRow(
        "TRASA EXTRA ZABALENÉ ZVLÁŠŤ - do 11:00 MAJO", "Zvlášť!!! Vojenský Tábor"
    ),
    DeliverySeedRow(
        "TRASA EXTRA ZABALENÉ ZVLÁŠŤ - do 11:00 MAJO",
        "Pozri dokument kvôli dennej adrese",
    ),
]

# Zrušené subjekty (klient potvrdil 2026-08-11). Prevádzky s objednávkovou históriou
# sa len deaktivujú (viď _delete_obsolete_celky), nemažú sa natvrdo.
#
# Mená tu zostávajú aj po tom, čo zmizli z DELIVERY_ROWS: úlohou zoznamu je
# upratať databázy, kde tieto prevádzky vznikli skoršími behmi seedu.
# Vyradenie z DELIVERY_ROWS ich odtiaľ samo neodstráni.
OBSOLETE_CELKY = (
    "MŠ Zdravé Bruško",
    "Walldom",  # duplicita Waldorf Kukučínova
    "Predškoláci",
    "Libellus Camp",
    "Tábor Balance",
    "Tábor Big Hug Gym",
    "Tábor Efka - Spolu do GN",
    "Tábor Jolly - spolu do GN",
    "Tábor Lab Café",
    "Tábor Medzi Stromami",
    "Tábor Omnibus",
    "Tábor Paint People",
    "Tábor VEVE 1",
    "Tábor Warrior",
    # Fantastická škôlka je teraz 2. prevádzka pod celkom "Fantastická Škola".
    "Fantastická Škôlka",
)


class Command(BaseCommand):
    help = "Seed real delivery routes and Excel-derived operations for local dev."

    def add_arguments(self, parser):
        # Kept for backward-compatible invocation (deploy_bootstrap still
        # passes it); no longer enforced. Purely idempotent get_or_create
        # seeding, same as seed_merge_celky which never had this guard.
        parser.add_argument("--allow-prod", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        for diet in Diet.objects.filter(name__in=DIET_COLORS):
            color = DIET_COLORS[diet.name]
            if diet.color != color:
                diet.color = color
                diet.save(update_fields=["color"])

        blocks: dict[str, DeliveryBlock] = {}
        for name, sort_order, main_summary, extra_summary in BLOCKS:
            block, _ = DeliveryBlock.objects.update_or_create(
                name=name,
                defaults={
                    "sort_order": sort_order,
                    "include_in_main_summary": main_summary,
                    "include_in_extra_summary": extra_summary,
                    "is_active": True,
                },
            )
            blocks[name] = block

        routes: dict[str, DeliveryRoute] = {}
        for block_name, route_name, sort_order in ROUTES:
            # Výdaj sa nastavuje len pri ZALOŽENÍ trasy (extra blok = druhý
            # výdajný bod). Existujúcim trasám ho seed neprepisuje: beží pri
            # každom nasadení a prepis by ručnú voľbu zakaždým zahodil.
            route, _ = DeliveryRoute.objects.get_or_create(
                name=route_name,
                defaults={
                    "block": blocks[block_name],
                    "sort_order": sort_order,
                    "is_active": True,
                    "vydaj": (
                        Vydaj.B
                        if blocks[block_name].include_in_extra_summary
                        else Vydaj.A
                    ),
                },
            )
            DeliveryRoute.objects.filter(pk=route.pk).update(
                block=blocks[block_name], sort_order=sort_order, is_active=True
            )
            route.refresh_from_db()
            routes[route_name] = route

        for route_name, rows in _rows_by_route().items():
            route = routes[route_name]
            for sort_order, row in enumerate(rows, start=1):
                _upsert_prevadzka(row, route, sort_order)

        _delete_obsolete_celky()

        self.stdout.write(
            self.style.SUCCESS(f"Seeded {len(DELIVERY_ROWS)} real delivery operations.")
        )


def _rows_by_route() -> dict[str, list[DeliverySeedRow]]:
    grouped: dict[str, list[DeliverySeedRow]] = {}
    for row in DELIVERY_ROWS:
        grouped.setdefault(row.route, []).append(row)
    return grouped


def _upsert_prevadzka(
    row: DeliverySeedRow, route: DeliveryRoute, sort_order: int
) -> Prevadzka:
    existing = _find_existing_prevadzka(row)
    if existing is not None:
        # Prevádzka už existuje — možno ako sub-prevádzka multi-prevádzkového celku
        # (napr. „Jolly 3" pod „Jolly Homeschool", „Les"/„Lúka" pod „Škôlka MS").
        # NEPRESÚVAME ju do facility-pomenovaného celku ani ju nepremenúvame — inak
        # by sme ju odtrhli od jej celku a narazili na unique(celok, nazov). Len
        # doplníme rozvozové info. Zdroj EDUPAGE riešime na jej vlastnom celku.
        if row.address:
            existing.adresa = row.address
        existing.delivery_route = route
        existing.delivery_sort_order = sort_order
        existing.report_alias = row.alias
        existing.delivery_note = row.note
        existing.is_active = True
        existing.save()
        if (
            row.is_edupage
            and existing.celok is not None
            and existing.celok.zdroj_objednavok != Celok.ZdrojObjednavok.EDUPAGE
        ):
            existing.celok.zdroj_objednavok = Celok.ZdrojObjednavok.EDUPAGE
            existing.celok.save(update_fields=["zdroj_objednavok"])
        return existing

    # Nová prevádzka → vlastný celok pomenovaný podľa facility (1 celok : 1 prevádzka).
    display_name = row.prevadzka_name
    celok, _ = Celok.objects.get_or_create(nazov=display_name)
    if row.is_edupage and celok.zdroj_objednavok != Celok.ZdrojObjednavok.EDUPAGE:
        celok.zdroj_objednavok = Celok.ZdrojObjednavok.EDUPAGE
        celok.save(update_fields=["zdroj_objednavok"])
    prevadzka = Prevadzka(
        celok=celok,
        nazov=display_name,
        adresa=row.address or "",
        delivery_route=route,
        delivery_sort_order=sort_order,
        report_alias=row.alias,
        delivery_note=row.note,
        is_active=True,
    )
    prevadzka.save()
    return prevadzka


def _find_existing_prevadzka(row: DeliverySeedRow) -> Prevadzka | None:
    for name in _candidate_names(row):
        existing = Prevadzka.objects.filter(nazov__iexact=name).first()
        if existing is not None:
            return existing
    return None


def _candidate_names(row: DeliverySeedRow) -> Iterable[str]:
    seen: set[str] = set()
    for raw_name in (row.prevadzka_name, row.name, row.alias, *row.match_names):
        name = raw_name.strip()
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        yield name


def _delete_obsolete_celky() -> None:
    for celok in Celok.objects.filter(nazov__in=OBSOLETE_CELKY):
        if celok.prevadzky.filter(orders__isnull=False).exists():
            celok.prevadzky.update(is_active=False, delivery_route=None)
            continue
        celok.prevadzky.all().delete()
        celok.delete()
