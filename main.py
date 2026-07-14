import sys
import os
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

from ui.dependency_downloader import ensure_dependencies

def main():
    # Force FFmpeg backend on macOS for robust video decoding
    os.environ["QT_MEDIA_BACKEND"] = "ffmpeg"
    
    # 1. Create the Qt Application
    app = QApplication(sys.argv)
    
    # Optional: Set a dark theme globally
    app.setStyle("Fusion")

    # Ensure FFmpeg is downloaded before starting
    if not ensure_dependencies():
        print("Failed to download or locate media dependencies.")
        sys.exit(1)

    # 2. Instantiate and show the Main Window
    window = MainWindow()
    window.show()

    # 3. Run the application's event loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main()