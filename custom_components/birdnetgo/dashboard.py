"""Auto-created Lovelace dashboard for BirdNET-Go.

Creates a "Birds" dashboard in the sidebar with formatted cards so users
never have to copy and paste YAML. The dashboard is a regular storage
dashboard, so users can freely customize it afterwards.

Two layouts are bundled side by side in the ``dashboards`` folder: a
polished one built on the community button-card plugin and a vanilla one
using only core cards. When button-card is installed, the polished layout
wins. Each layout lives in its own human-readable YAML file with
``__PLACEHOLDER__`` tokens that are filled in at creation time.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from pathlib import Path
from typing import Any

import yaml
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import storage

from .const import (
    DASHBOARD_ICON,
    DASHBOARD_ID,
    DASHBOARD_TITLE,
    DASHBOARD_URL_PATH,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_STORAGE_KEY = "lovelace.birdnetgo"
CONFIG_STORAGE_VERSION = 1

DASHBOARDS_DIR = Path(__file__).parent / "dashboards"
DEFAULT_LAYOUT = "default"
BUTTON_CARD_LAYOUT = "button-card"


def _render(layout: Any, replacements: dict[str, str]) -> Any:
    """Recursively fill in entity and URL placeholders in a layout."""
    if isinstance(layout, str):
        for placeholder, value in replacements.items():
            layout = layout.replace(placeholder, value)
        return layout
    if isinstance(layout, dict):
        return {key: _render(item, replacements) for key, item in layout.items()}
    if isinstance(layout, list):
        return [_render(item, replacements) for item in layout]
    return layout


def _load_layout(name: str) -> dict[str, Any]:
    """Return a bundled dashboard layout, placeholders included."""
    return yaml.safe_load((DASHBOARDS_DIR / f"{name}.yaml").read_text(encoding="utf-8"))


def _replacements(
    hass: HomeAssistant,
    entry_id: str,
    base_url: str,
) -> dict[str, str]:
    """Map layout placeholders to the entry's real entity ids and URL."""
    registry = er.async_get(hass)

    def entity_id(domain: str, suffix: str, fallback: str) -> str:
        found = registry.async_get_entity_id(domain, DOMAIN, f"{entry_id}_{suffix}")
        return found or fallback

    return {
        "__DAILY__": entity_id(
            "sensor", "daily_summary", "sensor.birdnet_daily_summary"
        ),
        "__SPECIES__": entity_id(
            "sensor", "species_summary", "sensor.birdnet_species_summary"
        ),
        "__INTEREST__": entity_id(
            "sensor", "birds_of_interest", "sensor.birdnet_birds_of_interest"
        ),
        "__LATEST_BIRD__": entity_id(
            "sensor", "latest_bird", "sensor.birdnet_latest_bird"
        ),
        "__DETECTIONS__": entity_id(
            "sensor", "detections_today", "sensor.birdnet_detections_today"
        ),
        "__LIFETIME__": entity_id(
            "sensor", "lifetime_species", "sensor.birdnet_lifetime_species"
        ),
        "__CAMERA__": entity_id(
            "camera", "latest_bird_image", "camera.birdnet_latest_bird_image"
        ),
        "__FOY__": entity_id("sensor", "first_of_year", "sensor.birdnet_first_of_year"),
        "__HISTORY__": entity_id(
            "sensor", "detections_history", "sensor.birdnet_detection_history"
        ),
        "__MIGRATION__": entity_id("sensor", "migration", "sensor.birdnet_migration"),
        "__FIRST_BIRD__": entity_id(
            "sensor", "first_bird_today", "sensor.birdnet_first_bird_today"
        ),
        "__BASE_URL__": base_url,
    }


async def _has_button_card(hass: HomeAssistant) -> bool:
    """Return whether the button-card Lovelace plugin is installed."""
    lovelace = _lovelace_data(hass)
    resources = getattr(lovelace, "resources", None) if lovelace is not None else None
    if resources is not None:
        items: list[Any] = []
        with suppress(Exception):
            await resources.async_load()
            items = resources.async_items() or []
        if any(
            isinstance(item, dict) and "button-card" in str(item.get("url", ""))
            for item in items
        ):
            return True
    # YAML-mode lovelace users can serve the plugin from <config>/www too.
    return Path(hass.config.path("www", "button-card.js")).is_file()


async def _dashboard_config(
    hass: HomeAssistant,
    entry_id: str,
    base_url: str,
) -> dict[str, Any]:
    """Build a rendered dashboard config from the best bundled layout."""
    layout = BUTTON_CARD_LAYOUT if await _has_button_card(hass) else DEFAULT_LAYOUT
    _LOGGER.info("Using the %s dashboard layout", layout)
    return _render(_load_layout(layout), _replacements(hass, entry_id, base_url))


def _lovelace_data(hass: HomeAssistant) -> Any | None:
    """Return the lovelace component data, if lovelace is loaded."""
    return hass.data.get("lovelace")


def _is_ours(dashboard: Any) -> bool:
    """Return whether a dashboard entry was created by this integration."""
    config = getattr(dashboard, "config", None)
    return isinstance(config, dict) and config.get("id") == DASHBOARD_ID


def _register_panel(hass: HomeAssistant) -> None:
    """Register the dashboard in the sidebar."""
    from homeassistant.components import frontend
    from homeassistant.components.lovelace.const import MODE_STORAGE

    frontend.async_register_built_in_panel(
        hass,
        "lovelace",
        sidebar_title=DASHBOARD_TITLE,
        sidebar_icon=DASHBOARD_ICON,
        frontend_url_path=DASHBOARD_URL_PATH,
        require_admin=False,
        show_in_sidebar=True,
        config={"mode": MODE_STORAGE},
        update=True,
    )


async def async_setup_dashboard(
    hass: HomeAssistant,
    entry_id: str,
    base_url: str,
) -> None:
    """Create or refresh the BirdNET-Go dashboard."""
    from homeassistant.components.lovelace.const import (
        CONF_ICON,
        CONF_MODE,
        CONF_REQUIRE_ADMIN,
        CONF_SHOW_IN_SIDEBAR,
        CONF_TITLE,
        CONF_URL_PATH,
        MODE_STORAGE,
        ConfigNotFound,
    )
    from homeassistant.components.lovelace.dashboard import LovelaceStorage

    lovelace = _lovelace_data(hass)
    if lovelace is None:
        _LOGGER.info("Lovelace is not loaded; the BirdNET-Go dashboard was not created")
        return

    dashboards = lovelace.dashboards
    existing = dashboards.get(DASHBOARD_URL_PATH)
    if existing is not None:
        if _is_ours(existing):
            _register_panel(hass)
            return
        _LOGGER.info(
            "A dashboard already exists at /%s; the BirdNET-Go dashboard was"
            " not created",
            DASHBOARD_URL_PATH,
        )
        return

    store = LovelaceStorage(
        hass,
        {
            "id": DASHBOARD_ID,
            CONF_URL_PATH: DASHBOARD_URL_PATH,
            CONF_TITLE: DASHBOARD_TITLE,
            CONF_ICON: DASHBOARD_ICON,
            CONF_MODE: MODE_STORAGE,
            CONF_REQUIRE_ADMIN: False,
            CONF_SHOW_IN_SIDEBAR: True,
        },
    )
    try:
        await store.async_load(False)
    except ConfigNotFound:
        await store.async_save(await _dashboard_config(hass, entry_id, base_url))

    dashboards[DASHBOARD_URL_PATH] = store
    _register_panel(hass)
    _LOGGER.info("Created the BirdNET-Go dashboard at /%s", DASHBOARD_URL_PATH)


async def async_reset_dashboard(
    hass: HomeAssistant,
    entry_id: str,
    base_url: str,
) -> bool:
    """Reset the BirdNET-Go dashboard to its default layout."""
    from homeassistant.components.lovelace.dashboard import LovelaceStorage

    lovelace = _lovelace_data(hass)
    if lovelace is None:
        return False

    store = lovelace.dashboards.get(DASHBOARD_URL_PATH)
    if not isinstance(store, LovelaceStorage) or not _is_ours(store):
        return False

    await store.async_save(await _dashboard_config(hass, entry_id, base_url))
    return True


async def async_delete_dashboard(hass: HomeAssistant) -> None:
    """Remove the BirdNET-Go dashboard panel and its stored config."""
    from homeassistant.components import frontend
    from homeassistant.components.lovelace.dashboard import LovelaceStorage

    frontend.async_remove_panel(hass, DASHBOARD_URL_PATH, warn_if_unknown=False)

    lovelace = _lovelace_data(hass)
    if lovelace is not None:
        store = lovelace.dashboards.pop(DASHBOARD_URL_PATH, None)
        if isinstance(store, LovelaceStorage) and _is_ours(store):
            with suppress(HomeAssistantError):
                await store.async_delete()
            return

    await storage.Store(hass, CONFIG_STORAGE_VERSION, CONFIG_STORAGE_KEY).async_remove()
