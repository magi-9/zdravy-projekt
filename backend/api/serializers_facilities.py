"""Serializery pre admin správu celkov a ich prevádzok.

Zoznam v admin konzole je po novom orientovaný na **celok** (fakturačná jednotka),
ktorý sa rozbalí na svoje **prevádzky**. Prevádzky žijú v jednej tabuľke (`Prevadzka`)
a majú plný CRUD; presun medzi celkami sa zámerne nepodporuje (celok je pri vytvorení
fixný). Model ostáva ako je — niektoré celky sú 1:1 s prevádzkou, iné (Jolly Homeschool,
Škôlka MS) majú viac prevádzok, a Zdravé Brúsko je päť samostatných celkov. UI len
zobrazuje realitu, nič nemigruje.
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from .models import (
    Celok,
    Diet,
    PasswordResetToken,
    PortionType,
    Prevadzka,
    PrevadzkaDiet,
)


class AdminPrevadzkaSerializer(serializers.ModelSerializer):
    """Zapisovateľná prevádzka pre admin CRUD.

    `celok` je povinné pri vytvorení a potom nemenné (presun medzi celkami sa
    nepodporuje) — validuje sa vo `validate_celok`/`update`.
    """

    celok_nazov = serializers.CharField(source="celok.nazov", read_only=True)
    celok_zdroj_objednavok = serializers.CharField(
        source="celok.zdroj_objednavok", read_only=True
    )
    edupage_connection_name = serializers.CharField(
        source="edupage_connection.name", read_only=True
    )
    orders_count = serializers.SerializerMethodField()
    client_user_id = serializers.SerializerMethodField()
    visible_diets = serializers.PrimaryKeyRelatedField(
        queryset=Diet.objects.all(), many=True, required=False
    )
    visible_portion_types = serializers.PrimaryKeyRelatedField(
        queryset=PortionType.objects.all(), many=True, required=False
    )
    # Priradené diéty s poznámkou per (prevádzka, diéta) — pozri PrevadzkaDiet.
    # Samostatné pole od `visible_diets` (to zostáva plochý zoznam id kvôli
    # spätnej kompatibilite so zápisom): toto je len na čítanie pre nový UI.
    diet_assignments = serializers.SerializerMethodField()
    # Zápis poznámok: {diet_id (ako string kľúč): poznámka}. Nastavuje sa
    # samostatne od `visible_diets`, aby PATCH mohol meniť len poznámku bez
    # dotknutia sa priradenia.
    diet_notes = serializers.DictField(
        child=serializers.CharField(allow_blank=True, max_length=255),
        required=False,
        write_only=True,
    )

    def get_diet_assignments(self, obj):
        assignments = getattr(obj, "_prefetched_diet_assignments", None)
        if assignments is None:
            assignments = obj.prevadzka_diets.select_related("diet").order_by(
                "diet__sort_order", "diet__name"
            )
        return [
            {
                "diet": assignment.diet_id,
                "name": assignment.diet.name,
                "color": assignment.diet.color,
                "note": assignment.note,
            }
            for assignment in assignments
        ]

    def _detail_profile(self, obj):
        scoped_accesses = getattr(obj, "_admin_profile_accesses", None)
        if scoped_accesses is None:
            scoped_accesses = getattr(obj, "_prefetched_objects_cache", {}).get(
                "profile_accesses"
            )
            if scoped_accesses is None:
                scoped_accesses = list(
                    obj.profile_accesses.select_related("profile__user")
                )
        if scoped_accesses:
            return scoped_accesses[0].profile

        celok_accesses = self.context.get("celok_accesses")
        if celok_accesses is None:
            celok = self.context.get("celok") or obj.celok
            celok_accesses = list(
                celok.profile_accesses.select_related("profile__user")
            )
        return celok_accesses[0].profile if celok_accesses else None

    def get_orders_count(self, obj):
        # Anotované vo viewsete; v inom kontexte (napr. po vytvorení) môže chýbať.
        return getattr(obj, "orders_count", None)

    def get_client_user_id(self, obj):
        profile = self._detail_profile(obj)
        return profile.user_id if profile else None

    class Meta:
        model = Prevadzka
        fields = [
            "id",
            "celok",
            "celok_nazov",
            "celok_zdroj_objednavok",
            "nazov",
            "adresa",
            "edupage_connection",
            "edupage_connection_name",
            "edupage_match",
            "report_alias",
            "delivery_note",
            "sort_order",
            "is_active",
            "billing_portion_coefficients",
            "visible_menus",
            "menu_day_restrictions",
            "visible_meals",
            "meal_day_restrictions",
            "visible_diets",
            "diet_assignments",
            "diet_notes",
            "visible_portion_types",
            "pack_separately_enabled",
            "adults_pack_separately_enabled",
            "olovrant_s_obedom",
            "admin_order_note",
            "orders_count",
            "client_user_id",
        ]

    def validate(self, attrs):
        # Unikátnosť názvu v rámci celku (DB constraint) — vrátime peknú chybu.
        celok = attrs.get("celok") or getattr(self.instance, "celok", None)
        nazov = attrs.get("nazov", getattr(self.instance, "nazov", None))
        if celok and nazov:
            qs = Prevadzka.objects.filter(celok=celok, nazov=nazov)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"nazov": "Prevádzka s týmto názvom už v celku existuje."}
                )
        return attrs

    def _apply_diet_notes(self, instance, diet_notes):
        for diet_id, note in diet_notes.items():
            try:
                diet_id_int = int(diet_id)
            except (TypeError, ValueError):
                continue
            PrevadzkaDiet.objects.filter(
                prevadzka=instance, diet_id=diet_id_int
            ).update(note=note)

    def create(self, validated_data):
        diet_notes = validated_data.pop("diet_notes", None)
        instance = super().create(validated_data)
        if diet_notes:
            self._apply_diet_notes(instance, diet_notes)
        return instance

    def update(self, instance, validated_data):
        # Celok je po vytvorení nemenný — prípadnú zmenu ticho ignorujeme.
        validated_data.pop("celok", None)
        diet_notes = validated_data.pop("diet_notes", None)
        instance = super().update(instance, validated_data)
        if diet_notes:
            self._apply_diet_notes(instance, diet_notes)
        return instance


class AdminCelokSerializer(serializers.ModelSerializer):
    """Celok s vnorenými prevádzkami pre rozbaliteľný zoznam."""

    prevadzky = serializers.SerializerMethodField()
    prevadzky_count = serializers.SerializerMethodField()
    logins = serializers.SerializerMethodField()

    class Meta:
        model = Celok
        fields = [
            "id",
            "nazov",
            "billing_name",
            "adresa",
            "ico",
            "dic",
            "zdroj_objednavok",
            "prevadzky_count",
            "prevadzky",
            "logins",
        ]

    @staticmethod
    def _prevadzky(obj):
        prefetched = getattr(obj, "_admin_prevadzky", None)
        if prefetched is not None:
            return prefetched
        return sorted(obj.prevadzky.all(), key=lambda p: (p.sort_order, p.nazov))

    @staticmethod
    def _celok_accesses(obj):
        prefetched = getattr(obj, "_admin_profile_accesses", None)
        return (
            prefetched if prefetched is not None else list(obj.profile_accesses.all())
        )

    def get_logins(self, obj):
        profiles_by_user_id = {}
        for access in self._celok_accesses(obj):
            profile = access.profile
            profiles_by_user_id[profile.user_id] = {
                "profile": profile,
                "whole_celok": True,
                "prevadzka_ids": set(),
            }
        for prevadzka in self._prevadzky(obj):
            accesses = getattr(prevadzka, "_admin_profile_accesses", None)
            if accesses is None:
                accesses = prevadzka.profile_accesses.all()
            for access in accesses:
                profile = access.profile
                current = profiles_by_user_id.setdefault(
                    profile.user_id,
                    {
                        "profile": profile,
                        "whole_celok": False,
                        "prevadzka_ids": set(),
                    },
                )
                if not current["whole_celok"]:
                    current["prevadzka_ids"].add(prevadzka.id)

        is_edupage = obj.zdroj_objednavok == Celok.ZdrojObjednavok.EDUPAGE
        password_statuses = (
            {}
            if is_edupage
            else self._password_statuses(
                [entry["profile"].user for entry in profiles_by_user_id.values()]
            )
        )
        return [
            {
                "user_id": entry["profile"].user_id,
                "email": entry["profile"].user.email,
                "company_name": entry["profile"].company_name,
                "is_edupage": is_edupage,
                "prevadzka_ids": sorted(entry["prevadzka_ids"]),
                "password_status": password_statuses.get(entry["profile"].user_id),
            }
            for entry in profiles_by_user_id.values()
        ]

    @staticmethod
    def _password_statuses(users) -> dict[int, str]:
        """Vráti `{user_id: "success" | "pending" | "failed"}` pre login riadky.

        `success` — heslo je nastavené (`has_usable_password`). Inak sa pozrie
        na posledný nepoužitý setup/reset token: platný → `pending`, vypršaný
        alebo žiadny → `failed` (link treba znova odoslať).

        Ak volajúci queryset dopredu naprefetchol `user.password_reset_tokens`
        (filtrované na `used=False`, zoradené `-created_at`) do atribútu
        `_active_reset_tokens`, použije sa bez ďalšieho dotazu — inak sa
        chýbajúce id-čka dotiahnu jedným bulk dotazom (fallback pre volajúcich
        bez prefetchu).
        """
        now = timezone.now()
        statuses: dict[int, str] = {}
        unprefetched_ids: list[int] = []
        for user in users:
            if user.has_usable_password():
                statuses[user.id] = "success"
                continue
            tokens = getattr(user, "_active_reset_tokens", None)
            if tokens is None:
                unprefetched_ids.append(user.id)
                continue
            token = tokens[0] if tokens else None
            statuses[user.id] = (
                "pending" if token and token.expires_at > now else "failed"
            )

        if unprefetched_ids:
            latest_tokens: dict[int, PasswordResetToken] = {}
            for token in PasswordResetToken.objects.filter(
                user_id__in=unprefetched_ids, used=False
            ).order_by("user_id", "-created_at"):
                latest_tokens.setdefault(token.user_id, token)
            for user_id in unprefetched_ids:
                token = latest_tokens.get(user_id)
                statuses[user_id] = (
                    "pending" if token and token.expires_at > now else "failed"
                )

        return statuses

    def get_prevadzky(self, obj):
        return AdminPrevadzkaSerializer(
            self._prevadzky(obj),
            many=True,
            context={
                **self.context,
                "celok": obj,
                "celok_accesses": self._celok_accesses(obj),
            },
        ).data

    def get_prevadzky_count(self, obj):
        # Počítame len aktívne — deaktivované (napr. retirovaný default po splite)
        # sa v zozname ukážu, ale do počtu „(N prevádzok)" nepatria.
        return sum(1 for p in self._prevadzky(obj) if p.is_active)
