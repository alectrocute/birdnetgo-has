"""Sensors for the BirdNET-Go integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_BASE_URL,
    ATTR_DAILY_COUNTS,
    ATTR_FRONTEND_URL,
    ATTR_SPECIES_LIST,
    DEFAULT_NAME,
    DOMAIN,
)
from .coordinator import BirdNETGoCoordinator, latest_species


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BirdNET-Go sensors from a config entry."""
    coordinator: BirdNETGoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            BirdNETGoDailySummarySensor(coordinator, entry),
            BirdNETGoSpeciesSummarySensor(coordinator, entry),
            BirdNETGoBirdsOfInterestSensor(coordinator, entry),
            BirdNETGoDetectionsTodaySensor(coordinator, entry),
            BirdNETGoLifetimeSpeciesSensor(coordinator, entry),
            BirdNETGoLatestBirdSensor(coordinator, entry),
            BirdNETGoLatestInterestSensor(coordinator, entry),
            BirdNETGoFirstOfYearSensor(coordinator, entry),
            BirdNETGoFirstBirdTodaySensor(coordinator, entry),
            BirdNETGoDetectionsHistorySensor(coordinator, entry),
            BirdNETGoMigrationSensor(coordinator, entry),
        ]
    )


class BirdNETGoEntity(CoordinatorEntity[BirdNETGoCoordinator], SensorEntity):
    """Base BirdNET-Go sensor."""

    _attr_has_entity_name = False
    _attr_icon = "mdi:bird"
    _id_suffix = "entity"

    def __init__(self, coordinator: BirdNETGoCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{self._id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=DEFAULT_NAME,
            manufacturer="BirdNET-Go",
            model="BirdNET-Go stats",
            configuration_url=coordinator.base_url,
        )

    @property
    def suggested_object_id(self) -> str:
        """Use a predictable entity id for the default dashboard."""
        return f"birdnet_{self._id_suffix}"

    def _species_list(self, key: str) -> list[dict[str, Any]]:
        """Return the species list from the coordinator data."""
        if self.coordinator.data is None:
            return []
        return getattr(self.coordinator.data, key) or []

    def _url_attributes(self) -> dict[str, str]:
        """Return the BirdNET-Go URLs for use by dashboard cards."""
        return {
            ATTR_BASE_URL: self.coordinator.base_url,
            ATTR_FRONTEND_URL: self.coordinator.frontend_url,
        }

    def _max_last_heard(self, species: list[dict[str, Any]]) -> datetime | None:
        """Return the most recent last_heard datetime from a species list."""
        timestamps: list[datetime] = []
        for bird in species:
            raw = bird.get("last_heard") if isinstance(bird, dict) else None
            if not raw:
                continue
            parsed = dt_util.parse_datetime(str(raw))
            if parsed is None:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            timestamps.append(dt_util.as_local(parsed))
        return max(timestamps) if timestamps else None

    def _latest_species(self, species: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Find the most recently heard species with a valid name and time."""
        return latest_species(species)


class BirdNETGoDailySummarySensor(BirdNETGoEntity):
    """Live sensor with today's species summary from BirdNET-Go."""

    _attr_name = "Species today"
    _attr_icon = "mdi:calendar-today"
    _id_suffix = "daily_summary"
    _attr_native_unit_of_measurement = "species"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int:
        """Return the number of unique species detected today."""
        return len(self._species_list("daily_species"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the full species list as an attribute."""
        attrs = {ATTR_SPECIES_LIST: self._species_list("daily_species")}
        attrs.update(self._url_attributes())
        return attrs


class BirdNETGoSpeciesSummarySensor(BirdNETGoEntity):
    """Live sensor with the overall species summary from BirdNET-Go."""

    _attr_name = "Last detection"
    _attr_icon = "mdi:clock-outline"
    _id_suffix = "species_summary"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        """Return the most recent detection time across all species."""
        return self._max_last_heard(self._species_list("summary_species"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the full species list as an attribute."""
        attrs = {ATTR_SPECIES_LIST: self._species_list("summary_species")}
        attrs.update(self._url_attributes())
        return attrs


class BirdNETGoBirdsOfInterestSensor(BirdNETGoEntity):
    """Sensor tracking the species configured as birds of interest.

    The list is managed via the integration's Configure dialog instead of
    editing dashboard YAML.
    """

    _attr_name = "Birds of interest"
    _attr_icon = "mdi:heart-outline"
    _id_suffix = "birds_of_interest"
    _attr_native_unit_of_measurement = "species"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def _filtered_species(self) -> list[dict[str, Any]]:
        """Return summary species matching the configured interest list."""
        if not self.coordinator.interest_names:
            return []
        return [
            bird
            for bird in self._species_list("summary_species")
            if isinstance(bird, dict)
            and str(bird.get("common_name", "")).lower()
            in self.coordinator.interest_names
        ]

    @property
    def native_value(self) -> int:
        """Return the number of birds of interest ever detected."""
        return len(self._filtered_species())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the filtered species list as an attribute."""
        attrs = {ATTR_SPECIES_LIST: self._filtered_species()}
        attrs.update(self._url_attributes())
        return attrs


class BirdNETGoDetectionsTodaySensor(BirdNETGoEntity):
    """Today's detection count, without the large dashboard attributes."""

    _attr_name = "Detections today"
    _attr_icon = "mdi:counter"
    _id_suffix = "detections_today"
    _attr_native_unit_of_measurement = "detections"
    # total_increasing is the correct class for a counter that resets at
    # midnight.
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> int:
        """Sum the daily counts across species."""
        return sum(
            int(bird["count"])
            for bird in self._species_list("daily_species")
            if isinstance(bird, dict)
            and isinstance(bird.get("count"), (int, float))
            and not isinstance(bird["count"], bool)
        )


class BirdNETGoLifetimeSpeciesSensor(BirdNETGoEntity):
    """Number of species ever heard."""

    _attr_name = "Species all time"
    _attr_icon = "mdi:bird"
    _id_suffix = "lifetime_species"
    _attr_native_unit_of_measurement = "species"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int:
        """Count species in the lifetime summary."""
        return len(self._species_list("summary_species"))


class BirdNETGoLatestBirdSensor(BirdNETGoEntity):
    """Most recently heard bird as a readable HA state."""

    _attr_name = "Latest bird"
    _attr_icon = "mdi:bird"
    _id_suffix = "latest_bird"

    @property
    def native_value(self) -> str | None:
        """Return the bird's common name."""
        bird = self._latest_species(self._species_list("summary_species"))
        return str(bird["common_name"]) if bird else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose only the useful details of the latest species."""
        bird = self._latest_species(self._species_list("summary_species"))
        if not bird:
            return {}
        attrs = {
            key: bird[key]
            for key in ("last_heard", "species_code", "scientific_name", "count")
            if key in bird
        }
        # Detection confidence, when the server provides it, so a confident
        # ID can be told apart from a doubtful one.
        for key in ("avg_confidence", "max_confidence"):
            value = bird.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                attrs[key] = round(float(value), 4)
        return attrs


class BirdNETGoLatestInterestSensor(BirdNETGoBirdsOfInterestSensor):
    """Most recently heard configured bird of interest."""

    _attr_name = "Latest bird of interest"
    _attr_icon = "mdi:heart-outline"
    _id_suffix = "latest_interest"
    _attr_native_unit_of_measurement = None
    _attr_state_class = None

    @property
    def native_value(self) -> str | None:
        """Return the most recently heard favorite's common name."""
        bird = self._latest_species(self._filtered_species())
        return str(bird["common_name"]) if bird else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the matching bird's time and species code, not the full list."""
        bird = self._latest_species(self._filtered_species())
        return (
            {key: bird[key] for key in ("last_heard", "species_code") if key in bird}
            if bird
            else {}
        )


class BirdNETGoFirstOfYearSensor(BirdNETGoEntity):
    """Most recently heard species that is new this year.

    Year lists are a birder tradition, so the first detection of a species
    in the calendar year is worth its own sensor and image.
    """

    _attr_name = "Latest first-of-year bird"
    _attr_icon = "mdi:calendar-star"
    _id_suffix = "first_of_year"

    def _new_this_year(self) -> list[dict[str, Any]]:
        """Return today's species flagged as new for the year."""
        return [
            bird
            for bird in self._species_list("daily_species")
            if isinstance(bird, dict) and bird.get("is_new_this_year")
        ]

    @property
    def native_value(self) -> str | None:
        """Return the newest first-of-year species' common name."""
        bird = self._latest_species(self._new_this_year())
        return str(bird["common_name"]) if bird else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose when the species was first heard this year."""
        bird = self._latest_species(self._new_this_year())
        return (
            {key: bird[key] for key in ("first_heard", "species_code") if key in bird}
            if bird
            else {}
        )


class BirdNETGoFirstBirdTodaySensor(BirdNETGoEntity):
    """Species that started the day, i.e. the earliest first_heard today."""

    _attr_name = "First bird today"
    _attr_icon = "mdi:weather-sunset-up"
    _id_suffix = "first_bird_today"

    @property
    def native_value(self) -> str | None:
        """Return the common name of the first species heard today."""
        bird = self._first_bird()
        return str(bird["common_name"]) if bird else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the first-heard time of the day's earliest species."""
        bird = self._first_bird()
        return (
            {key: bird[key] for key in ("first_heard", "species_code") if key in bird}
            if bird
            else {}
        )

    def _first_bird(self) -> dict[str, Any] | None:
        """Find the species with the earliest first_heard timestamp today."""
        first: dict[str, Any] | None = None
        first_time: datetime | None = None
        for bird in self._species_list("daily_species"):
            if not isinstance(bird, dict) or not bird.get("common_name"):
                continue
            parsed = dt_util.parse_datetime(str(bird.get("first_heard") or ""))
            if parsed is None:
                continue
            if first_time is None or parsed < first_time:
                first, first_time = bird, parsed
        return first


class BirdNETGoDetectionsHistorySensor(BirdNETGoEntity):
    """Daily detection counts for the last month, from BirdNET-Go's own history.

    Unlike Home Assistant statistics this works immediately on a fresh
    install, because BirdNET-Go already has the data.
    """

    _attr_name = "Detection history"
    _attr_icon = "mdi:chart-bar"
    _id_suffix = "detections_history"
    _attr_native_unit_of_measurement = "detections"
    _attr_state_class = None

    @property
    def native_value(self) -> int:
        """Return yesterday's detection count (today is still counting)."""
        history = self._history()
        if len(history) < 2:
            return 0
        return int(history[-2]["count"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the per-day counts and a compact text sparkline."""
        history = self._history()
        attrs: dict[str, Any] = {
            ATTR_DAILY_COUNTS: {row["date"]: row["count"] for row in history}
        }
        if history:
            attrs["sparkline"] = _sparkline([int(row["count"]) for row in history])
        return attrs

    def _history(self) -> list[dict[str, Any]]:
        """Return the per-day counts sorted oldest first."""
        rows = getattr(self.coordinator.data, "daily_history", []) or []
        return sorted(rows, key=lambda row: row["date"])


def _sparkline(counts: list[int]) -> str:
    """Render daily counts as a compact bar of unicode block characters."""
    if not counts:
        return ""
    blocks = "▁▂▃▄▅▆▇█"
    peak = max(counts)
    if peak <= 0:
        return blocks[0] * len(counts)
    return "".join(
        blocks[min(int(count * len(blocks) / peak), len(blocks) - 1)]
        for count in counts
    )


class BirdNETGoMigrationSensor(BirdNETGoEntity):
    """Migration activity: species that just arrived or went quiet.

    Requires a BirdNET-Go build with the insights API (enhanced database);
    the sensor reports unavailable otherwise.
    """

    _attr_name = "Migration activity"
    _attr_icon = "mdi:airplane"
    _id_suffix = "migration"

    @property
    def available(self) -> bool:
        """Be unavailable when the insights endpoint is not supported."""
        return bool(self._migration())

    def _migration(self) -> dict[str, Any]:
        """Return the migration payload from the coordinator."""
        if self.coordinator.data is None:
            return {}
        return getattr(self.coordinator.data, "migration", {}) or {}

    @property
    def native_value(self) -> int | None:
        """Return the number of new arrivals over the recent window."""
        arrivals = self._migration().get("new_arrivals")
        return len(arrivals) if isinstance(arrivals, list) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the arrival and departure lists."""
        migration = self._migration()
        attrs: dict[str, Any] = {}
        arrivals = migration.get("new_arrivals")
        quiet = migration.get("gone_quiet")
        if isinstance(arrivals, list):
            attrs["new_arrivals"] = [
                bird.get("common_name")
                for bird in arrivals
                if isinstance(bird, dict)
            ]
        if isinstance(quiet, list):
            attrs["gone_quiet"] = [
                {
                    "common_name": bird.get("common_name"),
                    "days_since": bird.get("days_since"),
                }
                for bird in quiet
                if isinstance(bird, dict)
            ]
        if isinstance(migration.get("recent_days"), int):
            attrs["recent_days"] = migration["recent_days"]
        return attrs
