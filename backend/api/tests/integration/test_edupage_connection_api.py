import pytest
from rest_framework import status

from api.edupage_scraper import ScrapeResult
from api.models import Celok, ClosedDay, DailyOrder, EdupageConnection, Prevadzka

pytestmark = pytest.mark.integration

CONNECTIONS_URL = "/api/admin/edupage-connections/"


@pytest.mark.django_db
def test_shared_url_creates_one_connection_for_multiple_celky():
    url = "https://shared.edupage.org/menu/mealsGuest?id=token"
    first = Celok.objects.create(
        nazov="First school",
        zdroj_objednavok=Celok.ZdrojObjednavok.EDUPAGE,
    )
    second = Celok.objects.create(
        nazov="Second school",
        zdroj_objednavok=Celok.ZdrojObjednavok.EDUPAGE,
    )
    connection = EdupageConnection.objects.create(
        name="Shared EduPage",
        mealsguest_url=url,
    )
    first_prevadzka = Prevadzka.objects.create(
        celok=first,
        nazov="First",
        edupage_connection=connection,
    )
    second_prevadzka = Prevadzka.objects.create(
        celok=second,
        nazov="Second",
        edupage_connection=connection,
    )
    assert first_prevadzka.edupage_connection_id == connection.pk
    assert second_prevadzka.edupage_connection_id == connection.pk


@pytest.mark.django_db
def test_admin_can_manage_connections_and_assign_them_to_prevadzka(admin_client):
    create_response = admin_client.post(
        CONNECTIONS_URL,
        {
            "name": "Managed EduPage",
            "mealsguest_url": (
                "https://managed.edupage.org/menu/mealsGuest?id=managed-token"
            ),
            "api_identifier": "managed",
            "is_active": True,
        },
        format="json",
    )

    assert create_response.status_code == status.HTTP_201_CREATED
    connection_id = create_response.json()["id"]

    update_response = admin_client.patch(
        f"{CONNECTIONS_URL}{connection_id}/",
        {"is_active": False},
        format="json",
    )

    assert update_response.status_code == status.HTTP_200_OK
    assert update_response.json()["is_active"] is False
    assert admin_client.get(CONNECTIONS_URL).json()[0]["id"] == connection_id

    celok = Celok.objects.create(nazov="Managed school")
    prevadzka_response = admin_client.post(
        "/api/admin/facility-prevadzky/",
        {
            "celok": celok.pk,
            "nazov": "Managed school",
            "edupage_connection": connection_id,
        },
        format="json",
    )

    assert prevadzka_response.status_code == status.HTTP_201_CREATED
    assert prevadzka_response.json()["edupage_connection"] == connection_id
    assert prevadzka_response.json()["edupage_connection_name"] == "Managed EduPage"


@pytest.mark.django_db
def test_scrape_action_lives_on_connection_endpoint(admin_client):
    response = admin_client.post(f"{CONNECTIONS_URL}scrape/", {}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"error": "date is required"}


@pytest.mark.django_db
def test_scrape_rejects_closed_day_before_import(admin_client, admin_user):
    target_date = "2099-08-07"
    ClosedDay.objects.create(date=target_date, closed_by=admin_user)

    response = admin_client.post(
        f"{CONNECTIONS_URL}scrape/",
        {"date": target_date},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["message"] == (
        "Deň je uzavretý, objednávky sa už nedajú upravovať."
    )
    assert not DailyOrder.objects.filter(date=target_date).exists()


@pytest.mark.django_db
def test_scrape_imports_orders_for_open_day(admin_client, admin_user, monkeypatch):
    target_date = "2099-08-08"
    celok = Celok.objects.create(nazov="Open import school")
    prevadzka = Prevadzka.objects.create(celok=celok, nazov="Open import school")
    operation = {
        "connection_id": 123,
        "name": "Open import",
        "url": "https://example.edupage.org/menu/mealsGuest?id=test",
        "user": admin_user,
        "prevadzky": [prevadzka],
    }
    monkeypatch.setattr(
        "api.views.edupage_views.edupage_operations",
        lambda connection_id=None: [operation],
    )
    monkeypatch.setattr(
        "api.views.edupage_views.EdupageScraper.scrape",
        lambda self, url, date, **kwargs: ScrapeResult(
            date=date,
            order_data={"lunch": {"menuCounts": {"A": 3}, "diets": {}}},
        ),
    )

    response = admin_client.post(
        f"{CONNECTIONS_URL}scrape/",
        {"date": target_date},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["results"][0]["status"] == "updated"
    order = DailyOrder.objects.get(prevadzka=prevadzka, date=target_date)
    assert order.data == {
        "lunch": {"Open import school": {"menuCounts": {"A": 3}, "diets": {}}}
    }


@pytest.mark.django_db
def test_manual_scrape_persists_attention_flags_for_kontrola(
    admin_client, admin_user, monkeypatch
):
    """Manuálny import nesmie zahodiť upozornenie, ktoré má vidieť Kontrola."""
    target_date = "2099-08-09"
    celok = Celok.objects.create(nazov="Attention import school")
    prevadzka = Prevadzka.objects.create(celok=celok, nazov="Attention import")
    operation = {
        "connection_id": 124,
        "name": "Attention import",
        "url": "https://example.edupage.org/menu/mealsGuest?id=attention",
        "user": admin_user,
        "prevadzky": [prevadzka],
    }
    monkeypatch.setattr(
        "api.views.edupage_views.edupage_operations",
        lambda connection_id=None: [operation],
    )
    monkeypatch.setattr(
        "api.views.edupage_views.EdupageScraper.scrape",
        lambda self, url, date, **kwargs: ScrapeResult(
            date=date,
            order_data={"lunch": {"menuCounts": {"A": 1}, "diets": {}}},
            attention=["A:legacy→NO MILK nie je medzi viditeľnými diétami prevádzky"],
            unmapped_letters=["N:Neznáma diéta"],
            uncertain_letters=["A:XY→NO MILK"],
            config_notes=["olovrant chýba"],
        ),
    )

    response = admin_client.post(
        f"{CONNECTIONS_URL}scrape/", {"date": target_date}, format="json"
    )

    assert response.status_code == status.HTTP_200_OK
    order = DailyOrder.objects.get(prevadzka=prevadzka, date=target_date)
    assert order.scrape_flags == {
        "attention": ["A:legacy→NO MILK nie je medzi viditeľnými diétami prevádzky"],
        "config_notes": ["olovrant chýba"],
        "unmapped_diets": ["N:Neznáma diéta"],
        "uncertain_diets": ["A:XY→NO MILK"],
    }
