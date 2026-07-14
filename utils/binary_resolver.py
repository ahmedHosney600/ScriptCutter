import os
import sys

def get_binary_path(binary_name):
    """
    Returns the path to the bundled binary if running as a PyInstaller executable,
    otherwise returns the binary name assuming it is in the system PATH.
    """
    ext = ".exe" if os.name == 'nt' else ""
    full_binary_name = f"{binary_name}{ext}"

    if getattr(sys, 'frozen', False):
        # Running as compiled PyInstaller executable
        base_path = sys._MEIPASS
        # Binaries are packed into a 'bin' folder inside the bundle
        bundled_path = os.path.join(base_path, "bin", full_binary_name)
        if os.path.exists(bundled_path):
            return bundled_path
    
    # Running as script or fallback
    return full_binary_name

def get_ffmpeg_path():
    return get_binary_path("ffmpeg")

def get_ffprobe_path():
    return get_binary_path("ffprobe")
