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
        return (
            {
                key: bird[key]
                for key in ("last_heard", "species_code", "scientific_name", "count")
                if key in bird
            }
            if bird
            else {}
        )


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
