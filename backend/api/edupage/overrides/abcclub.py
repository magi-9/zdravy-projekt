"""ABC Club — EduPage payer skupina pre diétu NONO.

ABC prešlo na EduPage v septembri 2026. Payer skupina "NoNo dieťa s
dotáciou" nemá skratku ani názov, z ktorého ju generický parser vie bezpečne
odvodiť. V pôvodných objednávkach ABC jej konzistentne zodpovedá diéta NONO.
"""

from __future__ import annotations

import unicodedata

from ..base import PayerRule


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", (value or "").casefold())
    return "".join(ch for ch in decomposed if ch.isalnum())


def abcclub_payer_hook(payer_name: str) -> PayerRule | None:
    """Rozpoznaj ABC skupinu ``NoNo dieťa s dotáciou`` ako diétu NONO."""
    if _fold(payer_name).startswith("nonodieta"):
        return PayerRule(diet="NONO")
    return None
