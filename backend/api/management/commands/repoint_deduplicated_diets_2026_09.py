"""Safely repoint confirmed legacy diets to their existing composite diets.

This command deliberately never creates, deactivates, or deletes a Diet.  Run it
first without ``--apply`` and keep its output as the migration audit.  ``--apply``
only proceeds when every mapped name exists and no unique/note conflict could lose
data. Historical DailyOrder JSON is intentionally never rewritten.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import (
    Diet,
    DietComponentMerge,
    MealPlanItem,
    MealTemplate,
    PrevadzkaDiet,
)

# Approved ledger: report section A, plus user-confirmed overrides #57, #65 and
# #131 (ŠPECI).  #46 is already the canonical legacy-named diet, not a repoint.
# #48, #60 and #63 stay unmatched by explicit decision and are not listed here.
MAPPINGS = (
    (
        "ADAM - NO ORECHY, ARAŠÍDY, SÓJA, STRUKOVINY, MAK, SEMIAČKA",
        "No Arašídy – NO SOJA – NO ORECH – NO STRUKOVINY – NO MAK – NO SEMIAČKA – ADAM",
    ),
    ("AURORA - NO ORECH, SEZAM, ZELER", "NO ORECH – NO ZELER – NO SEZAM – AURORA"),
    ("EIWA - HISTAMIN, NO MILK", "NO MILK – HISTAMIN – EIWA"),
    ("ELIŠKA - NO MILK, EGG, PARADAJKA", "NO MILK – NO EGG – NO PARADAJKA – ELIŠKA"),
    ("HISTAMIN, NO GLUTEN", "NO GLUTEN – HISTAMIN"),
    (
        "JULKA - HISTAMIN, NO ORECH, MAK, MED",
        "NO MED – HISTAMIN – NO ORECH – NO MAK – JULKA",
    ),
    ("LACKO - NO JABLKO", "NO JABLKO – LACKO"),
    ("LAURA - HISTAMIN, NO MILK, SÓJA", "NO MILK – HISTAMIN – NO SOJA – LAURA"),
    ("LILI - NONO, NO ZELER", "NO MILK – NO GLUTEN – NO ZELER – LILI"),
    (
        "LIZA - NO MILK, EGG, ZEMIAK, JABLKO",
        "NO MILK – NO EGG – NO ZEMIAK – NO JABLKO – LIZA",
    ),
    ("MIA - NONONO, NO SÓJA", "NO MILK – NO GLUTEN – NO EGG – NO SOJA – MIA"),
    ("NO BATÁTY, TEKVICA", "NO BATATY – NO TEKVICA"),
    ("NO EGG, ORECH, ARAŠÍDY", "No Arašídy – NO EGG – NO ORECH"),
    (
        "NO EGG, ORECH, ARAŠíDY, SÓJA, SEZAM",
        "No Arašídy – NO EGG – NO SOJA – NO ORECH – NO SEZAM",
    ),
    (
        "NO EGG/NO ORECH/NO ARASIDY/NO SOJA/NO SEZAM",
        "No Arašídy – NO EGG – NO SOJA – NO ORECH – NO SEZAM",
    ),
    ("NO GLUTEN, HRÍBY", "NO GLUTEN – NO HUBY"),
    ("NO GLUTEN, VEGGIE", "NO GLUTEN – VEGGIE"),
    ("NO MED, MAK, ORECH", "NO MED – NO ORECH – NO MAK"),
    ("NO MED, ŠKORICA", "NO MED – NO SKORICA"),
    ("NO MILK, BATÁTY", "NO MILK – NO BATATY"),
    ("NO MILK, EGG", "NO MILK – NO EGG"),
    ("NO MILK, NO CVIKLA", "NO MILK – NO CVIKLA"),
    ("NO MILK, ORECH", "NO MILK – NO ORECH"),
    ("NO MILK, OVOS, ČOKOLÁDA", "NO MILK – No Čokoláda – NO OVOS"),
    (
        "NO MILK, PARADAJKY, JAHODY, KAKAO, ORECHY, ŠKORICA",
        "NO MILK – NO PARADAJKA – NO ORECH – NO JAHODA – NO KAKAO – NO SKORICA",
    ),
    ("NO MILK, STRUKOVINA, MAK", "NO MILK – NO STRUKOVINY – NO MAK"),
    ("NO MILK, SÓJA", "NO MILK – NO SOJA"),
    ("NO MILK, VEGGIE", "NO MILK – VEGGIE"),
    ("NO MILK, VEGGIE, NO FISH", "NO MILK – VEGGIE – NO FISH"),
    ("NO MILK, ZELER, ZEMIAK", "NO MILK – NO ZEMIAK – NO ZELER"),
    ("NO MILK, ČOKOLÁDA, JAHODY", "NO MILK – No Čokoláda – NO JAHODA"),
    ("NO MILK/NO EGG", "NO MILK – NO EGG"),
    ("NO MILK/NO GLUTEN", "NO MILK – NO GLUTEN"),
    (
        "NO MILK/NO ORECH/NO PARADAJKA/NO JAHODA/NO KAKAO/NO SKORICA/NO ZELER",
        "NO MILK – NO PARADAJKA – NO ORECH – NO ZELER – NO JAHODA – NO KAKAO – NO SKORICA",
    ),
    ("NO MILK/REFLUX", "NO MILK – REFLUX"),
    ("NO MILK/VEGGIE", "NO MILK – VEGGIE"),
    (
        "NO ORECH, ARAŠÍDY, JABLKÁ, ZELER, PARADAJKY,",
        "No Arašídy – NO PARADAJKA – NO ORECH – NO ZELER – NO JABLKO",
    ),
    (
        "NO ORECH, MAK, ARAŠÍDY, SEMIAČKA, KOKOS, PARADAJKY",
        "No Arašídy – NO PARADAJKA – NO ORECH – NO MAK – NO SEMIAČKA – NO KOKOS",
    ),
    ("NO ORECH/NO FISH", "NO FISH – NO ORECH"),
    ("NO ORECH/NO JABLKO/NO JAHODA", "NO ORECH – NO JABLKO – NO JAHODA"),
    ("NO ORECH/NO KIWI", "NO ORECH – NO KIWI"),
    ("NO ORECH/NO SEZAM", "NO ORECH – NO SEZAM"),
    ("NO STRUKOVINY, MAK", "NO STRUKOVINY – NO MAK"),
    ("NO SÓJA, NO ORECHY, NO ARAŠÍDY", "No Arašídy – NO SOJA – NO ORECH"),
    ("NONO, NO ORECH", "NO MILK – NO GLUTEN – NO ORECH"),
    ("NONONO, NO ORECH", "NO MILK – NO GLUTEN – NO EGG – NO ORECH"),
    ("NONONO, NO STRUKOVINY", "NO MILK – NO GLUTEN – NO EGG – NO STRUKOVINY"),
    (
        "NONONO, SÓJA, TEĽACIE, JABLKÁ",
        "NO MILK – NO GLUTEN – NO EGG – NO SOJA – NO JABLKO – NO TELACIE",
    ),
    (
        "NONONO, TEĽACIE, JABLKÁ, ORECHY, ZELER, KAKAO, CITRUS",
        "NO MILK – NO GLUTEN – NO EGG – No Citrus – NO ORECH – NO ZELER – NO JABLKO – NO KAKAO – NO TELACIE",
    ),
    (
        "NONONO/NO ANANAS/NO STRUKOVINY/HISTAMIN",
        "NO MILK – NO GLUTEN – NO EGG – HISTAMIN – NO STRUKOVINY – NO ANANÁS",
    ),
    (
        "NONONO/NO BRAVCOVINA/NO BOBULE",
        "NO MILK – NO GLUTEN – NO EGG – NO BOBULE – NO BRAVCOVINA",
    ),
    ("REBEKA - NO MILK, ZEMIAK, ZELER", "NO MILK – NO ZEMIAK – NO ZELER – REBEKA"),
    ("SAMKO - NO ORECH, CITRUS", "No Citrus – NO ORECH – SAMKO"),
    (
        "TEO - NO EGG, FISH, MAK, HOVÄDZIE MÄSO",
        "NO EGG – NO FISH – NO CERVENE MASO – NO MAK – TEO",
    ),
    ("TIMEA - NO HRÁŠOK", "NO HRÁŠOK – TIMEA"),
    ("VEGGIE, NO FISH", "VEGGIE – NO FISH"),
    (
        "ZUZANA - NO MILK, EGG, ZEMIAK, JABLKO, STRUKOVINY, ORECHY",
        "NO MILK – NO EGG – NO ORECH – NO ZEMIAK – NO JABLKO – NO STRUKOVINY – ZUZANA",
    ),
    (
        "NO MILK, SÓJA, PAPRIKA, CIBUĽA, MAK, FAZUĽA",
        "NO MILK – NO SOJA – NO STRUKOVINY – NO MAK – NO CIBUĽA – NO PAPRIKA",
    ),
    ("SAMKO - NO MILK, SÓJA, KOREŇOVKA", "NO MILK – NO SOJA – NO KOREŇOVKA – SAMO"),
    (
        "ŠPECI - nG,nO,nStr,nPar,nPap,nPoh,nSoj,nQui",
        "NO GLUTEN – NO ORECH – NO STRUKOVINY – NO PARADAJKA – NO PAPRIKA – NO POHANKA – NO SOJA – NO QUINOA",
    ),
)


class Command(BaseCommand):
    help = "Dry-run/apply bezpečného prepojenia potvrdených duplicitných diét."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Vykoná prepojenie po čistom preflight-e.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Explicitný alias predvoleného režimu bez zápisu.",
        )

    def _diet(self, name: str) -> Diet:
        matches = list(Diet.objects.select_for_update().filter(name__iexact=name))
        if len(matches) != 1:
            raise CommandError(f"Diéta chýba alebo nie je jednoznačná: {name!r}")
        return matches[0]

    @staticmethod
    def _conflicts(old: Diet, new: Diet) -> list[str]:
        conflicts: list[str] = []
        for link in PrevadzkaDiet.objects.select_for_update().filter(diet=old):
            target = PrevadzkaDiet.objects.filter(
                prevadzka=link.prevadzka, diet=new
            ).first()
            if target and link.note and target.note and link.note != target.note:
                conflicts.append(
                    f"PrevadzkaDiet {link.prevadzka_id}: dve rozdielne poznámky"
                )
        for item in MealPlanItem.objects.select_for_update().filter(diet=old):
            if MealPlanItem.objects.filter(
                meal_plan=item.meal_plan,
                category=item.category,
                menu_variant=item.menu_variant,
                diet=new,
            ).exists():
                conflicts.append(f"MealPlanItem {item.pk}: cieľový slot už existuje")
        for merge in DietComponentMerge.objects.select_for_update().filter(diet=old):
            if DietComponentMerge.objects.filter(
                date=merge.date,
                meal=merge.meal,
                component_index=merge.component_index,
                diet=new,
            ).exists():
                conflicts.append(
                    f"DietComponentMerge {merge.pk}: cieľový slot už existuje"
                )
        old_bases = set(old.base_diets.values_list("pk", flat=True))
        new_bases = set(new.base_diets.values_list("pk", flat=True))
        if old_bases and new_bases and old_bases != new_bases:
            conflicts.append(f"Diet {old.pk}: rozdielne base_diets na zdroji a cieli")
        if old_bases and new.pk in old_bases:
            conflicts.append(f"Diet {old.pk}: base_diets by vytvorili cyklus")
        if old.composite_of.exists():
            conflicts.append(
                f"Diet {old.pk}: je zložkou inej diéty; vyžaduje manuálne posúdenie"
            )
        return conflicts

    @staticmethod
    def _counts(old: Diet) -> str:
        return (
            f"prevádzky={old.prevadzka_diets.count()}, šablóny={old.meal_templates.count()}, "
            f"položky={old.meal_plan_items.count()}, merge={old.component_merges.count()}, "
            f"base={old.base_diets.count()}, parent={old.composite_of.count()}"
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        if options["dry_run"] and apply:
            raise CommandError("Použi iba jeden z --dry-run alebo --apply.")
        if not apply:
            self.stdout.write(
                self.style.WARNING(
                    "DRY-RUN: nič sa nezapíše. Pre zápis pridaj --apply."
                )
            )

        with transaction.atomic():
            resolved = [
                (self._diet(old_name), self._diet(new_name))
                for old_name, new_name in MAPPINGS
            ]
            conflicts = [
                f"{old.name!r} → {new.name!r}: {reason}"
                for old, new in resolved
                for reason in self._conflicts(old, new)
            ]
            for old, new in resolved:
                self.stdout.write(
                    f"{old.pk}:{old.name!r} → {new.pk}:{new.name!r} ({self._counts(old)})"
                )
            if conflicts:
                raise CommandError(
                    "Preflight našiel konflikty; nič sa nezmenilo:\n"
                    + "\n".join(conflicts)
                )
            if not apply:
                transaction.set_rollback(True)
                return

            for old, new in resolved:
                for link in PrevadzkaDiet.objects.select_for_update().filter(diet=old):
                    target, created = PrevadzkaDiet.objects.get_or_create(
                        prevadzka=link.prevadzka, diet=new, defaults={"note": link.note}
                    )
                    if not created and not target.note and link.note:
                        target.note = link.note
                        target.save(update_fields=["note"])
                    link.delete()
                MealTemplate.objects.filter(diet=old).update(diet=new)
                MealPlanItem.objects.filter(diet=old).update(diet=new)
                DietComponentMerge.objects.filter(diet=old).update(diet=new)
                if old.base_diets.exists():
                    new.base_diets.set(old.base_diets.all())
                    old.base_diets.clear()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Prepojených {len(resolved)} potvrdených mapovaní; nič nebolo zmazané."
                )
            )
