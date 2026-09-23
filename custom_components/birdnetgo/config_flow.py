"""Config flow to configure the BirdNET-Go integration."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol
from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import dashboard as birdnet_dashboard
from .const import (
    CONF_BASE_URL,
    CONF_BIRDS_OF_INTEREST,
    CONF_COOLDOWN_MINUTES,
    CONF_FRONTEND_URL,
    CONF_HOST,
    CONF_NOTIFY_DETECTIONS,
    CONF_NOTIFY_FIRST_TIME,
    CONF_NOTIFY_RARE,
    CONF_NOTIFY_SERVICE,
    CONF_PORT,
    CONF_RARE_THRESHOLD_DAYS,
    CONF_RESET_DASHBOARD,
    CONF_SCAN_INTERVAL,
    CONF_SSL,
    DAILY_SUMMARY_ENDPOINT,
    DEFAULT_COOLDOWN_MINUTES,
    DEFAULT_PORT,
    DEFAULT_RARE_THRESHOLD_DAYS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    REQUEST_TIMEOUT,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): selector.TextSelector(),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=65535,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Required(CONF_SSL, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_FRONTEND_URL, default=""): selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.URL,
                autocomplete="url",
            )
        ),
        vol.Required(
            CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=MIN_SCAN_INTERVAL,
                max=MAX_SCAN_INTERVAL,
                step=1,
                unit_of_measurement="seconds",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
    }
)

NOTIFY_DISABLED = "disabled"


def normalize_connection_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize values returned by the connection selectors."""
    normalized = dict(user_input)
    normalized[CONF_PORT] = int(normalized[CONF_PORT])
    normalized[CONF_SCAN_INTERVAL] = int(normalized[CONF_SCAN_INTERVAL])
    normalized[CONF_SSL] = cv.boolean(normalized.get(CONF_SSL) or False)
    normalized[CONF_FRONTEND_URL] = (
        str(normalized.get(CONF_FRONTEND_URL, "") or "").strip().rstrip("/")
    )
    return normalized


def build_base_url(user_input: dict[str, Any]) -> str:
    """Build the base URL from user input."""
    host = str(user_input[CONF_HOST]).strip().rstrip("/")
    for prefix in ("https://", "http://"):
        if host.lower().startswith(prefix):
            host = host[len(prefix) :]
            break
    if not host:
        raise ValueError("A BirdNET-Go host is required")
    port = int(user_input[CONF_PORT])
    if not 1 <= port <= 65535:
        raise ValueError("A valid BirdNET-Go port is required")
    scheme = "https" if cv.boolean(user_input.get(CONF_SSL) or False) else "http"
    return f"{scheme}://{host}:{port}"


async def validate_connection(hass: HomeAssistant, base_url: str) -> bool:
    """Verify the BirdNET-Go API is reachable."""
    session = async_get_clientsession(hass)
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            response = await session.get(f"{base_url}{DAILY_SUMMARY_ENDPOINT}")
            if response.status != 200:
                return False
            data = await response.json()
    except (TimeoutError, ClientError, TypeError, ValueError):
        return False
    return isinstance(data, list)


def notify_service_options(hass: HomeAssistant) -> list[str]:
    """Build the list of available notification service names."""
    return sorted(hass.services.async_services().get("notify", {}))


class BirdNETGoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BirdNET-Go."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                normalized = normalize_connection_input(user_input)
                base_url = build_base_url(normalized)
            except (KeyError, TypeError, ValueError, vol.Invalid):
                errors["base"] = "cannot_connect"
            else:
                if await validate_connection(self.hass, base_url):
                    await self.async_set_unique_id(base_url)
                    self._abort_if_unique_id_configured()
                    data = dict(normalized)
                    data[CONF_BASE_URL] = base_url
                    return self.async_create_entry(title="BirdNET-Go", data=data)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_import(self, user_input: dict[str, Any]) -> FlowResult:
        """Handle import from configuration.yaml."""
        return await self.async_step_user(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> BirdNETGoOptionsFlow:
        """Get the options flow for this handler."""
        return BirdNETGoOptionsFlow()


class BirdNETGoOptionsFlow(config_entries.OptionsFlow):
    """Handle options for BirdNET-Go."""

    def __init__(self) -> None:
        """Initialize the options draft."""
        self._draft: dict[str, Any] | None = None

    def _get_draft(self) -> dict[str, Any]:
        """Return the mutable options draft."""
        if self._draft is None:
            draft = dict(self.config_entry.data)
            draft.update(self.config_entry.options)
            draft.setdefault(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            draft.setdefault(CONF_FRONTEND_URL, "")
            draft.setdefault(CONF_BIRDS_OF_INTEREST, "")
            draft.setdefault(CONF_NOTIFY_SERVICE, NOTIFY_DISABLED)
            draft.setdefault(CONF_NOTIFY_DETECTIONS, False)
            draft.setdefault(CONF_NOTIFY_FIRST_TIME, True)
            draft.setdefault(CONF_NOTIFY_RARE, True)
            draft.setdefault(CONF_COOLDOWN_MINUTES, DEFAULT_COOLDOWN_MINUTES)
            draft.setdefault(CONF_RARE_THRESHOLD_DAYS, DEFAULT_RARE_THRESHOLD_DAYS)
            draft.setdefault(CONF_RESET_DASHBOARD, False)
            self._draft = draft
        return self._draft

    def _suggested_schema(self, schema: vol.Schema) -> vol.Schema:
        """Apply the current draft to a form schema."""
        values = dict(self._get_draft())
        if not values.get(CONF_NOTIFY_SERVICE):
            values[CONF_NOTIFY_SERVICE] = NOTIFY_DISABLED
        return self.add_suggested_values_to_schema(schema, values)

    def _notify_selector(self) -> selector.SelectSelector:
        """Build a selector for available notification services."""
        options: list[dict[str, str]] = [
            {"value": NOTIFY_DISABLED, "label": "Disabled"}
        ]
        known_values = {NOTIFY_DISABLED}
        for name in notify_service_options(self.hass):
            value = f"notify.{name}"
            known_values.add(value)
            options.append({"value": value, "label": value})

        current_service = str(self._get_draft().get(CONF_NOTIFY_SERVICE, ""))
        if current_service and current_service not in known_values:
            options.append({"value": current_service, "label": current_service})

        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=options,
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the settings menu."""
        self._get_draft()
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "connection",
                "interests",
                "notifications",
                "dashboard",
                "save",
            ],
        )

    async def async_step_connection(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit connection and refresh settings."""
        if user_input is not None:
            self._get_draft().update(user_input)
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        unit_of_measurement="seconds",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(CONF_FRONTEND_URL): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.URL,
                        autocomplete="url",
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="connection",
            data_schema=self._suggested_schema(schema),
        )

    async def async_step_interests(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit the birds of interest list."""
        if user_input is not None:
            self._get_draft().update(user_input)
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Optional(CONF_BIRDS_OF_INTEREST): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                )
            }
        )
        return self.async_show_form(
            step_id="interests",
            data_schema=self._suggested_schema(schema),
        )

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit notification behavior."""
        if user_input is not None:
            self._get_draft().update(user_input)
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Optional(CONF_NOTIFY_SERVICE): self._notify_selector(),
                vol.Optional(CONF_NOTIFY_DETECTIONS): selector.BooleanSelector(),
                vol.Optional(CONF_NOTIFY_FIRST_TIME): selector.BooleanSelector(),
                vol.Optional(CONF_NOTIFY_RARE): selector.BooleanSelector(),
                vol.Optional(CONF_COOLDOWN_MINUTES): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=1440,
                        step=1,
                        unit_of_measurement="minutes",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(CONF_RARE_THRESHOLD_DAYS): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=3650,
                        step=1,
                        unit_of_measurement="days",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="notifications",
            data_schema=self._suggested_schema(schema),
        )

    async def async_step_dashboard(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit dashboard actions."""
        if user_input is not None:
            self._get_draft().update(user_input)
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_RESET_DASHBOARD, default=False
                ): selector.BooleanSelector()
            }
        )
        return self.async_show_form(
            step_id="dashboard",
            data_schema=self._suggested_schema(schema),
        )

    async def async_step_save(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Persist the draft and optionally reset the dashboard."""
        entry = self.config_entry
        draft = self._get_draft()
        if draft.get(CONF_RESET_DASHBOARD):
            frontend_url = (
                str(draft.get(CONF_FRONTEND_URL, "") or "").strip().rstrip("/")
            )
            base_url = str(entry.data[CONF_BASE_URL]).rstrip("/")
            await birdnet_dashboard.async_reset_dashboard(
                self.hass,
                entry.entry_id,
                frontend_url or base_url,
            )
        return self.async_create_entry(title="", data=self._normalize(draft))

    def _normalize(self, user_input: dict[str, Any]) -> dict[str, Any]:
        """Fill in defaults for fields the user left untouched."""
        entry = self.config_entry
        draft = self._get_draft()

        def value(key: str, default: Any) -> Any:
            result = user_input.get(key, draft.get(key, default))
            return default if result is None else result

        service = str(value(CONF_NOTIFY_SERVICE, NOTIFY_DISABLED))
        if service == NOTIFY_DISABLED:
            service = ""

        return {
            CONF_SCAN_INTERVAL: int(
                value(
                    CONF_SCAN_INTERVAL,
                    entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                )
            ),
            CONF_FRONTEND_URL: str(value(CONF_FRONTEND_URL, "")).strip().rstrip("/"),
            CONF_BIRDS_OF_INTEREST: str(value(CONF_BIRDS_OF_INTEREST, "")),
            CONF_NOTIFY_SERVICE: service,
            CONF_NOTIFY_DETECTIONS: cv.boolean(value(CONF_NOTIFY_DETECTIONS, False)),
            CONF_NOTIFY_FIRST_TIME: cv.boolean(value(CONF_NOTIFY_FIRST_TIME, True)),
            CONF_NOTIFY_RARE: cv.boolean(value(CONF_NOTIFY_RARE, True)),
            CONF_COOLDOWN_MINUTES: int(
                value(CONF_COOLDOWN_MINUTES, DEFAULT_COOLDOWN_MINUTES)
            ),
            CONF_RARE_THRESHOLD_DAYS: int(
                value(CONF_RARE_THRESHOLD_DAYS, DEFAULT_RARE_THRESHOLD_DAYS)
            ),
        }
