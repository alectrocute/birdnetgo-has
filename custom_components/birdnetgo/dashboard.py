"""Auto-created Lovelace dashboard for BirdNET-Go.

Creates a "Birds" dashboard in the sidebar with formatted cards so users
never have to copy and paste YAML. The dashboard is a regular storage
dashboard, so users can freely customize it afterwards.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any

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
    FIRST_OF_YEAR_EMPTY_STATE,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_STORAGE_KEY = "lovelace.birdnetgo"
CONFIG_STORAGE_VERSION = 1

DAILY_TEMPLATE = """{% if has_value('__DAILY__') -%}
{% set species_data = state_attr('__DAILY__', 'species_list') or [] -%}
{% if species_data | count > 0 -%}
| Last heard | Species | Count | Activity (6AM–6PM) |
| :-- | :-- | --: | :--: |
{% for bird in species_data | sort(attribute='count', reverse=true) -%}
{% set time = bird.get('latest_heard', '00:00:00') -%}
{% set name = bird.get('common_name', 'Unknown') -%}
{% set count = bird.get('count', 0) -%}
{% set species_code = bird.get('species_code', '') -%}
{% set ebird_url = 'https://ebird.org/species/' ~ species_code -%}
{% set hourly = bird.get('hourly_counts', []) -%}
{% set sparkline_str = '—' -%}
{% if hourly is iterable and hourly | count == 24 -%}
{% set early_sum = hourly[0:6] | sum -%}
{% set middle_part = hourly[6:18] -%}
{% set late_sum = hourly[18:24] | sum -%}
{% set aggregated_counts = [early_sum] + middle_part + [late_sum] -%}
{% if aggregated_counts | count == 14 -%}
{% set max_val = aggregated_counts | max -%}
{% set spark_chars = ['▁', '▂', '▃', '▄', '▅', '▆', '▇'] -%}
{% set sparkline = namespace(text='') -%}
{% for value in aggregated_counts -%}
{% set char_index = ([0, (value * 7 / max_val) | int, 6] | sort)[1] if max_val > 0 else 0 -%}
{% set sparkline.text = sparkline.text ~ spark_chars[char_index] -%}
{% endfor -%}
{% set sparkline_str = sparkline.text -%}
{% endif -%}
{% endif -%}
{{ today_at(time) | as_timestamp | timestamp_custom('%H:%M', true) }} | {% if species_code | length >= 1 and species_code | length <= 7 %}[{{ name }}]({{ ebird_url }}){% else %}{{ name }}{% endif %} | {{ count }} | {{ sparkline_str }}
{% endfor %}

**{{ species_data | sum(attribute='count') | int }} detections** · {{ species_data | count }} species
{% else -%}
No species detected yet today.
{% endif -%}
{% else -%}
Waiting for BirdNET-Go…
{% endif %}"""

LATEST_TEMPLATE = """{% if has_value('__SPECIES__') -%}
{% set species_data = state_attr('__SPECIES__', 'species_list') or [] -%}
{% if species_data | count > 0 -%}
| Species | Last heard |
| :-- | --: |
{% for bird in (species_data | sort(attribute='last_heard', reverse=true))[0:11] -%}
{% set time = bird.get('last_heard', '1970-01-01 00:00:00') -%}
{% set name = bird.get('common_name', 'Unknown') -%}
{% set species_code = bird.get('species_code', '') -%}
{% set ebird_url = 'https://ebird.org/species/' ~ species_code -%}
{% set last_heard_datetime = as_datetime(time) -%}
{% if species_code | length >= 1 and species_code | length <= 7 %}[{{ name }}]({{ ebird_url }}){% else %}{{ name }}{% endif %} | {{ relative_time(last_heard_datetime) }} ago
{% endfor -%}
{% else -%}
No recent bird data available.
{% endif -%}
{% else -%}
Waiting for BirdNET-Go…
{% endif %}"""

BRAND_NEW_TEMPLATE = """{% if has_value('__SPECIES__') -%}
{% set species_data = state_attr('__SPECIES__', 'species_list') or [] -%}
{% if species_data | count > 0 -%}
| Species | Count | First heard |
| :-- | --: | --: |
{% for bird in (species_data | sort(attribute='first_heard', reverse=true))[0:11] -%}
{% set time = bird.get('first_heard', '1970-01-01 00:00:00') -%}
{% set name = bird.get('common_name', 'Unknown') -%}
{% set species_code = bird.get('species_code', '') -%}
{% set count = bird.get('count', 0) -%}
{% set ebird_url = 'https://ebird.org/species/' ~ species_code -%}
{% set first_heard_datetime = as_datetime(time) -%}
{% if species_code | length >= 1 and species_code | length <= 7 %}[{{ name }}]({{ ebird_url }}){% else %}{{ name }}{% endif %} | {{ count }} | {{ relative_time(first_heard_datetime) }} ago
{% endfor -%}
{% else -%}
No recent bird data available.
{% endif -%}
{% else -%}
Waiting for BirdNET-Go…
{% endif %}"""

# BirdNET-Go omits is_new_this_year when false, so filter defined entries first.
FIRST_OF_YEAR_TEMPLATE = """{% if has_value('__DAILY__') -%}
{% set species_data = state_attr('__DAILY__', 'species_list') or [] -%}
{% set foy = species_data | selectattr('is_new_this_year', 'defined') | selectattr('is_new_this_year') | list -%}
{% if foy | count > 0 -%}
{% for bird in foy[:5] -%}
{% set time = bird.get('first_heard') -%}
{% set name = bird.get('common_name') or 'Unknown' -%}
{% set species_code = bird.get('species_code') or '' -%}
{% set ebird_url = 'https://ebird.org/species/' ~ species_code -%}
- {% if species_code | length >= 1 and species_code | length <= 7 %}[{{ name }}]({{ ebird_url }}){% else %}{{ name }}{% endif %}{% if time %} · {{ today_at(time) | as_timestamp | timestamp_custom('%H:%M', true) }}{% endif %}
{% endfor -%}
{% if foy | count > 5 -%}
_+{{ foy | count - 5 }} more first-of-year species_
{% endif -%}
{% elif species_data | count == 0 -%}
No birds heard yet today.
{% else -%}
No first-of-year sightings today.
{% endif -%}
{% else -%}
Waiting for BirdNET-Go…
{% endif %}"""

HISTORY_TEMPLATE = """{% if has_value('__HISTORY__') -%}
{% set counts = state_attr('__HISTORY__', 'daily_counts') or {} -%}
{% if counts | count > 1 -%}
**{{ counts.values() | sum }} detections** in {{ counts | count }} days · best day **{{ counts.values() | max }}**
{% elif counts | count == 1 -%}
**{{ counts.values() | sum }} detections** · one day of history so far.
{% else -%}
No detection history yet.
{% endif -%}
{% else -%}
Waiting for BirdNET-Go…
{% endif %}"""

MIGRATION_TEMPLATE = """{% set arrivals = state_attr('__MIGRATION__', 'new_arrivals') -%}
{% set quiet = state_attr('__MIGRATION__', 'gone_quiet') -%}
{% if arrivals is none and quiet is none -%}
Migration insights need a newer BirdNET-Go with the enhanced database.
{% else -%}
{% set arrivals = arrivals or [] -%}
{% set quiet = quiet or [] -%}
{% if arrivals | count == 0 and quiet | count == 0 -%}
No notable arrivals or departures lately.
{% else -%}
{% if arrivals | count > 0 -%}
{% for bird in arrivals[:3] -%}
- {{ bird }}
{% endfor %}
{% if arrivals | count > 3 -%}
_+{{ arrivals | count - 3 }} more arrivals_
{% endif -%}
{% else -%}
No new arrivals recently.
{% endif %}
**Gone quiet · {{ quiet | count }}**

{% if quiet | count > 0 -%}
{% for bird in quiet[:2] -%}
- {{ bird.get('common_name') or 'Unknown' }} · {{ bird.get('days_since') or '?' }} days
{% endfor %}
{% if quiet | count > 2 -%}
_+{{ quiet | count - 2 }} more_
{% endif -%}
{% else -%}
None recently.
{% endif -%}
{% endif -%}
{% endif %}"""

INTEREST_TEMPLATE = """{% if has_value('__INTEREST__') -%}
{% set species_data = state_attr('__INTEREST__', 'species_list') or [] -%}
{% if species_data | count > 0 -%}
| Species | Last heard |
| :-- | --: |
{% for bird in (species_data | sort(attribute='last_heard', reverse=true))[0:25] -%}
{% set time = bird.get('last_heard', '1970-01-01 00:00:00') -%}
{% set name = bird.get('common_name', 'Unknown') -%}
{% set species_code = bird.get('species_code', '') -%}
{% set ebird_url = 'https://ebird.org/species/' ~ species_code -%}
{% set last_heard_datetime = as_datetime(time) -%}
{% if species_code | length >= 1 and species_code | length <= 7 %}[{{ name }}]({{ ebird_url }}){% else %}{{ name }}{% endif %} | {{ relative_time(last_heard_datetime) }} ago
{% endfor -%}
{% else -%}
Add favorite species under **Settings → Devices & Services → BirdNET-Go → Configure** to follow them here.
{% endif -%}
{% else -%}
Waiting for BirdNET-Go…
{% endif %}"""


def _render(content: str, replacements: dict[str, str]) -> str:
    """Fill in entity and URL placeholders in a card template."""
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)
    return content


def _tile(entity: str, name: str, icon: str, columns: int = 3) -> dict[str, Any]:
    """Build a themed summary tile."""
    return {
        "type": "tile",
        "entity": entity,
        "name": name,
        "icon": icon,
        "grid_options": {"columns": columns, "rows": 1},
    }


def _default_config(
    daily_entity: str,
    species_entity: str,
    interest_entity: str,
    base_url: str,
    latest_bird_entity: str,
    detections_entity: str,
    lifetime_entity: str,
    camera_entity: str,
    foy_entity: str,
    history_entity: str,
    migration_entity: str,
) -> dict[str, Any]:
    """Build the default dashboard configuration."""
    replacements = {
        "__DAILY__": daily_entity,
        "__SPECIES__": species_entity,
        "__INTEREST__": interest_entity,
        "__HISTORY__": history_entity,
        "__MIGRATION__": migration_entity,
    }
    daily = _render(DAILY_TEMPLATE, replacements)
    latest = _render(LATEST_TEMPLATE, replacements)
    brand_new = _render(BRAND_NEW_TEMPLATE, replacements)
    foy = _render(FIRST_OF_YEAR_TEMPLATE, replacements)
    history = _render(HISTORY_TEMPLATE, replacements)
    migration = _render(MIGRATION_TEMPLATE, replacements)
    interest = _render(INTEREST_TEMPLATE, replacements)

    return {
        "version": 1,
        "views": [
            {
                "title": DASHBOARD_TITLE,
                "icon": DASHBOARD_ICON,
                "path": "birds",
                "type": "sections",
                "max_columns": 2,
                "sections": [
                    {
                        "type": "grid",
                        "title": "At a glance",
                        "column_span": 2,
                        "cards": [
                            {
                                "type": "picture-entity",
                                "entity": latest_bird_entity,
                                "camera_image": camera_entity,
                                "camera_view": "auto",
                                "show_name": False,
                                "show_state": False,
                                "grid_options": {"columns": 6, "rows": 3},
                            },
                            _tile(daily_entity, "Species today", "mdi:calendar-today"),
                            _tile(
                                detections_entity,
                                "Detections today",
                                "mdi:counter",
                            ),
                            _tile(
                                lifetime_entity,
                                "Species all time",
                                "mdi:bird",
                            ),
                            _tile(latest_bird_entity, "Latest bird", "mdi:bird"),
                            _tile(
                                interest_entity,
                                "Birds of interest",
                                "mdi:heart-outline",
                            ),
                            {
                                "type": "button",
                                "name": "Open BirdNET-Go",
                                "icon": "mdi:open-in-new",
                                "tap_action": {"action": "url", "url_path": base_url},
                                "grid_options": {"columns": 3, "rows": 1},
                            },
                        ],
                    },
                    {
                        "type": "grid",
                        "title": "Trends",
                        "column_span": 1,
                        "cards": [
                            _tile(history_entity, "Yesterday", "mdi:chart-bar"),
                            _tile(
                                migration_entity,
                                "New arrivals",
                                "mdi:bird",
                            ),
                            {
                                "type": "markdown",
                                "entity": history_entity,
                                "content": history,
                                "grid_options": {"columns": 12},
                            },
                            {
                                "type": "markdown",
                                "entity": migration_entity,
                                "content": migration,
                                "grid_options": {"columns": 12},
                            },
                        ],
                    },
                    {
                        "type": "grid",
                        "title": "First of year",
                        "column_span": 1,
                        "cards": [
                            _tile(
                                foy_entity,
                                "First of year",
                                "mdi:calendar-star",
                                columns=12,
                            ),
                            {
                                "type": "conditional",
                                "conditions": [
                                    {
                                        "condition": "state",
                                        "entity": foy_entity,
                                        "state_not": [
                                            FIRST_OF_YEAR_EMPTY_STATE,
                                            "unknown",
                                            "unavailable",
                                        ],
                                    }
                                ],
                                "card": {
                                    "type": "markdown",
                                    "entity": daily_entity,
                                    "content": foy,
                                },
                                "grid_options": {"columns": 12},
                            },
                        ],
                    },
                    {
                        "type": "grid",
                        "title": "Today's visitors",
                        "column_span": 2,
                        "cards": [
                            {
                                "type": "markdown",
                                "entity": daily_entity,
                                "content": daily,
                                "show_header_toggle": False,
                                "grid_options": {"columns": 12},
                            }
                        ],
                    },
                    {
                        "type": "grid",
                        "title": "Latest detections",
                        "column_span": 1,
                        "cards": [
                            {
                                "type": "markdown",
                                "entity": species_entity,
                                "content": latest,
                                "show_header_toggle": False,
                                "grid_options": {"columns": 12},
                            }
                        ],
                    },
                    {
                        "type": "grid",
                        "title": "New species",
                        "column_span": 1,
                        "cards": [
                            {
                                "type": "markdown",
                                "entity": species_entity,
                                "content": brand_new,
                                "show_header_toggle": False,
                                "grid_options": {"columns": 12},
                            }
                        ],
                    },
                    {
                        "type": "grid",
                        "title": "Birds of interest",
                        "column_span": 2,
                        "cards": [
                            {
                                "type": "markdown",
                                "entity": interest_entity,
                                "content": interest,
                                "show_header_toggle": False,
                                "grid_options": {"columns": 12},
                            }
                        ],
                    },
                ],
            }
        ],
    }


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


def _resolve_entities(hass: HomeAssistant, entry_id: str) -> tuple[str, ...]:
    """Resolve the entity ids used by the dashboard cards."""
    registry = er.async_get(hass)

    def entity_id(domain: str, suffix: str, fallback: str) -> str:
        found = registry.async_get_entity_id(domain, DOMAIN, f"{entry_id}_{suffix}")
        return found or fallback

    return (
        entity_id("sensor", "daily_summary", "sensor.birdnet_daily_summary"),
        entity_id("sensor", "species_summary", "sensor.birdnet_species_summary"),
        entity_id("sensor", "birds_of_interest", "sensor.birdnet_birds_of_interest"),
        entity_id("sensor", "latest_bird", "sensor.birdnet_latest_bird"),
        entity_id("sensor", "detections_today", "sensor.birdnet_detections_today"),
        entity_id("sensor", "lifetime_species", "sensor.birdnet_lifetime_species"),
        entity_id("camera", "latest_bird_image", "camera.birdnet_latest_bird_image"),
        entity_id("sensor", "first_of_year", "sensor.birdnet_first_of_year"),
        entity_id("sensor", "detections_history", "sensor.birdnet_detection_history"),
        entity_id("sensor", "migration", "sensor.birdnet_migration"),
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
        entities = _resolve_entities(hass, entry_id)
        await store.async_save(_default_config(*entities[:3], base_url, *entities[3:]))

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

    entities = _resolve_entities(hass, entry_id)
    await store.async_save(_default_config(*entities[:3], base_url, *entities[3:]))
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
