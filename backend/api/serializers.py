import datetime
import json
import logging
import time
from typing import Any, Dict

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from .cached_settings_service import get_global_settings
from .exceptions import (
    ClosedDayOrderModificationError,
    HolidayOrderNotAllowedError,
    OrderDeadlinePassedError,
    PrevadzkaClosureOrderNotAllowedError,
)
from .models import (
    ClosedDay,
    DailyOrder,
    Diet,
    Holiday,
    PortionType,
    Prevadzka,
    PrevadzkaClosure,
)
from .order_data import OrderData, safe_count
from .roles import is_admin_or_above
from .scheduling import is_prevadzka_closed
from .services.prevadzka_service import (
    PrevadzkaNedostupna,
    PrevadzkaNejednoznacna,
    vyber_prevadzku,
)

logger = logging.getLogger(__name__)


class DailyOrderSerializer(serializers.ModelSerializer):
    """
    Serializer for the DailyOrder model.

    Handles create/update with idempotent upsert semantics:
    - Submitting a ``draft`` status deletes any existing order for that date.
    - Any other status performs an atomic upsert (update or create) guarded
      against concurrent writes using ``SELECT FOR UPDATE``.
    """

    status = serializers.ChoiceField(
        choices=("draft", "submitted"), required=False, default="submitted"
    )
    prevadzka = serializers.PrimaryKeyRelatedField(
        queryset=Prevadzka.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = DailyOrder
        fields = [
            "id",
            "date",
            "status",
            "data",
            "is_auto",
            "updated_at",
            "prevadzka",
            "touched_meals",
        ]
        read_only_fields = ["id", "is_auto", "updated_at"]
        # DRF by z UniqueConstraint(prevadzka, date) odvodil UniqueTogetherValidator,
        # ktorý spraví `prevadzka` povinným poľom — lenže pri jedno-prevádzkovom
        # celku ho klient neposiela a dopĺňame ho my. Unikátnosť aj tak vynucuje
        # DB constraint + IntegrityError retry v `create()`.
        validators: list = []

    MEAL_FIELD_CONFIG = {
        "breakfast": ("deadline_breakfast", "deadline_breakfast_is_day_before"),
        "lunch": ("deadline_lunch", "deadline_lunch_is_day_before"),
        "olovrant": ("deadline_olovrant", "deadline_olovrant_is_day_before"),
    }

    MEAL_LABELS = {
        "breakfast": "raňajky",
        "lunch": "obed",
        "olovrant": "olovrant",
    }

    _ALLOWED_MEAL_KEYS = frozenset({"breakfast", "lunch", "olovrant"})

    # Ktoré jedlá klient/admin V TOMTO ZÁPISE skutočne odklikol/rozhodol —
    # aj keď výsledok je nula (viď `DailyOrder.touched_meals`). Nepovinné a
    # nezávislé od `data`, lebo `_ALLOWED_DATA_KEYS`/`validate_data` validuje
    # len tvar objednávky, nie audit toho, čo bolo "riešené". `create()`/
    # `update()` toto pole zlučujú (union) s tým, čo už na riadku bolo —
    # nikdy sa neuberá, len pridáva (Jarabinka 11.9.2026).
    touched_meals = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(_ALLOWED_MEAL_KEYS)),
        required=False,
        default=list,
    )
    # Poznámka k špeciálnej diéte sedí v `data` vedľa jedál (tak ju posiela klient
    # aj admin editor a tak ju číta admin UI), takže musí prejsť allowlistom —
    # nie je to jedlo, preto sa validuje zvlášť a preskakuje traverzáciu kategórií.
    # Musí sedieť s `SPECIAL_DIET_NAME` vo frontende (`config/constants.ts`) —
    # obe strany porovnávajú rovnaký reťazec z `diets` mapy, diéty žijú v DB,
    # nie ako zdieľaný enum.
    _SPECIAL_DIET_NAME = "Špeciálna"
    _SPECIAL_DIET_NOTE_KEY = "special_diet_note"
    # Príznak "Celodenná objednávka" sedí v `data` vedľa jedál z rovnakého
    # dôvodu ako `special_diet_note` vyššie — predtým žil len vo frontend
    # localStorage, takže sa medzi zariadeniami/prehliadačmi potichu strácal
    # (klient si na jednom zariadení myslel, že objednáva "na celý deň naraz",
    # na inom appka editovala jedlá nezávisle a časť dňa sa tak nechtiac
    # nezmenila — Veselý Úľ, 4.9.2026). Server ho teraz vracia ako
    # autoritatívny pri ďalšom načítaní, rovnako ako počty jedál.
    _FULL_DAY_ORDER_KEY = "full_day_order"
    _ALLOWED_DATA_KEYS = _ALLOWED_MEAL_KEYS | {
        _SPECIAL_DIET_NOTE_KEY,
        _FULL_DAY_ORDER_KEY,
    }
    _MAX_NOTE_CHARS = 1000
    _MAX_DATA_BYTES = 10 * 1024  # 10 KB
    _MAX_COUNT = 9999

    @staticmethod
    def _enforce_day_open(target_date: datetime.date) -> None:
        if ClosedDay.objects.filter(date=target_date).exists():
            raise ClosedDayOrderModificationError()

    @staticmethod
    def _sync_auto_order_pause(
        prevadzka: Prevadzka | None, data: Dict[str, Any]
    ) -> None:
        """Vynulovanie/zmazanie objednávky trvalo zastaví preklápanie dopredu.

        `apply_auto_orders` kopíruje poslednú NEPRÁZDNU objednávku ako šablónu
        na ďalší deň — bez tohto by teda zámerne vynulovaný deň iba preskočila
        a preklopila by staršiu šablónu spred neho. Nastavením
        `auto_order_paused` sa preklápanie pre danú prevádzku úplne zastaví,
        kým klient znova nepošle reálnu (neprázdnu) objednávku, ktorá príznak
        vráti na False.
        """
        if prevadzka is None:
            return
        is_empty = OrderData(data).is_empty()
        if prevadzka.auto_order_paused != is_empty:
            prevadzka.auto_order_paused = is_empty
            prevadzka.save(update_fields=["auto_order_paused"])

    def validate_data(self, data: Any) -> Dict[str, Any]:
        """Enforce meal keys, count bounds, and size limits for supported shapes."""
        if not isinstance(data, dict):
            raise serializers.ValidationError("Order data must be an object.")

        unknown_keys = set(data) - self._ALLOWED_DATA_KEYS
        if unknown_keys:
            allowed = ", ".join(sorted(self._ALLOWED_DATA_KEYS))
            raise serializers.ValidationError(
                f"Unknown meal keys: {sorted(unknown_keys)}. Allowed keys are: {allowed}."
            )

        if self._SPECIAL_DIET_NOTE_KEY in data:
            self._validate_special_diet_note(data[self._SPECIAL_DIET_NOTE_KEY])

        if self._FULL_DAY_ORDER_KEY in data:
            self._validate_full_day_order(data[self._FULL_DAY_ORDER_KEY])

        # Frontend (OrderPage aj AdminOrderEditorModal) blokuje odoslanie bez
        # poznámky, keď je objednaná diéta "Špeciálna" — jej názov kuchyni nič
        # nehovorí, kuchyňa potrebuje vedieť čo dieťaťu naložiť (viď gramážová
        # tabuľka). Vynucujeme to aj tu, nech to nejde obísť priamym API volaním.
        if self._order_has_special_diet(data):
            note = str(data.get(self._SPECIAL_DIET_NOTE_KEY) or "").strip()
            if not note:
                raise serializers.ValidationError(
                    f"Pri diéte '{self._SPECIAL_DIET_NAME}' je potrebné vyplniť "
                    f"'{self._SPECIAL_DIET_NOTE_KEY}'."
                )

        raw_size = len(
            json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        )
        if raw_size > self._MAX_DATA_BYTES:
            raise serializers.ValidationError(
                f"Order data exceeds the {self._MAX_DATA_BYTES // 1024} KB size limit."
            )

        for meal_key, meal in data.items():
            if meal_key in (self._SPECIAL_DIET_NOTE_KEY, self._FULL_DAY_ORDER_KEY):
                continue
            if not isinstance(meal, dict):
                raise serializers.ValidationError(f"'{meal_key}' must be an object.")
            if self._is_leaf_payload(meal):
                self._validate_leaf(meal, meal_key)
                continue
            for cat_name, cat_data in meal.items():
                if not isinstance(cat_data, dict):
                    raise serializers.ValidationError(
                        f"'{meal_key}.{cat_name}' must be an object."
                    )
                if self._is_leaf_payload(cat_data):
                    self._validate_leaf(cat_data, f"{meal_key}.{cat_name}")
                    continue
                for sub_name, sub_data in cat_data.items():
                    if not isinstance(sub_data, dict):
                        raise serializers.ValidationError(
                            f"'{meal_key}.{cat_name}.{sub_name}' must be an object."
                        )
                    if self._is_leaf_payload(sub_data):
                        self._validate_leaf(
                            sub_data, f"{meal_key}.{cat_name}.{sub_name}"
                        )

        return data

    @classmethod
    def _validate_special_diet_note(cls, note: Any) -> None:
        if note is None:
            return
        if not isinstance(note, str):
            raise serializers.ValidationError(
                f"'{cls._SPECIAL_DIET_NOTE_KEY}' musí byť text."
            )
        if len(note) > cls._MAX_NOTE_CHARS:
            raise serializers.ValidationError(
                f"'{cls._SPECIAL_DIET_NOTE_KEY}' môže mať najviac "
                f"{cls._MAX_NOTE_CHARS} znakov."
            )

    @classmethod
    def _validate_full_day_order(cls, value: Any) -> None:
        if value is None:
            return
        if not isinstance(value, bool):
            raise serializers.ValidationError(
                f"'{cls._FULL_DAY_ORDER_KEY}' musí byť true/false."
            )

    # Dva vzájomne sa vylučujúce spôsoby balenia zvlášť pre tú istú porciu -
    # "packSeparately" (bežné "zvlášť") a "packSeparatelyGn" (rovnaké, len
    # s poznámkou "do GN" pre kuchyňu). Súčet oboch pre daný kľúč nesmie
    # prekročiť objednaný počet.
    _PACK_FIELDS = ("packSeparately", "packSeparatelyGn")

    @classmethod
    def _order_has_special_diet(cls, data: Dict[str, Any]) -> bool:
        """Walk the same meal/category/sub-category shape as the main loop,
        looking for a positive count under diets['Špeciálna'] anywhere."""
        for meal_key, meal in data.items():
            if meal_key == cls._SPECIAL_DIET_NOTE_KEY or not isinstance(meal, dict):
                continue
            if cls._is_leaf_payload(meal):
                if cls._leaf_has_special_diet(meal):
                    return True
                continue
            for cat_data in meal.values():
                if not isinstance(cat_data, dict):
                    continue
                if cls._is_leaf_payload(cat_data):
                    if cls._leaf_has_special_diet(cat_data):
                        return True
                    continue
                for sub_data in cat_data.values():
                    if isinstance(sub_data, dict) and cls._leaf_has_special_diet(
                        sub_data
                    ):
                        return True
        return False

    @classmethod
    def _leaf_has_special_diet(cls, leaf: Dict[str, Any]) -> bool:
        diets = leaf.get("diets")
        if not isinstance(diets, dict):
            return False
        value = diets.get(cls._SPECIAL_DIET_NAME)
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    @staticmethod
    def _is_leaf_payload(value: Any) -> bool:
        return isinstance(value, dict) and (
            "menuCounts" in value
            or "diets" in value
            or "packSeparately" in value
            or "packSeparatelyGn" in value
        )

    def _validate_leaf(self, leaf: dict[str, Any], field_path: str) -> None:
        for sub_key in ("menuCounts", "diets"):
            if sub_key in leaf:
                self._validate_count_map(leaf[sub_key], f"{field_path}.{sub_key}")

        if not any(pack_field in leaf for pack_field in self._PACK_FIELDS):
            return

        raw_menu_counts = leaf.get("menuCounts")
        menu_counts = raw_menu_counts if isinstance(raw_menu_counts, dict) else {}
        raw_diets = leaf.get("diets")
        diets = raw_diets if isinstance(raw_diets, dict) else {}

        pack_by_field: dict[str, dict[str, Any]] = {}
        for pack_field in self._PACK_FIELDS:
            if pack_field not in leaf:
                continue
            pack_separately = leaf[pack_field]
            if not isinstance(pack_separately, dict):
                raise serializers.ValidationError(
                    f"'{field_path}.{pack_field}' musí byť objekt."
                )

            for sub_key in set(pack_separately) - {"menus", "diets"}:
                raise serializers.ValidationError(
                    f"'{field_path}.{pack_field}.{sub_key}' nie je podporované pole."
                )

            for sub_key, base_counts, label in (
                ("menus", menu_counts, "menu"),
                ("diets", diets, "diétu"),
            ):
                if sub_key not in pack_separately:
                    continue
                pack_counts = pack_separately[sub_key]
                self._validate_count_map(
                    pack_counts, f"{field_path}.{pack_field}.{sub_key}"
                )
                for key, value in pack_counts.items():
                    base_value = base_counts.get(key, 0)
                    if value > base_value:
                        raise serializers.ValidationError(
                            f"'{field_path}.{pack_field}.{sub_key}.{key}' nemôže byť väčšie než počet pre {label} '{key}'."
                        )
            pack_by_field[pack_field] = pack_separately

        # Krížový limit: jedna porcia nemôže byť naraz "zvlášť" aj "zvlášť do GN".
        zvlast = pack_by_field.get("packSeparately", {})
        gn = pack_by_field.get("packSeparatelyGn", {})
        for sub_key, base_counts, label in (
            ("menus", menu_counts, "menu"),
            ("diets", diets, "diétu"),
        ):
            zvlast_counts = zvlast.get(sub_key, {}) or {}
            gn_counts = gn.get(sub_key, {}) or {}
            for key in set(zvlast_counts) | set(gn_counts):
                combined = zvlast_counts.get(key, 0) + gn_counts.get(key, 0)
                base_value = base_counts.get(key, 0)
                if combined > base_value:
                    raise serializers.ValidationError(
                        f"'{field_path}': súčet packSeparately.{sub_key}.{key} a "
                        f"packSeparatelyGn.{sub_key}.{key} nemôže byť väčší než počet pre {label} '{key}'."
                    )

    @staticmethod
    def _validate_count_map(count_map: Any, field_path: str) -> None:
        """Validate that a counts dict contains only non-negative integers within bounds."""
        if not isinstance(count_map, dict):
            raise serializers.ValidationError(f"'{field_path}' must be an object.")
        for key, value in count_map.items():
            if not isinstance(value, int) or isinstance(value, bool):
                raise serializers.ValidationError(
                    f"'{field_path}.{key}' must be an integer, got {type(value).__name__}."
                )
            if value < 0 or value > DailyOrderSerializer._MAX_COUNT:
                raise serializers.ValidationError(
                    f"'{field_path}.{key}' must be between 0 and {DailyOrderSerializer._MAX_COUNT}."
                )

    @classmethod
    def _meal_has_content(cls, meal_data: Any) -> bool:
        od = OrderData({"_": meal_data})
        return any(
            any(safe_count(c) > 0 for c in cat.menu_counts.values())
            or any(safe_count(c) > 0 for c in cat.diets.values())
            for cat in od.iter_categories("_")
        )

    @classmethod
    def _meal_signature(cls, meal_data: Any) -> frozenset:
        """Content fingerprint of a meal, independent of JSON shape.

        The frontend re-normalizes meals it re-sends (``enforceStructure``
        fills in every category/diet key known to the current schema, even
        ones absent from what was actually stored). Comparing raw dicts would
        then flag an untouched, already-locked meal as "changed" whenever the
        schema gained a key after it was last submitted — which re-triggers
        its (possibly long-expired) deadline check and blocks the whole
        order. Compare by non-zero (category, kind, key) -> count instead, so
        only real content changes count as a change.
        """
        od = OrderData({"_": meal_data})
        entries: list[tuple[Any, str, str, int]] = []
        for cat in od.iter_categories("_"):
            prefix = (cat.prevadzka, cat.name)
            for menu, count in cat.menu_counts.items():
                c = safe_count(count)
                if c:
                    entries.append((prefix, "menu", menu, c))
            for diet, count in cat.diets.items():
                c = safe_count(count)
                if c:
                    entries.append((prefix, "diet", diet, c))
            for kind, counts in cat.pack_separately.items():
                if not isinstance(counts, dict):
                    continue
                for key, count in counts.items():
                    c = safe_count(count)
                    if c:
                        entries.append((prefix, "pack", f"{kind}:{key}", c))
        return frozenset(entries)

    @classmethod
    def _walk_meal_changes(
        cls,
        new_data: Dict[str, Any],
        existing_data: Dict[str, Any] | None,
        input_status: str,
        *,
        draft_predicate,
        submitted_predicate,
    ) -> list[str]:
        """Shared "for each configured meal, compare previous vs current under
        the draft-or-submitted rule" scaffold behind `_changed_meals` and
        `_changed_restricted_menus` - only the actual comparison (what counts
        as a "change" for that meal) differs between the two, so it's passed
        in rather than re-walking `MEAL_FIELD_CONFIG` twice."""
        existing_data = existing_data or {}
        changed: list[str] = []
        for meal_key in cls.MEAL_FIELD_CONFIG:
            previous = existing_data.get(meal_key, {}) or {}
            current = new_data.get(meal_key, {}) or {}
            if input_status == "draft":
                if draft_predicate(previous, current):
                    changed.append(meal_key)
                continue
            if submitted_predicate(previous, current):
                changed.append(meal_key)
        return changed

    @classmethod
    def _changed_meals(
        cls,
        new_data: Dict[str, Any],
        existing_data: Dict[str, Any] | None = None,
        input_status: str = "submitted",
    ) -> list[str]:
        return cls._walk_meal_changes(
            new_data,
            existing_data,
            input_status,
            draft_predicate=lambda prev, curr: (
                cls._meal_has_content(prev) or cls._meal_has_content(curr)
            ),
            submitted_predicate=lambda prev, curr: (
                cls._meal_signature(prev) != cls._meal_signature(curr)
                and (cls._meal_has_content(prev) or cls._meal_has_content(curr))
            ),
        )

    # Menu B, C a D majú vlastný, prísnejší termín (napr. 7:30 dva dni vopred) —
    # nezávislý od bežného per-jedlo deadlinu, platí rovnako pre všetky jedlá.
    _RESTRICTED_MENUS = frozenset({"B", "C", "D"})

    @classmethod
    def _meal_menu_signature(
        cls, meal_data: Any, allowed_menus: frozenset
    ) -> frozenset:
        """Content fingerprint of a meal, restricted to `menuCounts` of `allowed_menus`."""
        od = OrderData({"_": meal_data})
        entries: list[tuple[Any, str, int]] = []
        for cat in od.iter_categories("_"):
            prefix = (cat.prevadzka, cat.name)
            for menu, count in cat.menu_counts.items():
                if menu not in allowed_menus:
                    continue
                c = safe_count(count)
                if c:
                    entries.append((prefix, menu, c))
        return frozenset(entries)

    @classmethod
    def _changed_restricted_menus(
        cls,
        new_data: Dict[str, Any],
        existing_data: Dict[str, Any] | None = None,
        input_status: str = "submitted",
    ) -> list[str]:
        """Meal keys (`lunch`, ...) whose Menu B/C/D content changed. Returns a
        list (still truthy/falsy like the old bool) — `_validate_deadlines`
        needs the keys to check per-meal whether the change was an increase."""

        def sig(meal_data: Any) -> frozenset:
            return cls._meal_menu_signature(meal_data, cls._RESTRICTED_MENUS)

        return cls._walk_meal_changes(
            new_data,
            existing_data,
            input_status,
            draft_predicate=lambda prev, curr: bool(sig(prev)) or bool(sig(curr)),
            submitted_predicate=lambda prev, curr: (
                sig(prev) != sig(curr) and (sig(prev) or sig(curr))
            ),
        )

    @classmethod
    def _restricted_menu_counts(
        cls, meal_data: Any, allowed_menus: frozenset
    ) -> dict[tuple[Any, str], int]:
        """{(prevádzka, portion, menu): count} pre `allowed_menus`, na porovnanie
        starého a nového počtu — na rozdiel od `_meal_menu_signature` (frozenset
        na detekciu "zmenilo sa niečo") toto zachová KTORÝ počet sa zmenil a AKO."""
        od = OrderData({"_": meal_data})
        counts: dict[tuple[Any, str], int] = {}
        for cat in od.iter_categories("_"):
            prefix = (cat.prevadzka, cat.name)
            for menu, count in cat.menu_counts.items():
                if menu not in allowed_menus:
                    continue
                c = safe_count(count)
                if c:
                    counts[(prefix, menu)] = c
        return counts

    @classmethod
    def _restricted_menu_increased(cls, prev_meal: Any, curr_meal: Any) -> bool:
        """True, ak sa aspoň jeden Menu B/C/D počet (na prevádzku/porciu/menu)
        zvýšil alebo pribudol nový — odhlásenie/zníženie (nikdy nová/vyššia
        hodnota) sa nepovažuje za "increase" (user 2.9.2026: odhlásiť sa dá až
        do rána, nahlásiť/zvýšiť len do 2-dňového termínu)."""
        prev_counts = cls._restricted_menu_counts(prev_meal, cls._RESTRICTED_MENUS)
        curr_counts = cls._restricted_menu_counts(curr_meal, cls._RESTRICTED_MENUS)
        return any(
            count > prev_counts.get(key, 0) for key, count in curr_counts.items()
        )

    @classmethod
    def _restricted_menus_increased(
        cls,
        new_data: Dict[str, Any],
        existing_data: Dict[str, Any] | None,
        changed_meal_keys: list[str],
    ) -> bool:
        existing_data = existing_data or {}
        return any(
            cls._restricted_menu_increased(
                existing_data.get(meal_key, {}) or {},
                new_data.get(meal_key, {}) or {},
            )
            for meal_key in changed_meal_keys
        )

    @classmethod
    def _validate_deadlines(
        cls,
        target_date: datetime.date,
        new_data: Dict[str, Any],
        input_status: str,
        existing_data: Dict[str, Any] | None = None,
        prevadzka: Prevadzka | None = None,
    ) -> None:
        changed_meals = cls._changed_meals(new_data, existing_data, input_status)
        changed_restricted_menus = cls._changed_restricted_menus(
            new_data, existing_data, input_status
        )
        if not changed_meals and not changed_restricted_menus:
            return

        settings = get_global_settings()
        current_dt = timezone.localtime()
        current_tz = timezone.get_current_timezone()

        for meal_key in changed_meals:
            deadline_field, day_before_field = cls.MEAL_FIELD_CONFIG[meal_key]
            deadline_time = getattr(settings, deadline_field)
            deadline_date = (
                target_date - datetime.timedelta(days=1)
                if getattr(settings, day_before_field)
                else target_date
            )
            deadline_dt = timezone.make_aware(
                datetime.datetime.combine(deadline_date, deadline_time),
                current_tz,
            )
            if current_dt >= deadline_dt:
                label = cls.MEAL_LABELS[meal_key]
                raise OrderDeadlinePassedError(
                    deadline_time=deadline_dt.strftime("%d.%m.%Y %H:%M"),
                    current_time=current_dt.strftime("%d.%m.%Y %H:%M"),
                    detail=(
                        f"Objednávku pre {label} už nie je možné meniť. "
                        f"Termín: {deadline_dt.strftime('%d.%m.%Y %H:%M')}"
                    ),
                )

        if changed_restricted_menus and not (
            prevadzka is not None and prevadzka.menu_bc_same_deadline_as_lunch
        ):
            # Nahlásiť/zvýšiť Menu B/C má prísny 2-dňový termín (kuchyňa ich
            # dokupuje vopred) — ale ODHLÁSIŤ/znížiť sa dá až do rána v deň
            # výdaja, rovnaký termín ako bežné jedlo (user 2.9.2026: "nahlasit
            # si to vedia najviac 2 dni vopred ale odhlasit si to vedia az do
            # rana"). Bez tohto rozlíšenia by rodič nemohol odhlásiť dieťa
            # tesne pred obedom, len preto, že B/C termín už prešiel.
            #
            # Prevádzky s `menu_bc_same_deadline_as_lunch` (napr. piatkové
            # Menu B pre deti, user 10.9.2026) tento prísnejší termín vôbec
            # nevidia — Menu B/C tam podlieha len bežnej uzávierke jedla,
            # ktorú už vynútil `changed_meals` loop vyššie.
            is_increase = cls._restricted_menus_increased(
                new_data, existing_data, changed_restricted_menus
            )
            if is_increase:
                deadline_date = target_date - datetime.timedelta(
                    days=settings.deadline_menu_bc_days_before
                )
                # Explicitne pomenovať "prečo" (#573) — bez tohto rodičia/riaditelia
                # čítali toto hlásenie ako "appka je rozbitá" alebo "nastavenie
                # menu B nefunguje", hoci menu B bolo v nastaveniach v poriadku
                # zapnuté a šlo len o zmeškaný termín navýšenia.
                detail = (
                    "Menu B a C treba nahlásiť/navýšiť najneskôr "
                    f"{settings.deadline_menu_bc_days_before} dni vopred (kuchyňa ich "
                    "dokupuje) — tento termín už uplynul, nejde o chybu nastavenia."
                )
            else:
                deadline_date = target_date
                detail = "Menu B a C už nie je možné odhlásiť ani znížiť."
            deadline_dt = timezone.make_aware(
                datetime.datetime.combine(deadline_date, settings.deadline_menu_bc),
                current_tz,
            )
            if current_dt >= deadline_dt:
                raise OrderDeadlinePassedError(
                    deadline_time=deadline_dt.strftime("%d.%m.%Y %H:%M"),
                    current_time=current_dt.strftime("%d.%m.%Y %H:%M"),
                    detail=(
                        f"{detail} Termín: {deadline_dt.strftime('%d.%m.%Y %H:%M')}"
                    ),
                )

    def _enforce_holiday_restriction(
        self, user: Any, status: str, date: datetime.date
    ) -> None:
        """Disallow non-admin, non-draft orders on holidays.

        Obídenie je viazané na prihláseného aktéra (request.user), aby admin
        konajúci za klienta vedel objednať aj na sviatok. Rola, nie `is_staff` —
        kuchyňa toto obísť nesmie (#482).
        Falls back to the order owner's role if no request context exists.
        """
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        acting_admin = is_admin_or_above(actor) or is_admin_or_above(user)
        if not acting_admin and status != "draft":
            if Holiday.objects.filter(date=date).exists():
                raise HolidayOrderNotAllowedError()

    def _enforce_prevadzka_closure(
        self, user: Any, status: str, date: datetime.date, prevadzka: Prevadzka
    ) -> None:
        """Ako `_enforce_holiday_restriction`, ale pre voľno JEDNEJ prevádzky (#490).

        Samostatná metóda, lebo prevádzku pozná až `_resolve_prevadzka()` —
        globálne voľno sa dá overiť skôr, toto až po nej.
        """
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        is_staff = getattr(actor, "is_staff", False) or getattr(user, "is_staff", False)
        if not is_staff and status != "draft":
            if is_prevadzka_closed(date, prevadzka):
                raise PrevadzkaClosureOrderNotAllowedError()

    @staticmethod
    def _enforce_portion_types(prevadzka: Prevadzka, data: Dict[str, Any]) -> None:
        """Odmietni porcie v kategórii, ktorú prevádzka nemá povolenú.

        `visible_portion_types` je M2M s rovnakou sémantikou ako inde v appke:
        prázdna = neobmedzené (ešte nezakonfigurované), neprázdna = admin
        vedome zúžil veľkosti. Bez tejto kontroly sa dá zapísať zakázaná
        veľkosť napr. cez staré dáta v `data`, ktoré tam ostali z čias pred
        obmedzením (frontend ich pri ďalšom uložení znova pošle celé) —
        UI kontroluje len čo *renderuje*, nie čo v stave nosí ďalej.
        """
        allowed_names = {
            portion_type.name for portion_type in prevadzka.visible_portion_types.all()
        }
        if not allowed_names:
            return
        for meal_key, meal in data.items():
            if meal_key == DailyOrderSerializer._SPECIAL_DIET_NOTE_KEY:
                continue
            if not isinstance(meal, dict) or DailyOrderSerializer._is_leaf_payload(
                meal
            ):
                continue
            for cat_name, cat_data in meal.items():
                if cat_name in allowed_names or not isinstance(cat_data, dict):
                    continue
                menu_counts = cat_data.get("menuCounts")
                if isinstance(menu_counts, dict) and any(
                    (count or 0) > 0 for count in menu_counts.values()
                ):
                    raise serializers.ValidationError(
                        {
                            "data": (
                                f"Prevádzka '{prevadzka.nazov}' nemá veľkosť "
                                f"'{cat_name}' povolenú."
                            )
                        }
                    )

    @staticmethod
    def _enforce_menu_day_restrictions(
        prevadzka: Prevadzka, order_date: datetime.date, data: Dict[str, Any]
    ) -> None:
        """Odmietni menu písmeno v deň, na ktorý ho prevádzka neobmedzila.

        `menu_day_restrictions` je `{menu písmeno: [ISO deň, 1=pondelok..7=nedeľa]}`
        — napr. `{"B": [5]}` = Menu B len v piatok. Chýbajúci kľúč alebo prázdny
        zoznam = každý deň, rovnaká sémantika ako `filterMenusByDay` na frontende
        (`useOrder.ts`). Bez tejto kontroly frontend len *skryje* zakázaný deň v
        UI klienta — AdminOrderEditorModal aj priamy zápis do API ho vôbec
        nepozná, takže by sa dal zapísať bez obmedzenia.
        """
        restrictions = prevadzka.menu_day_restrictions or {}
        if not restrictions:
            return
        weekday = order_date.isoweekday()
        for meal_key, meal in data.items():
            if meal_key == DailyOrderSerializer._SPECIAL_DIET_NOTE_KEY:
                continue
            if not isinstance(meal, dict) or DailyOrderSerializer._is_leaf_payload(
                meal
            ):
                continue
            for cat_name, cat_data in meal.items():
                if not isinstance(cat_data, dict):
                    continue
                menu_counts = cat_data.get("menuCounts")
                if not isinstance(menu_counts, dict):
                    continue
                for menu_letter, count in menu_counts.items():
                    allowed_days = restrictions.get(menu_letter)
                    if not allowed_days:
                        continue
                    if (count or 0) > 0 and weekday not in allowed_days:
                        raise serializers.ValidationError(
                            {
                                "data": (
                                    f"Prevádzka '{prevadzka.nazov}' má menu "
                                    f"'{menu_letter}' povolené len v iný deň "
                                    "v týždni."
                                )
                            }
                        )

    @staticmethod
    def _enforce_meal_day_restrictions(
        prevadzka: Prevadzka, order_date: datetime.date, data: Dict[str, Any]
    ) -> None:
        """Odmietni jedlo (raňajky/obed/olovrant) v deň, na ktorý ho prevádzka
        neobmedzila.

        `meal_day_restrictions` je `{jedlo: [ISO deň, 1=pondelok..7=nedeľa]}`
        — napr. `{"breakfast": [5]}` = raňajky len v piatok. Chýbajúci kľúč
        alebo prázdny zoznam = každý deň — rovnaká sémantika ako
        `menu_day_restrictions`/`_enforce_menu_day_restrictions` a
        `filterMealsByDay` na frontende (`useOrder.ts`).
        """
        restrictions = prevadzka.meal_day_restrictions or {}
        if not restrictions:
            return
        weekday = order_date.isoweekday()
        for meal_key, meal in data.items():
            if meal_key == DailyOrderSerializer._SPECIAL_DIET_NOTE_KEY:
                continue
            allowed_days = restrictions.get(meal_key)
            if not allowed_days or weekday in allowed_days:
                continue
            if not isinstance(
                meal, dict
            ) or not DailyOrderSerializer._meal_has_positive_count(meal):
                continue
            raise serializers.ValidationError(
                {
                    "data": (
                        f"Prevádzka '{prevadzka.nazov}' má jedlo '{meal_key}' "
                        "povolené len v iný deň v týždni."
                    )
                }
            )

    @staticmethod
    def _meal_has_positive_count(meal: Dict[str, Any]) -> bool:
        """Walk the meal/category/sub-category shape looking for any positive
        count in menuCounts or diets, anywhere under this meal."""
        if DailyOrderSerializer._is_leaf_payload(meal):
            return DailyOrderSerializer._leaf_has_positive_count(meal)
        for cat_data in meal.values():
            if not isinstance(cat_data, dict):
                continue
            if DailyOrderSerializer._is_leaf_payload(cat_data):
                if DailyOrderSerializer._leaf_has_positive_count(cat_data):
                    return True
                continue
            for sub_data in cat_data.values():
                if isinstance(
                    sub_data, dict
                ) and DailyOrderSerializer._leaf_has_positive_count(sub_data):
                    return True
        return False

    @staticmethod
    def _leaf_has_positive_count(leaf: Dict[str, Any]) -> bool:
        for key in ("menuCounts", "diets"):
            counts = leaf.get(key)
            if isinstance(counts, dict) and any(
                isinstance(value, int) and not isinstance(value, bool) and value > 0
                for value in counts.values()
            ):
                return True
        return False

    def create(self, validated_data: Dict[str, Any]) -> DailyOrder:
        """
        Upsert a DailyOrder for (user, date).

        - ``status='draft'`` → delete any existing order and return an
          unsaved placeholder (drafts are never persisted).
        - Any other status → update or create the order using a
          ``SELECT FOR UPDATE`` lock to prevent concurrent-write races.

        Args:
            validated_data: Validated fields from the serializer.

        Returns:
            The saved (or placeholder) DailyOrder instance.
        """
        request = self.context.get("request")
        user = validated_data.get("user") or (request and request.user)
        if user is None:
            raise serializers.ValidationError(
                {"user": "User must be provided in request context or validated data."}
            )
        input_status = validated_data.get("status", "submitted")
        is_admin = is_admin_or_above(getattr(request, "user", None))

        self._enforce_day_open(validated_data["date"])
        self._enforce_holiday_restriction(user, input_status, validated_data["date"])

        prevadzka = self._resolve_prevadzka(user, validated_data)
        self._enforce_prevadzka_closure(
            user, input_status, validated_data["date"], prevadzka
        )
        if input_status != "draft":
            order_data = validated_data.get("data", {})
            self._enforce_portion_types(prevadzka, order_data)
            self._enforce_menu_day_restrictions(
                prevadzka, validated_data["date"], order_data
            )
            self._enforce_meal_day_restrictions(
                prevadzka, validated_data["date"], order_data
            )

        # If status is passed as 'draft', we treat it as a deletion request
        # because we do not persist drafts.
        if input_status == "draft":
            existing_order = DailyOrder.objects.filter(
                prevadzka=prevadzka, date=validated_data["date"]
            ).first()
            if not is_admin:
                self._validate_deadlines(
                    validated_data["date"],
                    validated_data.get("data", {}),
                    input_status,
                    existing_order.data if existing_order else None,
                    prevadzka,
                )
            DailyOrder.objects.filter(
                prevadzka=prevadzka, date=validated_data["date"]
            ).delete()
            self._sync_auto_order_pause(prevadzka, {})
            # Return an unsaved instance for the response
            result = DailyOrder(
                user=user,
                prevadzka=prevadzka,
                date=validated_data["date"],
                status="draft",
                data={},
            )
            # Audit trail (viď `perform_create` v `order_views.py`): draft je
            # jediná cesta, ktorou klient objednávku maže — POST na `/orders/`,
            # nikdy DELETE. Bez tohto tagu by sa toto zmazanie v EventLogu
            # stratilo, lebo view nemá odkiaľ vziať pôvodné dáta.
            result._audit_event = "delete" if existing_order else None
            result._audit_previous_data = existing_order.data if existing_order else {}
            return result

        new_data = validated_data.get("data", {})
        existing_order = (
            DailyOrder.objects.filter(prevadzka=prevadzka, date=validated_data["date"])
            .only("data", "touched_meals")
            .first()
        )
        # Tento vstup sa spojí až po ``select_for_update()`` nižšie. Výpočet
        # unionu zo snapshotu tu by pri dvoch súbežných requestoch vedel
        # stratiť marker, ktorý prvý request medzičasom práve uložil.
        incoming_touched_meals = set(validated_data.get("touched_meals") or [])
        if not is_admin:
            self._validate_deadlines(
                validated_data["date"],
                new_data,
                input_status,
                existing_order.data if existing_order else None,
                prevadzka,
            )

        # Use select_for_update inside an atomic block to prevent race conditions
        # when concurrent requests submit an order for the same (prevadzka, date).
        # The SELECT ... FOR UPDATE acquires a row lock so only one writer proceeds
        # at a time; the outer transaction.atomic() ensures the lock is held for the
        # full read-modify-write cycle.
        with transaction.atomic():
            try:
                t0 = time.monotonic()
                order = DailyOrder.objects.select_for_update(nowait=False).get(
                    prevadzka=prevadzka, date=validated_data["date"]
                )
                wait_ms = (time.monotonic() - t0) * 1000
                if wait_ms > 100:
                    logger.warning(
                        "select_for_update lock wait %.1f ms for prevadzka=%s date=%s",
                        wait_ms,
                        prevadzka.pk,
                        validated_data["date"],
                    )
                actual_previous_data = order.data or {}
                order.data = new_data
                order.touched_meals = sorted(
                    set(order.touched_meals or []) | incoming_touched_meals
                )
                # Issue #507: a manual submit overwriting an auto-generated
                # placeholder (`is_auto=True`, created by auto_order_service
                # after the deadline) is real, reviewed data now — clear the
                # flag so admin overview stops flagging it "na kontrolu"
                # forever, even after someone actually filled it in.
                order.is_auto = False
                order.save(
                    update_fields=["data", "touched_meals", "is_auto", "updated_at"]
                )
                actual_audit_event = "update"
            except DailyOrder.DoesNotExist:
                # Wrap create() in its own savepoint so that if IntegrityError is
                # raised (another request raced us to INSERT), only this savepoint
                # is rolled back and the outer atomic block remains usable.
                try:
                    with transaction.atomic():
                        order = DailyOrder.objects.create(
                            user=user,
                            prevadzka=prevadzka,
                            date=validated_data["date"],
                            data=new_data,
                            touched_meals=sorted(incoming_touched_meals),
                        )
                        actual_previous_data = {}
                        actual_audit_event = "create"
                except IntegrityError:
                    # Another request won the INSERT race; retry with a lock.
                    order = DailyOrder.objects.select_for_update(nowait=False).get(
                        prevadzka=prevadzka, date=validated_data["date"]
                    )
                    actual_previous_data = order.data or {}
                    order.data = new_data
                    # Retry už drží lock na aktuálnom riadku; union musí čítať
                    # jeho čerstvú hodnotu, nie hodnotu pred prvým pokusom.
                    order.touched_meals = sorted(
                        set(order.touched_meals or []) | incoming_touched_meals
                    )
                    order.save(update_fields=["data", "touched_meals", "updated_at"])
                    actual_audit_event = "update"

        self._sync_auto_order_pause(prevadzka, new_data)
        # Audit trail: `create()` je upsert (viď docstring), takže "create"
        # requesty tu bežne aj prepisujú existujúci riadok. `perform_create`
        # v `order_views.py` z tohto odvodí, či ide o skutočné vytvorenie
        # alebo o úpravu, a čo bolo predtým.
        order._audit_event = actual_audit_event
        order._audit_previous_data = actual_previous_data
        return order

    @staticmethod
    def _resolve_prevadzka(user, validated_data: Dict[str, Any]) -> Prevadzka:
        """Za ktorú prevádzku sa objednáva. Pri viacerých ju musí klient poslať."""
        explicit = validated_data.pop("prevadzka", None)
        if explicit is not None and is_admin_or_above(user):
            return explicit
        try:
            return vyber_prevadzku(user, explicit.pk if explicit else None)
        except PrevadzkaNejednoznacna as exc:
            raise serializers.ValidationError({"prevadzka": str(exc)}) from exc
        except PrevadzkaNedostupna as exc:
            raise serializers.ValidationError({"prevadzka": str(exc)}) from exc

    def update(
        self, instance: DailyOrder, validated_data: Dict[str, Any]
    ) -> DailyOrder:
        input_status = validated_data.get("status", instance.status)
        new_data = validated_data.get("data", instance.data)
        request = self.context.get("request")
        user = validated_data.get("user") or instance.user
        is_admin = is_admin_or_above(getattr(request, "user", None))

        self._enforce_day_open(instance.date)
        self._enforce_holiday_restriction(user, input_status, instance.date)
        if instance.prevadzka_id:
            self._enforce_prevadzka_closure(
                user, input_status, instance.date, instance.prevadzka
            )

        if not is_admin:
            self._validate_deadlines(
                instance.date,
                new_data,
                input_status,
                instance.data,
                instance.prevadzka if instance.prevadzka_id else None,
            )

        if input_status != "draft" and instance.prevadzka_id:
            self._enforce_portion_types(instance.prevadzka, new_data)
            self._enforce_menu_day_restrictions(
                instance.prevadzka, instance.date, new_data
            )
            self._enforce_meal_day_restrictions(
                instance.prevadzka, instance.date, new_data
            )

        if input_status == "draft":
            prevadzka = instance.prevadzka
            instance.delete()
            self._sync_auto_order_pause(prevadzka, {})
            return DailyOrder(
                user=instance.user, date=instance.date, status="draft", data={}
            )

        # ``instance`` mohol view načítať dávno pred PATCHom. Zamkneme a znova
        # načítame aktuálny riadok, aby paralelný PATCH nikdy nevymazal marker
        # pridaný iným requestom.
        with transaction.atomic():
            instance = DailyOrder.objects.select_for_update().get(pk=instance.pk)
            actual_previous_data = instance.data or {}
            instance.data = new_data
            instance.touched_meals = sorted(
                set(instance.touched_meals or [])
                | set(validated_data.get("touched_meals") or [])
            )
            # Issue #507: see the matching comment in create() above.
            instance.is_auto = False
            instance.save(
                update_fields=["data", "touched_meals", "is_auto", "updated_at"]
            )
        instance._audit_previous_data = actual_previous_data
        self._sync_auto_order_pause(instance.prevadzka, new_data)
        return instance


class GlobalSettingsSerializer(serializers.ModelSerializer):
    """
    Serializer for GlobalSettings (singleton model).

    Non-admin users receive the response without the
    ``report_email_recipients`` field (stripped in ``to_representation``).
    """

    report_email_recipients = serializers.ListField(
        child=serializers.EmailField(),
        required=False,
        allow_empty=True,
    )

    class Meta:
        from .models import GlobalSettings

        model = GlobalSettings
        fields = [
            "maintenance_enabled",
            "maintenance_starts_at",
            "maintenance_ends_at",
            "deadline_breakfast",
            "deadline_breakfast_is_day_before",
            "deadline_lunch",
            "deadline_lunch_is_day_before",
            "deadline_olovrant",
            "deadline_olovrant_is_day_before",
            "deadline_menu_bc",
            "deadline_menu_bc_days_before",
            "edupage_auto_scrape_enabled",
            "edupage_scrape_time_breakfast",
            "edupage_scrape_time_breakfast_is_day_before",
            "edupage_scrape_time_lunch",
            "edupage_scrape_time_lunch_is_day_before",
            "edupage_scrape_time_olovrant",
            "edupage_scrape_time_olovrant_is_day_before",
            "daily_report_enabled",
            "report_email_recipients",
            "client_contact_name",
            "client_contact_role",
            "client_contact_email",
            "client_contact_phone",
        ]

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """An enabled maintenance notice must always have a real end time."""
        enabled = attrs.get("maintenance_enabled", self.instance.maintenance_enabled)
        starts_at = attrs.get(
            "maintenance_starts_at", self.instance.maintenance_starts_at
        )
        ends_at = attrs.get("maintenance_ends_at", self.instance.maintenance_ends_at)
        if enabled:
            errors = {}
            if not starts_at:
                errors["maintenance_starts_at"] = "Zadajte začiatok údržby."
            if not ends_at:
                errors["maintenance_ends_at"] = "Zadajte koniec údržby."
            elif starts_at and ends_at <= starts_at:
                errors["maintenance_ends_at"] = (
                    "Koniec údržby musí byť po jej začiatku."
                )
            if errors:
                raise serializers.ValidationError(errors)
        return attrs

    def to_representation(self, instance: Any) -> Dict[str, Any]:
        """Strip ``report_email_recipients`` for non-admin callers."""
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        is_admin = is_admin_or_above(user)
        if not is_admin:
            data.pop("report_email_recipients", None)
        return data


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ["id", "date", "reason"]


class PrevadzkaClosureSerializer(serializers.ModelSerializer):
    """Voľno jednej prevádzky (#490) — deň alebo rozsah."""

    prevadzka_nazov = serializers.CharField(source="prevadzka.nazov", read_only=True)

    class Meta:
        model = PrevadzkaClosure
        fields = [
            "id",
            "prevadzka",
            "prevadzka_nazov",
            "date_from",
            "date_to",
            "reason",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        # Pri PATCHi príde len jedno pole — druhý koniec doplň z inštancie,
        # inak by sa dal rozsah "obrátiť" čiastočnou úpravou.
        date_from = attrs.get("date_from") or getattr(self.instance, "date_from", None)
        date_to = attrs.get("date_to") or getattr(self.instance, "date_to", None)
        if date_from and date_to and date_to < date_from:
            raise serializers.ValidationError(
                {"date_to": "Koniec voľna nesmie byť pred jeho začiatkom."}
            )
        return attrs


class PrevadzkaDietSerializer(serializers.ModelSerializer):
    class Meta:
        model = Diet
        fields = ["id", "name", "sort_order", "is_active", "description", "color"]


class PrevadzkaPortionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortionType
        fields = ["id", "name", "sort_order", "is_active"]


class PrevadzkaSerializer(serializers.ModelSerializer):
    celok = serializers.CharField(source="celok.nazov", read_only=True)
    visible_diets = PrevadzkaDietSerializer(many=True, read_only=True)
    visible_portion_types = PrevadzkaPortionTypeSerializer(many=True, read_only=True)

    class Meta:
        model = Prevadzka
        # `pack_separately_enabled` sem patrí, aby klient čítal príznak z toho istého
        # miesta, kam ho admin zapisuje (Prevadzka).
        fields = [
            "id",
            "nazov",
            "adresa",
            "celok",
            "visible_menus",
            "menu_day_restrictions",
            "visible_meals",
            "meal_day_restrictions",
            "visible_diets",
            "visible_portion_types",
            "pack_separately_enabled",
        ]
        read_only_fields = fields
