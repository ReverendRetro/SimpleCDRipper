import sys
import os
import subprocess
import json
import requests  # Use the requests library for more robust HTTP handling
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QPushButton, QComboBox, QTableWidget,
    QTableWidgetItem, QProgressBar, QTextEdit, QFileDialog, QMessageBox,
    QHeaderView, QCheckBox, QDialog, QDialogButtonBox, QListWidget
)
from PyQt6.QtCore import QThread, pyqtSignal, QSettings, Qt
from PyQt6.QtGui import QPixmap, QIcon

# --- Configuration ---
# Set to True to enable detailed logging in the app's log window for debugging.
VERBOSE = False

# --- Main Application Window ---
class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SimpleCDRipper")
        self.setGeometry(100, 100, 800, 600)
        self.setWindowIcon(self.get_app_icon())

        # Load settings
        self.settings = QSettings("Gemini", "SimpleCDRipper")

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.init_ui()

        # Initialize worker thread
        self.worker = None

    def get_app_icon(self):
        # Create a simple icon programmatically to avoid external files
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        # This is a placeholder icon. A real app would load an SVG or PNG.
        return QIcon(pixmap)

    def init_ui(self):
        # --- Top Section: Drive and Lookup ---
        top_layout = QHBoxLayout()
        self.drive_combo = QComboBox()
        self.populate_drives()
        top_layout.addWidget(QLabel("CD Drive:"))
        top_layout.addWidget(self.drive_combo)
        
        self.lookup_button = QPushButton("Lookup CD")
        self.lookup_button.clicked.connect(self.start_lookup)
        top_layout.addWidget(self.lookup_button)
        
        self.eject_button = QPushButton("Eject")
        self.eject_button.clicked.connect(self.eject_cd)
        top_layout.addWidget(self.eject_button)
        
        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.open_settings)
        top_layout.addWidget(self.settings_button)

        self.layout.addLayout(top_layout)

        # --- Middle Section: Album Info and Tracklist ---
        middle_layout = QHBoxLayout()
        
        # Left side: Album Info & Cover Art
        info_layout = QVBoxLayout()
        info_grid = QGridLayout()

        info_grid.addWidget(QLabel("Artist:"), 0, 0)
        self.artist_edit = QLineEdit()
        info_grid.addWidget(self.artist_edit, 0, 1, 1, 2)

        info_grid.addWidget(QLabel("Album:"), 1, 0)
        self.album_edit = QLineEdit()
        info_grid.addWidget(self.album_edit, 1, 1, 1, 2)

        info_grid.addWidget(QLabel("Year:"), 2, 0)
        self.year_edit = QLineEdit()
        info_grid.addWidget(self.year_edit, 2, 1, 1, 2)
        
        info_grid.addWidget(QLabel("Disc #:"), 3, 0)
        self.disc_num_edit = QLineEdit()
        info_grid.addWidget(self.disc_num_edit, 3, 1)
        self.disc_total_edit = QLineEdit()
        info_grid.addWidget(self.disc_total_edit, 3, 2)
        
        self.cover_art_label = QLabel("Cover Art")
        self.cover_art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_art_label.setFixedSize(200, 200)
        self.cover_art_label.setStyleSheet("border: 1px solid grey;")

        self.change_cover_button = QPushButton("Change Cover")
        self.change_cover_button.clicked.connect(self.change_cover_art)

        info_layout.addLayout(info_grid)
        info_layout.addWidget(self.cover_art_label)
        info_layout.addWidget(self.change_cover_button)
        info_layout.addStretch()

        middle_layout.addLayout(info_layout)

        # Right side: Tracklist
        self.track_table = QTableWidget()
        self.track_table.setColumnCount(2)
        self.track_table.setHorizontalHeaderLabels(["Track #", "Title"])
        self.track_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.track_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        middle_layout.addWidget(self.track_table)

        self.layout.addLayout(middle_layout)

        # --- Bottom Section: Output and Ripping ---
        output_grid = QGridLayout()
        
        output_grid.addWidget(QLabel("Output Format:"), 0, 0)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["FLAC", "WAV", "MP3", "OGG"])
        self.format_combo.setCurrentText(self.settings.value("defaultFormat", "FLAC"))
        output_grid.addWidget(self.format_combo, 0, 1)

        output_grid.addWidget(QLabel("Save Location:"), 1, 0)
        self.save_location_edit = QLineEdit(self.settings.value("defaultSavePath", os.path.expanduser("~/Music")))
        output_grid.addWidget(self.save_location_edit, 1, 1)
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self.browse_save_location)
        output_grid.addWidget(self.browse_button, 1, 2)
        
        self.layout.addLayout(output_grid)

        # --- Progress and Status ---
        self.album_progress = QProgressBar()
        self.album_progress.setFormat("Overall Progress: %p%")
        self.layout.addWidget(self.album_progress)

        self.status_label = QLabel("Ready.")
        self.layout.addWidget(self.status_label)
        
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.layout.addWidget(self.log_output)

        self.rip_button = QPushButton("Rip CD")
        self.rip_button.clicked.connect(self.start_rip)
        self.layout.addWidget(self.rip_button)

    def populate_drives(self):
        # Find all /dev/sr* devices
        drives = [os.path.join("/dev", d) for d in os.listdir("/dev") if d.startswith("sr")]
        self.drive_combo.addItems(drives)

    def start_lookup(self):
        self.clear_fields()
        self.status_label.setText("Looking up CD...")
        self.log_output.clear()
        self.lookup_button.setEnabled(False)
        
        device = self.drive_combo.currentText()
        self.worker = LookupWorker(device)
        self.worker.finished.connect(self.lookup_finished)
        self.worker.error.connect(self.handle_error)
        self.worker.log_message.connect(self.log_output.append)
        self.worker.start()

    def lookup_finished(self, metadata):
        self.status_label.setText("Lookup complete.")
        self.lookup_button.setEnabled(True)
        if not metadata or ('releases' not in metadata or not metadata['releases']) and 'cdstub' not in metadata:
            self.handle_error("Could not find metadata for this disc.")
            return

        releases = metadata.get('releases', [])
        if not releases: # Handle CDStubs if no official release is found
            self.handle_error("Found a CDStub, but no official release. Please add to MusicBrainz or enter manually.")
            return

        if len(releases) > 1:
            dialog = ReleaseChoiceDialog(releases, self)
            if dialog.exec():
                selected_index = dialog.get_selected_index()
                if selected_index is not None:
                    self.populate_ui_from_release(releases[selected_index])
                else: # User chose manual entry
                    self.status_label.setText("Lookup cancelled. Please enter details manually.")
            else: # User cancelled
                self.status_label.setText("Lookup cancelled.")
        else:
            release = releases[0]
            reply = QMessageBox.question(self, 'Confirm Release',
                                         f"Found one release:\n\n{release['artist-credit'][0]['name']} - {release['title']}\n\nUse this one?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.Yes)
            if reply == QMessageBox.StandardButton.Yes:
                self.populate_ui_from_release(release)
            else:
                self.status_label.setText("Lookup rejected. Please enter details manually.")

    def populate_ui_from_release(self, release):
        self.artist_edit.setText(release['artist-credit'][0]['name'])
        self.album_edit.setText(release['title'])
        self.year_edit.setText(release['date'].split('-')[0] if 'date' in release else "")
        
        media = release['media'][0]
        self.disc_num_edit.setText(str(media.get('position', '1')))
        self.disc_total_edit.setText(str(release.get('media-count', '1')))

        self.track_table.setRowCount(len(media['tracks']))
        for i, track in enumerate(media['tracks']):
            self.track_table.setItem(i, 0, QTableWidgetItem(str(track['number'])))
            self.track_table.setItem(i, 1, QTableWidgetItem(track['title']))
            
        if release.get('cover-art-archive', {}).get('front', False):
            mbid = release['id']
            self.download_cover_art(mbid)

    def download_cover_art(self, mbid):
        self.status_label.setText("Downloading cover art...")
        url = f"http://coverartarchive.org/release/{mbid}/front-250"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            pixmap = QPixmap()
            pixmap.loadFromData(response.content)
            self.cover_art_label.setPixmap(pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio))
        except Exception as e:
            self.log_output.append(f"Could not download cover art: {e}")
            self.status_label.setText("Lookup complete (no cover art).")

    def change_cover_art(self):
        fname, _ = QFileDialog.getOpenFileName(self, 'Open file', os.path.expanduser("~"), "Image files (*.jpg *.png)")
        if fname:
            pixmap = QPixmap(fname)
            self.cover_art_label.setPixmap(pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio))

    def start_rip(self):
        rip_config = {
            "device": self.drive_combo.currentText(),
            "format": self.format_combo.currentText(),
            "save_path": self.save_location_edit.text(),
            "artist": self.artist_edit.text(),
            "album": self.album_edit.text(),
            "year": self.year_edit.text(),
            "disc_num": self.disc_num_edit.text(),
            "disc_total": self.disc_total_edit.text(),
            "tracks": [],
            "cover_art": self.cover_art_label.pixmap()
        }
        
        for row in range(self.track_table.rowCount()):
            rip_config["tracks"].append({
                "number": self.track_table.item(row, 0).text(),
                "title": self.track_table.item(row, 1).text()
            })
            
        if not all([rip_config['artist'], rip_config['album'], rip_config['tracks']]):
            self.handle_error("Artist, Album, and Track information cannot be empty.")
            return

        self.status_label.setText("Starting rip...")
        self.rip_button.setEnabled(False)
        self.lookup_button.setEnabled(False)
        
        self.worker = RipWorker(rip_config)
        self.worker.log_message.connect(self.log_output.append)
        self.worker.album_progress.connect(self.album_progress.setValue)
        self.worker.status_update.connect(self.status_label.setText)
        self.worker.finished.connect(self.rip_finished)
        self.worker.error.connect(self.handle_error)
        self.worker.start()

    def rip_finished(self):
        self.status_label.setText("Ripping complete!")
        self.rip_button.setEnabled(True)
        self.lookup_button.setEnabled(True)
        self.album_progress.setValue(100)
        if self.settings.value("autoEject", True, type=bool):
            self.eject_cd()

    def eject_cd(self):
        device = self.drive_combo.currentText()
        try:
            subprocess.run(["eject", device], check=True)
            self.status_label.setText(f"Ejected {device}.")
        except Exception as e:
            self.handle_error(f"Failed to eject {device}: {e}")

    def browse_save_location(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Directory", self.save_location_edit.text())
        if directory:
            self.save_location_edit.setText(directory)
            
    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def handle_error(self, message):
        self.status_label.setText(f"Error: {message}")
        self.rip_button.setEnabled(True)
        self.lookup_button.setEnabled(True)
        QMessageBox.critical(self, "Error", message)
        
    def clear_fields(self):
        self.artist_edit.clear()
        self.album_edit.clear()
        self.year_edit.clear()
        self.disc_num_edit.clear()
        self.disc_total_edit.clear()
        self.track_table.setRowCount(0)
        self.cover_art_label.clear()
        self.cover_art_label.setText("Cover Art")

# --- Settings Dialog ---
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.settings = QSettings("Gemini", "SimpleCDRipper")
        
        layout = QVBoxLayout(self)
        
        self.replaygain_check = QCheckBox("Apply ReplayGain to FLAC files")
        self.replaygain_check.setChecked(self.settings.value("replayGain", True, type=bool))
        layout.addWidget(self.replaygain_check)
        
        self.hda_check = QCheckBox("Rip hidden track (HDA) if found")
        self.hda_check.setChecked(self.settings.value("ripHDA", True, type=bool))
        layout.addWidget(self.hda_check)
        
        self.eject_check = QCheckBox("Auto-eject disc after ripping")
        self.eject_check.setChecked(self.settings.value("autoEject", True, type=bool))
        layout.addWidget(self.eject_check)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def accept(self):
        self.settings.setValue("replayGain", self.replaygain_check.isChecked())
        self.settings.setValue("ripHDA", self.hda_check.isChecked())
        self.settings.setValue("autoEject", self.eject_check.isChecked())
        super().accept()

# --- Release Choice Dialog ---
class ReleaseChoiceDialog(QDialog):
    def __init__(self, releases, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Multiple Releases Found")
        self.selected_index = None
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Please choose the correct release or select manual entry:"))
        
        self.list_widget = QListWidget()
        for release in releases:
            item_text = f"{release['artist-credit'][0]['name']} - {release['title']}"
            self.list_widget.addItem(item_text)
        layout.addWidget(self.list_widget)
        
        manual_button = QPushButton("Enter Manually")
        manual_button.clicked.connect(self.select_manual)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.addButton(manual_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        if self.list_widget.currentItem():
            self.selected_index = self.list_widget.currentRow()
        super().accept()
        
    def select_manual(self):
        self.selected_index = None
        super().accept()

    def get_selected_index(self):
        return self.selected_index

# --- Worker Threads ---

class LookupWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    log_message = pyqtSignal(str)

    def __init__(self, device):
        super().__init__()
        self.device = device

    def run(self):
        try:
            self.log_message.emit(f"Getting Table of Contents from {self.device}...")
            proc = subprocess.run(["cdparanoia", "-Q", "-d", self.device], capture_output=True, text=True, check=True)
            
            lines = proc.stderr.splitlines()
            if VERBOSE:
                self.log_message.emit("--- cdparanoia Raw Output ---")
                self.log_message.emit(proc.stderr)
                self.log_message.emit("-----------------------------")

            track_lines = [l for l in lines if l.strip() and l.strip().split()[0].endswith('.')]
            track_count = len(track_lines)

            if track_count == 0:
                self.error.emit("No audio tracks found.")
                return

            offsets = [line.split()[3] for line in track_lines]
            
            # Corrected leadout calculation to match the working Bash script
            first_track_sector = int(track_lines[0].split()[3])
            total_sectors = 0
            for line in lines:
                if line.strip().startswith("TOTAL"):
                    total_sectors = int(line.split()[1])
                    break
            
            leadout = first_track_sector + total_sectors
            
            toc_str = f"1+{track_count}+{leadout}+{'+'.join(offsets)}"
            
            self.log_message.emit(f"DEBUG: Final TOC String: {toc_str}")
            
            # Corrected URL: removed cover-art-archive from the inc parameter
            url = f"https://musicbrainz.org/ws/2/discid/-?toc={toc_str}&fmt=json&inc=artist-credits+recordings+release-groups"
            self.log_message.emit(f"DEBUG: Querying URL: {url}")
            headers = {'User-Agent': 'SimpleCDRipper/1.5 (https://gemini.google.com)'}
            
            response = requests.get(url, headers=headers, timeout=15)
            self.log_message.emit(f"DEBUG: Received HTTP Status: {response.status_code}")
            if VERBOSE:
                self.log_message.emit("--- Server Raw Response ---")
                self.log_message.emit(response.text)
                self.log_message.emit("---------------------------")
            
            response.raise_for_status()
            
            data = response.json()
            if ('releases' in data and data['releases']) or 'cdstub' in data:
                self.finished.emit(data)
            else:
                self.error.emit("No releases found for this disc.")

        except subprocess.CalledProcessError as e:
            self.error.emit(f"Failed to read CD: {e.stderr}")
        except requests.exceptions.RequestException as e:
            self.error.emit(f"Network error: {e}")
        except Exception as e:
            self.error.emit(str(e))

class RipWorker(QThread):
    log_message = pyqtSignal(str)
    album_progress = pyqtSignal(int)
    status_update = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config

    def run(self):
        try:
            total_tracks = len(self.config['tracks'])
            base_path = os.path.join(
                self.config['save_path'],
                self.sanitize_filename(self.config['artist']),
                self.sanitize_filename(self.config['album'])
            )
            
            # Add Disc subdirectory if disc number is specified
            output_path = base_path
            if self.config['disc_num']:
                output_path = os.path.join(base_path, f"Disc {self.config['disc_num']}")

            os.makedirs(output_path, exist_ok=True)
            
            cover_art_path = ""
            if self.config['cover_art'] and not self.config['cover_art'].isNull():
                cover_art_path = os.path.join(output_path, "cover.jpg")
                self.config['cover_art'].save(cover_art_path, "JPG")

            for i, track in enumerate(self.config['tracks']):
                track_num = int(track['number'])
                self.status_update.emit(f"Ripping Track {track_num}/{total_tracks}: '{track['title']}'")
                
                output_filename = os.path.join(
                    output_path,
                    f"{track_num:02d}. {self.sanitize_filename(track['title'])}.{self.config['format'].lower()}"
                )

                if self.config['format'] == "WAV":
                    # Special case for WAV: rip directly to the file
                    rip_cmd = ["cdparanoia", "-q", "-d", self.config['device'], str(track_num), output_filename]
                    self.log_message.emit(f"Ripping directly to WAV: {' '.join(rip_cmd)}")
                    result = subprocess.run(rip_cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        self.error.emit(f"cdparanoia failed for track {track_num}: {result.stderr}")
                        return
                else:
                    # Pipe for all other formats
                    rip_cmd = ["cdparanoia", "-q", "-d", self.config['device'], str(track_num), "-"]
                    encoder_cmd = self.get_encoder_cmd(track, cover_art_path, output_filename)
                    
                    self.log_message.emit(f"Ripping: {' '.join(rip_cmd)}")
                    self.log_message.emit(f"Encoding: {' '.join(encoder_cmd)}")

                    rip_proc = subprocess.Popen(rip_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    enc_proc = subprocess.Popen(encoder_cmd, stdin=rip_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    
                    rip_proc.stdout.close()
                    
                    enc_stderr = enc_proc.communicate()[1]
                    
                    if enc_proc.returncode != 0:
                        self.error.emit(f"Encoder failed for track {track_num}: {enc_stderr.decode()}")
                        return
                    
                self.album_progress.emit(int((i + 1) / total_tracks * 100))

            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))
            
    def get_encoder_cmd(self, track, cover_art_path, output_filename):
        artist = self.config['artist']
        album = self.config['album']
        year = self.config['year']
        track_num = track['number']
        title = track['title']
        disc_num = self.config['disc_num']
        disc_total = self.config['disc_total']
        
        fmt = self.config['format']
        if fmt == "FLAC":
            cmd = ["flac", "-s", "--best", "--verify",
                   "-T", f"ARTIST={artist}",
                   "-T", f"ALBUM={album}",
                   "-T", f"TITLE={title}",
                   "-T", f"TRACKNUMBER={track_num}",
                   "-T", f"DATE={year}",
                   "-", "-o", output_filename]
            if disc_num: cmd.insert(3, f"-T DISCNUMBER={disc_num}")
            if disc_total: cmd.insert(3, f"-T TOTALDISCS={disc_total}")
            if cover_art_path: cmd.insert(3, f"--picture={cover_art_path}")
            return cmd
        elif fmt == "MP3":
            cmd = ["lame", "-S", "-b", "320", "--add-id3v2",
                    "--tt", title, "--ta", artist, "--tl", album,
                    "--ty", year, "--tn", track_num]
            if disc_num and disc_total: cmd.extend(["--tv", f"TPOS={disc_num}/{disc_total}"])
            cmd.extend(["-", output_filename])
            return cmd
        elif fmt == "OGG":
            cmd = ["oggenc", "-Q", "-q", "10",
                    "-a", artist, "-l", album, "-t", title,
                    "-N", track_num, "-d", year]
            if disc_num: cmd.extend(["-c", f"DISCNUMBER={disc_num}"])
            if disc_total: cmd.extend(["-c", f"TOTALDISCS={disc_total}"])
            cmd.extend(["-o", output_filename, "-"])
            return cmd
        return []

    def sanitize_filename(self, name):
        return "".join(c for c in name if c.isalnum() or c in (' ', '.', '_')).rstrip()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = App()
    ex.show()
    sys.exit(app.exec())
