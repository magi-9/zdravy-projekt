import os

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from api.models import Prevadzka, ProfilePrevadzkaAccess, UserProfile

DEMO_ADMIN_EMAIL = "admin@example.com"
DEMO_ADMIN_PASSWORD = "admin"
DEMO_OPERATION_EMAIL = "prevadzka@example.com"
DEMO_OPERATION_PASSWORD = "prevadzka"
DEMO_OPERATION_CELOK = "Demo prevádzka"
DEMO_SPRAVCA_EMAIL = "spravca@example.com"
DEMO_SPRAVCA_PASSWORD = "spravca"
DEMO_KUCHYNA_EMAIL = "kuchyna@example.com"
DEMO_KUCHYNA_PASSWORD = "kuchyna"
# Demo login je zámerne viac-prevádzkový: jedno-prevádzkový celok nikdy
# neodhalí, že objednávka patrí prevádzke a nie prihláseniu — práve tam vznikali
# chyby (výber prevádzky pri odosielaní, história a súčty za celok).
DEMO_EXTRA_PREVADZKY = ["Demo jasle", "Demo škola"]


class Command(BaseCommand):
    help = "Initialize roles and, outside production, optional demo users"

    def add_arguments(self, parser):
        parser.add_argument(
            "--create-default-users",
            action="store_true",
            help=(
                "Create the legacy demo admin/prevadzka users. This is refused "
                "when DJANGO_SETTINGS_MODULE points to production."
            ),
        )
        parser.add_argument(
            "--fast-access-only",
            action="store_true",
            help=(
                "Create only the local fast-access accounts. Unlike the legacy "
                "demo setup this does not create a Celok or Prevádzka."
            ),
        )

    def handle(self, *args, **options):
        roles = ["Client", "Admin", "Staff"]
        for role_name in roles:
            group, created = Group.objects.get_or_create(name=role_name)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created group "{role_name}"'))
            else:
                self.stdout.write(f'Group "{role_name}" already exists')

        settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
        is_production = settings_module.endswith(".prod")
        create_default_users = options["create_default_users"] or not is_production

        if not create_default_users:
            self.stdout.write(
                self.style.SUCCESS(
                    "Production mode detected: roles initialized; default demo users skipped."
                )
            )
            return

        if is_production:
            raise RuntimeError(
                "Refusing to create default users with weak passwords in production."
            )

        if options["fast_access_only"]:
            self._ensure_fast_access_users()
            return

        admin_user, created = self._get_or_create_demo_user(
            email=DEMO_ADMIN_EMAIL,
            legacy_username="admin",
            is_staff=True,
            is_superuser=True,
        )
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.set_password(DEMO_ADMIN_PASSWORD)
        admin_user.save()
        admin_group = Group.objects.get(name="Admin")
        admin_user.groups.add(admin_group)

        # Demo admin je zámerne superadmin, aby sa dala prejsť celá konzola.
        # Migrácia 0073 degraduje ostatných superadminov, takže sa mu rola
        # obnovuje tu — v produkcii sa sem beh nikdy nedostane.
        demo_profile, _ = UserProfile.objects.get_or_create(
            user=admin_user, defaults={"company_name": "Demo admin"}
        )
        if demo_profile.role != UserProfile.Role.SUPERADMIN:
            demo_profile.role = UserProfile.Role.SUPERADMIN
            demo_profile.save(update_fields=["role"])

        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Created superuser "{DEMO_ADMIN_EMAIL}"')
            )
            self.stdout.write(
                self.style.WARNING(
                    "SECURITY WARNING: Created default admin user with weak password. CHANGE IN PRODUCTION!"
                )
            )
        else:
            self.stdout.write(f'Superuser "{DEMO_ADMIN_EMAIL}" already exists')

        operation_user, created = self._get_or_create_demo_user(
            email=DEMO_OPERATION_EMAIL,
            legacy_username="prevadzka",
            is_staff=False,
            is_superuser=False,
        )
        operation_user.is_staff = False
        operation_user.is_superuser = False
        operation_user.set_password(DEMO_OPERATION_PASSWORD)
        operation_user.save()
        client_group = Group.objects.get(name="Client")
        operation_user.groups.add(client_group)
        profile, _ = UserProfile.objects.get_or_create(user=operation_user)
        if not profile.company_name:
            profile.company_name = "Demo prevádzka"
        profile.save()
        celok = profile.primary_celok()
        if celok:
            celok.nazov = DEMO_OPERATION_CELOK
            if not celok.billing_name:
                celok.billing_name = "Demo prevádzka, s.r.o."
            celok.save(update_fields=["nazov", "billing_name"])
            if profile.dostupne_prevadzky().count() == 1:
                profile.dostupne_prevadzky().update(nazov=DEMO_OPERATION_CELOK)
            self._ensure_demo_prevadzky(celok)

        if created:
            self.stdout.write(self.style.SUCCESS('Created operation user "prevadzka"'))
            self.stdout.write(
                self.style.WARNING(
                    "SECURITY WARNING: Created default prevádzka user with weak password. CHANGE IN PRODUCTION!"
                )
            )
        else:
            self.stdout.write(f'Operation user "{DEMO_OPERATION_EMAIL}" already exists')

        self._ensure_demo_spravca()
        self._ensure_demo_kuchyna()

    def _ensure_fast_access_users(self) -> None:
        """Create local quick-login accounts without seeding demo domain data."""
        users = (
            (DEMO_ADMIN_EMAIL, "admin", UserProfile.Role.SUPERADMIN, True, True),
            (DEMO_OPERATION_EMAIL, "prevadzka", UserProfile.Role.KLIENT, False, False),
            (DEMO_SPRAVCA_EMAIL, "spravca", UserProfile.Role.ADMIN, True, False),
            (DEMO_KUCHYNA_EMAIL, "kuchyna", UserProfile.Role.KUCHYNA, False, False),
        )
        passwords = {
            DEMO_ADMIN_EMAIL: DEMO_ADMIN_PASSWORD,
            DEMO_OPERATION_EMAIL: DEMO_OPERATION_PASSWORD,
            DEMO_SPRAVCA_EMAIL: DEMO_SPRAVCA_PASSWORD,
            DEMO_KUCHYNA_EMAIL: DEMO_KUCHYNA_PASSWORD,
        }
        profiles: dict[str, UserProfile] = {}
        for email, username, role, is_staff, is_superuser in users:
            user, _ = self._get_or_create_demo_user(
                email=email,
                legacy_username=username,
                is_staff=is_staff,
                is_superuser=is_superuser,
            )
            user.is_staff = is_staff
            user.is_superuser = is_superuser
            user.set_password(passwords[email])
            user.save()
            profile = getattr(user, "profile", None)
            if profile is None:
                profile = UserProfile(user=user, company_name=f"Fast access {username}")
                profile.role = role
                profile._skip_default_facility = True
                profile.save()
            elif profile.role != role:
                profile.role = role
                profile.save(update_fields=["role"])
            profiles[email] = profile

        operation = profiles[DEMO_OPERATION_EMAIL]
        if not operation.dostupne_prevadzky().exists():
            prevadzka = Prevadzka.objects.filter(is_active=True).order_by("pk").first()
            if prevadzka is None:
                raise RuntimeError("Fast access needs an existing prevádzka.")
            ProfilePrevadzkaAccess.objects.get_or_create(
                profile=operation, prevadzka=prevadzka
            )

    def _ensure_demo_spravca(self) -> None:
        """Demo login pre rolu Admin (#483).

        Bez neho sa nedá vyskúšať okresanie práv: `admin@example.com` je
        superadmin, takže vidí všetko a rozdiel oproti adminovi nie je vidieť.
        """
        from api.models import UserProfile

        user, created = self._get_or_create_demo_user(
            email=DEMO_SPRAVCA_EMAIL,
            legacy_username="spravca",
            is_staff=True,
            is_superuser=False,
        )
        user.is_staff = True
        user.is_superuser = False
        user.set_password(DEMO_SPRAVCA_PASSWORD)
        user.save()

        profile = getattr(user, "profile", None)
        if profile is None:
            profile = UserProfile(user=user, company_name="Demo admin")
            profile.role = UserProfile.Role.ADMIN
            profile._skip_default_facility = True
            profile.save()
        elif profile.role != UserProfile.Role.ADMIN:
            profile.role = UserProfile.Role.ADMIN
            profile.save(update_fields=["role"])

        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Created admin user "{DEMO_SPRAVCA_EMAIL}"')
            )
        else:
            self.stdout.write(f'Admin user "{DEMO_SPRAVCA_EMAIL}" already exists')

    def _ensure_demo_kuchyna(self) -> None:
        """Demo login pre rolu Kuchyňa (#486).

        Kuchyňa nemá `is_staff` a nedostáva vlastný celok ani prevádzku —
        neobjednáva, len číta prehľad nakladania.
        """
        from api.models import UserProfile

        user, created = self._get_or_create_demo_user(
            email=DEMO_KUCHYNA_EMAIL,
            legacy_username="kuchyna",
            is_staff=False,
            is_superuser=False,
        )
        user.is_staff = False
        user.is_superuser = False
        user.set_password(DEMO_KUCHYNA_PASSWORD)
        user.save()

        profile = getattr(user, "profile", None)
        if profile is None:
            profile = UserProfile(user=user, company_name="Demo kuchyňa")
            profile.role = UserProfile.Role.KUCHYNA
            profile._skip_default_facility = True
            profile.save()
        elif profile.role != UserProfile.Role.KUCHYNA:
            profile.role = UserProfile.Role.KUCHYNA
            profile.save(update_fields=["role"])

        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Created kuchyňa user "{DEMO_KUCHYNA_EMAIL}"')
            )
        else:
            self.stdout.write(f'Kuchyňa user "{DEMO_KUCHYNA_EMAIL}" already exists')

    def _ensure_demo_prevadzky(self, celok) -> None:
        """Dorob demo celku ďalšie prevádzky (idempotentne).

        Nastavenia sa kopírujú z prvej prevádzky, aby sa dalo objednávať za
        každú z nich — inak by nové prevádzky nemali viditeľné menu ani jedlá
        a v objednávkovom formulári by boli prázdne.
        """
        primary = celok.prevadzky.order_by("sort_order", "pk").first()
        if primary is None:
            return

        for offset, nazov in enumerate(DEMO_EXTRA_PREVADZKY, start=1):
            prevadzka, created = Prevadzka.objects.get_or_create(
                celok=celok,
                nazov=nazov,
                defaults={
                    "sort_order": primary.sort_order + offset,
                    "visible_menus": list(primary.visible_menus or []),
                    "visible_meals": list(primary.visible_meals or []),
                },
            )
            if created:
                prevadzka.visible_diets.set(primary.visible_diets.all())
                self.stdout.write(
                    self.style.SUCCESS(f'  Demo prevádzka vytvorená: "{nazov}"')
                )
            else:
                self.stdout.write(f'  Demo prevádzka existuje: "{nazov}"')

    def _get_or_create_demo_user(
        self,
        *,
        email: str,
        legacy_username: str,
        is_staff: bool,
        is_superuser: bool,
    ) -> tuple[User, bool]:
        user = User.objects.filter(email__iexact=email).first()
        if user:
            return user, False

        legacy_user = User.objects.filter(username=legacy_username).first()
        if legacy_user:
            legacy_user.username = email
            legacy_user.email = email
            legacy_user.save(update_fields=["username", "email"])
            return legacy_user, False

        user = User.objects.create_user(
            username=email,
            email=email,
            is_staff=is_staff,
            is_superuser=is_superuser,
        )
        return user, True
