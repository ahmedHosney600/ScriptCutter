import sys
import os
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QSplitter, QTextEdit, QPushButton, QLabel, QListWidget,
                               QFileDialog, QMessageBox, QTabWidget, QInputDialog)
from PySide6.QtCore import Qt, QTimer, QUrl, QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QColor, QTextCharFormat, QTextCursor
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from core.parser import parse_script, parse_script_with_spans
from ui.settings_modal import SettingsModal
from utils.file_manager import load_settings, parse_subtitle_file
from ui.timeline_widget import TimelineWidget
from core.matcher import find_precise_clip_boundaries
from core.media_engine import generate_waveform_data
from core.exporter import export_clip 
from ui.downloader_widget import DownloaderWidget

# --- NEW: Custom Video Widget that detects Right-Clicks ---
class ClickableVideoWidget(QVideoWidget):
    rightClicked = Signal()
    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.rightClicked.emit()
        super().mousePressEvent(event)

class WaveformWorker(QThread):
    finished = Signal(list) 
    def __init__(self, video_path):
        super().__init__()
        self.video_path = video_path
    def run(self):
        peaks = generate_waveform_data(self.video_path)
        self.finished.emit(peaks)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MediaStudio Pro")
        self.resize(1200, 800) 
        self.app_settings = load_settings()
        
        self.current_video_path = None
        self.current_subtitles = []
        
        # --- NEW: Memory Cache for Clip Edits ---
        self.clip_bounds_cache = {}
        self.clip_names_cache = {} # Map of clip_id -> custom_name
        self.script_clip_spans = {} # Map of script clip id -> (start, end)
        self.current_active_clip_id = None
        self.preview_mode = False
        self.undo_stack = []
        self.redo_stack = []
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        self.main_tabs = QTabWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.main_tabs)
        
        # --- TAB 1: Cutter ---
        self.cutter_tab = QWidget()
        self.main_tabs.addTab(self.cutter_tab, "✂️ Cutter")
        main_layout = QVBoxLayout(self.cutter_tab)

        # --- TAB 2: Downloader ---
        self.downloader_tab = DownloaderWidget()
        self.main_tabs.addTab(self.downloader_tab, "⬇️ Downloader")

        # --- Top Menu / Action Bar ---
        action_bar = QHBoxLayout()
        self.import_video_btn = QPushButton("🎬 Import Video")
        self.import_video_btn.clicked.connect(self.import_video)
        self.settings_btn = QPushButton("⚙️ Settings")
        self.settings_btn.clicked.connect(self.open_settings)
        self.export_btn = QPushButton("✂️ Export Current Clip")
        self.export_btn.clicked.connect(self.export_current_clip) 
        self.batch_export_btn = QPushButton("🚀 Batch Export All")
        self.batch_export_btn.clicked.connect(self.batch_export_all) 
        
        action_bar.addWidget(self.import_video_btn)
        action_bar.addStretch() 
        action_bar.addWidget(self.settings_btn)
        action_bar.addWidget(self.export_btn)
        action_bar.addWidget(self.batch_export_btn)
        main_layout.addLayout(action_bar)

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # --- LEFT PANEL (The Script Hub) ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.clip_tabs = QTabWidget()
        
        # Tab 1: Script Clips
        self.script_tab = QWidget()
        script_layout = QVBoxLayout(self.script_tab)
        script_layout.setContentsMargins(0, 0, 0, 0)
        
        script_top_layout = QHBoxLayout()
        script_top_layout.addWidget(QLabel("<b>Script Importer</b> (Wrap clips in \"\"\")"))
        
        self.import_sub_btn = QPushButton("📝 Import Subtitles")
        self.import_sub_btn.clicked.connect(self.import_subtitle)
        script_top_layout.addWidget(self.import_sub_btn)
        
        script_layout.addLayout(script_top_layout)
        
        self.script_input = QTextEdit()
        self.script_input.setPlaceholderText('"""Paste your script segments here..."""')
        self.last_generated_text = ""
        self.script_input.textChanged.connect(self.check_script_changes)
        script_layout.addWidget(self.script_input)

        self.generate_btn = QPushButton("Generate Clips")
        self.generate_btn.setMinimumHeight(40)
        self.generate_btn.setEnabled(False) # Disabled initially
        self.generate_btn.setText("Clips Generated - Up to date")
        self.generate_btn.setStyleSheet("color: gray;")
        self.generate_btn.clicked.connect(self.process_script)
        script_layout.addWidget(self.generate_btn)

        self.script_clip_list = QListWidget()
        self.script_clip_list.itemClicked.connect(self.load_clip_to_timeline)
        script_layout.addWidget(self.script_clip_list)
        
        self.clip_tabs.addTab(self.script_tab, "📝 Script Clips")
        
        # Tab 2: Custom Clips
        self.custom_tab = QWidget()
        custom_layout = QVBoxLayout(self.custom_tab)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        
        self.custom_clip_list = QListWidget()
        self.custom_clip_list.itemClicked.connect(self.load_clip_to_timeline)
        custom_layout.addWidget(self.custom_clip_list)
        
        custom_btn_layout = QHBoxLayout()
        self.add_custom_btn = QPushButton("➕ Add Custom Clip")
        self.add_custom_btn.clicked.connect(self.add_custom_clip)
        self.delete_custom_btn = QPushButton("🗑️ Delete Selected")
        self.delete_custom_btn.clicked.connect(self.delete_custom_clip)
        custom_btn_layout.addWidget(self.add_custom_btn)
        custom_btn_layout.addWidget(self.delete_custom_btn)
        
        custom_layout.addLayout(custom_btn_layout)
        self.clip_tabs.addTab(self.custom_tab, "✂️ Custom Clips")

        left_layout.addWidget(self.clip_tabs)
        
        self.rename_btn = QPushButton("✏️ Rename Selected Clip")
        self.rename_btn.clicked.connect(self.rename_clip)
        left_layout.addWidget(self.rename_btn)
        
        splitter.addWidget(left_panel)

        # --- RIGHT PANEL (Viewer & Timeline) ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 1. ACTUAL VIDEO PLAYER (Now Clickable!)
        self.video_widget = ClickableVideoWidget()
        self.video_widget.setStyleSheet("background-color: #000000;")
        self.video_widget.rightClicked.connect(self.stop_playback) # Hook up the stop function!
        right_layout.addWidget(self.video_widget, stretch=2)
        
        self.status_label = QLabel("Waiting for media...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #aaaaaa; padding: 2px;")
        right_layout.addWidget(self.status_label)

        self.timeline_view = TimelineWidget()
        right_layout.addWidget(self.timeline_view, stretch=1)
        
        control_layout = QHBoxLayout()
        self.fit_btn = QPushButton("↔️ Fit to Screen")
        self.focus_btn = QPushButton("🔍 Focus on Clip") 
        self.fit_btn.clicked.connect(self.timeline_view.fit_to_screen)
        self.focus_btn.clicked.connect(self.timeline_view.focus_on_clip) 
        
        control_layout.addWidget(self.fit_btn)
        control_layout.addWidget(self.focus_btn) 
        control_layout.addStretch()
        right_layout.addLayout(control_layout)

        # Listeners
        self.timeline_view.playhead_jumped.connect(self.force_audio_jump)
        self.timeline_view.bounds_drag_finished.connect(self.save_clip_bounds) # Memory Saver & Undo Commit
        
        splitter.addWidget(right_panel)
        splitter.setSizes([360, 840])
        
        # --- TRUE AUDIO PLAYBACK ENGINE ---
        self.audio_output = QAudioOutput(self)
        self.media_player = QMediaPlayer(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget) 
        self.audio_output.setVolume(1.0)
        
        self.sync_timer = QTimer(self)
        self.sync_timer.setTimerType(Qt.PreciseTimer)
        self.sync_timer.timeout.connect(self.sync_playhead_to_audio)
        
        self.setup_shortcuts()

    # ==========================================
    # METHODS & LOGIC
    # ==========================================
    @property
    def clip_list(self):
        if self.clip_tabs.currentIndex() == 0:
            return self.script_clip_list
        return self.custom_clip_list

    def get_clip_id(self, item):
        if item.listWidget() == self.script_clip_list:
            return f"script_{self.script_clip_list.row(item)}"
        return f"custom_{self.custom_clip_list.row(item)}"

    def add_custom_clip(self):
        if not self.current_video_path:
            return
        start = 0.0
        end = self.timeline_view.total_duration
        
        count = self.custom_clip_list.count()
        clip_name = f"Custom Clip {count + 1}"
        self.custom_clip_list.addItem(clip_name)
        
        # Manually cache it
        clip_id = f"custom_{count}"
        self.clip_bounds_cache[clip_id] = {"start": start, "end": end}
        
        self.custom_clip_list.setCurrentRow(count)
        self.load_clip_to_timeline(self.custom_clip_list.currentItem())

    def rename_clip(self):
        item = self.clip_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Rename", "Please select a clip to rename first.")
            return
            
        clip_id = self.get_clip_id(item)
        current_name = self.clip_names_cache.get(clip_id, "")
        
        new_name, ok = QInputDialog.getText(self, "Rename Clip", "Enter custom tag to append:", text=current_name)
        if ok:
            clean_name = new_name.strip()
            if clean_name:
                self.clip_names_cache[clip_id] = clean_name
            elif clip_id in self.clip_names_cache:
                del self.clip_names_cache[clip_id]
                
            raw_text = item.text()
            if " [" in raw_text:
                raw_text = raw_text.split(" [")[0]
                
            if clean_name:
                item.setText(f"{raw_text} [{clean_name}]")
            else:
                item.setText(raw_text)

    def build_clip_export_name(self, clip_id, row_index):
        is_script = clip_id.startswith("script_")
        clip_type = "scripted" if is_script else "custom"
        
        base = f"{clip_type}_clip#({row_index + 1})"
        
        custom_name = self.clip_names_cache.get(clip_id, "")
        if custom_name:
            safe_name = "".join([c if c.isalnum() else "_" for c in custom_name])
            base += f"_{safe_name}"
            
        return base

    def delete_custom_clip(self):
        row = self.custom_clip_list.currentRow()
        if row >= 0:
            self.custom_clip_list.takeItem(row)
            clip_id = f"custom_{row}"
            if clip_id in self.clip_bounds_cache:
                del self.clip_bounds_cache[clip_id]
            if self.current_active_clip_id == clip_id:
                self.current_active_clip_id = None
    def clear_script_highlight(self):
        self.script_input.setExtraSelections([])

    def highlight_script_clip(self, clip_id):
        self.clear_script_highlight()
        if clip_id in self.script_clip_spans:
            start, end = self.script_clip_spans[clip_id]
            cursor = self.script_input.textCursor()
            # Position at end first, then anchor to start so the cursor ends up at the start position.
            cursor.setPosition(end)
            cursor.setPosition(start, QTextCursor.KeepAnchor)
            
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            
            format = QTextCharFormat()
            format.setBackground(QColor("yellow"))
            format.setForeground(QColor("black"))
            selection.format = format
            
            self.script_input.setExtraSelections([selection])
            self.script_input.setTextCursor(cursor)

    def check_script_changes(self):
        current_text = self.script_input.toPlainText()
        if current_text != self.last_generated_text:
            self.generate_btn.setEnabled(True)
            self.generate_btn.setText("Generate Clips")
            self.generate_btn.setStyleSheet("")
        else:
            self.generate_btn.setEnabled(False)
            self.generate_btn.setText("Clips Generated - Up to date")
            self.generate_btn.setStyleSheet("color: gray;")

    def process_script(self):
        raw_text = self.script_input.toPlainText()
        self.last_generated_text = raw_text
        self.check_script_changes()
        
        clips_with_spans = parse_script_with_spans(raw_text)
        
        self.script_clip_list.clear()
        self.script_clip_spans.clear()
        self.clear_script_highlight()
        
        # Clear ONLY script bounds from cache
        keys_to_remove = [k for k in self.clip_bounds_cache.keys() if str(k).startswith("script_")]
        for k in keys_to_remove:
            del self.clip_bounds_cache[k]
            
        if self.current_active_clip_id and str(self.current_active_clip_id).startswith("script_"):
            self.current_active_clip_id = None
        
        if clips_with_spans:
            for i, (clip_text, span_start, span_end) in enumerate(clips_with_spans):
                # Calculate bounds using the FULL text, before we truncate it for UI display!
                full_clean_text = clip_text.replace('\n', ' ').strip()
                start_time, end_time = find_precise_clip_boundaries(full_clean_text, self.current_subtitles)
                
                # Pre-populate the cache so load_clip_to_timeline doesn't have to guess
                clip_id = f"script_{i}"
                self.clip_bounds_cache[clip_id] = {"start": start_time, "end": end_time}
                self.script_clip_spans[clip_id] = (span_start, span_end)
                
                # Now truncate just for the UI
                display_text = full_clean_text
                if len(display_text) > 40:
                    display_text = display_text[:40] + "..."
                self.script_clip_list.addItem(f"Clip {i+1}: {display_text}")
        else:
            self.script_clip_list.addItem("No valid clips found. Make sure to use triple quotes.")
            
        self.setFocus()

    def open_settings(self):
        modal = SettingsModal(self.app_settings, self)
        if modal.exec():
            self.app_settings = load_settings() 
            self.setup_shortcuts()
    
    def save_clip_bounds(self, start, end):
        """Saves manual line adjustments to memory and tracks undo state."""
        print(f"save_clip_bounds called with {start}, {end}")
        if self.current_active_clip_id is not None:
            if self.current_active_clip_id in self.clip_bounds_cache:
                old_bounds = self.clip_bounds_cache[self.current_active_clip_id]
                print(f"old_bounds: {old_bounds}")
                if old_bounds["start"] != start or old_bounds["end"] != end:
                    print("Pushing to undo stack!")
                    self.undo_stack.append({
                        "clip_id": self.current_active_clip_id,
                        "old": old_bounds.copy(),
                        "new": {"start": start, "end": end}
                    })
                    self.redo_stack.clear()
            
            self.clip_bounds_cache[self.current_active_clip_id] = {"start": start, "end": end}

    def navigate_to_clip(self, clip_id):
        is_script = str(clip_id).startswith("script_")
        try:
            row = int(str(clip_id).split("_")[1])
        except IndexError:
            return
            
        target_list = self.script_clip_list if is_script else self.custom_clip_list
        self.clip_tabs.setCurrentIndex(0 if is_script else 1)
        target_list.setCurrentRow(row)
        
        item = target_list.item(row)
        if item:
            self.load_clip_to_timeline(item)

    def undo_edit(self):
        print(f"undo_edit called. Stack size: {len(self.undo_stack)}")
        if not self.undo_stack: return
        action = self.undo_stack.pop()
        clip_id = action["clip_id"]
        
        self.clip_bounds_cache[clip_id] = action["old"].copy()
        self.redo_stack.append(action)
        
        if self.current_active_clip_id != clip_id:
            self.navigate_to_clip(clip_id)
        else:
            bounds = action["old"]
            self.timeline_view.set_clip_bounds(bounds["start"], bounds["end"])

    def redo_edit(self):
        if not self.redo_stack: return
        action = self.redo_stack.pop()
        clip_id = action["clip_id"]
        
        self.clip_bounds_cache[clip_id] = action["new"].copy()
        self.undo_stack.append(action)
        
        if self.current_active_clip_id != clip_id:
            self.navigate_to_clip(clip_id)
        else:
            bounds = action["new"]
            self.timeline_view.set_clip_bounds(bounds["start"], bounds["end"])

    def load_clip_to_timeline(self, item):
        raw_list_text = item.text()
        
        clip_id = self.get_clip_id(item)
        self.current_active_clip_id = clip_id
        
        # Check if we already manually edited this clip in memory
        if clip_id not in self.clip_bounds_cache:
            if clip_id.startswith("script_"):
                # Fallback just in case, but this should be pre-populated now
                start_time, end_time = 0.0, 5.0 
            else:
                start_time, end_time = 0.0, 5.0 # Fallback for custom
            self.clip_bounds_cache[clip_id] = {"start": start_time, "end": end_time}
            
        bounds = self.clip_bounds_cache[clip_id]
        self.timeline_view.set_clip_bounds(bounds["start"], bounds["end"])
        
        if clip_id.startswith("script_"):
            self.highlight_script_clip(clip_id)
            
        self.setFocus()

    def import_video(self):
        video_path, _ = QFileDialog.getOpenFileName(self, "Select Video File", "", "Video Files (*.mp4 *.mkv *.mov)")
        if not video_path: return

        self.current_video_path = video_path
        self.media_player.setSource(QUrl.fromLocalFile(video_path))
        
        # Clear cache in case they loaded a new video with existing clips
        self.clip_bounds_cache.clear()
        
        file_name = os.path.basename(video_path)
        self.status_label.setText(f"Loading waveform for: {file_name}...")
        
        display_name = file_name if len(file_name) <= 15 else file_name[:12] + "..."
        full_status = f"✅ Video: {file_name}"
        
        self.import_video_btn.setText(f"✅ Video: {display_name}")
        self.import_video_btn.setToolTip(full_status)
        self.import_video_btn.setStyleSheet("background-color: #2e7d32; color: white;")
        
        self.waveform_worker = WaveformWorker(self.current_video_path)
        self.waveform_worker.finished.connect(self.on_waveform_ready)
        self.waveform_worker.start()

    def import_subtitle(self):
        sub_path, _ = QFileDialog.getOpenFileName(self, "Select Subtitle File", "", "Subtitle Files (*.srt *.vtt)")
        if not sub_path: return
        
        self.current_subtitles = parse_subtitle_file(sub_path)
        file_name = os.path.basename(sub_path)
        display_name = file_name if len(file_name) <= 15 else file_name[:12] + "..."
        full_status = f"✅ Subtitles: {file_name}"
        
        self.import_sub_btn.setText(f"✅ Subtitles: {display_name}")
        self.import_sub_btn.setToolTip(full_status)
        self.import_sub_btn.setStyleSheet("background-color: #2e7d32; color: white;")

    def on_waveform_ready(self, peaks):
        duration = self.current_subtitles[-1]['end'] if self.current_subtitles else 100
        self.timeline_view.set_waveform(peaks, duration)
        self.status_label.setText(f"Loaded: {self.current_video_path.split('/')[-1]} | Waveform Ready.")

    # ==========================================
    # SHORTCUTS & AUDIO SYNC
    # ==========================================
    def setup_shortcuts(self):
        sc_forward = self.app_settings.get("sc_play_forward", "L")
        sc_backward = self.app_settings.get("sc_play_backward", "J")
        sc_stop = self.app_settings.get("sc_stop", "K")
        
        sc_mark_start = self.app_settings.get("sc_mark_start", "I")
        sc_mark_end = self.app_settings.get("sc_mark_end", "O")
        sc_snap_start = self.app_settings.get("sc_snap_start", "Shift+I")
        sc_snap_end = self.app_settings.get("sc_snap_end", "Shift+O")
        
        sc_preview_cut = self.app_settings.get("sc_preview_cut", "Alt+Space")
        sc_review_cut = self.app_settings.get("sc_review_cut", "Shift+Space")
        
        QShortcut(QKeySequence(sc_forward), self).activated.connect(self.play_forward)
        QShortcut(QKeySequence(sc_stop), self).activated.connect(self.stop_playback)
        QShortcut(QKeySequence(sc_backward), self).activated.connect(self.play_backward)

        QShortcut(QKeySequence(sc_mark_start), self).activated.connect(self.mark_start)
        QShortcut(QKeySequence(sc_mark_end), self).activated.connect(self.mark_end)
        QShortcut(QKeySequence(sc_snap_start), self).activated.connect(self.snap_playhead_to_start)
        QShortcut(QKeySequence(sc_snap_end), self).activated.connect(self.snap_playhead_to_end)

        QShortcut(QKeySequence(sc_preview_cut), self).activated.connect(self.play_in_to_out)
        QShortcut(QKeySequence(sc_review_cut), self).activated.connect(self.play_review_cut)
        
        self.nudge_short = float(self.app_settings.get("nudge_short", 0.1))
        self.nudge_med = float(self.app_settings.get("nudge_med", 1.0))
        self.nudge_long = float(self.app_settings.get("nudge_long", 5.0))
        
        sc_n_s_l = self.app_settings.get("sc_nudge_start_left", "Alt+Left")
        sc_n_s_r = self.app_settings.get("sc_nudge_start_right", "Alt+Right")
        sc_n_e_l = self.app_settings.get("sc_nudge_end_left", "Ctrl+Left")
        sc_n_e_r = self.app_settings.get("sc_nudge_end_right", "Ctrl+Right")
        
        QShortcut(QKeySequence(sc_n_s_l), self).activated.connect(lambda: self.nudge_start_line(-self.nudge_short))
        QShortcut(QKeySequence(sc_n_s_r), self).activated.connect(lambda: self.nudge_start_line(self.nudge_short))
        QShortcut(QKeySequence(sc_n_e_l), self).activated.connect(lambda: self.nudge_end_line(-self.nudge_short))
        QShortcut(QKeySequence(sc_n_e_r), self).activated.connect(lambda: self.nudge_end_line(self.nudge_short))

        sc_n_p_l_s = self.app_settings.get("sc_nudge_playhead_left_short", "Left")
        sc_n_p_r_s = self.app_settings.get("sc_nudge_playhead_right_short", "Right")
        sc_n_p_l_m = self.app_settings.get("sc_nudge_playhead_left_med", "Shift+Left")
        sc_n_p_r_m = self.app_settings.get("sc_nudge_playhead_right_med", "Shift+Right")
        sc_n_p_l_l = self.app_settings.get("sc_nudge_playhead_left_long", "Ctrl+Left")
        sc_n_p_r_l = self.app_settings.get("sc_nudge_playhead_right_long", "Ctrl+Right")

        QShortcut(QKeySequence(sc_n_p_l_s), self).activated.connect(lambda: self.nudge_playhead(-self.nudge_short))
        QShortcut(QKeySequence(sc_n_p_r_s), self).activated.connect(lambda: self.nudge_playhead(self.nudge_short)) 
        QShortcut(QKeySequence(sc_n_p_l_m), self).activated.connect(lambda: self.nudge_playhead(-self.nudge_med))
        QShortcut(QKeySequence(sc_n_p_r_m), self).activated.connect(lambda: self.nudge_playhead(self.nudge_med))
        QShortcut(QKeySequence(sc_n_p_l_l), self).activated.connect(lambda: self.nudge_playhead(-self.nudge_long))
        QShortcut(QKeySequence(sc_n_p_r_l), self).activated.connect(lambda: self.nudge_playhead(self.nudge_long))

        sc_prev = self.app_settings.get("sc_prev_clip", "Up")
        sc_next = self.app_settings.get("sc_next_clip", "Down")
        sc_focus = self.app_settings.get("sc_focus_clip", "Shift+Z")
        
        QShortcut(QKeySequence(sc_prev), self).activated.connect(self.select_previous_clip)
        QShortcut(QKeySequence(sc_next), self).activated.connect(self.select_next_clip)
        QShortcut(QKeySequence(sc_focus), self).activated.connect(self.timeline_view.focus_on_clip)
        
        sc_undo = self.app_settings.get("sc_undo", "Ctrl+Z")
        sc_redo = self.app_settings.get("sc_redo", "Ctrl+Shift+Z")
        QShortcut(QKeySequence(sc_undo), self).activated.connect(self.undo_edit)
        QShortcut(QKeySequence(sc_redo), self).activated.connect(self.redo_edit)
        
        # Fallbacks to ensure Mac Cmd+Z always works perfectly
        QShortcut(QKeySequence(QKeySequence.StandardKey.Undo), self).activated.connect(self.undo_edit)
        QShortcut(QKeySequence(QKeySequence.StandardKey.Redo), self).activated.connect(self.redo_edit)

    def force_audio_jump(self, time_sec):
        self.media_player.setPosition(int(time_sec * 1000))

    def sync_playhead_to_audio(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            current_sec = self.media_player.position() / 1000.0
            self.timeline_view.playhead.setValue(current_sec)
            
            if self.preview_mode and current_sec >= self.timeline_view.end_line.value():
                self.stop_playback()
                self.preview_mode = False

    def play_forward(self):
        if hasattr(self, 'backward_timer'):
            self.backward_timer.stop()
        current_ms = int(self.timeline_view.playhead.value() * 1000)
        self.media_player.setPosition(current_ms)
        self.media_player.setPlaybackRate(1.0)
        self.media_player.play()
        self.sync_timer.start(33) 

    def play_backward(self):
        self.media_player.pause()
        self.sync_timer.stop()
        if not hasattr(self, 'backward_timer'):
            self.backward_timer = QTimer(self)
            self.backward_timer.setInterval(100) 
            self.backward_timer.timeout.connect(self.step_backward)
        self.backward_timer.start()

    def step_backward(self):
        current_ms = int(self.timeline_view.playhead.value() * 1000)
        new_ms = max(0, current_ms - 100)
        self.media_player.setPosition(new_ms)
        self.timeline_view.playhead.setValue(new_ms / 1000.0)
        if new_ms == 0:
            self.backward_timer.stop()

    def stop_playback(self):
        self.preview_mode = False
        self.media_player.pause()
        self.sync_timer.stop()
        if hasattr(self, 'backward_timer'):
            self.backward_timer.stop()
        self.media_player.setPosition(int(self.timeline_view.playhead.value() * 1000))

    def snap_playhead_to_start(self):
        self.stop_playback()
        self.timeline_view.playhead.setValue(self.timeline_view.start_line.value())
        
    def snap_playhead_to_end(self):
        self.stop_playback()
        self.timeline_view.playhead.setValue(self.timeline_view.end_line.value())

    def nudge_playhead(self, amount):
        self.stop_playback()
        current = self.timeline_view.playhead.value()
        new_val = max(0, min(self.timeline_view.total_duration, current + amount))
        self.timeline_view.playhead.setValue(new_val)

    def mark_start(self):
        current = self.timeline_view.playhead.value()
        end_val = self.timeline_view.end_line.value()
        if current < end_val:
            self.timeline_view.start_line.setValue(current)
            self.save_clip_bounds(current, end_val)
            
    def mark_end(self):
        current = self.timeline_view.playhead.value()
        start_val = self.timeline_view.start_line.value()
        if current > start_val:
            self.timeline_view.end_line.setValue(current)
            self.save_clip_bounds(start_val, current)
            
    def nudge_start_line(self, amount):
        start_val = self.timeline_view.start_line.value()
        end_val = self.timeline_view.end_line.value()
        new_start = min(end_val - 0.05, max(0, start_val + amount))
        self.timeline_view.start_line.setValue(new_start)
        self.save_clip_bounds(new_start, end_val)
        
    def nudge_end_line(self, amount):
        start_val = self.timeline_view.start_line.value()
        end_val = self.timeline_view.end_line.value()
        new_end = min(self.timeline_view.total_duration, max(start_val + 0.05, end_val + amount))
        self.timeline_view.end_line.setValue(new_end)
        self.save_clip_bounds(start_val, new_end)

    def select_previous_clip(self):
        current_row = self.clip_list.currentRow()
        if current_row > 0:
            self.clip_list.setCurrentRow(current_row - 1)
            self.load_clip_to_timeline(self.clip_list.currentItem())
        elif current_row == -1 and self.clip_list.count() > 0:
            self.clip_list.setCurrentRow(0)
            self.load_clip_to_timeline(self.clip_list.currentItem())

    def select_next_clip(self):
        current_row = self.clip_list.currentRow()
        if current_row < self.clip_list.count() - 1:
            self.clip_list.setCurrentRow(max(0, current_row + 1))
            self.load_clip_to_timeline(self.clip_list.currentItem())

    def play_in_to_out(self):
        self.snap_playhead_to_start()
        self.preview_mode = True
        self.play_forward()
        
    def play_review_cut(self):
        review_duration = float(self.app_settings.get("review_duration", 2.0))
        review_start = max(0, self.timeline_view.start_line.value() - review_duration)
        self.timeline_view.playhead.setValue(review_start)
        self.play_forward()

    # ==========================================
    # EXPORT LOGIC
    # ==========================================
    def get_project_folder(self):
        base_dir = self.app_settings.get("save_path", os.path.expanduser("~/Desktop/ScriptCutter_Exports"))
        if not os.path.exists(base_dir):
            os.makedirs(base_dir, exist_ok=True)
            
        if not hasattr(self, 'current_project_folder') or not self.current_project_folder:
            existing_projects = [d for d in os.listdir(base_dir) if d.startswith("project#(") and d.endswith(")")]
            max_num = 0
            for d in existing_projects:
                try:
                    num = int(d.replace("project#(", "").replace(")", ""))
                    max_num = max(max_num, num)
                except ValueError:
                    pass
            self.current_project_folder = f"project#({max_num + 1})"
            
        full_project_path = os.path.join(base_dir, self.current_project_folder)
        os.makedirs(full_project_path, exist_ok=True)
        return full_project_path

    def get_unique_filename(self, directory, base_name, ext):
        path = os.path.join(directory, f"{base_name}.{ext}")
        if not os.path.exists(path):
            return path
        counter = 2
        while os.path.exists(os.path.join(directory, f"{base_name}_v{counter}.{ext}")):
            counter += 1
        return os.path.join(directory, f"{base_name}_v{counter}.{ext}")

    def export_current_clip(self):
        if not self.current_video_path:
            QMessageBox.warning(self, "Error", "Please import a video first.")
            return

        save_dir = self.get_project_folder()
        export_mode = self.app_settings.get("cut_speed", "Fastest (Keyframe Copy)")
        export_format = self.app_settings.get("export_format", "Video")
        
        start = self.timeline_view.start_line.value()
        end = self.timeline_view.end_line.value()
        
        current_item = self.clip_list.currentItem()
        if not current_item:
            return
            
        clip_id = self.get_clip_id(current_item)
        row = self.clip_list.currentRow()
        clip_base = self.build_clip_export_name(clip_id, row)
        
        video_ext = os.path.splitext(self.current_video_path)[1].lstrip('.')
        
        self.status_label.setText(f"Exporting {clip_base}...")
        self.repaint() 
        
        if export_format in ["Video", "Both"]:
            vid_name = f"{self.current_project_folder}_{clip_base}_video"
            out_vid = self.get_unique_filename(save_dir, vid_name, video_ext)
            success, msg = export_clip(self.current_video_path, start, end, save_dir, os.path.basename(out_vid), export_mode, "Video")
            if not success:
                QMessageBox.critical(self, "Export Failed", f"FFmpeg Video Error:\n{msg}")
                return
                
        if export_format in ["Audio", "Both"]:
            from core.exporter import get_audio_extension
            audio_ext = get_audio_extension(self.current_video_path)
            aud_name = f"{self.current_project_folder}_{clip_base}_audio"
            out_aud = self.get_unique_filename(save_dir, aud_name, audio_ext)
            success, msg = export_clip(self.current_video_path, start, end, save_dir, os.path.basename(out_aud), export_mode, "Audio")
            if not success:
                QMessageBox.critical(self, "Export Failed", f"FFmpeg Audio Error:\n{msg}")
                return
        
        self.status_label.setText(f"Successfully saved to: {save_dir}")

    def batch_export_all(self):
        if not self.current_video_path:
            QMessageBox.warning(self, "Error", "Please import a video first.")
            return
            
        if self.script_clip_list.count() == 0 and self.custom_clip_list.count() == 0:
            QMessageBox.warning(self, "Error", "No clips exist across any tab to export.")
            return
            
        from PySide6.QtWidgets import QInputDialog
        formats = ["Video", "Audio", "Both"]
        default_fmt = self.app_settings.get("export_format", "Video")
        default_idx = formats.index(default_fmt) if default_fmt in formats else 0
        
        format_type, ok = QInputDialog.getItem(self, "Batch Export Format", "Select export format:", formats, default_idx, False)
        
        if ok and format_type:
            from ui.batch_export_modal import BatchExportModal
            modal = BatchExportModal(self, format_type)
            modal.exec()