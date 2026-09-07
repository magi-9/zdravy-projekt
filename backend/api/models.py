import datetime
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, List

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class EventLog(models.Model):
    class EventType(models.TextChoices):
        # Kľúče si držia pôvodné meno `order_admin_*` (historické dáta, filtre,
        # frontend) hoci teraz sa logujú objednávky všetkých aktorov, nielen
        # admina — mení sa preto len zobrazovaný label, nie hodnota v DB.
        ORDER_ADMIN_CREATE = "order_admin_create", "Objednávka vytvorená"
        ORDER_ADMIN_UPDATE = "order_admin_update", "Objednávka upravená"
        ORDER_ADMIN_DELETE = "order_admin_delete", "Objednávka vymazaná"
        AUTO_ORDER_RUN = "auto_order_run", "Spustenie auto-objednávok"
        PUSH_BROADCAST = "push_broadcast", "Odoslanie push notifikácie"
        SETTINGS_CHANGE = "settings_change", "Zmena nastavení"
        CRON_RUN = "cron_run", "Cron úloha dobehla"
        CRON_SKIPPED = "cron_skipped", "Cron úloha preskočená (víkend/voľný deň)"
        CRON_FAILED = "cron_failed", "Cron úloha zlyhala"
        DEPLOY_VERSION = "deploy_version", "Nasadená nová verzia"

    event_type = models.CharField(max_length=50, choices=EventType.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="event_logs",
    )
    actor_label = models.CharField(max_length=255, blank=True)
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="targeted_event_logs",
    )
    # Ktorej prevádzky sa udalosť týka — pri objednávkach je to identita
    # riadku (`DailyOrder.prevadzka`), zatiaľ čo `target_user` môže mať viac
    # prevádzok naraz, takže samo osebe nestačí na filter "ktorá prevádzka".
    prevadzka = models.ForeignKey(
        "Prevadzka",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="event_logs",
    )
    summary = models.CharField(max_length=255)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["event_type"]),
            models.Index(fields=["actor"]),
            models.Index(fields=["target_user"]),
            models.Index(fields=["prevadzka"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_event_type_display()}: {self.summary}"


class DailyOrder(models.Model):
    # `user` = kto objednávku zadal (audit, deadline kontroly).
    # `prevadzka` = za koho je objednávka. Identita riadku je (prevadzka, date):
    # jeden login môže objednávať za viac prevádzok, a jednu prevádzku môže
    # objednávať viac loginov.
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="orders",
        null=True,
        help_text="Login, ktorý objednávku naposledy zapísal; môže byť zmazaný.",
    )
    prevadzka = models.ForeignKey(
        "Prevadzka",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    date = models.DateField(db_index=True)
    data = models.JSONField(default=dict)
    scrape_flags = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Poznámky z posledného EduPage scrapu tejto objednávky, napr. "
            "{'attention': [...], 'config_notes': [...], 'unmapped_diets': [...], "
            "'uncertain_diets': [...]}. Prázdne pri ručných objednávkach a "
            "pri scrape bez upozornení."
        ),
    )
    is_auto = models.BooleanField(
        default=False, help_text="True if this order was auto-generated after deadline"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["prevadzka", "date"], name="unique_order_per_prevadzka_date"
            )
        ]
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["prevadzka", "date"]),
            models.Index(fields=["is_auto"]),  # For filtering auto-generated orders
            models.Index(fields=["created_at"]),  # For audit and recent order queries
        ]
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.prevadzka or self.user.email} - {self.date}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Doplní prevádzku, ak ju volajúci neuviedol a je jednoznačná.

        Pri celku s jednou prevádzkou nemá zmysel nútiť každého volajúceho, aby ju
        vypisoval. Pri viacerých je to však nejednoznačné — radšej vyhodíme chybu,
        než by sme uložili objednávku bez prevádzky (tichý `None`), ktorá by sa
        nezobrazila v žiadnom per-prevádzka reporte a obišla by aj unique constraint
        (Postgres pripúšťa viac NULL). Celok bez prevádzky (napr. účet bez profilu)
        necháme prejsť ako legacy.
        """
        if self.prevadzka_id is None and self.user_id is not None:
            profile = UserProfile.objects.filter(user_id=self.user_id).first()
            if profile is not None:
                prve_dve = list(profile.dostupne_prevadzky()[:2])
                if len(prve_dve) == 1:
                    self.prevadzka = prve_dve[0]
                elif len(prve_dve) > 1:
                    raise ValueError(
                        "DailyOrder bez prevádzky pre login s viacerými prevádzkami "
                        f"(user_id={self.user_id}). Prevádzku musí určiť volajúci."
                    )
        return super().save(*args, **kwargs)

    @property
    def status(self) -> str:
        return getattr(self, "_response_status", "submitted")

    @status.setter
    def status(self, value: str) -> None:
        self._response_status = value


class ClosedDay(models.Model):
    """Globálne uzavretý objednávkový deň pre všetky prevádzky."""

    date = models.DateField(unique=True)
    closed_at = models.DateTimeField(auto_now_add=True)
    # SET_NULL (nie PROTECT) — kto deň uzamkol je audit informácia, nie
    # niečo, čo má brániť zmazaniu jeho loginu (mazanie admin účtu padalo
    # na ProtectedError, lebo dotyčný kedysi uzamkol jeden deň).
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="closed_order_days",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"Uzavretý deň {self.date}"


class Diet(models.Model):
    name = models.CharField(max_length=100, unique=True)
    sort_order = models.PositiveSmallIntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, null=True)
    color = models.CharField(
        max_length=7,
        blank=True,
        default="",
        help_text="Voliteľná HEX farba pre admin prehľady, napr. #F97316.",
    )
    text_color = models.CharField(
        max_length=7,
        blank=True,
        default="",
        help_text=(
            "Voliteľná HEX farba textu v gramážnej tabuľke a PDF. Keď je "
            "nastavená spolu s background_color, použije sa presne táto "
            "dvojica namiesto automaticky dopočítanej (#536)."
        ),
    )
    background_color = models.CharField(
        max_length=7,
        blank=True,
        default="",
        help_text=(
            "Voliteľná HEX farba podfarbenia riadku v gramážnej tabuľke a "
            "PDF, viď text_color."
        ),
    )
    base_diets = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        related_name="composite_of",
    )

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


def _default_all_meals() -> List[str]:
    return ["breakfast", "lunch", "olovrant"]


def _default_visible_menus() -> List[str]:
    # "D" a "VEGE1" nie sú v defaulte — sú British School špecifiká (Cluster C,
    # kusový sumár, žiadna gramáž), viditeľné len tej prevádzke cez explicitný
    # `visible_menus` v jej seed-e, nie ako všeobecná voľba (`DEFAULT_VISIBLE_MENUS`
    # v `api/default_visibility.py` musí zostať zosynchronizovaný — viď
    # `TestDefaultVisibleMenus.test_model_field_default_matches_canonical_default`).
    return ["A", "B", "C", "V"]


class GlobalSettings(models.Model):
    deadline_breakfast = models.TimeField(
        default=datetime.time(10, 0), help_text="Deadline for breakfast orders"
    )
    deadline_lunch = models.TimeField(
        default=datetime.time(10, 0), help_text="Deadline for lunch orders"
    )
    deadline_olovrant = models.TimeField(
        default=datetime.time(10, 0), help_text="Deadline for olovrant orders"
    )
    deadline_breakfast_is_day_before = models.BooleanField(
        default=False,
        help_text=(
            "When enabled, breakfast deadline applies to the day before the meal date"
        ),
    )
    deadline_lunch_is_day_before = models.BooleanField(
        default=False,
        help_text=(
            "When enabled, lunch deadline applies to the day before the meal date"
        ),
    )
    deadline_olovrant_is_day_before = models.BooleanField(
        default=False,
        help_text=(
            "When enabled, olovrant deadline applies to the day before the meal date"
        ),
    )
    deadline_menu_bc = models.TimeField(
        default=datetime.time(7, 30),
        help_text="Deadline for ordering/changing menu B and C, N days before the meal date",
    )
    deadline_menu_bc_days_before = models.PositiveSmallIntegerField(
        default=2,
        help_text="How many days before the meal date the menu B/C deadline falls on",
    )
    edupage_auto_scrape_enabled = models.BooleanField(
        default=True,
        help_text="When disabled, automatic EduPage scraping periodic tasks are removed.",
    )
    edupage_scrape_time_breakfast = models.TimeField(
        null=True,
        blank=True,
        help_text=(
            "Override: scrape breakfast EduPage orders at this time instead of "
            "at deadline_breakfast. Leave empty to keep scraping at the deadline."
        ),
    )
    edupage_scrape_time_lunch = models.TimeField(
        null=True,
        blank=True,
        help_text=(
            "Override: scrape lunch EduPage orders at this time instead of "
            "at deadline_lunch. Leave empty to keep scraping at the deadline."
        ),
    )
    edupage_scrape_time_olovrant = models.TimeField(
        null=True,
        blank=True,
        help_text=(
            "Override: scrape olovrant EduPage orders at this time instead of "
            "at deadline_olovrant. Leave empty to keep scraping at the deadline."
        ),
    )
    edupage_scrape_time_breakfast_is_day_before = models.BooleanField(
        default=False,
        help_text=(
            "Only used when edupage_scrape_time_breakfast is set: whether that "
            "override time targets the next workday (like a day-before deadline) "
            "or today. Independent of deadline_breakfast_is_day_before, because "
            "an override commonly runs after midnight — already on the meal's "
            "own day — even though the deadline itself falls the evening before."
        ),
    )
    edupage_scrape_time_lunch_is_day_before = models.BooleanField(
        default=False,
        help_text=(
            "Only used when edupage_scrape_time_lunch is set. See "
            "edupage_scrape_time_breakfast_is_day_before."
        ),
    )
    edupage_scrape_time_olovrant_is_day_before = models.BooleanField(
        default=False,
        help_text=(
            "Only used when edupage_scrape_time_olovrant is set. See "
            "edupage_scrape_time_breakfast_is_day_before."
        ),
    )
    daily_report_enabled = models.BooleanField(
        default=True,
        help_text=(
            "When disabled, the daily report periodic tasks are removed without "
            "touching report_email_recipients."
        ),
    )
    report_email_recipients = models.JSONField(
        default=list,
        blank=True,
        help_text="List of email addresses that receive the daily order report.",
    )
    client_contact_name = models.CharField(max_length=120, blank=True, default="")
    client_contact_role = models.CharField(max_length=120, blank=True, default="")
    client_contact_email = models.EmailField(blank=True, default="")
    client_contact_phone = models.CharField(max_length=40, blank=True, default="")

    class Meta:
        verbose_name = "System Settings"
        verbose_name_plural = "System Settings"

    def edupage_scrape_schedule_for(self, meal_type: str) -> tuple[datetime.time, bool]:
        """Effective (time, is_day_before) the EduPage scrape fires at for `meal_type`.

        Defaults to the order deadline (`deadline_{meal_type}`,
        `deadline_{meal_type}_is_day_before`) — the scrape then runs at the exact
        moment orders close, so nothing placed right up to the deadline is missed.
        Setting `edupage_scrape_time_{meal_type}` decouples the scrape from the
        deadline (e.g. deadline stays the evening before, but the scrape runs
        after midnight); its own `edupage_scrape_time_{meal_type}_is_day_before`
        then governs the target-day rule instead of the deadline's.
        """
        override_time = getattr(self, f"edupage_scrape_time_{meal_type}", None)
        if override_time is not None:
            return override_time, getattr(
                self, f"edupage_scrape_time_{meal_type}_is_day_before", False
            )
        return getattr(self, f"deadline_{meal_type}"), getattr(
            self, f"deadline_{meal_type}_is_day_before", False
        )

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.pk and GlobalSettings.objects.exists():
            raise ValueError(
                "GlobalSettings is a singleton; update the existing instance (pk=1) "
                "instead of creating a new one."
            )
        return super(GlobalSettings, self).save(*args, **kwargs)

    def __str__(self) -> str:
        return "Global System Settings"


class UserProfile(models.Model):
    """Login-level údaje; doménové dáta žijú na Celok/Prevadzka/access modeloch."""

    class Role(models.TextChoices):
        KLIENT = "klient", "Klient"
        ADMIN = "admin", "Admin"
        SUPERADMIN = "superadmin", "Superadmin"
        KUCHYNA = "kuchyna", "Kuchyňa"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    company_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Interný názov prevádzky (používa sa interne)",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.KLIENT,
        db_index=True,
        help_text=(
            "Rola loginu (#482). `is_staff` zostáva odvodeným zrkadlom pre Django "
            "admin — autoritatívna je táto hodnota, čítaj ju cez `api.roles.role_of`."
        ),
    )
    section_overrides = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Granulárne oprávnenia per sekcia (#484) ako {sekcia: úroveň}. "
            'Chýbajúci kľúč znamená „podľa role", nie „bez prístupu". Býva to '
            "pár položiek a číta sa pri každom requeste, preto sedí na profile "
            "a nie vo vlastnej tabuľke — príde spolu s ním jedným dotazom."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    onboarding_completed = models.BooleanField(
        default=False,
        help_text="True once the client has completed or dismissed the onboarding tour.",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.company_name or self.user.email

    def dostupne_prevadzky(self):
        """Aktívne prevádzky z explicitných celok/prevádzka access záznamov."""
        celok_ids = self.celok_accesses.values_list("celok_id", flat=True)
        prevadzka_ids = self.prevadzka_accesses.values_list("prevadzka_id", flat=True)
        return (
            Prevadzka.objects.filter(is_active=True)
            .filter(models.Q(celok_id__in=celok_ids) | models.Q(pk__in=prevadzka_ids))
            .distinct()
        )

    def dostupne_celky(self):
        """Celky dosiahnuteľné cez oba explicitné access scope modely."""
        return Celok.objects.filter(
            models.Q(profile_accesses__profile=self)
            | models.Q(prevadzky__profile_accesses__profile=self)
        ).distinct()

    def primary_celok(self):
        """Vráti jediný dostupný celok; pri 0/N celkoch je výsledok nejednoznačný."""
        celky = list(self.dostupne_celky()[:2])
        return celky[0] if len(celky) == 1 else None

    def is_edupage_only(self) -> bool:
        """True, ak všetky dostupné prevádzky prijímajú objednávky cez EduPage."""
        prevadzky = self.dostupne_prevadzky()
        return (
            prevadzky.exists()
            and not prevadzky.exclude(
                celok__zdroj_objednavok=Celok.ZdrojObjednavok.EDUPAGE
            ).exists()
        )


class EdupageConnection(models.Model):
    """Jeden EduPage feed, ktorý môže zásobovať prevádzky z viacerých celkov."""

    name = models.CharField(max_length=255)
    mealsguest_url = models.URLField(max_length=500, unique=True)
    api_identifier = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    dedicated_scrape_hour = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Set together with dedicated_scrape_minute to scrape this "
            "connection on its own crontab (day before, Sun-Thu, targeting "
            "the next workday) instead of at the shared GlobalSettings meal "
            "deadlines every other connection uses. For a facility whose "
            "deadline schedule genuinely doesn't apply, e.g. British School "
            "(#535) — code review 2026-08-31 generalized this off a "
            "hardcoded connection name."
        ),
    )
    dedicated_scrape_minute = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]

    def __str__(self) -> str:
        return self.name


class Celok(models.Model):
    """Fakturačná jednotka — zastrešuje 1..N prevádzok a 1..N prihlásení.

    Celok má fakturačnú adresu; prevádzka má výdajnú adresu. Sú to rôzne adresy,
    preto sú to rôzne modely. `Celok` je samostatná entita (nie `UserProfile`), lebo
    pod jeden celok môže patriť viac loginov — každý s prístupom k inej podmnožine
    prevádzok.
    """

    class ZdrojObjednavok(models.TextChoices):
        APP = "app", "Aplikácia"
        EDUPAGE = "edupage", "EduPage"

    nazov = models.CharField(max_length=255, unique=True)
    billing_name = models.CharField(max_length=255, blank=True)
    adresa = models.CharField(
        max_length=500, blank=True, help_text="Fakturačná adresa celku."
    )
    ico = models.CharField(max_length=20, blank=True)
    dic = models.CharField(max_length=20, blank=True)
    zdroj_objednavok = models.CharField(
        max_length=16,
        choices=ZdrojObjednavok.choices,
        default=ZdrojObjednavok.APP,
        db_index=True,
        help_text=(
            "Odkiaľ chodia objednávky celku: 'edupage' (scraper) alebo 'app' "
            "(klient v appke). Určuje zaradenie v admin prehľade dodania podkladov."
        ),
    )

    class Meta:
        ordering = ["nazov"]

    def __str__(self) -> str:
        return self.nazov


class Vydaj(models.TextChoices):
    """Výdajný bod kuchyne (na obrazovke "Cluster"), z ktorého ide jedlo von.

    Kuchyňa vydáva stravu z dvoch miest súčasne a každé chce vlastnú tabuľku.
    Výdaj je vlastnosť TRASY: prevádzka patrí do toho výdaja, v ktorého trase
    stojí, takže sa nastavuje na jednom mieste a nemá si ako protirečiť.

    Kľúče (`A`/`B`/`C`/`D`) sú interné a nemenia sa (#531) — premenované je len
    zobrazované meno "Výdaj X" → "Cluster X".
    """

    A = "A", "Cluster A"
    B = "B", "Cluster B"
    C = "C", "Cluster C"
    D = "D", "Cluster D"


class Prevadzka(models.Model):
    """Jedna prevádzka (miesto výdaja) v rámci celku.

    Objednávky sa vždy vedú per prevádzka (`DailyOrder.prevadzka`), aj keď má celok
    len jednu — jednotný model je lacnejší než dve vetvy v každom reporte.
    """

    celok = models.ForeignKey(Celok, on_delete=models.PROTECT, related_name="prevadzky")
    edupage_connection = models.ForeignKey(
        EdupageConnection,
        on_delete=models.SET_NULL,
        related_name="prevadzky",
        null=True,
        blank=True,
    )
    nazov = models.CharField(
        max_length=255,
        help_text="Názov prevádzky, napr. 'Jolly 1'. Kľúč v DailyOrder.data.",
    )
    adresa = models.CharField(
        max_length=500, blank=True, help_text="Adresa výdajného miesta."
    )
    # Prázdne pre jedno-prevádzkové celky: berie sa všetko, čo scraper vráti.
    edupage_match = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            "Prefix payer labelu / menu skratky, podľa ktorého sa EduPage riadky "
            "priradia tejto prevádzke (napr. 'J1', 'Palisády', 'B - Les'). "
            "Viac prefixov oddeľ BODKOČIARKOU — škola nemá spoločný prefix, jej "
            "skupiny sa volajú '1.st', '2.st' aj 'Dospelý' ('1.st; 2.st; Dospelý'). "
            "Čiarka oddeľovač byť nemôže: sama sa vyskytuje v skratkách menu "
            "('mšMal,Hey' je jedna skratka pre dve škôlky)."
        ),
    )

    def edupage_prefixes(self) -> list[str]:
        """`edupage_match` rozpadnutý na jednotlivé prefixy.

        Jeden prefix nestačí všade: MŠ skupiny zdieľajú prefix `MŠ`, ale školské sa
        volajú `1.st.`, `2.st.` aj `Dospelý` — bez viacerých prefixov by školské
        riadky ostali nezaradené a scrape by celý celok zahodil ako neúplný.

        Oddeľovač je bodkočiarka, nie čiarka: EduPage skratky čiarku bežne obsahujú
        (`mšMal,Hey` je JEDNA skratka zdieľaná dvoma škôlkami), takže čiarkový
        oddeľovač by ju rozsekol na dva neplatné prefixy.
        """
        return [part.strip() for part in self.edupage_match.split(";") if part.strip()]

    sort_order = models.PositiveSmallIntegerField(default=0)
    delivery_route = models.ForeignKey(
        "DeliveryRoute",
        on_delete=models.SET_NULL,
        related_name="prevadzky",
        null=True,
        blank=True,
        help_text="Rozvozová trasa používaná v admin Prehľade.",
    )
    delivery_sort_order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Poradie prevádzky v rámci rozvozovej trasy.",
    )
    report_alias = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Voliteľný názov v admin Prehľade, ak sa má líšiť od názvu prevádzky.",
    )
    delivery_note = models.TextField(
        blank=True,
        default="",
        help_text="Interná poznámka pre rozvozový/gramážový prehľad.",
    )
    is_active = models.BooleanField(default=True)
    # Oddelené od PortionType.coefficient (ten je len gramáž): prevádzka môže
    # fakturovať porciu inou váhou, než akú má na tanieri. Edulienka účtuje
    # predškoláka (EduPage `porcia=1` → `ZŠ 1.stupeň`) ako 1,25 porcie.
    billing_portion_coefficients = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "{PortionType.name: koeficient} pre počet fakturovaných porcií. "
            "Chýbajúci typ = 1.0, teda prázdne {} = beží po hlavách ako doteraz."
        ),
    )
    visible_menus = models.JSONField(
        default=_default_visible_menus,
        blank=True,
        help_text="Menu typy dostupné pre objednávky tejto prevádzky.",
    )
    menu_day_restrictions = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "{menu písmeno: [ISO deň v týždni, 1=pondelok..7=nedeľa]} — obmedzenie, "
            "kedy sa dané menu (z visible_menus) dá objednať, napr. menu B len "
            'v piatok = {"B": [5]}. Chýbajúci kľúč alebo prázdny zoznam = každý deň.'
        ),
    )
    visible_meals = models.JSONField(
        default=_default_all_meals,
        blank=True,
        help_text="Chody dostupné pre objednávky tejto prevádzky.",
    )
    visible_diets = models.ManyToManyField(
        Diet,
        through="PrevadzkaDiet",
        blank=True,
        related_name="visible_for_prevadzky",
        help_text="Diéty dostupné pre objednávky tejto prevádzky.",
    )
    visible_portion_types = models.ManyToManyField(
        "PortionType",
        blank=True,
        related_name="visible_for_prevadzky_portion_types",
        help_text="Veľkosti porcií dostupné pre objednávky tejto prevádzky.",
    )
    pack_separately_enabled = models.BooleanField(default=False)
    adults_pack_separately_enabled = models.BooleanField(
        default=False,
        help_text="Keď je zapnuté, všetky porcie „Dospelý (SŠ)“ sa v gramážnej "
        "tabuľke automaticky vykazujú ako zabalené zvlášť — bez toho, aby ich "
        "klient musel manuálne označiť cez „Zabaliť zvlášť“.",
    )
    admin_order_note = models.TextField(
        blank=True,
        default="",
        help_text="Interná poznámka k objednávkam prevádzky v admin prehľadoch.",
    )
    auto_order_paused = models.BooleanField(
        default=False,
        help_text=(
            "Nastaví sa automaticky, keď klient vynuluje alebo zmaže objednávku "
            "(prázdne 'submitted' dáta, alebo 'draft'). Kým je True, "
            "apply_auto_orders pre túto prevádzku nič nepreklápa — obnoví sa "
            "opäť False pri najbližšej reálnej (neprázdnej) objednávke."
        ),
    )
    auto_order_breakfast_source = models.CharField(
        max_length=20,
        choices=[("breakfast", "Raňajky"), ("lunch", "Obed")],
        default="breakfast",
        help_text=(
            "Z ktorého chodu predošlého dňa apply_auto_orders naplní raňajky. "
            "Default 'breakfast' = raňajky sa kopírujú z predošlých raňajok. "
            "'lunch' = raňajky sa namiesto toho naplnia predošlým obedom "
            "(napr. Bystrá škôlky, kde sa raňajky objednávajú ako obed z "
            "predošlého dňa)."
        ),
    )
    olovrant_s_obedom = models.BooleanField(
        default=False,
        help_text=(
            "Olovrant tejto prevádzky ide s obedovým, nie popoludňajším "
            "rozvozom — v gramážnej tabuľke (aj v PDF) sa preto zvýrazní žlto, "
            "aby si ho kuchyňa naložila spolu s obedom."
        ),
    )
    gramage_summary_only = models.BooleanField(
        default=False,
        help_text=(
            "Prevádzka nemá gramážové menu-šablóny (British School, Cluster C, "
            "#531) — objednávky sa v gramážnej tabuľke/PDF vôbec nevykazujú "
            "cez bežnú per-klientsku mriežku s gramami, len ako samostatný "
            "kusový sumár (+ prepočet na MŠ porcie) v `MealPlanService."
            "_build_gramage_summary_only_cluster`."
        ),
    )

    class Meta:
        ordering = ["celok_id", "sort_order", "nazov"]
        constraints = [
            models.UniqueConstraint(
                fields=["celok", "nazov"], name="unique_prevadzka_nazov_per_celok"
            )
        ]

    def billing_coefficient(self, portion_name: str) -> Decimal:
        """Koeficient fakturovanej porcie pre daný PortionType.name (default 1.0)."""
        raw = (self.billing_portion_coefficients or {}).get(portion_name)
        if raw is None:
            return Decimal("1")
        try:
            return Decimal(str(raw))
        except (InvalidOperation, TypeError):
            logger.warning(
                "Prevadzka %s: nečitateľný billing koeficient %r pre %r — beriem 1.0",
                self.pk,
                raw,
                portion_name,
            )
            return Decimal("1")

    def __str__(self) -> str:
        return self.nazov


class PrevadzkaDiet(models.Model):
    """`through` model pre `Prevadzka.visible_diets` — nesie internú
    poznámku k danej dvojici (prevádzka, diéta), napr. "len na objednávku
    vopred" alebo kontakt na rodiča alergika. Poznámka je viazaná na
    dvojicu, nie na diétu samotnú, lebo tá istá diéta môže mať v rôznych
    prevádzkach inú poznámku."""

    prevadzka = models.ForeignKey(
        Prevadzka, on_delete=models.CASCADE, related_name="prevadzka_diets"
    )
    diet = models.ForeignKey(
        Diet, on_delete=models.CASCADE, related_name="prevadzka_diets"
    )
    note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["prevadzka", "diet"], name="unique_prevadzka_diet"
            )
        ]

    def __str__(self) -> str:
        return f"{self.prevadzka} — {self.diet}"


class ProfileCelokAccess(models.Model):
    """Login má prístup ku všetkým súčasným aj budúcim prevádzkam celku."""

    profile = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="celok_accesses",
    )
    celok = models.ForeignKey(
        Celok,
        on_delete=models.CASCADE,
        related_name="profile_accesses",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "celok"],
                name="unique_profile_celok_access",
            )
        ]


class ProfilePrevadzkaAccess(models.Model):
    """Login má prístup iba ku konkrétnej prevádzke."""

    profile = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="prevadzka_accesses",
    )
    prevadzka = models.ForeignKey(
        Prevadzka,
        on_delete=models.CASCADE,
        related_name="profile_accesses",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "prevadzka"],
                name="unique_profile_prevadzka_access",
            )
        ]


class DeliveryBlock(models.Model):
    """Hlavný blok rozvozového prehľadu, napr. bežné trasy alebo extra trasy."""

    name = models.CharField(max_length=120, unique=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    include_in_main_summary = models.BooleanField(default=True)
    include_in_extra_summary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class DeliveryRoute(models.Model):
    """Jedna rozvozová trasa v rámci bloku."""

    block = models.ForeignKey(
        DeliveryBlock, on_delete=models.CASCADE, related_name="routes"
    )
    vydaj = models.CharField(
        max_length=1,
        choices=Vydaj.choices,
        default=Vydaj.A,
        db_index=True,
        help_text=(
            "Výdajný bod kuchyne, ktorý túto trasu obsluhuje. Gramážová tabuľka "
            "sa delí podľa neho — trasy výdaja A tvoria tabuľku A, trasy výdaja "
            "B tabuľku B, atď."
        ),
    )
    name = models.CharField(max_length=160)
    driver = models.CharField(max_length=80, blank=True, default="")
    departure_time = models.TimeField(null=True, blank=True)
    note = models.TextField(blank=True, default="")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["block__sort_order", "sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["block", "name"], name="unique_delivery_route_name_per_block"
            )
        ]

    def __str__(self) -> str:
        return self.name


class PasswordResetToken(models.Model):
    """
    Single-use token for password reset via email.
    Expires after TOKEN_EXPIRY_HOURS hours and is invalidated once used.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    token = models.CharField(max_length=128, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "used", "expires_at"]),
        ]

    def __str__(self) -> str:
        return f"PasswordResetToken for {self.user.email}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.used and not self.is_expired


# ──────────────────────────────────────────────────────────────────────────────
# Jedálniček (Meal Plan) module
# ──────────────────────────────────────────────────────────────────────────────


class MealCategory(models.TextChoices):
    BREAKFAST_SNACK = "breakfast_snack", "Raňajky-desiata"
    SOUP = "soup", "Polievka"
    MAIN_COURSE = "main_course", "Hlavný chod"
    AFTERNOON_SNACK = "afternoon_snack", "Olovrant"


class MealTemplate(models.Model):
    """
    Reusable meal template selected when building a daily plan.
    Comes from a fixed catalog of numbered types (e.g. "Hlavný chod 3"),
    each with a weight breakdown per component.
    """

    category = models.CharField(
        max_length=20, choices=MealCategory.choices, db_index=True
    )
    name = models.CharField(max_length=200)
    # Human-readable composition label, e.g. "185g + šalát 25g + syr 10g"
    weight_label = models.CharField(max_length=100, blank=True)
    # Base weight in grams used for calculations (Adult 100% portion).
    # Sum of the gram components below.
    base_weight_grams = models.DecimalField(max_digits=8, decimal_places=2)
    # Structured weight breakdown, e.g.
    # [{"label": "Hlavná zložka", "grams": "110", "unit": "g"}, ...]
    components = models.JSONField(default=list, blank=True)
    # For the two catalog rows where a component is a fixed piece-count per
    # portion type instead of grams × coefficient (vajce / gulička-fašírka):
    # {"component_label": str, "unit": "ks", "counts_by_portion_type": {name: count}}
    unit_exception = models.JSONField(null=True, blank=True)
    # Lunch can have variants A / B / C …
    menu_variant = models.CharField(
        max_length=10,
        blank=True,
        help_text="Leave empty for breakfast/snack. E.g. 'A', 'B', 'C'.",
    )
    diet = models.ForeignKey(
        "Diet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="meal_templates",
        help_text="Optional diet this template variant is prepared for.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "menu_variant", "name"]
        indexes = [
            models.Index(fields=["category", "is_active"]),
        ]

    def __str__(self) -> str:
        variant = f" [{self.menu_variant}]" if self.menu_variant else ""
        return f"{self.get_category_display()}{variant}: {self.name}"


class PortionType(models.Model):
    """
    Defines a consumer group and their weight coefficient.
    Seeded with Škôlka/MS as the 1.00 baseline; other groups are multipliers.
    """

    name = models.CharField(max_length=100, unique=True)
    coefficient = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        help_text="Multiplier applied to template base_weight_grams. 1.0 = 100%.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        pct = int(self.coefficient * 100)
        return f"{self.name} ({pct}%)"


class DailyMealPlan(models.Model):
    """
    The meal plan for one calendar day.
    Contains the template selections and the enrolled person counts.
    """

    date = models.DateField(unique=True, db_index=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="meal_plans_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"Jedálniček {self.date}"


class MealPlanItem(models.Model):
    """
    One meal slot within a DailyMealPlan.
    One item per (meal_plan, category, menu_variant) combination.
    """

    meal_plan = models.ForeignKey(
        DailyMealPlan, on_delete=models.CASCADE, related_name="items"
    )
    template = models.ForeignKey(
        MealTemplate, on_delete=models.PROTECT, related_name="plan_items"
    )
    # Denormalised for query convenience
    category = models.CharField(max_length=20, choices=MealCategory.choices)
    menu_variant = models.CharField(max_length=10, blank=True)
    diet = models.ForeignKey(
        "Diet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="meal_plan_items",
        help_text="Optional diet-specific meal plan item. Null means standard/default.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["meal_plan", "category", "menu_variant", "diet"],
                name="uniq_meal_plan_item_slot_diet",
                nulls_distinct=False,
            )
        ]

    def __str__(self) -> str:
        diet = f" {self.diet.name}" if self.diet_id else ""
        return f"{self.meal_plan.date} {self.category} {self.menu_variant}{diet}"


class EnrolledCount(models.Model):
    """
    How many persons of a given PortionType are enrolled on a specific DailyMealPlan.
    Used to compute total gramage per day.
    """

    meal_plan = models.ForeignKey(
        DailyMealPlan, on_delete=models.CASCADE, related_name="enrolled_counts"
    )
    portion_type = models.ForeignKey(
        PortionType, on_delete=models.PROTECT, related_name="enrolled_counts"
    )
    count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ["meal_plan", "portion_type"]

    def __str__(self) -> str:
        return f"{self.meal_plan.date} {self.portion_type.name}: {self.count}"


class Holiday(models.Model):
    """
    A day on which no orders can be placed.
    Admin can define individual dates or ranges.
    """

    date = models.DateField(unique=True, db_index=True)
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["date"]

    def __str__(self) -> str:
        suffix = f" ({self.reason})" if self.reason else ""
        return f"Voľný deň {self.date}{suffix}"


class PrevadzkaClosure(models.Model):
    """Voľno JEDNEJ prevádzky — deň alebo súvislý rozsah (napr. prázdniny škôlky).

    Zámerne nie `Holiday`: `Holiday` je celosystémové voľno kuchyne (nevarí sa
    nikde), toto zavrie len konkrétnu prevádzku, kým ostatné objednávajú ďalej.
    Preto aj rozsah namiesto riadku na deň — prázdniny sú súvislý úsek a admin
    ho má vedieť zrušiť jedným klikom, nie mazať 14 riadkov.
    """

    prevadzka = models.ForeignKey(
        Prevadzka, on_delete=models.CASCADE, related_name="closures"
    )
    date_from = models.DateField(db_index=True)
    date_to = models.DateField(db_index=True)
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_from", "prevadzka_id"]
        verbose_name = "voľno prevádzky"
        verbose_name_plural = "voľná prevádzky"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(date_to__gte=models.F("date_from")),
                name="prevadzka_closure_range_ordered",
            )
        ]
        indexes = [
            models.Index(
                fields=["prevadzka", "date_from", "date_to"],
                name="prevadzka_closure_lookup",
            )
        ]

    def clean(self) -> None:
        super().clean()
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise DjangoValidationError(
                {"date_to": "Koniec voľna nesmie byť pred jeho začiatkom."}
            )

    def covers(self, day: datetime.date) -> bool:
        return self.date_from <= day <= self.date_to

    def __str__(self) -> str:
        span = (
            str(self.date_from)
            if self.date_from == self.date_to
            else f"{self.date_from} – {self.date_to}"
        )
        suffix = f" ({self.reason})" if self.reason else ""
        return f"Voľno {self.prevadzka_id}: {span}{suffix}"


class PushSubscription(models.Model):
    """
    Web Push subscription for a user device/browser.
    Stores the endpoint and ECDH keys needed to send push messages via VAPID.
    One user can have multiple subscriptions (multi-device support).
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="push_subscriptions"
    )
    endpoint = models.TextField()
    p256dh = models.TextField()
    auth = models.TextField()
    user_agent = models.TextField(blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    failure_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["user", "endpoint"]
        indexes = [
            models.Index(fields=["user"]),
        ]

    def __str__(self) -> str:
        return f"PushSubscription({self.user.email}, …{self.endpoint[-20:]})"


class PushNotificationAttempt(models.Model):
    """Audit trail for Web Push delivery attempts."""

    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_STALE_REMOVED = "stale_removed"
    STATUS_UNAVAILABLE = "unavailable"

    STATUS_CHOICES = [
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
        (STATUS_STALE_REMOVED, "Stale removed"),
        (STATUS_UNAVAILABLE, "Unavailable"),
    ]

    subscription = models.ForeignKey(
        PushSubscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_attempts",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="push_notification_attempts",
    )
    endpoint = models.TextField()
    title = models.CharField(max_length=200)
    body = models.TextField()
    url = models.CharField(max_length=500, default="/home")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    http_status = models.PositiveIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    attempt_number = models.PositiveSmallIntegerField(default=1)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["user", "read_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"PushNotificationAttempt({self.status}, …{self.endpoint[-20:]})"


class LoadingStatus(models.Model):
    """Odkliknutie, že položka je pre danú prevádzku a deň naložená (#487).

    `item_key` je kľúč stĺpcovej skupiny z gramážového prehľadu
    (`col_groups[].key` — napr. `soup`, `main_course_A`, `afternoon_snack_diet_3`).
    Je odvodený z obsahu jedálnička, nie z poradia riadkov, takže prežije
    prekreslenie tabuľky aj zmenu triedenia prevádzok.

    Riadok sa nemaže ani pri odškrtnutí — `is_loaded=False` si ponecháva stopu,
    kto a kedy naposledy stav zmenil. Kuchyňa je rola s viacerými účtami, takže
    „kto to odklikol" je pri reklamácii podstatná informácia.
    """

    date = models.DateField(db_index=True)
    prevadzka = models.ForeignKey(
        Prevadzka, on_delete=models.CASCADE, related_name="loading_statuses"
    )
    item_key = models.CharField(
        max_length=100, help_text="Kľúč stĺpcovej skupiny z gramážového prehľadu."
    )
    is_loaded = models.BooleanField(default=True)
    marked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loading_marks",
    )
    marked_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["date", "prevadzka", "item_key"]
        indexes = [models.Index(fields=["date", "prevadzka"])]
        ordering = ["date", "prevadzka_id", "item_key"]

    def __str__(self) -> str:
        stav = "naložené" if self.is_loaded else "nenaložené"
        return f"{self.date} {self.prevadzka}: {self.item_key} — {stav}"


class PrevadzkaLoadingConfirmation(models.Model):
    """Finálne potvrdenie, že prevádzka je celá naložená (#487).

    Samostatný model, nie `item_key=""` na `LoadingStatus` — potvrdenie je iná
    vec než položka a miešať ich do jednej tabuľky by si vyžiadalo strážiť
    magickú hodnotu kľúča.
    """

    date = models.DateField(db_index=True)
    prevadzka = models.ForeignKey(
        Prevadzka, on_delete=models.CASCADE, related_name="loading_confirmations"
    )
    confirmed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loading_confirmations",
    )
    confirmed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["date", "prevadzka"]
        ordering = ["-confirmed_at"]

    def __str__(self) -> str:
        return f"{self.date} {self.prevadzka}: naložené"
