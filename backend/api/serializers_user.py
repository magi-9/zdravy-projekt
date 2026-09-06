from typing import Any, Dict, List, Optional

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from rest_framework import serializers

from .models import (
    Celok,
    Diet,
    PortionType,
    Prevadzka,
    ProfileCelokAccess,
    ProfilePrevadzkaAccess,
    UserProfile,
)
from .roles import role_for_flags


class DietSerializer(serializers.ModelSerializer):
    """Read/write serializer for the Diet catalogue model."""

    base_diets = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Diet.objects.all(),
        required=False,
    )
    base_colors = serializers.SerializerMethodField()

    def get_base_colors(self, obj: Diet) -> List[str]:
        return [diet.color or "#FDE68A" for diet in obj.base_diets.all()]

    def validate_base_diets(self, value: List[Diet]) -> List[Diet]:
        if self.instance and any(diet.pk == self.instance.pk for diet in value):
            raise serializers.ValidationError("A diet cannot include itself.")
        if Diet.objects.filter(
            pk__in=[diet.pk for diet in value], base_diets__isnull=False
        ).exists():
            raise serializers.ValidationError(
                "Zložená diéta nemôže byť základnou diétou inej zloženej diéty."
            )
        if value and self.instance and self.instance.composite_of.exists():
            raise serializers.ValidationError(
                "Zložená diéta nemôže byť základnou diétou inej zloženej diéty."
            )
        return value

    class Meta:
        model = Diet
        fields = [
            "id",
            "name",
            "sort_order",
            "is_active",
            "description",
            "color",
            "text_color",
            "background_color",
            "base_diets",
            "base_colors",
        ]


class PortionTypeSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortionType
        fields = ["id", "name", "sort_order", "is_active"]


#: Slovenské znenie hlášok z `AUTH_PASSWORD_VALIDATORS`. Django ich prekladá cez
#: `LANGUAGE_CODE`, ktorý je `en-us` (a meniť ho kvôli hláškam by prepísalo aj
#: formáty dátumov a čísel v celej appke), takže si ich mapujeme sami podľa kódu
#: chyby. Škôlky pri onboardingu videli anglické vety a nevedeli, čo majú opraviť.
#:
#: `password_too_similar` je najčastejší prípad: prihlasovacie meno je e-mail, tak
#: heslo odvodené od názvu škôlky validátor odmietne — hláška to musí povedať.
PASSWORD_ERROR_MESSAGES = {
    "password_too_similar": (
        "Heslo je príliš podobné vašej e-mailovej adrese. "
        "Zvoľte heslo, ktoré neobsahuje časti adresy."
    ),
    "password_too_short": "Heslo musí mať aspoň 8 znakov.",
    "password_too_common": "Toto heslo je príliš bežné. Zvoľte menej obvyklé.",
    "password_entirely_numeric": "Heslo nemôže byť zložené iba z číslic.",
}


def validate_password_strength(password: str, user: User | None = None) -> str:
    """Validate passwords with Django's configured AUTH_PASSWORD_VALIDATORS."""
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        # Neznámy kód necháme v pôvodnom znení — lepšie anglická veta než žiadna.
        spravy = [
            PASSWORD_ERROR_MESSAGES.get(chyba.code, message)
            for chyba, message in zip(exc.error_list, exc.messages)
        ]
        raise serializers.ValidationError(spravy) from exc
    return password


class UserProfileDetailSerializer(serializers.ModelSerializer):
    """Serializer for UserProfile details."""

    billing_name = serializers.SerializerMethodField()
    ico = serializers.SerializerMethodField()
    dic = serializers.SerializerMethodField()
    is_edupage = serializers.SerializerMethodField()
    api_identifier = serializers.SerializerMethodField()
    mealsguest_url = serializers.SerializerMethodField()

    def _connection(self, obj):
        prevadzka = (
            obj.dostupne_prevadzky()
            .select_related("edupage_connection")
            .filter(edupage_connection__isnull=False)
            .first()
        )
        return prevadzka.edupage_connection if prevadzka else None

    def _celok_value(self, obj, field):
        summary = self.context.get("access_summary")
        if summary is not None:
            return summary.get(field, "")
        celok = obj.primary_celok()
        return getattr(celok, field, "") if celok else ""

    def get_billing_name(self, obj):
        return self._celok_value(obj, "billing_name")

    def get_ico(self, obj):
        return self._celok_value(obj, "ico")

    def get_dic(self, obj):
        return self._celok_value(obj, "dic")

    def get_is_edupage(self, obj):
        summary = self.context.get("access_summary")
        if summary is not None:
            return summary["is_edupage"]
        return obj.is_edupage_only()

    def get_api_identifier(self, obj):
        summary = self.context.get("access_summary")
        if summary is not None:
            return summary["api_identifier"]
        connection = self._connection(obj)
        return connection.api_identifier if connection else ""

    def get_mealsguest_url(self, obj):
        summary = self.context.get("access_summary")
        if summary is not None:
            return summary["mealsguest_url"]
        connection = self._connection(obj)
        return connection.mealsguest_url if connection else ""

    class Meta:
        model = UserProfile
        fields = [
            "company_name",
            "billing_name",
            "ico",
            "dic",
            "is_edupage",
            "api_identifier",
            "mealsguest_url",
            "created_at",
            "onboarding_completed",
        ]
        read_only_fields = ["created_at"]


class ClientUserProfileDetailSerializer(serializers.ModelSerializer):
    """Profile details visible to the operation itself."""

    billing_name = serializers.SerializerMethodField()
    ico = serializers.SerializerMethodField()
    dic = serializers.SerializerMethodField()
    is_edupage = serializers.SerializerMethodField()
    api_identifier = serializers.SerializerMethodField()

    def _celok_value(self, obj, field):
        celok = obj.primary_celok()
        return getattr(celok, field, "") if celok else ""

    def get_billing_name(self, obj):
        return self._celok_value(obj, "billing_name")

    def get_ico(self, obj):
        return self._celok_value(obj, "ico")

    def get_dic(self, obj):
        return self._celok_value(obj, "dic")

    def get_is_edupage(self, obj):
        return obj.is_edupage_only()

    def get_api_identifier(self, obj):
        prevadzka = (
            obj.dostupne_prevadzky()
            .select_related("edupage_connection")
            .filter(edupage_connection__isnull=False)
            .first()
        )
        if prevadzka and prevadzka.edupage_connection:
            return prevadzka.edupage_connection.api_identifier
        return ""

    class Meta:
        model = UserProfile
        fields = [
            "billing_name",
            "ico",
            "dic",
            "is_edupage",
            "api_identifier",
            "created_at",
            "onboarding_completed",
        ]
        read_only_fields = ["created_at"]


class PrevadzkaSettingsSerializer(serializers.ModelSerializer):
    """Kompatibilný settings payload čítaný z kanonickej Prevádzky."""

    visible_diets = DietSerializer(many=True, read_only=True)
    visible_portion_types = PortionTypeSettingsSerializer(many=True, read_only=True)

    class Meta:
        model = Prevadzka
        fields = [
            "visible_menus",
            "menu_day_restrictions",
            "visible_meals",
            "visible_diets",
            "visible_portion_types",
            "admin_order_note",
        ]


class UserProfileSerializer(serializers.ModelSerializer):
    groups = serializers.SerializerMethodField()
    email = serializers.EmailField(required=True)
    settings = serializers.SerializerMethodField()
    profile = serializers.SerializerMethodField()
    billing_name = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    ico = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    dic = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    onboarding_completed = serializers.BooleanField(
        source="profile.onboarding_completed", required=False
    )
    role = serializers.SerializerMethodField()
    sections = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "billing_name",
            "ico",
            "dic",
            "onboarding_completed",
            "date_joined",
            "groups",
            "settings",
            "profile",
            "is_staff",
            "role",
            "sections",
        ]
        read_only_fields = ["id", "date_joined", "is_staff", "role", "sections"]

    def get_role(self, obj: User) -> str:
        """Rola cez `role_of` — login bez profilu ju odvodí zo starých príznakov."""
        from .roles import role_of

        return role_of(obj)

    def get_sections(self, obj: User) -> Dict[str, str]:
        """Efektívne úrovne prístupu k sekciám (#484).

        Frontend z toho gejtuje menu aj režim „len na čítanie". Je to len
        zrkadlo — skutočná zábrana je `SectionAccess` na endpointoch.
        """
        from .access import effective_map

        return effective_map(obj)

    def validate_email(self, value: str) -> str:
        """Enforce unique email for profile updates."""
        normalized_email = value.lower()
        if (
            User.objects.filter(email__iexact=normalized_email)
            .exclude(pk=self.instance.pk if self.instance else None)
            .exists()
        ):
            raise serializers.ValidationError("Používateľ s týmto emailom už existuje.")
        return normalized_email

    @transaction.atomic
    def update(self, instance: User, validated_data: Dict[str, Any]) -> User:
        profile_data = validated_data.pop("profile", None)
        billing_data = {
            field: validated_data.pop(field)
            for field in ("billing_name", "ico", "dic")
            if field in validated_data
        }
        billing_celok = None
        if billing_data:
            profile, _ = UserProfile.objects.get_or_create(user=instance)
            billing_celok = profile.primary_celok()
            if billing_celok is None:
                raise serializers.ValidationError(
                    {
                        "billing_name": (
                            "Fakturačné údaje sa dajú upraviť iba pre login "
                            "s práve jedným dostupným celkom."
                        )
                    }
                )

        # Keep internal username in sync with email
        if "email" in validated_data:
            new_email = validated_data["email"].lower()
            validated_data["email"] = new_email
            if (
                User.objects.filter(username__iexact=new_email)
                .exclude(pk=instance.pk)
                .exists()
                or User.objects.filter(email__iexact=new_email)
                .exclude(pk=instance.pk)
                .exists()
            ):
                raise serializers.ValidationError(
                    {"email": "Používateľ s týmto emailom už existuje."}
                )
            validated_data["username"] = new_email

        user = super().update(instance, validated_data)

        if profile_data is not None:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if "onboarding_completed" in profile_data:
                profile.onboarding_completed = profile_data["onboarding_completed"]
                profile.save(update_fields=["onboarding_completed"])

        if billing_data:
            assert billing_celok is not None
            for field, value in billing_data.items():
                setattr(billing_celok, field, value or "")
            billing_celok.save(update_fields=list(billing_data))

        return user

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if hasattr(instance, "profile"):
            celok = instance.profile.primary_celok()
            data["billing_name"] = celok.billing_name if celok else ""
            data["ico"] = celok.ico if celok else ""
            data["dic"] = celok.dic if celok else ""
        return data

    def get_groups(self, obj: User) -> List[str]:
        return [group.name for group in obj.groups.all()]

    def get_profile(self, obj: User) -> Optional[Dict[str, Any]]:
        """Return profile details if exists."""
        if hasattr(obj, "profile"):
            return ClientUserProfileDetailSerializer(obj.profile).data
        return None

    def get_settings(self, obj: User) -> Dict[str, Any]:
        """Return compatibility settings only for an unambiguous Prevádzka."""
        if not hasattr(obj, "profile"):
            return {}
        prevadzky = list(
            obj.profile.dostupne_prevadzky().prefetch_related(
                "visible_diets", "visible_portion_types"
            )[:2]
        )
        return (
            PrevadzkaSettingsSerializer(prevadzky[0]).data
            if len(prevadzky) == 1
            else {}
        )


class AdminPrevadzkaSettingsSerializer(serializers.ModelSerializer):
    """Compatibility serializer backed by Prevádzka, not by the login."""

    visible_diets = serializers.PrimaryKeyRelatedField(
        queryset=Diet.objects.all(), many=True, required=False
    )

    class Meta:
        model = Prevadzka
        fields = [
            "visible_menus",
            "menu_day_restrictions",
            "visible_meals",
            "visible_diets",
            "admin_order_note",
        ]


class AdminUserSerializer(serializers.ModelSerializer):
    """Admin správa loginu; prevádzkové nastavenia sú iba compatibility payload."""

    settings = serializers.SerializerMethodField()
    profile = serializers.SerializerMethodField()
    email = serializers.EmailField(required=True)
    company_name = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
    )
    # Voliteľné napojenie nového loginu: na existujúci celok, prípadne obmedzené len
    # na vybrané prevádzky (login „na prevádzku"). Bez `celok` sa správa ako doteraz —
    # signál profilu vytvorí vlastný celok podľa company_name.
    celok = serializers.PrimaryKeyRelatedField(
        queryset=Celok.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
    )
    prevadzky = serializers.PrimaryKeyRelatedField(
        queryset=Prevadzka.objects.all(),
        many=True,
        required=False,
        write_only=True,
    )

    role = serializers.ChoiceField(
        choices=UserProfile.Role.choices,
        required=False,
        help_text=(
            "Rola loginu (#482). Ak sa neuvedie, odvodí sa z `is_staff` — "
            "tým ostáva správanie existujúcich klientov nezmenené."
        ),
    )

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "settings",
            "profile",
            "company_name",
            "celok",
            "prevadzky",
            "role",
        ]

    def to_representation(self, instance: User) -> Dict[str, Any]:
        """`role` žije na `profile`, nie na `User` — bez `source` ho DRF na výstupe
        potichu vynechá (`required=False` → `SkipField`), lebo `User.role`
        neexistuje. Zoznam správcov (`AdminUserList.tsx`) tak nedostal `role` vôbec
        a padal na `is_staff` fallback, ktorý superadmina aj kuchyňu ukazoval ako
        obyčajného admina."""
        data = super().to_representation(instance)
        if hasattr(instance, "profile"):
            data["role"] = instance.profile.role
        return data

    def validate_email(self, value: str) -> str:
        """Enforce unique email for admin create/update."""
        normalized_email = value.lower()
        if (
            User.objects.filter(email__iexact=normalized_email)
            .exclude(pk=self.instance.pk if self.instance else None)
            .exists()
        ):
            raise serializers.ValidationError("Používateľ s týmto emailom už existuje.")
        return normalized_email

    def validate(self, attrs):
        celok = attrs.get("celok")
        prevadzky = attrs.get("prevadzky")
        if celok is not None and prevadzky:
            if any(prevadzka.celok_id != celok.id for prevadzka in prevadzky):
                raise serializers.ValidationError(
                    {"prevadzky": "Prevádzky musia patriť zadanému celku."}
                )
        return attrs

    @transaction.atomic
    def create(self, validated_data: Dict[str, Any]) -> User:
        company_name = validated_data.pop("company_name", "") or ""
        celok = validated_data.pop("celok", None)
        prevadzky = validated_data.pop("prevadzky", None)
        role = validated_data.pop("role", None)
        # Normalize email and keep username in sync to satisfy uniqueness constraints.
        normalized_email = validated_data["email"].lower()
        # Check both email and username to prevent IntegrityError on save
        if User.objects.filter(
            Q(email__iexact=normalized_email) | Q(username__iexact=normalized_email)
        ).exists():
            raise serializers.ValidationError(
                {"email": "Používateľ s týmto emailom už existuje."}
            )
        validated_data["email"] = normalized_email
        validated_data["username"] = normalized_email
        user = User(**validated_data)
        user.set_unusable_password()
        user.save()

        # Ak je zadaný celok, nastavíme ho hneď pri vytvorení — tým sa vypne
        # auto-vytvorenie vlastného celku v `on_user_profile_saved` signáli.
        profile = UserProfile(user=user, company_name=company_name)
        # Bez explicitnej role sa odvodí zo `is_staff`, aby vytváranie klientov
        # aj adminov cez existujúce volania fungovalo presne ako doteraz.
        profile.role = role or role_for_flags(
            is_staff=user.is_staff, is_superuser=user.is_superuser
        )
        # Vlastný celok/prevádzka dávajú zmysel len zákazníckemu loginu. Kuchyňa
        # ani admin ich dostať nesmú — inak by im systém generoval objednávky.
        profile._skip_default_facility = (
            celok is not None
            or bool(prevadzky)
            or profile.role != UserProfile.Role.KLIENT
        )
        profile.save()
        # Login „na prevádzku": obmedz rozsah na vybrané prevádzky (M2M). Prázdne =
        # celý celok. Validujeme, že prevádzky patria zadanému celku.
        if prevadzky:
            ProfilePrevadzkaAccess.objects.bulk_create(
                [
                    ProfilePrevadzkaAccess(profile=profile, prevadzka=prevadzka)
                    for prevadzka in prevadzky
                ]
            )
        elif celok is not None:
            ProfileCelokAccess.objects.create(profile=profile, celok=celok)
        return user

    def get_profile(self, obj: User) -> Optional[Dict[str, Any]]:
        """Return profile details if exists."""
        if hasattr(obj, "profile"):
            view = self.context.get("view")
            access_summary = None
            if getattr(view, "action", None) == "list":
                has_one_celok = (
                    getattr(obj, "_first_celok_id", None) is not None
                    and getattr(obj, "_second_celok_id", None) is None
                )
                access_summary = {
                    "billing_name": (
                        getattr(obj, "_billing_name", "") or "" if has_one_celok else ""
                    ),
                    "ico": getattr(obj, "_ico", "") or "" if has_one_celok else "",
                    "dic": getattr(obj, "_dic", "") or "" if has_one_celok else "",
                    "is_edupage": bool(
                        getattr(obj, "_has_access", False)
                        and not getattr(obj, "_has_app_access", False)
                    ),
                    "api_identifier": (getattr(obj, "_api_identifier", "") or ""),
                    "mealsguest_url": (getattr(obj, "_mealsguest_url", "") or ""),
                }
            return UserProfileDetailSerializer(
                obj.profile,
                context={
                    **self.context,
                    "access_summary": access_summary,
                },
            ).data
        return None

    def get_settings(self, obj: User) -> Optional[Dict[str, Any]]:
        """Return settings only on detail; facility CRUD is their write owner."""
        view = self.context.get("view")
        if getattr(view, "action", None) == "list" or not hasattr(obj, "profile"):
            return None
        prevadzky = list(
            obj.profile.dostupne_prevadzky().prefetch_related(
                "visible_diets", "visible_portion_types"
            )[:2]
        )
        if len(prevadzky) != 1:
            return None
        return AdminPrevadzkaSettingsSerializer(prevadzky[0]).data

    @transaction.atomic
    def update(self, instance: User, validated_data: Dict[str, Any]) -> User:
        """
        Update user fields and optionally update one accessible Prevádzka.

        Settings data is read from ``self.initial_data`` because the
        ``settings`` field is a read-only ``SerializerMethodField``.  It is
        validated explicitly with ``AdminPrevadzkaSettingsSerializer`` before
        being applied.
        """
        settings_data = self.initial_data.get("settings", None)
        company_name = validated_data.pop("company_name", serializers.empty)
        celok = validated_data.pop("celok", serializers.empty)
        prevadzky = validated_data.pop("prevadzky", serializers.empty)
        role = validated_data.pop("role", None)
        settings_serializer = None
        if settings_data is not None:
            if not hasattr(instance, "profile"):
                raise serializers.ValidationError(
                    {"settings": "Login nemá profil ani dostupnú prevádzku."}
                )
            settings_target_prevadzky = list(instance.profile.dostupne_prevadzky()[:2])
            if len(settings_target_prevadzky) != 1:
                raise serializers.ValidationError(
                    {
                        "settings": (
                            "Nastavenia upravte na konkrétnej prevádzke; "
                            "login nemá práve jednu dostupnú prevádzku."
                        )
                    }
                )
            settings_serializer = AdminPrevadzkaSettingsSerializer(
                settings_target_prevadzky[0],
                data=settings_data,
                partial=True,
            )
            settings_serializer.is_valid(raise_exception=True)

        # Keep internal username in sync with email, ensuring uniqueness
        if "email" in validated_data:
            new_email = validated_data["email"].lower()
            validated_data["email"] = new_email
            if (
                User.objects.filter(username__iexact=new_email)
                .exclude(pk=instance.pk)
                .exists()
                or User.objects.filter(email__iexact=new_email)
                .exclude(pk=instance.pk)
                .exists()
            ):
                raise serializers.ValidationError(
                    {"email": "Používateľ s týmto emailom už existuje."}
                )
            validated_data["username"] = new_email

        instance = super().update(instance, validated_data)

        profile_needs_update = (
            company_name is not serializers.empty
            or celok is not serializers.empty
            or prevadzky is not serializers.empty
        )
        if profile_needs_update:
            try:
                profile = instance.profile
            except UserProfile.DoesNotExist:
                profile = UserProfile(user=instance)
                profile._skip_default_facility = True
                profile.save()
            if company_name is not serializers.empty:
                profile.company_name = company_name or ""
                profile.save(update_fields=["company_name"])

            if celok is not serializers.empty or prevadzky is not serializers.empty:
                ProfileCelokAccess.objects.filter(profile=profile).delete()
                ProfilePrevadzkaAccess.objects.filter(profile=profile).delete()

                selected_prevadzky = [] if prevadzky is serializers.empty else prevadzky
                if selected_prevadzky:
                    ProfilePrevadzkaAccess.objects.bulk_create(
                        [
                            ProfilePrevadzkaAccess(
                                profile=profile,
                                prevadzka=prevadzka,
                            )
                            for prevadzka in selected_prevadzky
                        ]
                    )
                elif celok is not serializers.empty and celok is not None:
                    ProfileCelokAccess.objects.create(profile=profile, celok=celok)

        if settings_serializer is not None:
            settings_serializer.save()

        # `role` musí ostať v súlade s `is_staff` — inak by prepnutie príznaku
        # v admin UI nechalo profilu starú rolu a `role_of` by po #483 vrátila
        # nesprávnu odpoveď. Profil tu už nemusí existovať (legacy loginy).
        profile = getattr(instance, "profile", None)
        if profile is not None:
            new_role = role or role_for_flags(
                is_staff=instance.is_staff, is_superuser=instance.is_superuser
            )
            if profile.role != new_role:
                profile.role = new_role
                profile.save(update_fields=["role"])

        return instance
