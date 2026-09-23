"""The BirdNET-Go integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback

from . import dashboard as birdnet_dashboard
from .const import (
    DOMAIN,
    NOTIFY_RESET_ACTION,
    PLATFORMS,
)
from .coordinator import BirdNETGoCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BirdNET-Go from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    coordinator = BirdNETGoCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    @callback
    def handle_cooldown_reset(event: Event) -> None:
        """Clear the notification cooldown from a notification action."""
        if event.data.get("action") == NOTIFY_RESET_ACTION:
            hass.async_create_task(coordinator.async_clear_cooldown())

    entry.async_on_unload(
        hass.bus.async_listen("mobile_app_notification_action", handle_cooldown_reset)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Create the dashboard after the sensor platform has registered its
    # entities so the cards can reference their real entity ids.
    try:
        await birdnet_dashboard.async_setup_dashboard(
            hass,
            entry.entry_id,
            coordinator.frontend_url or coordinator.base_url,
        )
    except Exception:
        _LOGGER.warning("Failed to set up the BirdNET-Go dashboard", exc_info=True)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the dashboard when the last config entry is removed."""
    if hass.config_entries.async_entries(DOMAIN):
        return
    await birdnet_dashboard.async_delete_dashboard(hass)
