#!/bin/bash
# version 1.0
# BirdNET-Go Video Generator (New Search Dashboard)
# Builds a shareable MP4 (black background + metadata overlays) from audio
# files downloaded via the newer BirdNET-Go Search Dashboard
# (filenames like 12345.mp4, served from /api/v2/detections/).
#
# Requires: curl, jq, ffmpeg, awk

# Default values
duration=15
location="YOUR_TOWN, ST"
weather="Partly Cloudy"
input_file="$(ls -t ~/Downloads/*.mp4 2>/dev/null | head -n 1)"
boost_sound=false
species_override=""
subtitle=""
start_offset="0" # Default start offset in seconds
api_detections_endpoint="http://YOUR_BIRDNET_ENDPOINT/api/v2/detections/"

# === Dependency Check ===
for cmd in curl jq ffmpeg awk; do
  if ! command -v $cmd &> /dev/null; then
    echo "ERROR: Required command '$cmd' not found. Please install it."
    exit 1
  fi
done
# === END Dependency Check ===

# === Temp Directory and Cleanup ===
TMPDIR=$(mktemp -d)
if [ ! -d "$TMPDIR" ]; then
    echo "ERROR: Failed to create temporary directory."
    exit 1
fi
trap 'echo "DEBUG: Cleaning up temp dir: $TMPDIR"; rm -rf "$TMPDIR"' EXIT
echo "DEBUG: Created temp directory: $TMPDIR"
# === END Temp Directory ===

# Help function
help_function() {
  echo "Usage: $0 [options]"
  echo "Options:"
  echo "  -d <duration>       Duration of the video in seconds (default: 15)"
  echo "  -l <location>       Location (default: YOUR_TOWN, ST)"
  echo "  -w <weather>        Weather (default: Partly Cloudy)"
  echo "  -i <input_file>     Input audio/video file (default: newest .mp4 in ~/Downloads/)"
  echo "  -b <boost_sound>    Boost audio (true or false, default: false)"
  echo "  -s <species_text>   Override the species text displayed in the video"
  echo "  -u <subtitle>       Optional subtitle text below species name"
  echo "  -m <start_offset>   Start the clip at this many seconds into the input file (default: 0)"
  echo "  --help              Display this help message"
  exit 0
}

# Parse command-line arguments
while getopts "d:l:w:i:b:s:u:m:" opt; do
  case "$opt" in
  d) duration="$OPTARG" ;;
  l) location="$OPTARG" ;;
  w) weather="$OPTARG" ;;
  i) input_file="$OPTARG" ;;
  b) boost_sound="$OPTARG" ;;
  s) species_override="$OPTARG" ;;
  u) subtitle="$OPTARG" ;;
  m) start_offset="$OPTARG" ;;
  \?|:|*) help_function ;;
  esac
done
shift $((OPTIND - 1))

# Validate start_offset
if ! [[ "$start_offset" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    echo "ERROR: Invalid start offset '$start_offset'. Must be a non-negative number."
    exit 1
fi
echo "DEBUG: Start offset set to: $start_offset seconds"

# --- Input File and API Data Processing ---
if [ -z "$input_file" ]; then
    echo "Error: No input file specified and couldn't find a default .mp4 file in ~/Downloads/."
    exit 1
fi
if [ ! -f "$input_file" ]; then echo "Error: Input file '$input_file' not found."; exit 1; fi

filename=$(basename "$input_file")
echo "DEBUG: Processing filename: $filename"
file_id="${filename%.*}" # Get filename without extension

if ! [[ "$file_id" =~ ^[0-9]+$ ]]; then
    echo "ERROR: Filename (without extension) '$file_id' is not a valid numeric ID."
    exit 1
fi
echo "DEBUG: Extracted File ID: $file_id"

API_URL="$api_detections_endpoint$file_id"
echo "DEBUG: Fetching data from API: $API_URL"

api_response=$(curl -s -L "$API_URL") # -L to follow redirects
curl_exit_status=$?

if [ $curl_exit_status -ne 0 ]; then
    echo "ERROR: curl command failed with exit status $curl_exit_status when fetching data for ID $file_id."
    exit 1
fi

if [ -z "$api_response" ] || [ "$(echo "$api_response" | jq '.id')" = "null" ]; then
    echo "ERROR: API did not return valid data for ID $file_id. Response: $api_response"
    exit 1
fi

# Extract data using jq
api_common_name=$(echo "$api_response" | jq -r '.commonName')
api_begin_time=$(echo "$api_response" | jq -r '.beginTime')
api_confidence_float=$(echo "$api_response" | jq -r '.confidence')

if [ "$api_common_name" = "null" ] || [ -z "$api_common_name" ]; then
    echo "ERROR: Could not extract commonName from API response."
    exit 1
fi
if [ "$api_begin_time" = "null" ] || [ -z "$api_begin_time" ]; then
    echo "ERROR: Could not extract beginTime from API response."
    exit 1
fi
if [ "$api_confidence_float" = "null" ] || [ -z "$api_confidence_float" ]; then
    echo "ERROR: Could not extract confidence from API response."
    exit 1
fi

echo "DEBUG: API Common Name: $api_common_name"
echo "DEBUG: API Begin Time: $api_begin_time"
echo "DEBUG: API Confidence (float): $api_confidence_float"

# Format timestamp (e.g., YYYY-MM-DDTHH:MM:SS-04:00 -> YYYY-MM-DD HH:MM:SS)
timestamp=$(echo "$api_begin_time" | sed 's/T/ /; s/\([-+][0-9][0-9]:[0-9][0-9]Z\{0,1\}\)$//')
if [ -z "$timestamp" ]; then
    echo "ERROR: Failed to format timestamp from API beginTime '$api_begin_time'."
    exit 1
fi
echo "DEBUG: Formatted Timestamp: $timestamp"

# Format confidence (e.g., 0.96 -> 96% Confidence)
confidence_percentage=$(awk -v conf="$api_confidence_float" 'BEGIN { printf "%.0f", conf * 100 }')
if [ -z "$confidence_percentage" ]; then
    echo "ERROR: Failed to calculate confidence percentage from '$api_confidence_float'."
    exit 1
fi
confidence_text_unescaped="${confidence_percentage}% Confidence"
echo "DEBUG: Confidence Text (unescaped): $confidence_text_unescaped"
# --- End API Data Processing ---

# Determine final species text
species_from_api="$api_common_name" # Use common name from API

if [ -n "$species_override" ]; then
  echo "INFO: Using species override text: '$species_override'"
  final_species_text="$species_override"
else
  echo "INFO: Using API-derived species text: '$species_from_api'"
  final_species_text="$species_from_api"
fi
if [ -z "$final_species_text" ]; then echo "ERROR: Species text is empty."; exit 1; fi

# Prepare other display text (unescaped) for textfile method
timestamp_display=$(echo "$timestamp" | sed 's/Z//g')
weather_display="Weather: $weather"

# --- Write text to temporary files (Using \% escape for files) ---
species_file="$TMPDIR/species.txt"
subtitle_file_path=""
confidence_file="$TMPDIR/confidence.txt"
location_file="$TMPDIR/location.txt"
timestamp_file="$TMPDIR/timestamp.txt"
weather_file="$TMPDIR/weather.txt"

echo "DEBUG: Writing text to temp files..."
printf "%s" "$final_species_text" > "$species_file"
printf "%s" "$location" > "$location_file"
printf "%s" "$timestamp_display" > "$timestamp_file"
printf "%s" "$weather_display" > "$weather_file"

confidence_text_for_file=$(echo "$confidence_text_unescaped" | sed 's/%/\\%/g')
printf "%s" "$confidence_text_for_file" > "$confidence_file"
echo "DEBUG: Confidence text written to $confidence_file (using \% escape)"

if [ -n "$subtitle" ]; then
    subtitle_file_path=$(mktemp "$TMPDIR/subtitle_XXXXXX.txt")
    if [ -z "$subtitle_file_path" ] || [ ! -w "$(dirname "$subtitle_file_path")" ]; then
        echo "ERROR: Failed to create subtitle temp file in $TMPDIR."
        subtitle_file_path=""
    else
        subtitle_text_for_file=$(echo "$subtitle" | sed 's/%/\\%/g')
        printf "%s" "$subtitle_text_for_file" > "$subtitle_file_path"
        echo "DEBUG: Subtitle text written to $subtitle_file_path (using \% escape)"
    fi
fi
# --- End Write text ---


# <<< Calculate Y Positions >>>
y_offset_species=-200; y_offset_confidence=-115; y_offset_location=-35; y_offset_timestamp=45; y_offset_weather=125; line_spacing=85
calc_y_pos() { local offset=$1; echo "(h/2)-text_h/2+($offset)"; }
y_pos_species=$(calc_y_pos $y_offset_species); y_pos_confidence=$(calc_y_pos $y_offset_confidence); y_pos_location=$(calc_y_pos $y_offset_location); y_pos_timestamp=$(calc_y_pos $y_offset_timestamp); y_pos_weather=$(calc_y_pos $y_offset_weather)
y_pos_subtitle=""
if [ -n "$subtitle_file_path" ] ; then
    y_pos_subtitle=$(calc_y_pos $((y_offset_species + line_spacing)))
    y_pos_confidence=$(calc_y_pos $((y_offset_confidence + line_spacing)))
    y_pos_location=$(calc_y_pos $((y_offset_location + line_spacing)))
    y_pos_timestamp=$(calc_y_pos $((y_offset_timestamp + line_spacing)))
    y_pos_weather=$(calc_y_pos $((y_offset_weather + line_spacing)))
fi
# <<< END Calculate Y Positions >>>


# <<< Build Filter Complex using textfile= for ALL lines >>>
filter_complex="\
[0:v]drawtext=textfile='$species_file':fontcolor=white:fontsize=72:x=(w-text_w)/2:y=${y_pos_species}"
if [ -n "$subtitle_file_path" ] ; then
    filter_complex="$filter_complex,\
drawtext=textfile='$subtitle_file_path':fontcolor=white:fontsize=60:x=(w-text_w)/2:y=${y_pos_subtitle}"
fi
filter_complex="$filter_complex,\
drawtext=textfile='$confidence_file':fontcolor=white:fontsize=60:x=(w-text_w)/2:y=${y_pos_confidence},\
drawtext=textfile='$location_file':fontcolor=white:fontsize=60:x=(w-text_w)/2:y=${y_pos_location},\
drawtext=textfile='$timestamp_file':fontcolor=white:fontsize=60:x=(w-text_w)/2:y=${y_pos_timestamp},\
drawtext=textfile='$weather_file':fontcolor=white:fontsize=60:x=(w-text_w)/2:y=${y_pos_weather}[v]"
if [ "$boost_sound" = true ]; then filter_complex="$filter_complex;[1:a]volume=15dB,compand=attacks=0:points=-80/-80|-12/-10|0/-2|20/25[a]"; else filter_complex="$filter_complex;[1:a]anull[a]"; fi
# <<< END Build Filter Complex >>>


# ============================================================
# --- Construct the output path ---
input_dir=$(dirname "$input_file")
filename_species_part="$final_species_text"
safe_species_name=$(echo "$filename_species_part" | sed 's/[^a-zA-Z0-9_ -]//g' | tr ' ' '_')
timestamp_filename=$(echo "$timestamp" | sed 's/ /_/g; s/:/-/g')
output_filename_base="${timestamp_filename}_${safe_species_name}.mp4"
output_file="$input_dir/$output_filename_base"
echo "INFO: Output file path: $output_file"
# ============================================================

# Construct the ffmpeg command string for eval
ffmpeg_input_options=""
# Check if start_offset is greater than 0 using awk for float comparison
is_offset_positive=$(awk -v offset="$start_offset" 'BEGIN { print (offset > 0) }')

if [ "$is_offset_positive" -eq 1 ]; then
  ffmpeg_input_options="-ss $start_offset"
  echo "INFO: Applying start offset of $start_offset seconds to input file."
fi

ffmpeg_command="ffmpeg -f lavfi -i \"color=c=black:s=1280x700\" $ffmpeg_input_options -i \"$input_file\" \
-filter_complex \"$filter_complex\" \
-map \"[v]\" -map \"[a]\" -c:v libx264 -c:a aac -t $duration -y \"$output_file\""
echo "DEBUG: FFmpeg command string built for eval: $ffmpeg_command"

# Execute the command using eval
echo "INFO: Executing ffmpeg command..."
eval "$ffmpeg_command"

exit_status=$?
if [ $exit_status -ne 0 ]; then
    echo "ERROR: ffmpeg command failed with exit status $exit_status"
    exit $exit_status
else
    echo "SUCCESS: Successfully created video: $output_file"
fi

exit 0
