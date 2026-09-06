"""Helpers for applying default order visibility consistently."""

from __future__ import annotations

from django.db.models import QuerySet

from .models import Diet, PortionType, Prevadzka
from .order_data import MEAL_KEYS
from .reference_data import DEFAULT_DIET_NAMES

DEFAULT_VISIBLE_MEALS = list(MEAL_KEYS)
DEFAULT_VISIBLE_MENUS = ["A", "B", "C", "V"]


def default_visible_diets() -> list[Diet]:
    return list(Diet.objects.filter(name__in=DEFAULT_DIET_NAMES, is_active=True))


def ensure_default_visible_diets(relation) -> bool:
    """Set default diets on an empty M2M relation.

    Empty diet visibility has historically meant "not configured yet" in this app,
    so deploy/startup bootstrap fills it with the standard set.
    """
    if relation.exists():
        return False
    diets = default_visible_diets()
    if not diets:
        return False
    relation.set(diets)
    return True


def default_visible_portion_types() -> list[PortionType]:
    return list(PortionType.objects.filter(is_active=True))


def ensure_default_visible_portion_types(relation) -> bool:
    """Set all active portion types on an empty M2M relation."""
    if relation.exists():
        return False
    portion_types = default_visible_portion_types()
    if not portion_types:
        return False
    relation.set(portion_types)
    return True


def ensure_default_visible_diets_for_empty_prevadzky(
    prevadzky: QuerySet[Prevadzka] | None = None,
) -> int:
    qs = Prevadzka.objects.all() if prevadzky is None else prevadzky
    updated_count = 0
    for prevadzka in qs.filter(visible_diets__isnull=True).distinct():
        if ensure_default_visible_diets(prevadzka.visible_diets):
            updated_count += 1
    return updated_count


def ensure_default_visible_portion_types_for_empty_prevadzky(
    prevadzky: QuerySet[Prevadzka] | None = None,
) -> int:
    qs = Prevadzka.objects.all() if prevadzky is None else prevadzky
    updated_count = 0
    for prevadzka in qs.filter(visible_portion_types__isnull=True).distinct():
        if ensure_default_visible_portion_types(prevadzka.visible_portion_types):
            updated_count += 1
    return updated_count
