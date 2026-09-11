"""Doplní chýbajúce `base_diets` pre dve kombinované diéty nahlásené 10.9.2026.

Klient sa sťažoval, že sa mu tieto 2 kombinácie "nedali vytvoriť, appka hlási
že už existujú, ale ja ich nevidím":

    1) NoMilk/NoEgg/NoOrech/NoJablko
    2) NoMilk/NoGluten/NoEgg/NoTelacie/NoTekvica/NoJablko/NoOrech/NoSezam/
       NoArasidy/NoZeler/NoKakao/NoCitrusy/NoSosovica/NoHorcica

Vyšetrenie priamo v produkčnej DB (read-only, cez SSH) ukázalo:

  - #1 UŽ existuje (`id=128`, presný názov "NO MILK – NO EGG – NO ORECH –
    NO JABLKO"), len má prázdne `base_diets` — DietManager admin zoraďuje do
    sekcií podľa `base_diets.length`, takže bez tohto prepojenia appka počíta
    komponenty ako 1 a schová ju do sekcie "1-zložkové" namiesto
    "Viac-zložkové". Preto ju klient nevedel nájsť.
  - #2 pod NOVÝM názvom (14× "NO X" spojené pomlčkou) neexistuje — má 163
    znakov, čo presahovalo pôvodný `Diet.name` limit 100
    (`0110_alter_diet_name_max_length` limit zdvihol na 255). Vytvorenie
    preto padalo na validácii dĺžky poľa, nie na duplicite — frontend ale
    pre každú chybu ukazuje rovnaké "možno už existuje".
    TÁ ISTÁ kombinácia ale reálne UŽ existuje pod STARÝM (predkompozitným)
    názvom `id=46`, "NONONO, TEĽACIE, TEKVICE, JABLKA, ORECHY, SEZAM,
    ARAŠÍDY, ZELER, KAKAO, CITRUSY, ŠOŠOVICE, HORČICA" — "NONONO" je podľa
    `reference_data.py` alias pre "Bez mlieka, lepku a vajec", takže sedí
    presne na 14 požadovaných zložiek. Táto diéta je aktívne priradená a
    používaná (`Little Big`, objednávky za posledných 180 dní) — príkaz ju
    preto MUSÍ nájsť podľa tohto starého mena a doplniť jej base_diets,
    NIE založiť vedľa nej duplicitnú novú diétu (to by problém nevyriešilo,
    len by pridalo nepoužívanú kombináciu naviac).

Dve zo zložiek navyše nemali presný náprotivok (`No Citrus` v appke existuje
len v jednotnom čísle, `NO SOSOVICA` vôbec) — dopĺňa ich tento príkaz.

Príkaz je idempotentný — dá sa spustiť opakovane bez duplicít. Nemení `id`
ani `name` žiadnej z existujúcich diét (#1 aj legacy #2 existujú už), takže
žiadne priradenie k prevádzke/klientovi (`PrevadzkaDiet`) ani historická
objednávka (ktorá diétu nesie ako meno v JSON dátach, nie FK) sa touto
zmenou nestratí — pridáva sa len `base_diets` metadáta pre zobrazenie v
adminovi.

    python manage.py fix_combined_diet_base_links_2026_09
    python manage.py fix_combined_diet_base_links_2026_09 --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import Diet

# Poradie zodpovedá tomu, ako appka skladá názov kombinovanej diéty
# (`DietManager.tsx`: mená zložiek spojené " – ", v poradí `sort_order`).
DIET_1_NAME = "NO MILK – NO EGG – NO ORECH – NO JABLKO"
DIET_1_COMPONENTS = ["NO MILK", "NO EGG", "NO ORECH", "NO JABLKO"]

DIET_2_NAME = (
    "NO MILK – NO GLUTEN – NO EGG – NO TELACIE – NO TEKVICA – NO JABLKO – "
    "NO ORECH – NO SEZAM – NO ARASIDY – NO ZELER – NO KAKAO – NO CITRUSY – "
    "NO SOSOVICA – NO HORCICA"
)
# Rovnaká kombinácia existuje aj pod starým, predkompozitným menom (aktívne
# priradená, "Little Big") — príkaz na ňu musí prednostne naviazať base_diets
# namiesto založenia duplicitnej novej diéty pod `DIET_2_NAME`.
DIET_2_LEGACY_NAME = (
    "NONONO, TEĽACIE, TEKVICE, JABLKA, ORECHY, SEZAM, ARAŠÍDY, ZELER, KAKAO, "
    "CITRUSY, ŠOŠOVICE, HORČICA"
)
DIET_2_COMPONENTS = [
    "NO MILK",
    "NO GLUTEN",
    "NO EGG",
    "NO TELACIE",
    "NO TEKVICA",
    "NO JABLKO",
    "NO ORECH",
    "NO SEZAM",
    "NO ARASIDY",
    "NO ZELER",
    "NO KAKAO",
    "NO CITRUSY",
    "NO SOSOVICA",
    "NO HORCICA",
]


class Command(BaseCommand):
    help = (
        "Doplní base_diets pre kombinované diéty #1 a #2 nahlásené 10.9.2026 "
        "(vytvorí diétu #2 a chýbajúce jednozložkové diéty, ak ešte neexistujú)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def _get_or_create_single(self, name: str) -> Diet:
        diet = Diet.objects.filter(name__iexact=name).first()
        if diet is not None:
            return diet
        diet = Diet.objects.create(name=name)
        self.stdout.write(
            self.style.SUCCESS(f"  vytvorená jednozložková diéta {name!r}")
        )
        return diet

    def _link_composite(
        self,
        name: str,
        component_names: list[str],
        dry_run: bool,
        legacy_name: str | None = None,
    ) -> None:
        # Nájdi cieľovú diétu PRED riešením zložiek — čisté čítanie, nič sa
        # nevytvára, takže toto sa musí spustiť aj v --dry-run móde. Bez
        # tohto poradia dry-run pri chýbajúcich zložkách skončil skôr, než
        # vôbec skúsil legacy meno, a ukázal zavádzajúci náhľad "založím
        # novú diétu", hoci ostrý beh správne našiel existujúcu (id=46).
        diet = None
        if legacy_name is not None:
            diet = Diet.objects.filter(name__iexact=legacy_name).first()
            if diet is not None:
                self.stdout.write(
                    f"  kombinovaná diéta nájdená pod starým menom {diet.name!r} "
                    f"(id={diet.id}) — nezakladám duplicitu pod {name!r}"
                )
        if diet is None:
            diet = Diet.objects.filter(name__iexact=name).first()
            if diet is not None:
                self.stdout.write(
                    f"  kombinovaná diéta {name!r} už existuje (id={diet.id})"
                )

        missing = [
            c
            for c in component_names
            if not Diet.objects.filter(name__iexact=c).exists()
        ]

        if dry_run:
            if diet is None:
                self.stdout.write(f"  [dry-run] vytvoril by som diétu {name!r}")
            for component in missing:
                self.stdout.write(
                    f"  [dry-run] vytvoril by som jednozložkovú diétu {component!r}"
                )
            target = f"{diet.name!r} (id={diet.id})" if diet else f"{name!r} (nová)"
            self.stdout.write(
                f"    [dry-run] nastavil by som base_diets diéty {target} na "
                f"{component_names}"
            )
            return

        components = [
            self._get_or_create_single(component) for component in component_names
        ]
        if diet is None:
            diet, created = Diet.objects.get_or_create(
                name__iexact=name, defaults={"name": name}
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"  vytvorená kombinovaná diéta {name!r}")
                )

        existing = set(diet.base_diets.values_list("id", flat=True))
        wanted = {c.id for c in components}
        if existing == wanted:
            self.stdout.write("    base_diets už sedia, nič nemením")
            return
        diet.base_diets.set(components)
        self.stdout.write(f"    base_diets nastavené na {component_names}")

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("--dry-run: nič sa neuloží"))

        self.stdout.write("Diéta #1 (NoMilk/NoEgg/NoOrech/NoJablko):")
        self._link_composite(DIET_1_NAME, DIET_1_COMPONENTS, dry_run)

        self.stdout.write("Diéta #2 (14-zložková kombinácia):")
        self._link_composite(
            DIET_2_NAME, DIET_2_COMPONENTS, dry_run, legacy_name=DIET_2_LEGACY_NAME
        )

        if dry_run:
            transaction.set_rollback(True)
