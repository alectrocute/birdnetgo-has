"""Data update coordinator for the BirdNET-Go integration."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BASE_URL,
    CONF_BIRDS_OF_INTEREST,
    CONF_COOLDOWN_MINUTES,
    CONF_FRONTEND_URL,
    CONF_NOTIFY_DETECTIONS,
    CONF_NOTIFY_FIRST_TIME,
    CONF_NOTIFY_RARE,
    CONF_NOTIFY_SERVICE,
    CONF_RARE_THRESHOLD_DAYS,
    CONF_SCAN_INTERVAL,
    DAILY_HISTORY_DAYS,
    DAILY_HISTORY_ENDPOINT,
    DAILY_SUMMARY_ENDPOINT,
    DEFAULT_COOLDOWN_MINUTES,
    DEFAULT_RARE_THRESHOLD_DAYS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIGRATION_ENDPOINT,
    NOTIFICATION_CHANNEL,
    NOTIFICATION_GROUP,
    NOTIFICATION_ICON,
    NOTIFICATION_TAG,
    NOTIFY_RESET_ACTION,
    REQUEST_TIMEOUT,
    SPECIES_SUMMARY_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class BirdNETGoData:
    """Data from the BirdNET-Go analytics API."""

    daily_species: list[dict[str, Any]] = field(default_factory=list)
    summary_species: list[dict[str, Any]] = field(default_factory=list)
    # Recent per-day detection counts, oldest first:
    # [{"date": "2026-09-01", "count": 123}, ...]
    daily_history: list[dict[str, Any]] = field(default_factory=list)
    # Migration insights; empty when the endpoint is unavailable (older
    # BirdNET-Go builds without the insights API).
    migration: dict[str, Any] = field(default_factory=dict)


def _parse_timestamp(raw: Any) -> datetime | None:
    """Parse a BirdNET-Go timestamp into a local datetime."""
    if not raw:
        return None
    parsed = dt_util.parse_datetime(str(raw))
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return dt_util.as_local(parsed)


def latest_species(species: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find the most recently heard species with a valid name and time."""
    latest: dict[str, Any] | None = None
    latest_time: datetime | None = None
    for bird in species:
        if not isinstance(bird, dict) or not bird.get("common_name"):
            continue
        parsed = _parse_timestamp(bird.get("last_heard"))
        if parsed is None:
            continue
        if latest_time is None or parsed > latest_time:
            latest, latest_time = bird, parsed
    return latest


class BirdNETGoCoordinator(DataUpdateCoordinator[BirdNETGoData]):
    """Coordinator that polls the BirdNET-Go analytics API.

    Also diffs consecutive species summaries to raise built-in
    notifications (new detection, first-time species, rare return)
    without requiring any user-created automations or helpers.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.base_url: str = str(entry.data[CONF_BASE_URL]).rstrip("/")
        # Optional browser-facing URL (e.g. https://birdnet.example.com) used
        # by dashboard cards for image lookups. Falls back to the base URL.
        self.frontend_url: str = (
            str(
                entry.options.get(
                    CONF_FRONTEND_URL, entry.data.get(CONF_FRONTEND_URL, "")
                )
            )
            .strip()
            .rstrip("/")
        )
        self.session = async_get_clientsession(hass)
        update_interval = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        # Notification settings
        self.notify_service: str = str(
            entry.options.get(CONF_NOTIFY_SERVICE, "")
        ).strip()
        self.notify_detections: bool = bool(
            entry.options.get(CONF_NOTIFY_DETECTIONS, False)
        )
        self.notify_first_time: bool = bool(
            entry.options.get(CONF_NOTIFY_FIRST_TIME, True)
        )
        self.notify_rare: bool = bool(entry.options.get(CONF_NOTIFY_RARE, True))
        self.cooldown: timedelta = timedelta(
            minutes=int(
                entry.options.get(CONF_COOLDOWN_MINUTES, DEFAULT_COOLDOWN_MINUTES)
            )
        )
        self.rare_threshold_days: int = int(
            entry.options.get(CONF_RARE_THRESHOLD_DAYS, DEFAULT_RARE_THRESHOLD_DAYS)
        )

        # Birds of interest (configured as comma/newline separated names)
        self.interest_names: frozenset[str] = frozenset(
            name.strip().lower()
            for name in str(
                entry.options.get(
                    CONF_BIRDS_OF_INTEREST,
                    entry.data.get(CONF_BIRDS_OF_INTEREST, ""),
                )
            )
            .replace(";", ",")
            .replace("\r", ",")
            .replace("\n", ",")
            .split(",")
            if name.strip()
        )

        self._previous_summary: list[dict[str, Any]] | None = None
        self._last_detection_notify: datetime | None = None
        # Species codes already alerted as rare today, so the server-driven
        # gap detection does not re-alert on every refresh.
        self._rare_notified: dict[str, datetime.date] = {}

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_update_data(self) -> BirdNETGoData:
        """Fetch data from the BirdNET-Go API and process notifications."""
        daily = await self._fetch(DAILY_SUMMARY_ENDPOINT)
        summary = await self._fetch(SPECIES_SUMMARY_ENDPOINT)
        history = await self._fetch_daily_history()
        migration = await self._fetch_migration()
        data = BirdNETGoData(
            daily_species=daily,
            summary_species=summary,
            daily_history=history,
            migration=migration,
        )
        self._process_notifications(summary, daily)
        return data

    async def _fetch(self, endpoint: str) -> list[dict[str, Any]]:
        """Fetch a JSON list from a BirdNET-Go API endpoint."""
        url = f"{self.base_url}{endpoint}"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self.session.get(url)
                response.raise_for_status()
                data: Any = await response.json()
        except TimeoutError as err:
            raise UpdateFailed(f"Timeout fetching {url}") from err
        except ClientError as err:
            raise UpdateFailed(f"Error fetching {url}: {err}") from err

        if not isinstance(data, list):
            raise UpdateFailed(f"Unexpected response from {url}, expected a list")
        return data

    async def _fetch_daily_history(self) -> list[dict[str, Any]]:
        """Fetch the per-day detection counts for the last month."""
        end = dt_util.now().date()
        start = end - timedelta(days=DAILY_HISTORY_DAYS - 1)
        url = (
            f"{self.base_url}{DAILY_HISTORY_ENDPOINT}"
            f"?start_date={start.isoformat()}&end_date={end.isoformat()}"
        )
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self.session.get(url)
                response.raise_for_status()
                payload: Any = await response.json()
        except (TimeoutError, ClientError) as err:
            _LOGGER.warning("Could not load detection history: %s", err)
            return []
        except ValueError as err:
            _LOGGER.warning("Detection history was not valid JSON: %s", err)
            return []

        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        return [
            row
            for row in rows
            if isinstance(row, dict)
            and isinstance(row.get("date"), str)
            and isinstance(row.get("count"), int)
        ]

    async def _fetch_migration(self) -> dict[str, Any]:
        """Fetch migration insights, tolerating their absence.

        The insights API only exists on BirdNET-Go builds with the enhanced
        (v2) database, so a 404 or any other failure simply leaves the data
        empty instead of failing the refresh.
        """
        url = f"{self.base_url}{MIGRATION_ENDPOINT}"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self.session.get(url)
                if response.status == 404:
                    return {}
                response.raise_for_status()
                payload: Any = await response.json()
        except (TimeoutError, ClientError, ValueError) as err:
            _LOGGER.debug("Migration insights unavailable: %s", err)
            return {}
        return payload if isinstance(payload, dict) else {}

    async def async_clear_cooldown(self) -> None:
        """Clear the notification cooldown (Reset action on notifications)."""
        self._last_detection_notify = None

    def _process_notifications(
        self,
        current: list[dict[str, Any]],
        daily: list[dict[str, Any]] | None = None,
    ) -> None:
        """Diff the current species summary against the previous one."""
        previous = self._previous_summary
        self._previous_summary = list(current)

        if not self.notify_service or not (
            self.notify_detections or self.notify_first_time or self.notify_rare
        ):
            return

        # First successful refresh is only a baseline so that a freshly
        # installed integration does not flood notifications.
        if previous is None:
            return

        previous_by_code = {
            bird.get("species_code"): bird
            for bird in previous
            if isinstance(bird, dict)
        }

        new_species: list[dict[str, Any]] = []
        rare_species: list[tuple[dict[str, Any], int, datetime | None]] = []
        diff_rare: list[tuple[dict[str, Any], int, datetime | None]] = []
        detections: list[dict[str, Any]] = []

        for bird in current:
            if not isinstance(bird, dict):
                continue
            name = bird.get("common_name")
            last_heard = _parse_timestamp(bird.get("last_heard"))
            if not name or last_heard is None:
                continue

            old = previous_by_code.get(bird.get("species_code"))
            if old is None or not old.get("last_heard"):
                # Not in the previous refresh: a brand new species, which is
                # its first ever detection in the lifetime summary.
                detections.append(bird)
                new_species.append(bird)
                continue

            old_last_heard = _parse_timestamp(old.get("last_heard"))
            if old_last_heard is None or last_heard <= old_last_heard:
                continue

            # The species was heard again since the previous refresh.
            detections.append(bird)
            gap_days = (last_heard - old_last_heard).days
            if gap_days > self.rare_threshold_days:
                diff_rare.append((bird, gap_days, old_last_heard))

        # Prefer the server-computed absence length from today's summary: it
        # counts the days since the previous detection, so returns that happen
        # while Home Assistant was offline or restarting are not missed. The
        # diff-based estimate above is only a fallback for older servers that
        # do not provide the field.
        today = dt_util.now().date()
        for bird in daily or []:
            if not isinstance(bird, dict):
                continue
            raw_gap = bird.get("days_since_last_seen")
            if raw_gap is None:
                continue
            gap_days = int(raw_gap)
            code = str(bird.get("species_code") or "")
            if gap_days <= self.rare_threshold_days:
                continue
            # Only alert once per species per day.
            if self._rare_notified.get(code) == today:
                continue
            self._rare_notified[code] = today
            rare_species.append((bird, gap_days, None))
        if not rare_species:
            rare_species = diff_rare

        if not self.notify_detections:
            detections = []
        if not self.notify_first_time:
            new_species = []
        if not self.notify_rare:
            rare_species = []

        if not (new_species or rare_species or detections):
            return

        cooldown_active = (
            self._last_detection_notify is not None
            and dt_util.now() - self._last_detection_notify < self.cooldown
        )
        if detections and not cooldown_active:
            self._last_detection_notify = dt_util.now()
            for bird in detections:
                self._schedule_notification(
                    title=f"🦜 {bird.get('common_name')}!",
                    message=(
                        f"{bird.get('common_name')} was just detected"
                        f" ({bird.get('count', 1)} total detections)."
                    ),
                )

        for bird in new_species:
            self._schedule_notification(
                title="🐦 New Bird Species Alert!",
                message=(
                    f"The {bird.get('common_name')} has been detected"
                    " for the first time!"
                ),
            )

        for bird, gap_days, previously_heard in rare_species:
            self._schedule_notification(
                title=f"🐦 {bird.get('common_name')} is back ({gap_days} days)!",
                message=(
                    f"{bird.get('common_name')} has been heard again!\n"
                    + (
                        f"Previously heard: {previously_heard.strftime('%b %d, %Y')}\n"
                        if previously_heard
                        else ""
                    )
                    + f"That's a gap of {gap_days} days!"
                ),
            )

    def _schedule_notification(self, title: str, message: str) -> None:
        """Send a notification through the configured notify service."""
        self.hass.async_create_task(self._async_send_notification(title, message))

    async def _async_send_notification(self, title: str, message: str) -> None:
        """Call the configured notify service."""
        domain, _, service = self.notify_service.partition(".")
        if not service:
            return
        await self.hass.services.async_call(
            domain,
            service,
            {
                "title": title,
                "message": message,
                "data": {
                    "notification_icon": NOTIFICATION_ICON,
                    "group": NOTIFICATION_GROUP,
                    "channel": NOTIFICATION_CHANNEL,
                    "tag": NOTIFICATION_TAG,
                    "ttl": 0,
                    "priority": "high",
                    "push": {"interruption-level": "time-sensitive"},
                    "actions": [
                        {"action": NOTIFY_RESET_ACTION, "title": "Reset"},
                    ],
                },
            },
            blocking=False,
        )
