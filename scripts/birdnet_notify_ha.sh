#!/bin/bash
# version 1.0
# BirdNET-Go custom action: notify Home Assistant of a bird detection.
# Configure this script as a custom action in BirdNET-Go under Settings > Species,
# including the CommonName, Confidence, Time, and Source parameters (any order).

# === Debug: Log Raw Input Arguments ===
echo "--- Raw Script Arguments Received ---" >&2
arg_count=0
for raw_arg in "$@"; do
  arg_count=$((arg_count + 1))
  echo "Arg ${arg_count}: ${raw_arg}" >&2 # Print each argument exactly as received
done
echo "Total arguments received: ${arg_count}" >&2
echo "-------------------------------------" >&2
# === End Debug ===


# === Configuration ===
HA_WEBHOOK_URL="http://HOME_ASSISTANT_URL:8123/api/webhook/notify-bird-detection-123456789" # Replace with your actual webhook URL

# === Argument Parsing ===
# Initialize variables to store argument values
COMMON_NAME_VAL=""
CONFIDENCE_VAL=""
SOURCE_VAL=""
TIME_VAL=""
MISSING_ARGS="" # Keep track of missing arguments

# Loop through all provided arguments
for arg in "$@"; do
  case $arg in
    --CommonName=*)
      COMMON_NAME_VAL="${arg#*=}" # Extract value after '='
      # *** BUG FIX: Remove potential surrounding quotes from the value ***
      COMMON_NAME_VAL=$(echo "$COMMON_NAME_VAL" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
      ;;
    --Confidence=*)
      CONFIDENCE_VAL="${arg#*=}"
      ;;
    --Source=*)
      SOURCE_VAL="${arg#*=}"
      ;;
    --Time=*)
      TIME_VAL="${arg#*=}"
      ;;
    *)
      echo "WARNING: Ignoring unrecognized argument: $arg" >&2
      ;;
  esac
done

# === Validation ===
# Check if all required arguments were found
if [ -z "$COMMON_NAME_VAL" ]; then MISSING_ARGS="${MISSING_ARGS} --CommonName"; fi
if [ -z "$CONFIDENCE_VAL" ]; then MISSING_ARGS="${MISSING_ARGS} --Confidence"; fi
if [ -z "$SOURCE_VAL" ]; then MISSING_ARGS="${MISSING_ARGS} --Source"; fi
if [ -z "$TIME_VAL" ]; then MISSING_ARGS="${MISSING_ARGS} --Time"; fi

# If any arguments are missing...
if [ -n "$MISSING_ARGS" ]; then
    # --- Debug Fallback ---
    ERROR_REASON="Missing required arguments"
    echo "ERROR: ${ERROR_REASON}: ${MISSING_ARGS}" >&2

    # Construct a debug JSON payload for Home Assistant
    DEBUG_JSON=$(printf '{"type": "script_error", "reason": "%s", "missing_args": "%s"}' \
        "$ERROR_REASON" \
        "${MISSING_ARGS# }" ) # Remove leading space from MISSING_ARGS

    echo "Sending error details to Home Assistant webhook..." >&2

    # Attempt to send the error notification via curl to the HA webhook
    curl --silent --show-error --fail \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$DEBUG_JSON" \
        "${HA_WEBHOOK_URL}"

    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to send *debug* JSON to Home Assistant webhook." >&2
        # Even if sending debug fails, we continue to exit 0 below
    fi

    # Print standard usage instructions to console for the user
    echo "Usage: $0 --Time=\"<value>\" --CommonName=\"<value>\" --Confidence=\"<value>\" --Source=\"<value>\""
    echo "Arguments can be in any order."
    echo "Example: $0 --Time=\"07:53:30\" --CommonName=\"White-crowned Sparrow\" --Confidence=\"0.54\" --Source=\"rtsp://user@10.0.0.1/stream\""

    # Exit with a success status code, even though curl failed, that way nothing downstream breaks
    echo "Exiting with status 0 despite missing arguments." >&2
    exit 0
fi

# === Normal Operation (if all arguments are present) ===

# --- Source Mapping ---
# Use a temporary variable for the source before mapping
# This remaps any source that contains the IP and replaces the entire source with a friendly name
SOURCE_MAPPED="$SOURCE_VAL"
# Check if the source id value CONTAINS a known HEX using pattern matching (*)
# Source IDs can be listed via: /api/v2/streams/sources
case "$SOURCE_VAL" in
    *"abcd1234"*) SOURCE_MAPPED="Pool Camera" ;;
    *"123123ab"*) SOURCE_MAPPED="Tree Camera" ;;
    *"ab12cd34"*) SOURCE_MAPPED="Spy Camera" ;;
esac
# --- End Source Mapping ---

# --- Confidence Formatting ---
# Convert decimal confidence to percentage string
CONFIDENCE_DISPLAY=$(awk -v conf="$CONFIDENCE_VAL" 'BEGIN { printf "%.0f%%", conf }')
# --- End Confidence Formatting ---

# === JSON Construction ===
# Create the JSON payload for Home Assistant
JSON_PAYLOAD=$(printf '{"type": "bird_detection", "time": "%s", "common_name": "%s", "confidence_pct": "%s", "confidence_raw": "%s", "source_camera": "%s"}' \
    "$TIME_VAL" \
    "$COMMON_NAME_VAL" \
    "$CONFIDENCE_DISPLAY" \
    "$CONFIDENCE_VAL" \
    "$SOURCE_MAPPED" )

# === Send Data to Home Assistant ===
echo "Sending data to Home Assistant webhook..."

# --- Debug: Show Final Values Before Sending ---
echo "--- Values used in JSON ---" >&2
echo "Time:           $TIME_VAL" >&2
echo "Common Name:    $COMMON_NAME_VAL" >&2
echo "Confidence Pct: $CONFIDENCE_DISPLAY" >&2
echo "Confidence Raw: $CONFIDENCE_VAL" >&2
echo "Source Mapped:  $SOURCE_MAPPED" >&2
echo "---------------------------" >&2
echo "JSON Payload: $JSON_PAYLOAD" # Print the final JSON
# --- End Debug ---


# Use curl to send the JSON payload via POST
curl --silent --show-error --fail \
    -X POST \
    -H "Content-Type: application/json" \
    -d "$JSON_PAYLOAD" \
    "${HA_WEBHOOK_URL}"

# === Check Result ===
CURL_EXIT_CODE=$? # Capture the exit code of curl
if [ $CURL_EXIT_CODE -eq 0 ]; then
    echo "Data sent successfully to Home Assistant webhook."
    exit 0 # Success exit code
else
    echo "ERROR: Failed to send data to Home Assistant webhook (curl exit code: $CURL_EXIT_CODE)." >&2
    # Exit with a success status code, even though curl failed, that way nothing downstream breaks
    echo "Exiting with status 0 despite webhook send failure." >&2
    exit 0
fi
