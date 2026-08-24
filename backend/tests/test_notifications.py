import datetime as dt

from app.notifications.service import (
    EventNotification,
    SubscriptionPrefs,
    TokenBucket,
    render_notification,
    should_notify,
)


OFFICIAL = EventNotification("ev1", "red", ["MAZOWIECKIE"], True, "Test oficjalny")
UNOFFICIAL = EventNotification("ev2", "orange", ["MAZOWIECKIE"], False, "Test nieoficjalny")


def test_loud_only_for_official():
    prefs = SubscriptionPrefs("s1", ["MAZOWIECKIE"], min_level="yellow",
                              official_only=False, muted=False)
    ok, style, _ = should_notify(OFFICIAL, prefs)
    assert ok and style == "loud"
    ok2, style2, _ = should_notify(UNOFFICIAL, prefs)
    assert ok2 and style2 == "silent"


def test_official_only_blocks_unofficial():
    prefs = SubscriptionPrefs("s1", [], min_level="yellow", official_only=True, muted=False)
    ok, _, _ = should_notify(UNOFFICIAL, prefs)
    assert not ok


def test_muted_always_silent():
    prefs = SubscriptionPrefs("s1", [], min_level="yellow", official_only=False, muted=True)
    ok, _, _ = should_notify(OFFICIAL, prefs)
    assert not ok


def test_voivodeship_filter():
    prefs = SubscriptionPrefs("s1", ["POMORSKIE"], min_level="yellow",
                              official_only=False, muted=False)
    ok, _, _ = should_notify(OFFICIAL, prefs)
    assert not ok


def test_min_level_respected():
    yellow = EventNotification("ev3", "yellow", [], True, "t")
    prefs = SubscriptionPrefs("s1", [], min_level="orange", official_only=False, muted=False)
    ok, _, _ = should_notify(yellow, prefs)
    assert not ok


def test_merge_window_key_groups_5min():
    t = dt.datetime(2026, 8, 23, 17, 37, tzinfo=dt.timezone.utc)
    prefs = SubscriptionPrefs("s1", [], min_level="yellow", official_only=False, muted=False)
    _, _, key1 = should_notify(OFFICIAL, prefs, now=t)
    _, _, key2 = should_notify(EventNotification("ev9", "red", ["MAZOWIECKIE"], True, "x"),
                               prefs, now=t + dt.timedelta(minutes=2))
    assert key1 == key2


def test_token_bucket_limits_flood():
    bucket = TokenBucket(max_per_hour=10)
    for _ in range(10):
        assert bucket.allow("s1")
    assert not bucket.allow("s1")


def test_unverified_notification_text_is_neutral():
    out = render_notification(UNOFFICIAL, "silent")
    assert out["title"] == "Niezweryfikowana informacja do sprawdzenia"
