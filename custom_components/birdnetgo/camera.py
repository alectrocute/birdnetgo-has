"""Cameras showing BirdNET-Go species images."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import quote

from aiohttp import ClientError
from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_NAME,
    DOMAIN,
    MEDIA_IMAGE_ENDPOINT,
)
from .coordinator import BirdNETGoCoordinator, latest_species

_LOGGER = logging.getLogger(__name__)

FETCH_TIMEOUT = 10
COLD_CACHE_RETRIES = 4
COLD_CACHE_BACKOFF = 3


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the BirdNET-Go cameras from a config entry."""
    coordinator: BirdNETGoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BirdNETGoLatestBirdCamera(coordinator, entry)])

    # Remove the old camera from the entity registry as well as the dashboard.
    registry = er.async_get(hass)
    old_image = registry.async_get_entity_id(
        "camera", DOMAIN, f"{entry.entry_id}_first_of_year_image"
    )
    if old_image:
        registry.async_remove(old_image)


class BirdNETGoSpeciesCamera(CoordinatorEntity[BirdNETGoCoordinator], Camera):
    """Still image of a species, served by BirdNET-Go."""

    _attr_has_entity_name = False
    _attr_icon = "mdi:bird"

    _id_suffix = "camera"

    def __init__(self, coordinator: BirdNETGoCoordinator, entry: ConfigEntry) -> None:
        """Initialize the camera."""
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{self._id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=DEFAULT_NAME,
            manufacturer="BirdNET-Go",
            model="BirdNET-Go stats",
            configuration_url=coordinator.base_url,
        )
        self._cached_image: tuple[str, bytes] | None = None
        self._warned_species: set[str] = set()

    @property
    def suggested_object_id(self) -> str:
        """Use a predictable entity id for the default dashboard."""
        return f"birdnet_{self._id_suffix}"

    def _species(self) -> dict[str, Any] | None:
        """Return the species this camera should show."""
        raise NotImplementedError

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return the species image from BirdNET-Go."""
        if self.coordinator.data is None:
            return None
        bird = self._species()
        scientific_name = str((bird or {}).get("scientific_name") or "").strip()
        if not scientific_name:
            return None

        if self._cached_image and self._cached_image[0] == scientific_name:
            return self._cached_image[1]

        # base_url is guaranteed reachable from HA (the coordinator polls it);
        # frontend_url may only be reachable from browsers, so it is the
        # fallback rather than the primary.
        urls = [
            f"{base}{MEDIA_IMAGE_ENDPOINT}{quote(scientific_name)}"
            for base in dict.fromkeys(
                (self.coordinator.base_url, self.coordinator.frontend_url)
            )
            if base
        ]
        session = async_get_clientsession(self.hass)
        for url in urls:
            image = await self._async_fetch_image(session, url, scientific_name)
            if image is not None:
                self._cached_image = (scientific_name, image)
                self._warned_species.discard(scientific_name)
                return image
        return None

    async def _async_fetch_image(
        self, session, url: str, scientific_name: str
    ) -> bytes | None:
        """Fetch one image URL, retrying while BirdNET-Go caches a cold species."""
        for attempt in range(COLD_CACHE_RETRIES):
            try:
                async with asyncio.timeout(FETCH_TIMEOUT):
                    response = await session.get(url)
            except (TimeoutError, ClientError) as err:
                self._log_failure(scientific_name, f"request to {url} failed: {err}")
                return None

            if response.status == 200:
                image = await response.read()
                content_type = response.headers.get("Content-Type", "").split(";")[0]
                if content_type.startswith("image/"):
                    self.content_type = content_type
                return image

            await response.read()

            if response.status == 503 and attempt < COLD_CACHE_RETRIES - 1:
                # BirdNET-Go downloads cold species images in the background
                # and answers 503 until the first fetch finishes.
                await asyncio.sleep(COLD_CACHE_BACKOFF)
                continue

            self._log_failure(
                scientific_name, f"unexpected status {response.status} from {url}"
            )
            return None
        return None

    def _log_failure(self, scientific_name: str, detail: str) -> None:
        """Log image fetch failures without spamming the log."""
        if scientific_name in self._warned_species:
            _LOGGER.debug(
                "Could not load the image for %s: %s", scientific_name, detail
            )
            return
        _LOGGER.warning("Could not load the image for %s: %s", scientific_name, detail)
        self._warned_species.add(scientific_name)


class BirdNETGoLatestBirdCamera(BirdNETGoSpeciesCamera):
    """Still image of the most recently heard species."""

    _attr_name = "Latest bird image"
    _id_suffix = "latest_bird_image"

    def _species(self) -> dict[str, Any] | None:
        """Return the most recently heard species."""
        return latest_species(self.coordinator.data.summary_species)
