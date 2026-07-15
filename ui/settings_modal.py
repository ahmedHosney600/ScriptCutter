from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox, 
                               QSpinBox, QDoubleSpinBox, QPushButton, QHBoxLayout, 
                               QLineEdit, QFileDialog, QKeySequenceEdit, QGroupBox,
                               QScrollArea, QWidget)
from utils.file_manager import save_settings, DEFAULT_SETTINGS

class SettingsModal(QDialog):
    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ScriptCutter Settings")
        self.setMinimumWidth(550)
        self.setMinimumHeight(600)
        self.settings = current_settings
        
        self.main_layout = QVBoxLayout(self)
        
        # Scroll Area Setup
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        
        # 1. General Settings
        self.general_group = QGroupBox("General")
        self.general_layout = QFormLayout()
        
        self.path_layout = QHBoxLayout()
        self.path_input = QLineEdit(self.settings.get("save_path", ""))
        self.path_input.setReadOnly(True)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.browse_folder)
        self.path_layout.addWidget(self.path_input)
        self.path_layout.addWidget(self.browse_btn)
        self.general_layout.addRow("Master Save Location:", self.path_layout)
        
        self.cut_speed_dropdown = QComboBox()
        self.cut_speed_dropdown.addItems(["Fastest (Keyframe Copy)", "Accurate (Re-encode)"])
        self.cut_speed_dropdown.setCurrentText(self.settings.get("cut_speed", "Fastest (Keyframe Copy)"))
        self.general_layout.addRow("Default Cut Method:", self.cut_speed_dropdown)
        
        self.export_format_dropdown = QComboBox()
        self.export_format_dropdown.addItems(["Video", "Audio", "Both"])
        self.export_format_dropdown.setCurrentText(self.settings.get("export_format", "Video"))
        self.general_layout.addRow("Default Export Format:", self.export_format_dropdown)

        self.concurrency_spinner = QSpinBox()
        self.concurrency_spinner.setRange(1, 16)
        self.concurrency_spinner.setValue(self.settings.get("concurrent_tasks", 2))
        self.general_layout.addRow("Concurrent Batch Exports:", self.concurrency_spinner)
        
        self.general_group.setLayout(self.general_layout)
        self.scroll_layout.addWidget(self.general_group)

        # 2. Timing & Nudging
        self.timing_group = QGroupBox("Timing & Nudges (Seconds)")
        self.timing_layout = QFormLayout()
        
        self.review_spinner = QDoubleSpinBox()
        self.review_spinner.setDecimals(2)
        self.review_spinner.setSingleStep(0.5)
        self.review_spinner.setValue(float(self.settings.get("review_duration", 2.0)))
        
        self.nudge_short_spinner = QDoubleSpinBox()
        self.nudge_short_spinner.setDecimals(2)
        self.nudge_short_spinner.setSingleStep(0.05)
        self.nudge_short_spinner.setValue(float(self.settings.get("nudge_short", 0.10)))
        
        self.nudge_med_spinner = QDoubleSpinBox()
        self.nudge_med_spinner.setDecimals(2)
        self.nudge_med_spinner.setSingleStep(0.5)
        self.nudge_med_spinner.setValue(float(self.settings.get("nudge_med", 1.0)))
        
        self.nudge_long_spinner = QDoubleSpinBox()
        self.nudge_long_spinner.setDecimals(2)
        self.nudge_long_spinner.setSingleStep(1.0)
        self.nudge_long_spinner.setValue(float(self.settings.get("nudge_long", 5.0)))
        
        self.timing_layout.addRow("Review Cut Preroll:", self.review_spinner)
        self.timing_layout.addRow("Short Nudge:", self.nudge_short_spinner)
        self.timing_layout.addRow("Medium Nudge:", self.nudge_med_spinner)
        self.timing_layout.addRow("Long Nudge:", self.nudge_long_spinner)
        self.timing_group.setLayout(self.timing_layout)
        self.scroll_layout.addWidget(self.timing_group)
        
        # 3. Shortcuts
        self.shortcut_group = QGroupBox("Keyboard Shortcuts")
        self.shortcut_layout = QFormLayout()
        
        self.shortcuts_inputs = {}
        
        shortcut_definitions = {
            "sc_play_forward": "Play Forward",
            "sc_play_backward": "Play Backward",
            "sc_stop": "Pause / Stop",
            "sc_mark_start": "Mark Start (In)",
            "sc_mark_end": "Mark End (Out)",
            "sc_snap_start": "Snap Playhead to Start",
            "sc_snap_end": "Snap Playhead to End",
            "sc_preview_cut": "Preview Cut (In to Out)",
            "sc_review_cut": "Review Cut (with Preroll)",
            "sc_play_to_out": "Play to Out Mark",
            "sc_nudge_start_left": "Nudge Start Left",
            "sc_nudge_start_right": "Nudge Start Right",
            "sc_nudge_end_left": "Nudge End Left",
            "sc_nudge_end_right": "Nudge End Right",
            "sc_nudge_playhead_left_short": "Nudge Playhead Left (Short)",
            "sc_nudge_playhead_right_short": "Nudge Playhead Right (Short)",
            "sc_nudge_playhead_left_med": "Nudge Playhead Left (Medium)",
            "sc_nudge_playhead_right_med": "Nudge Playhead Right (Medium)",
            "sc_nudge_playhead_left_long": "Nudge Playhead Left (Long)",
            "sc_nudge_playhead_right_long": "Nudge Playhead Right (Long)",
            "sc_prev_clip": "Select Previous Clip",
            "sc_next_clip": "Select Next Clip",
            "sc_focus_clip": "Zoom to Fit Clip",
            "sc_undo": "Undo",
            "sc_redo": "Redo"
        }
        
        for key, label in shortcut_definitions.items():
            current_val = self.settings.get(key, DEFAULT_SETTINGS.get(key, ""))
            seq_edit = QKeySequenceEdit(current_val)
            self.shortcuts_inputs[key] = seq_edit
            self.shortcut_layout.addRow(label + ":", seq_edit)
            
        self.shortcut_group.setLayout(self.shortcut_layout)
        self.scroll_layout.addWidget(self.shortcut_group)

        self.scroll_area.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll_area)

        # 4. Save / Cancel Buttons
        self.button_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save Settings")
        self.cancel_btn = QPushButton("Cancel")
        self.button_layout.addStretch()
        self.button_layout.addWidget(self.cancel_btn)
        self.button_layout.addWidget(self.save_btn)
        self.main_layout.addLayout(self.button_layout)

        self.save_btn.clicked.connect(self.save_and_close)
        self.cancel_btn.clicked.connect(self.reject)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Master Save Location")
        if folder:
            self.path_input.setText(folder)

    def save_and_close(self):
        self.settings["save_path"] = self.path_input.text()
        self.settings["cut_speed"] = self.cut_speed_dropdown.currentText()
        self.settings["export_format"] = self.export_format_dropdown.currentText()
        self.settings["concurrent_tasks"] = self.concurrency_spinner.value()
        
        self.settings["review_duration"] = self.review_spinner.value()
        self.settings["nudge_short"] = self.nudge_short_spinner.value()
        self.settings["nudge_med"] = self.nudge_med_spinner.value()
        self.settings["nudge_long"] = self.nudge_long_spinner.value()
        
        # We need to manually clean up old settings that are obsolete if we want, but it's safe to leave them
        
        for key, edit_widget in self.shortcuts_inputs.items():
            self.settings[key] = edit_widget.keySequence().toString()
        
        save_settings(self.settings)
        self.accept()