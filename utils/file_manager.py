import json
import os
import re

SETTINGS_FILE = "settings.json"

# The defaults if the user opens the app for the very first time
DEFAULT_SETTINGS = {
    "cut_speed": "Fastest (Keyframe Copy)",
    "export_format": "Video",
    "concurrent_tasks": 2,
    "save_path": "",
    "review_duration": 2.0,
    "nudge_short": 0.10,
    "nudge_med": 1.0,
    "nudge_long": 5.0,
    
    "sc_play_forward": "L",
    "sc_play_backward": "J",
    "sc_stop": "K",
    "sc_mark_start": "I",
    "sc_mark_end": "O",
    "sc_snap_start": "Shift+I",
    "sc_snap_end": "Shift+O",
    "sc_preview_cut": "Alt+Space",
    "sc_review_cut": "Shift+Space",
    "sc_play_to_out": "Ctrl+Space",
    
    "sc_nudge_start_left": "Alt+Left",
    "sc_nudge_start_right": "Alt+Right",
    "sc_nudge_end_left": "Ctrl+Left",
    "sc_nudge_end_right": "Ctrl+Right",
    
    "sc_nudge_playhead_left_short": "Left",
    "sc_nudge_playhead_right_short": "Right",
    "sc_nudge_playhead_left_med": "Shift+Left",
    "sc_nudge_playhead_right_med": "Shift+Right",
    "sc_nudge_playhead_left_long": "Ctrl+Left",
    "sc_nudge_playhead_right_long": "Ctrl+Right",
    
    "sc_prev_clip": "Up",
    "sc_next_clip": "Down",
    "sc_focus_clip": "Shift+Z",
    "sc_undo": "Ctrl+Z",
    "sc_redo": "Ctrl+Shift+Z"
}

def load_settings():
    """Loads settings from JSON, merges with defaults to ensure all keys exist."""
    settings = DEFAULT_SETTINGS.copy()
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            try:
                loaded = json.load(f)
                settings.update(loaded)
            except json.JSONDecodeError:
                pass
    return settings

def save_settings(settings):
    """Saves the settings dictionary to a JSON file."""
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)


def time_to_sec(time_str):
    """Converts SRT/VTT timestamp (00:00:01,000, 00:00:01.000, or 01.000) to seconds."""
    time_str = time_str.strip().split()[0] # Take first part to ignore VTT metadata like align:start
    time_str = time_str.replace(',', '.') # Normalize SRT commas to VTT periods
    
    parts = time_str.split(':')
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    else:
        return float(time_str)


def parse_subtitle_file(file_path):
    """Reads an SRT or VTT file and returns a list of subtitle dictionaries."""
    parsed_subtitles = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Normalize line endings
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    # Split the file by double (or more) line breaks
    blocks = re.split(r'\n{2,}', content.strip())

    for block in blocks:
        lines = block.split('\n')
        
        # Find the line with the timestamp arrow
        time_line_index = -1
        for i, line in enumerate(lines):
            if "-->" in line:
                time_line_index = i
                break
                
        if time_line_index != -1:
            time_line = lines[time_line_index]
            start_str, end_str = time_line.split("-->")
            
            try:
                start_sec = time_to_sec(start_str.strip())
                end_sec = time_to_sec(end_str.strip())
                
                # Join all remaining lines after the time_line as the text
                text = " ".join(lines[time_line_index+1:]).strip()
                
                # Strip VTT/HTML tags like <c> or <00:00:08.960>
                text = re.sub(r'<[^>]+>', '', text).strip()
                
                parsed_subtitles.append({
                    "start": start_sec,
                    "end": end_sec,
                    "text": text
                })
            except Exception as e:
                print(f"Skipping invalid timestamp line: {time_line} - Error: {e}")
                    
    return parsed_subtitles