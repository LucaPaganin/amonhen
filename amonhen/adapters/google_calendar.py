"""Google Calendar behind `ports.calendar`, read with a service account.

A service account's key does not expire the way a user's OAuth consent does, and
the calendar is shared with its address in read-only: nothing to renew, and
nothing this process could write. The token request is signed here with PyJWT,
which the Enable Banking client already needs, so no Google library comes in.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path
from urllib.parse import quote

import jwt
import requests

from amonhen.ports.calendar import (
    CalendarChanges,
    CalendarError,
    CalendarEvent,
    CalendarWindow,
    SyncTokenExpired,
)

log = logging.getLogger(__name__)

SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{calendar}/events"
TIMEOUT_SECONDS = 30
TOKEN_LIFETIME_SECONDS = 3600
# Every page of one listing carries the same parameters: the sync token is
# bound to the request that produced it, and Google refuses a mismatch.
LIST_PARAMS = {"singleEvents": "true", "maxResults": "2500"}


class GoogleCalendar:
    def __init__(self, key_file: str | Path, session: requests.Session | None = None) -> None:
        try:
            key = json.loads(Path(key_file).read_text(encoding="utf-8"))
            self._email = key["client_email"]
            self._private_key = key["private_key"]
            self._token_uri = key["token_uri"]
        except (OSError, ValueError, KeyError) as exc:
            raise ValueError(f"the service account key {key_file} is not usable: {exc}") from exc
        self._http = session or requests.Session()
        self._access_token: str | None = None
        self._expires_at = 0.0

    def changes(self, calendar_id: str, sync_token: str | None, window: CalendarWindow) -> CalendarChanges:
        """The events of ``window``, or those changed since ``sync_token``.

        The bounds are always sent: without them Google answers within its own
        undocumented range, and whether a session exists would depend on a
        default nobody can read.
        """
        params = dict(LIST_PARAMS)
        params["timeMin"] = _instant(window.start, end_of_day=False)
        params["timeMax"] = _instant(window.end, end_of_day=True)
        if sync_token:
            params["syncToken"] = sync_token
        url = EVENTS_URL.format(calendar=quote(calendar_id, safe=""))
        events: list[CalendarEvent] = []
        while True:
            page = self._get(url, params)
            events.extend(_event(item) for item in page.get("items", []))
            if "nextPageToken" not in page:
                break
            params["pageToken"] = page["nextPageToken"]
        if "nextSyncToken" not in page:
            raise CalendarError(f"calendar {calendar_id}: the last page carried no sync token")
        return CalendarChanges(events, page["nextSyncToken"])

    def _get(self, url: str, params: dict) -> dict:
        try:
            response = self._http.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {self._token()}"},
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise CalendarError(f"Google Calendar did not answer: {exc}") from exc
        if response.status_code == 410:
            raise SyncTokenExpired("the sync token expired")
        if response.status_code != 200:
            raise CalendarError(f"Google Calendar answered {response.status_code}: {response.text[:300]}")
        return response.json()

    def _token(self) -> str:
        """An access token, asked again a minute before the last one ends."""
        now = time.time()
        if self._access_token and now < self._expires_at - 60:
            return self._access_token
        assertion = jwt.encode(
            {
                "iss": self._email,
                "scope": SCOPE,
                "aud": self._token_uri,
                "iat": int(now),
                "exp": int(now) + TOKEN_LIFETIME_SECONDS,
            },
            self._private_key,
            algorithm="RS256",
        )
        try:
            response = self._http.post(
                self._token_uri,
                data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise CalendarError(f"Google did not answer the token request: {exc}") from exc
        if response.status_code != 200:
            raise CalendarError(f"Google refused the token ({response.status_code}): {response.text[:300]}")
        body = response.json()
        self._access_token = body["access_token"]
        self._expires_at = now + int(body.get("expires_in", TOKEN_LIFETIME_SECONDS))
        log.info("Google Calendar token obtained for %s", self._email)
        return self._access_token


def _event(item: dict) -> CalendarEvent:
    start = item.get("start", {})
    return CalendarEvent(
        event_id=item["id"],
        summary=item.get("summary", ""),
        start=start.get("dateTime") or start.get("date") or "",
        cancelled=item.get("status") == "cancelled",
    )


def _instant(day: dt.date, *, end_of_day: bool) -> str:
    """The day as the RFC3339 instant Google wants, in this machine's timezone."""
    moment = dt.datetime.combine(day, dt.time.max if end_of_day else dt.time.min)
    return moment.astimezone().isoformat(timespec="seconds")
