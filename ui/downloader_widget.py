import os
import sys
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
                               QPushButton, QLabel, QCheckBox, QFileDialog, 
                               QMessageBox, QGroupBox, QLineEdit, QSplitter,
                               QComboBox, QSpinBox, QListWidget, QListWidgetItem,
                               QDialog, QProgressBar)
from PySide6.QtCore import Qt, QProcess, QTimer, QSettings, QThread, Signal, QProcessEnvironment
from core.yt_dlp_manager import get_latest_yt_dlp_version, get_local_yt_dlp_version, update_yt_dlp, remove_id_from_filenames, fix_vtt_overlap_in_directory, export_subtitles_to_text, get_yt_dlp_executable_path, download_yt_dlp_binary

class UpdateCheckWorker(QThread):
    finished = Signal(bool, str)
    download_progress = Signal(int, int)
    download_started = Signal()
    
    def run(self):
        binary_path = get_yt_dlp_executable_path()
        if not os.path.exists(binary_path):
            self.download_started.emit()
            download_yt_dlp_binary(self._progress_callback)
            self.finished.emit(False, "yt-dlp downloaded successfully.")
            return

        local_v = get_local_yt_dlp_version()
        latest_v = get_latest_yt_dlp_version()
        
        needs_update = False
        msg = "yt-dlp is up to date."
        
        if not local_v:
            needs_update = True
            msg = "yt-dlp is not installed. Needs installation."
        elif latest_v:
            def norm_ver(v):
                try:
                    return ".".join(str(int(x)) for x in v.split("."))
                except ValueError:
                    return v

            if norm_ver(local_v) != norm_ver(latest_v):
                needs_update = True
                msg = f"Update available: {local_v} -> {latest_v}"
                
        self.finished.emit(needs_update, msg)
        
    def _progress_callback(self, dl, total):
        self.download_progress.emit(dl, total)

class UpdateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Installing/Updating yt-dlp")
        self.setFixedSize(500, 300)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        self.label = QLabel("Please wait while yt-dlp is installed or updated...")
        layout.addWidget(self.label)
        
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)
        
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: monospace;")
        layout.addWidget(self.text_edit)
        
    def append_text(self, text):
        self.text_edit.insertPlainText(text)
        self.text_edit.ensureCursorVisible()

class DownloaderWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.output_dir = os.path.expanduser("~/Downloads")
        self.process = None
        self._is_loading = True
        
        self.init_ui()
        self.load_settings()
        self._is_loading = False
        
        self.show_only_terminal(True)
        self.run_btn.setEnabled(False)
        self.term_output.append(">>> Checking for yt-dlp updates...\n")
        
        # Delay the version check slightly so the UI can load first
        QTimer.singleShot(1000, self.check_for_updates)

    def show_only_terminal(self, show: bool):
        self.top_splitter.setVisible(not show)
        self.cmd_preview.setVisible(not show)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # --- Top Section: Links and Settings ---
        self.top_splitter = QSplitter(Qt.Horizontal)
        
        # Left: Links Input
        links_group = QGroupBox("YouTube Links (One per line)")
        links_layout = QVBoxLayout(links_group)
        self.links_input = QTextEdit()
        self.links_input.setPlaceholderText("https://www.youtube.com/watch?v=...\nhttps://www.youtube.com/playlist?list=...")
        self.links_input.textChanged.connect(self.update_command_preview)
        links_layout.addWidget(self.links_input)
        self.top_splitter.addWidget(links_group)
        
        # Right: Settings
        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout(settings_group)
        
        # Output Dir
        dir_layout = QHBoxLayout()
        self.dir_label = QLabel(f"Save: {self.output_dir}")
        self.dir_btn = QPushButton("Change Folder")
        self.dir_btn.clicked.connect(self.change_output_dir)
        dir_layout.addWidget(self.dir_label)
        dir_layout.addWidget(self.dir_btn)
        settings_layout.addLayout(dir_layout)
        
        # Concurrent Fragments
        concurrent_layout = QHBoxLayout()
        concurrent_layout.addWidget(QLabel("Concurrent Fragments:"))
        self.spin_concurrent = QSpinBox()
        self.spin_concurrent.setRange(1, 100)
        self.spin_concurrent.setValue(20)
        self.spin_concurrent.valueChanged.connect(self.update_command_preview)
        concurrent_layout.addWidget(self.spin_concurrent)
        settings_layout.addLayout(concurrent_layout)

        # Update yt-dlp Button
        self.update_btn = QPushButton("🔄 Check for yt-dlp Update")
        self.update_btn.clicked.connect(self.manual_check_updates)
        settings_layout.addWidget(self.update_btn)

        # Playlist Checkbox
        self.chk_playlist = QCheckBox("Download as Playlist (--yes-playlist)")
        self.chk_playlist.stateChanged.connect(self.update_command_preview)
        settings_layout.addWidget(self.chk_playlist)
        
        # --- Video Section ---
        self.video_group = QGroupBox("Download Video")
        self.video_group.setCheckable(True)
        self.video_group.setChecked(True)
        self.video_group.toggled.connect(self.update_command_preview)
        video_layout = QVBoxLayout(self.video_group)
        
        # Video Quality / Format Dropdown
        quality_layout = QHBoxLayout()
        quality_layout.addWidget(QLabel("Quality:"))
        self.combo_quality = QComboBox()
        self.combo_quality.addItems([
            "bestvideo[vcodec!=av01]+bestaudio/best (Best Available)",
            "bestvideo[height<=1080][vcodec!=av01]+bestaudio/best[height<=1080] (1080p Best)",
            "bestvideo[height<=2160][vcodec!=av01]+bestaudio/best[height<=2160] (4K Best)",
            "bestvideo[height<=720][vcodec!=av01]+bestaudio/best[height<=720] (720p)",
            "bestvideo[height<=480][vcodec!=av01]+bestaudio/best[height<=480] (480p)",
            "bestaudio/best (Audio Only)"
        ])
        self.combo_quality.currentIndexChanged.connect(self.update_command_preview)
        quality_layout.addWidget(self.combo_quality)
        video_layout.addLayout(quality_layout)
        
        # Merge Format Dropdown
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Output Format:"))
        self.combo_format = QComboBox()
        # The items will be populated based on the default quality via on_quality_changed
        self.combo_quality.currentIndexChanged.connect(self.on_quality_changed)
        self.combo_format.currentIndexChanged.connect(self.update_command_preview)
        format_layout.addWidget(self.combo_format)
        video_layout.addLayout(format_layout)
        
        settings_layout.addWidget(self.video_group)
        

        # --- Subtitles Section ---
        self.subs_group = QGroupBox("Subtitles")
        self.subs_group.setCheckable(True)
        self.subs_group.setChecked(True)
        self.subs_group.toggled.connect(self.on_subs_toggled)
        subs_layout = QVBoxLayout(self.subs_group)
        
        subs_options_layout = QHBoxLayout()
        
        # Left side: Languages
        langs_layout = QVBoxLayout()
        langs_layout.addWidget(QLabel("Languages:"))
        self.lang_list = QListWidget()
        self.lang_list.setMaximumHeight(90)
        langs = [("Arabic (ar)", "ar"), ("English (en)", "en"), ("French (fr)", "fr"), ("Spanish (es)", "es")]
        for text, code in langs:
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if code == "ar" else Qt.Unchecked)
            item.setData(Qt.UserRole, code)
            self.lang_list.addItem(item)
        self.lang_list.itemChanged.connect(self.update_command_preview)
        langs_layout.addWidget(self.lang_list)
        subs_options_layout.addLayout(langs_layout)
        
        # Right side: Options
        opts_layout = QVBoxLayout()
        self.chk_embed_subs = QCheckBox("Embed Subs")
        self.chk_embed_subs.setChecked(True)
        self.chk_embed_subs.stateChanged.connect(self.update_command_preview)
        
        self.chk_write_subs = QCheckBox("Write Subs")
        self.chk_write_subs.setChecked(True)
        self.chk_write_subs.stateChanged.connect(self.update_command_preview)
        
        self.chk_write_auto_subs = QCheckBox("Write Auto Subs")
        self.chk_write_auto_subs.setChecked(True)
        self.chk_write_auto_subs.stateChanged.connect(self.update_command_preview)
        
        self.chk_fix_overlap = QCheckBox("Fix Subtitle Overlap")
        self.chk_fix_overlap.setChecked(True)
        self.chk_fix_overlap.stateChanged.connect(self.update_command_preview)
        
        self.chk_txt_export = QCheckBox("Export as Text (.txt)")
        self.chk_txt_export.setChecked(False)
        self.chk_txt_export.stateChanged.connect(self.update_command_preview)
        
        opts_layout.addWidget(self.chk_embed_subs)
        opts_layout.addWidget(self.chk_write_subs)
        opts_layout.addWidget(self.chk_write_auto_subs)
        opts_layout.addWidget(self.chk_fix_overlap)
        opts_layout.addWidget(self.chk_txt_export)
        opts_layout.addStretch()
        subs_options_layout.addLayout(opts_layout)
        
        subs_layout.addLayout(subs_options_layout)
        settings_layout.addWidget(self.subs_group)
        
        settings_layout.addStretch()
        
        self.top_splitter.addWidget(settings_group)
        self.top_splitter.setSizes([400, 450])
        
        main_layout.addWidget(self.top_splitter, stretch=2)
        
        # --- Middle Section: Command Preview ---
        cmd_group = QGroupBox("Final Command (Editable)")
        cmd_layout = QVBoxLayout(cmd_group)
        self.cmd_preview = QLineEdit()
        cmd_layout.addWidget(self.cmd_preview)
        
        btn_layout = QHBoxLayout()
        self.run_btn = QPushButton("🚀 Start Download")
        self.run_btn.setMinimumHeight(40)
        self.run_btn.clicked.connect(self.start_download)
        
        self.stop_btn = QPushButton("🛑 Stop Download")
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_download)
        
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.stop_btn)
        cmd_layout.addLayout(btn_layout)
        
        main_layout.addWidget(cmd_group, stretch=0)
        
        # --- Bottom Section: Terminal Output ---
        term_group = QGroupBox("Terminal Output")
        term_layout = QVBoxLayout(term_group)
        self.term_output = QTextEdit()
        self.term_output.setReadOnly(True)
        self.term_output.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: monospace;")
        term_layout.addWidget(self.term_output)
        
        main_layout.addWidget(term_group, stretch=3)
        
        self.update_command_preview()

    def load_settings(self):
        settings = QSettings("ScriptCutter", "Downloader")
        self.output_dir = settings.value("output_dir", os.path.expanduser("~/Downloads"))
        if hasattr(self, 'dir_label'):
            self.dir_label.setText(f"Save: {self.output_dir}")
            
        def get_bool(key, default):
            v = settings.value(key, default)
            return str(v).lower() in ['true', '1'] if isinstance(v, str) else bool(v)
            
        self.chk_playlist.setChecked(get_bool("chk_playlist", False))
        self.video_group.setChecked(get_bool("video_group", True))
        
        q_val = settings.value("combo_quality")
        if q_val:
            self.combo_quality.setCurrentText(settings.value("combo_quality", "bestvideo[height<=1080]+bestaudio/best[height<=1080] (1080p Best)"))
        self.on_quality_changed() # Force populate the format dropdown based on the loaded quality
        
        self.combo_format.setCurrentText(settings.value("combo_format", "Unspecified"))
        
        self.spin_concurrent.setValue(int(settings.value("spin_concurrent", 20)))
            
        self.subs_group.setChecked(get_bool("subs_group", True))
        self.chk_embed_subs.setChecked(get_bool("chk_embed_subs", True))
        self.chk_write_subs.setChecked(get_bool("chk_write_subs", True))
        self.chk_write_auto_subs.setChecked(get_bool("chk_write_auto_subs", True))
        if hasattr(self, 'chk_fix_overlap'):
            self.chk_fix_overlap.setChecked(get_bool("chk_fix_overlap", True))
        if hasattr(self, 'chk_txt_export'):
            self.chk_txt_export.setChecked(get_bool("chk_txt_export", False))
                
        checked_langs = settings.value("lang_list_checked", ["ar"])
        if isinstance(checked_langs, str):
            checked_langs = [checked_langs]
        for i in range(self.lang_list.count()):
            item = self.lang_list.item(i)
            if item.data(Qt.UserRole) in checked_langs:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
                
        links = settings.value("links_input", "")
        if links:
            self.links_input.setText(str(links))

    def save_settings(self):
        if getattr(self, '_is_loading', False):
            return
        settings = QSettings("ScriptCutter", "Downloader")
        settings.setValue("output_dir", self.output_dir)
        settings.setValue("chk_playlist", self.chk_playlist.isChecked())
        settings.setValue("video_group", self.video_group.isChecked())
        settings.setValue("combo_quality", self.combo_quality.currentText())
        settings.setValue("combo_format", self.combo_format.currentText())
        settings.setValue("spin_concurrent", self.spin_concurrent.value())
        settings.setValue("subs_group", self.subs_group.isChecked())
        settings.setValue("chk_embed_subs", self.chk_embed_subs.isChecked())
        settings.setValue("chk_write_subs", self.chk_write_subs.isChecked())
        settings.setValue("chk_write_auto_subs", self.chk_write_auto_subs.isChecked())
        if hasattr(self, 'chk_fix_overlap'):
            settings.setValue("chk_fix_overlap", self.chk_fix_overlap.isChecked())
        if hasattr(self, 'chk_txt_export'):
            settings.setValue("chk_txt_export", self.chk_txt_export.isChecked())
            
        checked_langs = []
        for i in range(self.lang_list.count()):
            item = self.lang_list.item(i)
            if item.checkState() == Qt.Checked:
                checked_langs.append(item.data(Qt.UserRole))
        settings.setValue("lang_list_checked", checked_langs)
        
        settings.setValue("links_input", self.links_input.toPlainText())

    def on_subs_toggled(self, checked):
        self.update_command_preview()

    def change_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Output Directory", self.output_dir)
        if dir_path:
            self.output_dir = dir_path
            self.dir_label.setText(f"Save: {self.output_dir}")
            self.update_command_preview()

    def manual_check_updates(self):
        if hasattr(self, 'update_checker') and self.update_checker.isRunning():
            QMessageBox.information(self, "Checking", "Already checking for updates...")
            return
            
        self.term_output.append(">>> Checking for yt-dlp updates manually...\n")
        self.check_for_updates()

    def check_for_updates(self):
        self.update_checker = UpdateCheckWorker()
        self.update_checker.download_started.connect(self.on_download_started)
        self.update_checker.download_progress.connect(self.on_download_progress)
        self.update_checker.finished.connect(self.on_check_finished)
        self.update_checker.start()

    def on_download_started(self):
        self.show_only_terminal(True)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        
        self.update_dialog = UpdateDialog(self)
        self.update_dialog.label.setText("Downloading standalone yt-dlp executable...")
        self.update_dialog.show()

    def on_download_progress(self, dl, total):
        if hasattr(self, 'update_dialog'):
            self.update_dialog.progress.setRange(0, total)
            self.update_dialog.progress.setValue(dl)

    def on_check_finished(self, needs_update, msg):
        if msg == "yt-dlp downloaded successfully." and hasattr(self, 'update_dialog'):
            self.update_dialog.accept()
            self.term_output.append(f">>> {msg}\n")
            self.show_only_terminal(False)
            self.run_btn.setEnabled(True)
            self.update_command_preview()
            return

        self.term_output.append(f">>> {msg}\n")
        if needs_update:
            self.run_binary_update()
        else:
            self.show_only_terminal(False)
            self.run_btn.setEnabled(True)

    def run_binary_update(self):
        self.show_only_terminal(True)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        
        self.update_dialog = UpdateDialog(self)
        self.update_dialog.label.setText("Updating yt-dlp executable...")
        self.update_dialog.show()
        
        self.term_output.append(">>> Updating yt-dlp...\n")
        self.process = QProcess()
        
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.on_update_finished)
        
        binary_path = get_yt_dlp_executable_path()
        self.process.start(binary_path, ["-U"])

    def on_update_finished(self, exit_code, exit_status):
        if hasattr(self, 'update_dialog'):
            self.update_dialog.accept()
            
        self.term_output.append(">>> Update finished.\n")
        self.show_only_terminal(False)
        self.run_btn.setEnabled(True)

    def on_quality_changed(self):
        q_text = self.combo_quality.currentText()
        current_fmt = self.combo_format.currentText()
        
        self.combo_format.blockSignals(True)
        self.combo_format.clear()
        
        if "Audio Only" in q_text:
            self.combo_format.addItems(["Unspecified", "mp3", "m4a", "wav", "flac"])
            if current_fmt not in ["Unspecified", "mp3", "m4a", "wav", "flac"]:
                self.combo_format.setCurrentText("Unspecified")
            else:
                self.combo_format.setCurrentText(current_fmt)
        else:
            self.combo_format.addItems(["Unspecified", "mp4", "mkv", "webm"])
            if current_fmt not in ["Unspecified", "mp4", "mkv", "webm"]:
                self.combo_format.setCurrentText("Unspecified")
            else:
                self.combo_format.setCurrentText(current_fmt)
                
        self.combo_format.blockSignals(False)
        self.update_command_preview()

    def update_command_preview(self, *args):
        links = self.links_input.toPlainText().strip().split('\n')
        links = [l.strip() for l in links if l.strip()]
        
        # Auto-detect playlist from first link if not manually checked
        if not self.chk_playlist.isChecked() and any("list=" in l for l in links):
            self.chk_playlist.blockSignals(True)
            self.chk_playlist.setChecked(True)
            self.chk_playlist.blockSignals(False)
            
        binary_path = get_yt_dlp_executable_path()
        cmd = [f'"{binary_path}"']
        
        # Paths
        cmd.append(f'-P "{self.output_dir}"')
        
        if self.chk_playlist.isChecked():
            cmd.append("--yes-playlist")
            
        # Quality and Format
        if getattr(self, 'video_group', None) and self.video_group.isChecked():
            q_text = self.combo_quality.currentText()
            q_format = q_text.split(" ")[0] # extract the format part before the space
            cmd.append(f'-f "{q_format}"')
            
            out_fmt = self.combo_format.currentText()
            if "Audio Only" in q_text:
                cmd.append("--extract-audio")
                if out_fmt != "Unspecified":
                    cmd.append(f"--audio-format {out_fmt}")
            else:
                if out_fmt != "Unspecified":
                    cmd.append(f"--merge-output-format {out_fmt}")
        elif getattr(self, 'video_group', None) and not self.video_group.isChecked():
            cmd.append("--skip-download")
        
        # Concurrent Fragments
        cmd.append(f"--concurrent-fragments {self.spin_concurrent.value()}")
        
        # Subtitles
        if self.subs_group.isChecked():
            # Get checked languages
            checked_langs = []
            for i in range(self.lang_list.count()):
                item = self.lang_list.item(i)
                if item.checkState() == Qt.Checked:
                    checked_langs.append(f"{item.data(Qt.UserRole)},{item.data(Qt.UserRole)}-*")
            
            if checked_langs:
                langs_str = ",".join(checked_langs)
                cmd.append(f'--sub-langs "{langs_str}"')
                
            if self.chk_embed_subs.isChecked():
                cmd.append("--embed-subs")
            if self.chk_write_subs.isChecked():
                cmd.append("--write-subs")
            if self.chk_write_auto_subs.isChecked():
                cmd.append("--write-auto-subs")
            
        for link in links:
            cmd.append(f'"{link}"')
            
        self.cmd_preview.setText(" ".join(cmd))
        
        if not getattr(self, '_is_loading', False):
            self.save_settings()

    def start_download(self):
        if self.process and self.process.state() == QProcess.Running:
            QMessageBox.warning(self, "Already Running", "A download process is already running.")
            return
            
        cmd_string = self.cmd_preview.text().strip()
        binary_path = get_yt_dlp_executable_path()
        if not cmd_string or cmd_string == f'"{binary_path}"':
            QMessageBox.warning(self, "No Links", "Please add some YouTube links first.")
            return

        self.term_output.clear()
        self.term_output.append(f">>> Running: {cmd_string}\n")
        
        self.process = QProcess()
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.on_download_finished)
        
        # Use sh -c on mac/linux or cmd.exe /c on windows
        if os.name == 'nt':
            self.process.start("cmd.exe", ["/c", cmd_string])
        else:
            self.process.start("sh", ["-c", cmd_string])
            
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.show_only_terminal(True)

    def handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode('utf-8', errors='replace')
        self.term_output.insertPlainText(data)
        self.term_output.ensureCursorVisible()
        if hasattr(self, 'update_dialog') and self.update_dialog.isVisible():
            self.update_dialog.append_text(data)

    def handle_stderr(self):
        data = self.process.readAllStandardError().data().decode('utf-8', errors='replace')
        self.term_output.insertPlainText(data)
        self.term_output.ensureCursorVisible()
        if hasattr(self, 'update_dialog') and self.update_dialog.isVisible():
            self.update_dialog.append_text(data)

    def stop_download(self):
        if self.process and self.process.state() == QProcess.Running:
            self.term_output.append("\n>>> Stopping download...\n")
            self.process.terminate()

    def on_download_finished(self, exit_code, exit_status):
        self.show_only_terminal(False)
        self.run_btn.setEnabled(True)
        if hasattr(self, 'stop_btn'):
            self.stop_btn.setEnabled(False)
            
        self.term_output.append(f"\n>>> Process finished with exit code {exit_code}.\n")
        
        self.term_output.append(">>> Starting post-processing to remove [id] from filenames...\n")
        remove_id_from_filenames(self.output_dir)
        
        if getattr(self, 'chk_fix_overlap', None) and self.chk_fix_overlap.isChecked():
            self.term_output.append(">>> Starting post-processing to fix overlapping subtitles...\n")
            fix_vtt_overlap_in_directory(self.output_dir)
            
        if getattr(self, 'chk_txt_export', None) and self.chk_txt_export.isChecked():
            self.term_output.append(">>> Starting post-processing to export raw text...\n")
            export_subtitles_to_text(self.output_dir)
            
        self.term_output.append(">>> Post-processing completed.\n")
