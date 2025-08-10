# SimpleCDRipper

This is a simple and fast utility to RIP your CD collection to lossless or lossy formats. Uses MusicBrainz and pulls in cover art while ripping. Allows adding in info for unknown/bootleg CDs during RIP if they're not in MusicBrainz. It's designed to create high-quality, archival-grade digital copies of your music collection, complete with detailed metadata, cover art, and a verification log.

### The script automates the entire process, from looking up album information online to tagging the files and organizing them into a clean directory structure (Artist/Album/XX. Track.ext).
Features

- Multiple Formats: Rip to FLAC (lossless), WAV (uncompressed), MP3 (320kbps), or OGG (~500kbps).

- Automatic Metadata: Fetches album, artist, track titles, year, and genre from the MusicBrainz database.

- Cover Art: Automatically downloads and embeds front cover art where available.

- Advanced Tagging: Handles composer tags for classical music and allows you to select a genre if multiple are found.

- ReplayGain: Scans FLAC files to add ReplayGain tags, ensuring consistent playback volume across your library.

- Archival Logging: Creates a detailed rip_log.txt for each album, containing tool versions, drive analysis, MD5 checksums for file verification, and the MusicBrainz release URL.

- CUE Sheet: Generates a .cue file for preserving the CD's track layout.

- Hidden Track Ripping: Detects and rips audio from the pre-gap (Hidden Track 1 Audio) if it exists.

- Auto-Eject: Ejects the CD tray upon successful completion.

## Dependencies

To use all features of this script, you will need to have the following command-line tools installed on your Linux system. You can typically install them using your distribution's package manager (e.g., apt, dnf, zypper, pacman).

### Core Dependencies:

- cdparanoia: For securely ripping audio from the CD.

- curl: For communicating with the MusicBrainz API.

- jq: For parsing the metadata returned by MusicBrainz.

- md5sum: For creating file integrity checksums.

- eject: For ejecting the CD tray.

### Format-Specific Dependencies:

- flac: Required for ripping to FLAC format.

- metaflac: Required for ReplayGain scanning (usually included with flac).

- lame: Required for ripping to MP3 format.

- oggenc: Required for ripping to OGG (Vorbis) format.

### Usage

- Save the script to a file (e.g., SimpleCDRipper.sh).

- Make it executable: chmod +x SimpleCDRipper.sh

- Run it from your terminal: ./SimpleCDRipper.sh

The script will then guide you through the process.

# Handling Unknown Discs

If you insert a CD that cannot be found in the MusicBrainz database, the script will not fail. Instead, it will fall back to a manual entry mode. It will prompt you for the following information before it begins ripping:

- Album Artist

- Album Title

- Year

- Genre

- Title for each track, one by one.

- Disc Number (If part of set)

Once you have provided this information, the script will proceed with the rip, tagging, and file organization just as it would with automatically fetched data.
