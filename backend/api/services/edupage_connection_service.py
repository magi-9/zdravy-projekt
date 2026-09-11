"""Canonical EduPage connection lookup."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import Prefetch

from api.models import EdupageConnection, Prevadzka

SYSTEM_SCRAPE_EMAIL = "edupage-scrape@system.local"


def system_scrape_user() -> User:
    user, _ = User.objects.get_or_create(
        username=SYSTEM_SCRAPE_EMAIL,
        defaults={
            "email": SYSTEM_SCRAPE_EMAIL,
            "is_active": False,
            "is_staff": False,
        },
    )
    return user


def _operation_user(prevadzky: list[Prevadzka]) -> User:
    for prevadzka in prevadzky:
        access = prevadzka.profile_accesses.order_by("pk").first()
        if access is not None:
            return access.profile.user
    for prevadzka in prevadzky:
        access = prevadzka.celok.profile_accesses.order_by("pk").first()
        if access is not None:
            return access.profile.user
    return system_scrape_user()


def edupage_operations(
    connection_id: int | str | None = None,
) -> list[dict]:
    prevadzky = (
        Prevadzka.objects.filter(is_active=True)
        .select_related("celok")
        .prefetch_related(
            "visible_diets",
            "profile_accesses__profile__user",
            "celok__profile_accesses__profile__user",
        )
        .order_by("celok_id", "sort_order", "nazov")
    )
    connections = EdupageConnection.objects.filter(is_active=True).prefetch_related(
        Prefetch("prevadzky", queryset=prevadzky)
    )
    if connection_id is not None:
        connections = connections.filter(pk=connection_id)

    result = []
    for connection in connections:
        connection_prevadzky = list(connection.prevadzky.all())
        result.append(
            {
                "connection_id": connection.pk,
                "name": connection.name,
                "url": connection.mealsguest_url,
                "user": _operation_user(connection_prevadzky),
                "prevadzky": connection_prevadzky,
                "connection": connection,
            }
        )
    return result
