import os
import sys
import platform
import zipfile
import urllib.request
from pathlib import Path
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QApplication
from PySide6.QtCore import Qt, QThread, Signal

def get_platform_suffix():
    system = platform.system().lower()
    machine = platform.machine().lower()
    
    if system == "windows":
        return "win32"
    elif system == "darwin":
        if machine == "arm64":
            return "darwin_arm64"
        else:
            return "darwin"
    elif system == "linux":
        return "linux"
    return "linux"

def get_bin_dir():
    return Path.home() / ".ScriptCutter" / "bin"

def check_dependencies_exist():
    bin_dir = get_bin_dir()
    ffmpeg_exe = "ffmpeg.exe" if platform.system().lower() == "windows" else "ffmpeg"
    ffprobe_exe = "ffprobe.exe" if platform.system().lower() == "windows" else "ffprobe"
    
    return (bin_dir / ffmpeg_exe).exists() and (bin_dir / ffprobe_exe).exists()

class DownloadWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(bool, str)

    def run(self):
        try:
            suffix = get_platform_suffix()
            url = f"https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/{suffix}.zip"
            
            bin_dir = get_bin_dir()
            bin_dir.mkdir(parents=True, exist_ok=True)
            
            zip_path = bin_dir / f"ffmpeg_{suffix}.zip"
            
            self.status.emit(f"Downloading media engine ({suffix})...")
            
            def reporthook(blocknum, blocksize, totalsize):
                if totalsize > 0:
                    readsofar = blocknum * blocksize
                    if readsofar > totalsize:
                        readsofar = totalsize
                    percent = int((readsofar * 100) / totalsize)
                    self.progress.emit(percent)
            
            urllib.request.urlretrieve(url, zip_path, reporthook)
            
            self.status.emit("Extracting media engine...")
            self.progress.emit(0)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for member in zip_ref.namelist():
                    filename = os.path.basename(member)
                    if not filename:
                        continue
                    
                    source = zip_ref.open(member)
                    target_path = bin_dir / filename
                    with open(target_path, "wb") as target:
                        target.write(source.read())
                    
                    if platform.system().lower() != "windows":
                        os.chmod(target_path, 0o755)
            
            os.remove(zip_path)
            
            self.finished.emit(True, "Success")
            
        except Exception as e:
            self.finished.emit(False, str(e))

class DependencyDownloader(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ScriptCutter Initial Setup")
        self.setFixedSize(400, 150)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        
        self.title_label = QLabel("First Time Setup", self)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)
        
        self.status_label = QLabel("Initializing download...", self)
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        self.worker = DownloadWorker()
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.status.connect(self.status_label.setText)
        self.worker.finished.connect(self.on_download_finished)
        
        self.success = False

    def start_download(self):
        self.worker.start()

    def on_download_finished(self, success, error_message):
        self.success = success
        if success:
            self.accept()
        else:
            self.status_label.setText(f"Error: {error_message}")
            self.status_label.setStyleSheet("color: red;")
            self.progress_bar.hide()

def ensure_dependencies():
    if not check_dependencies_exist():
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)
            
        dialog = DependencyDownloader()
        dialog.show()
        dialog.start_download()
        dialog.exec()
        
        if not dialog.success:
            return False
            
    bin_dir = str(get_bin_dir())
    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    return True
