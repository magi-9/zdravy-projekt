"""Menu D a VEGE1 nesmú byť dostupné žiadnej prevádzke ako default — sú to
British School špecifiká (Cluster C, kusový sumár), viditeľné len tej jednej
prevádzke cez explicitný `visible_menus` v jej seed-e, nie cez globálny
default (user 4.9.2026: "má byť disabled teda neviditeľná inak pre british
úplne rovnako ako menu Vege 1")."""

import pytest

from api.default_visibility import DEFAULT_VISIBLE_MENUS
from api.models import _default_visible_menus


@pytest.mark.django_db
class TestDefaultVisibleMenus:
    def test_menu_d_not_in_default(self):
        assert "D" not in DEFAULT_VISIBLE_MENUS

    def test_vege1_not_in_default(self):
        assert "VEGE1" not in DEFAULT_VISIBLE_MENUS

    def test_model_field_default_matches_canonical_default(self):
        # `_default_visible_menus` (JSONField default) a `DEFAULT_VISIBLE_MENUS`
        # (aplikovaný na created Prevadzka cez `on_prevadzka_saved` signal) musia
        # zostať zosynchronizované, inak sa novozaložená prevádzka správa inak
        # ako priamy DB default naznačuje.
        assert _default_visible_menus() == DEFAULT_VISIBLE_MENUS
