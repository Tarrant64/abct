"""Refresh stamps must carry a date AND a time zone (WQ-0376).

The web "Last updated" stamps used to show only a time-of-day, so a stamp
taken before today was indistinguishable from one taken now, and the zone
was invisible. The contract pinned here (the matching mobile/ change ships
as a patch for the Mac; this route does not publish mobile/):

- every display site formats via formatRefreshTimestamp (web), which
  renders MM/DD h:mm AM/PM TZ with the OS local zone abbreviation;
- server timestamps are naive UTC on the classic web endpoints
  (datetime.now()/utcnow().isoformat() with no "Z"), so the web helpers
  must normalize through parseServerDate before formatting;
- the admin pages must not call raw toLocaleTimeString() for their
  last-refresh stamps again.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_JS = (ROOT / "frontend" / "js" / "app.js").read_text()
V2_JS = (ROOT / "frontend" / "v2" / "js" / "v2-app.js").read_text()

ADMIN_PAGES = ["services.html", "settings.html", "system.html"]


def test_app_js_has_the_helpers():
    assert "function formatRefreshTimestamp" in APP_JS
    assert "function localTzAbbr" in APP_JS
    assert "function parseServerDate" in APP_JS
    assert "timeZoneName" in APP_JS  # zone abbreviation comes from Intl


def test_v2_app_js_has_the_helpers():
    assert "function formatRefreshTimestamp" in V2_JS
    assert "function localTzAbbr" in V2_JS
    assert "function parseServerDate" in V2_JS


def test_v2_hero_uses_the_helper_not_raw_time():
    assert "formatRefreshTimestamp(stamp)" in V2_JS
    assert "heroLastUpdated', `Last updated: ${new Date().toLocaleTimeString()}`" not in V2_JS


def test_admin_pages_use_the_shared_stamp():
    for page in ADMIN_PAGES:
        src = (ROOT / "frontend" / page).read_text()
        assert "formatRefreshTimestamp()" in src, page
        assert "getElementById('lastUpdate').textContent = new Date().toLocaleTimeString()" not in src, page


def test_classic_last_updated_parses_server_time_as_utc():
    # the dashboard header must not re-add the naive-UTC parsing bug
    assert "parseServerDate(data.last_updated)" in APP_JS


def test_central_time_zone_resolves_to_cdt_cst():
    # The user sits in US Central: a CT machine's zone abbreviation must be
    # CDT (summer) / CST (winter). The web helper renders whatever the OS
    # reports via Intl timeZoneName:short; this pins the zone data that
    # makes CT users see exactly that.
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("America/Chicago")
    summer = datetime(2026, 7, 15, 17, 32, tzinfo=tz)
    winter = datetime(2026, 1, 15, 17, 32, tzinfo=tz)
    assert summer.tzname() == "CDT"
    assert winter.tzname() == "CST"
