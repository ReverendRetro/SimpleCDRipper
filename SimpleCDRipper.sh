#!/bin/bash

#==============================================================================
#   DESCRIPTION: A script to rip CDs to various formats, automatically fetching
#                metadata, genres, composer info, and cover art from
#                MusicBrainz. It organizes files into a clean, archival-quality
#                directory structure with ReplayGain, HDA ripping, and auto-eject.
#
#  REQUIREMENTS: cdparanoia, flac, curl, jq, md5sum, eject, metaflac,
#                and lame/oggenc for MP3/OGG.
#        AUTHOR: ReverendRetro
#       CREATED: 2025-08-10
#      REVISION: 4.3
#==============================================================================

# --- Configuration ---
# Set to "true" to see detailed debugging output
VERBOSE="false"
SCRIPT_REVISION="4.3"

# --- Functions ---

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function for verbose output
verbose_echo() {
    if [ "$VERBOSE" == "true" ]; then
        echo "VERBOSE: $1"
    fi
}

# Function to display an error message and exit
error_exit() {
    echo "Error: $1" >&2
    exit 1
}

# Function to clean up temporary files
cleanup() {
    verbose_echo "Cleaning up temporary files..."
    rm -f /tmp/musicbrainz_response.json /tmp/cdparanoia_toc.txt /tmp/cover_art.jpg
}

# --- Dependency Check ---

echo "Checking for required dependencies..."
for cmd in cdparanoia curl jq md5sum eject; do
    if ! command_exists "$cmd"; then
        error_exit "'$cmd' is not installed. Please install it to continue."
    fi
done
echo "Core dependencies are satisfied."
echo

# --- Auto-detect CD Drive ---
echo "Scanning for CD drives with a disc..."
DRIVES=($(ls /dev/sr* 2>/dev/null))
VALID_DRIVES=()
for drive in "${DRIVES[@]}"; do
    # Check if a disc is present and readable by cdparanoia
    if cdparanoia -Q -d "$drive" &>/dev/null; then
        VALID_DRIVES+=("$drive")
    fi
done

if [ ${#VALID_DRIVES[@]} -eq 0 ]; then
    error_exit "No readable audio CD found in any drive. Please insert a disc."
elif [ ${#VALID_DRIVES[@]} -eq 1 ]; then
    CD_DEVICE=${VALID_DRIVES[0]}
    echo "Found CD in: $CD_DEVICE"
else
    echo "Found discs in multiple drives. Please choose which one to rip:"
    select drive in "${VALID_DRIVES[@]}"; do
        if [ -n "$drive" ]; then
            CD_DEVICE=$drive
            break
        else
            echo "Invalid selection."
        fi
    done
fi
echo

# --- Choose Output Format ---
echo "Please choose an output format:"
echo "  1) FLAC (lossless, with ReplayGain, default)"
echo "  2) WAV (uncompressed)"
echo "  3) MP3 (320kbps)"
echo "  4) OGG (Vorbis, ~500kbps)"
read -p "Enter your choice [1-4]: " FORMAT_CHOICE

case $FORMAT_CHOICE in
    2)
        ENCODER="wav"
        EXTENSION="wav"
        ;;
    3)
        command_exists "lame" || error_exit "'lame' is not installed. Please install it for MP3 encoding."
        ENCODER="mp3"
        EXTENSION="mp3"
        ;;
    4)
        command_exists "oggenc" || error_exit "'oggenc' is not installed. Please install it for OGG encoding."
        ENCODER="ogg"
        EXTENSION="ogg"
        ;;
    *)
        command_exists "flac" || error_exit "'flac' is not installed. Please install it for FLAC encoding."
        command_exists "metaflac" || error_exit "'metaflac' is not installed. Please install it for ReplayGain scanning."
        ENCODER="flac"
        EXTENSION="flac"
        ;;
esac
echo "Selected format: ${ENCODER^^}"
echo

# --- Set Save Directory ---

read -p "Enter the directory to save the ripped files (default: $HOME/Music): " SAVE_DIR
SAVE_DIR=${SAVE_DIR:-"$HOME/Music"}

if [ ! -d "$SAVE_DIR" ]; then
    echo "Directory '$SAVE_DIR' does not exist. Creating it..."
    mkdir -p "$SAVE_DIR" || error_exit "Could not create directory '$SAVE_DIR'."
fi

echo "Rips will be saved in: $SAVE_DIR"
echo

# --- Get CD Information from MusicBrainz ---

echo "Attempting to retrieve CD information from MusicBrainz..."

cdparanoia -Q -d "$CD_DEVICE" > /tmp/cdparanoia_toc.txt 2>&1
TRACK_COUNT_ACTUAL=$(grep '^[[:space:]]*[0-9]\+\.' /tmp/cdparanoia_toc.txt | wc -l)

if [ "$TRACK_COUNT_ACTUAL" -eq 0 ]; then
    error_exit "No audio tracks found on the disc or could not read the disc."
fi
echo "Found $TRACK_COUNT_ACTUAL tracks on the disc."

# --- Construct the TOC string for the MusicBrainz API ---
TOC_STRING="1"
TOC_STRING+="+$TRACK_COUNT_ACTUAL"
FIRST_TRACK_SECTOR=$(grep '^[[:space:]]*1\.' /tmp/cdparanoia_toc.txt | awk '{print $4}')
TOTAL_SECTORS=$(grep 'TOTAL' /tmp/cdparanoia_toc.txt | awk '{print $2}')
LEADOUT_SECTOR=$((FIRST_TRACK_SECTOR + TOTAL_SECTORS))
TOC_STRING+="+$LEADOUT_SECTOR"
OFFSETS=$(grep '^[[:space:]]*[0-9]\+\.' /tmp/cdparanoia_toc.txt | awk '{print $4}' | tr '\n' '+')
TOC_STRING+="+${OFFSETS%?}"

verbose_echo "Constructed TOC for API: '$TOC_STRING'"

# Add genres and work-rels (for composers) to the API request
API_URL="https://musicbrainz.org/ws/2/discid/-?toc=$TOC_STRING&fmt=json&inc=artist-credits+recordings+release-groups+genres+work-rels"
verbose_echo "Constructed API URL: $API_URL"

HTTP_STATUS=$(curl -s -o /tmp/musicbrainz_response.json -w "%{http_code}" -A "GeminiCDRipper/$SCRIPT_REVISION (https://gemini.google.com)" "$API_URL")
verbose_echo "Received HTTP Status: $HTTP_STATUS"

# Initialize variables
RELEASE_URL=""
SUCCESS_COUNT=0
COVER_ART_FILE=""
COVER_ART_STATUS="No"
GENRE=""
DISC_SUBDIR=""
METADATA_SOURCE="Manual" # Default to manual, change if found

# Check if the API call was successful and found any releases
if [ "$HTTP_STATUS" -eq 200 ] && [ -s /tmp/musicbrainz_response.json ] && [ "$(jq '.releases | length' /tmp/musicbrainz_response.json 2>/dev/null)" -gt 0 ]; then
    RELEASE_COUNT=$(jq '.releases | length' /tmp/musicbrainz_response.json)
    SELECTED_INDEX=0

    if [ "$RELEASE_COUNT" -eq 1 ]; then
        echo "Found one matching release:"
        jq -r '.releases[0] | "\(.|."artist-credit"[0].name) - \(.title)"' /tmp/musicbrainz_response.json
        read -p "Use this release? (y/n): " CONFIRM
        if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
            METADATA_SOURCE="MusicBrainz"
        fi
    else # This handles RELEASE_COUNT > 1
        echo "Found multiple matching releases. Please choose the correct one:"
        echo "  0) None of these - Enter manually"
        jq -r '.releases[] | "\(.|."artist-credit"[0].name) - \(.title)"' /tmp/musicbrainz_response.json | nl -w2 -s'. '
        
        while true; do
            read -p "Enter your choice (0-$RELEASE_COUNT): " SELECTION
            if [[ "$SELECTION" =~ ^[0-9]+$ ]] && [ "$SELECTION" -ge 0 ] && [ "$SELECTION" -le "$RELEASE_COUNT" ]; then
                if [ "$SELECTION" -ne 0 ]; then
                    SELECTED_INDEX=$((SELECTION - 1))
                    METADATA_SOURCE="MusicBrainz"
                fi
                break
            else
                echo "Invalid selection. Please try again."
            fi
        done
    fi
fi

if [ "$METADATA_SOURCE" == "MusicBrainz" ]; then
    echo "Metadata found on MusicBrainz!"
    
    ALBUM_ARTIST=$(jq -r --argjson idx "$SELECTED_INDEX" '.releases[$idx]."artist-credit"[0].name' /tmp/musicbrainz_response.json)
    ALBUM_TITLE=$(jq -r --argjson idx "$SELECTED_INDEX" '.releases[$idx].title' /tmp/musicbrainz_response.json)
    YEAR=$(jq -r --argjson idx "$SELECTED_INDEX" '.releases[$idx].date' /tmp/musicbrainz_response.json | cut -d'-' -f1)
    TRACK_COUNT=$(jq --argjson idx "$SELECTED_INDEX" '.releases[$idx].media[0]."track-count"' /tmp/musicbrainz_response.json)
    MBID=$(jq -r --argjson idx "$SELECTED_INDEX" '.releases[$idx].id' /tmp/musicbrainz_response.json)
    RELEASE_URL="https://musicbrainz.org/release/$MBID"

    # --- Genre Selection ---
    GENRES=($(jq -r --argjson idx "$SELECTED_INDEX" '.releases[$idx].genres[].name' /tmp/musicbrainz_response.json))
    if [ ${#GENRES[@]} -gt 0 ]; then
        if [ ${#GENRES[@]} -gt 1 ]; then
            echo "Found multiple genres. Please choose one:"
            for i in "${!GENRES[@]}"; do
                echo "  $((i+1))) ${GENRES[$i]}"
            done
            read -p "Enter your choice [1-${#GENRES[@]}]: " GENRE_CHOICE
            GENRE=${GENRES[$((GENRE_CHOICE-1))]}
        else
            GENRE=${GENRES[0]}
        fi
        echo "Selected genre: $GENRE"
    fi

    # --- Fetch Cover Art ---
    COVER_ART_FOUND=$(jq -r --argjson idx "$SELECTED_INDEX" '.releases[$idx]."cover-art-archive".front' /tmp/musicbrainz_response.json)
    if [ "$COVER_ART_FOUND" == "true" ]; then
        echo "Front cover art found, downloading..."
        COVER_ART_URL="http://coverartarchive.org/release/$MBID/front"
        COVER_ART_FILE="/tmp/cover_art.jpg"
        curl -sL -o "$COVER_ART_FILE" "$COVER_ART_URL"
        if [ $? -eq 0 ] && [ -s "$COVER_ART_FILE" ]; then
            echo "Cover art downloaded successfully."
            COVER_ART_STATUS="Yes"
        else
            echo "Warning: Failed to download cover art."
            COVER_ART_FILE=""
        fi
    else
        echo "No front cover art found for this release."
    fi

    declare -a TRACK_TITLES
    declare -a COMPOSERS
    for i in $(seq 0 $((TRACK_COUNT - 1))); do
        title=$(jq -r --argjson idx "$SELECTED_INDEX" --argjson i "$i" '.releases[$idx].media[0].tracks[$i].title' /tmp/musicbrainz_response.json)
        TRACK_TITLES+=("$title")
        
        composer=$(jq -r --argjson idx "$SELECTED_INDEX" --argjson i "$i" '[.releases[$idx].media[0].tracks[$i].recording.relations[]? | select(.type == "composer") | .artist.name] | first // ""' /tmp/musicbrainz_response.json)
        COMPOSERS+=("$composer")
    done

else
    echo "Could not find metadata on MusicBrainz. Please enter it manually."
    read -p "Album Artist: " ALBUM_ARTIST
    read -p "Album Title: " ALBUM_TITLE
    read -p "Year: " YEAR
    read -p "Genre: " GENRE

    # --- Multi-disc Handling for Manual Entry ---
    read -p "Is this part of a multi-disc set? (y/n): " IS_MULTI
    if [[ "$IS_MULTI" =~ ^[Yy]$ ]]; then
        read -p "Please enter the disc number: " DISC_NUMBER
        if [[ "$DISC_NUMBER" =~ ^[0-9]+$ ]]; then
            DISC_SUBDIR="Disc $DISC_NUMBER"
        else
            echo "Invalid number, proceeding without disc subdirectory."
        fi
    fi

    declare -a TRACK_TITLES
    for i in $(seq 1 $TRACK_COUNT_ACTUAL); do
        read -p "Title for Track $i: " title
        TRACK_TITLES+=("$title")
    done
    TRACK_COUNT=$TRACK_COUNT_ACTUAL
fi

# --- Ripping Process ---

SAFE_ALBUM_ARTIST=$(echo "$ALBUM_ARTIST" | sed 's/\//_/g')
SAFE_ALBUM_TITLE=$(echo "$ALBUM_TITLE" | sed 's/\//_/g')

# Modify OUTPUT_DIR to include disc subdirectory if it exists
if [ -n "$DISC_SUBDIR" ]; then
    OUTPUT_DIR="$SAVE_DIR/$SAFE_ALBUM_ARTIST/$SAFE_ALBUM_TITLE/$DISC_SUBDIR"
else
    OUTPUT_DIR="$SAVE_DIR/$SAFE_ALBUM_ARTIST/$SAFE_ALBUM_TITLE"
fi

echo "Creating output directory: $OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR" || error_exit "Could not create output directory."

# --- Initialize Log File ---
LOG_FILE="$OUTPUT_DIR/rip_log.txt"
CUE_FILE="$OUTPUT_DIR/$SAFE_ALBUM_TITLE.cue"

{
    echo "CD Rip Log for: $ALBUM_ARTIST - $ALBUM_TITLE"
    if [ -n "$DISC_SUBDIR" ]; then echo "Disc: ${DISC_SUBDIR##* }"; fi
    echo "Rip started on: $(date)"
    echo "Ripped with script version: $SCRIPT_REVISION"
    echo "Output Format: ${ENCODER^^}"
    if [ "$METADATA_SOURCE" == "MusicBrainz" ]; then
        echo "MusicBrainz Release URL: $RELEASE_URL"
    else
        echo "Metadata entered manually."
    fi
    echo "Selected Genre: $GENRE"
    echo "Cover Art Embedded: $COVER_ART_STATUS"
    echo ""
    echo "--- Tool Versions ---"
    cdparanoia --version 2>&1 | head -n 1
    case $ENCODER in
        flac) flac --version | head -n 1; metaflac --version | head -n 1 ;;
        mp3) lame --version | head -n 1 ;;
        ogg) oggenc --version | head -n 1 ;;
        wav) echo "Encoder: WAV (native cdparanoia output)" ;;
    esac
    echo ""
    echo "--- Drive Information ---"
    echo "Ripping Device: $CD_DEVICE"
    # Extract just the drive model from the initial TOC check
    DRIVE_MODEL=$(grep 'CDROM model' /tmp/cdparanoia_toc.txt | sed 's/CDROM model sensed sensed://g' | xargs)
    if [ -n "$DRIVE_MODEL" ]; then
        echo "Drive Model: $DRIVE_MODEL"
    fi
    echo "=============================================================================="
    echo ""
    echo "--- cdparanoia Table of Contents ---"
    cat /tmp/cdparanoia_toc.txt
    echo "------------------------------------------------------------------------------"
} > "$LOG_FILE"

# --- HDA (Hidden Track One Audio) Ripping ---
if grep -q '^[[:space:]]*0\.' /tmp/cdparanoia_toc.txt; then
    echo "Hidden track (pre-gap audio) found. Ripping track 0..."
    HDA_FILE="$OUTPUT_DIR/00. Hidden Track.$EXTENSION"
    cdparanoia -q -d "$CD_DEVICE" 0 - | flac -s --best -o "$HDA_FILE"
    if [ $? -eq 0 ]; then
        echo "Successfully ripped hidden track."
        echo "Hidden Track (Track 0): Ripped to $HDA_FILE" >> "$LOG_FILE"
    else
        echo "Warning: Failed to rip hidden track."
        echo "Hidden Track (Track 0): FAILED" >> "$LOG_FILE"
    fi
    echo "------------------------------------------------------------------------------" >> "$LOG_FILE"
fi


# --- Generate CUE Sheet ---
{
    echo "PERFORMER \"$ALBUM_ARTIST\""
    echo "TITLE \"$ALBUM_TITLE\""
} > "$CUE_FILE"

for i in $(seq 1 $TRACK_COUNT); do
    TRACK_NUM=$(printf "%02d" $i)
    TRACK_TITLE=${TRACK_TITLES[$((i-1))]}
    COMPOSER=${COMPOSERS[$((i-1))]}
    SAFE_TRACK_TITLE=$(echo "$TRACK_TITLE" | sed 's/\//_/g')
    OUTPUT_FILE="$OUTPUT_DIR/$TRACK_NUM. $SAFE_TRACK_TITLE.$EXTENSION"
    
    {
        echo "  FILE \"$TRACK_NUM. $SAFE_TRACK_TITLE.$EXTENSION\" WAVE"
        echo "    TRACK $(printf "%02d" $i) AUDIO"
        echo "      TITLE \"$TRACK_TITLE\""
        echo "      PERFORMER \"$ALBUM_ARTIST\""
        if [ -n "$COMPOSER" ]; then echo "      COMPOSER \"$COMPOSER\""; fi
        echo "      INDEX 01 00:00:00"
    } >> "$CUE_FILE"

    echo "Ripping Track $i of $TRACK_COUNT: '$TRACK_TITLE' to ${EXTENSION^^}"

    COMPOSER_TAG=""
    if [ -n "$COMPOSER" ]; then COMPOSER_TAG="-T COMPOSER=$COMPOSER"; fi

    case $ENCODER in
        flac)
            PICTURE_OPTION=""
            if [ -n "$COVER_ART_FILE" ]; then PICTURE_OPTION="--picture=$COVER_ART_FILE"; fi
            cdparanoia -q -d "$CD_DEVICE" "$i" - 2>> "$LOG_FILE" | flac -s --best --verify $PICTURE_OPTION -T "ARTIST=$ALBUM_ARTIST" -T "ALBUM=$ALBUM_TITLE" -T "TITLE=$TRACK_TITLE" -T "TRACKNUMBER=$i" -T "DATE=$YEAR" -T "GENRE=$GENRE" $COMPOSER_TAG - -o "$OUTPUT_FILE"
            ;;
        wav)
            cdparanoia -q -d "$CD_DEVICE" "$i" "$OUTPUT_FILE" 2>> "$LOG_FILE"
            ;;
        mp3)
            cdparanoia -q -d "$CD_DEVICE" "$i" - 2>> "$LOG_FILE" | lame -S -b 320 --add-id3v2 --tt "$TRACK_TITLE" --ta "$ALBUM_ARTIST" --tl "$ALBUM_TITLE" --ty "$YEAR" --tn "$i" --tg "$GENRE" --tc "$COMPOSER" - "$OUTPUT_FILE"
            ;;
        ogg)
            cdparanoia -q -d "$CD_DEVICE" "$i" - 2>> "$LOG_FILE" | oggenc -Q -q 10 -a "$ALBUM_ARTIST" -l "$ALBUM_TITLE" -t "$TRACK_TITLE" -N "$i" -d "$YEAR" -G "$GENRE" -C "COMPOSER=$COMPOSER" -o "$OUTPUT_FILE" -
            ;;
    esac

    if [ $? -eq 0 ]; then
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        echo "Track $i ('$TRACK_TITLE'): OK" >> "$LOG_FILE"
    else
        echo "Warning: There was an issue ripping or encoding Track $i."
        echo "Track $i ('$TRACK_TITLE'): FAILED" >> "$LOG_FILE"
    fi
done

# --- Post-Processing ---
if [ "$ENCODER" == "flac" ]; then
    echo "Applying ReplayGain tags to FLAC files..."
    metaflac --add-replay-gain "$OUTPUT_DIR"/*.flac
    echo "ReplayGain scanning complete." >> "$LOG_FILE"
fi


# --- Finalization ---
{
    echo ""
    echo "--- File Integrity (MD5 Checksums) ---"
} >> "$LOG_FILE"
(cd "$OUTPUT_DIR" && md5sum -- *."$EXTENSION" >> "$LOG_FILE")

{
    echo ""
    echo "--- Rip Summary ---"
    echo "Successfully ripped and encoded $SUCCESS_COUNT of $TRACK_COUNT tracks."
    echo ""
    echo "Files created:"
    ls -1 "$OUTPUT_DIR"
    echo "=============================================================================="
    echo "Rip completed on: $(date)"
} >> "$LOG_FILE"

cleanup
echo "CD ripping complete!"
echo "A detailed log has been saved to: $LOG_FILE"
echo "A CUE sheet has been saved to: $CUE_FILE"

# Eject the disc
echo "Ejecting disc..."
eject "$CD_DEVICE"

exit 0


