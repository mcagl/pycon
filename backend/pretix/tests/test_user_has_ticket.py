from django.test import override_settings
from pytest import mark

from pretix.db import user_has_admission_ticket


@override_settings(SIMULATE_PRETIX_DB=True)
def test_user_always_has_ticket_when_db_is_simulated():
    assert (
        user_has_admission_ticket(
            email="nina@fake-work-email.ca",
            event_organizer="organizer",
            event_slug="event",
        )
        is True
    )


@override_settings(SIMULATE_PRETIX_DB=False)
@mark.parametrize("has_ticket", [True, False])
def test_user_has_admission_ticket(mocker, has_ticket):
    connections_mock = mocker.patch("pretix.db.connections")
    connections_mock.__getitem__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = (  # noqa
        has_ticket,
    )

    assert (
        user_has_admission_ticket(
            email="nina@fake-work-email.ca",
            event_organizer="organizer",
            event_slug="slug",
        )
        is has_ticket
    )
