"""Constants for the BirdNET-Go integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "birdnetgo"
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CAMERA]

CONF_BASE_URL = "base_url"
CONF_FRONTEND_URL = "frontend_url"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_SSL = "ssl"
CONF_SCAN_INTERVAL = "scan_interval"

# Notification options
CONF_NOTIFY_SERVICE = "notify_service"
CONF_NOTIFY_DETECTIONS = "notify_detections"
CONF_NOTIFY_FIRST_TIME = "notify_first_time"
CONF_NOTIFY_RARE = "notify_rare"
CONF_COOLDOWN_MINUTES = "cooldown_minutes"
CONF_RARE_THRESHOLD_DAYS = "rare_threshold_days"
CONF_RESET_DASHBOARD = "reset_dashboard"

# Birds of interest option (comma/newline separated species names)
CONF_BIRDS_OF_INTEREST = "birds_of_interest"

DEFAULT_NAME = "BirdNET-Go"
DEFAULT_PORT = 8080
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 3600

DEFAULT_COOLDOWN_MINUTES = 15
DEFAULT_RARE_THRESHOLD_DAYS = 180

REQUEST_TIMEOUT = 30

DAILY_SUMMARY_ENDPOINT = "/api/v2/analytics/species/daily"
SPECIES_SUMMARY_ENDPOINT = "/api/v2/analytics/species/summary"
MEDIA_IMAGE_ENDPOINT = "/api/v2/media/image/"

ATTR_BASE_URL = "base_url"
ATTR_FRONTEND_URL = "frontend_url"
ATTR_SPECIES_LIST = "species_list"

# Auto-created dashboard
DASHBOARD_URL_PATH = "birdnetgo"
DASHBOARD_ID = "birdnetgo"
DASHBOARD_TITLE = "Birds"
DASHBOARD_ICON = "mdi:bird"

# Mobile-app notification action used to clear the notification cooldown
NOTIFY_RESET_ACTION = "BIRDNET_RESET_COOLDOWN"

# Grouping metadata shared by all built-in notifications
NOTIFICATION_TAG = "birdnet-alert"
NOTIFICATION_GROUP = "birdnet-alert"
NOTIFICATION_CHANNEL = "birdnet-alert"
NOTIFICATION_ICON = "mdi:bird"
