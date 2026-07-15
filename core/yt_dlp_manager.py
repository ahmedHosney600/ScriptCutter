import os
import subprocess
import requests
import glob

import platform
import stat

def get_yt_dlp_executable_path():
    """Returns the expected path to the standalone yt-dlp binary."""
    app_data_dir = os.path.expanduser("~/.scriptcutter/bin")
    os.makedirs(app_data_dir, exist_ok=True)
    
    if platform.system() == "Windows":
        return os.path.join(app_data_dir, "yt-dlp.exe")
    else:
        return os.path.join(app_data_dir, "yt-dlp")

def download_yt_dlp_binary(progress_callback=None):
    """Downloads the standalone yt-dlp binary if it doesn't exist."""
    binary_path = get_yt_dlp_executable_path()
        
    system = platform.system()
    if system == "Windows":
        url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    elif system == "Darwin":
        url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"
    else:
        url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"

    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        total_length = response.headers.get('content-length')
        
        with open(binary_path, 'wb') as f:
            if total_length is None: # no content length header
                f.write(response.content)
            else:
                dl = 0
                total_length = int(total_length)
                for data in response.iter_content(chunk_size=8192):
                    dl += len(data)
                    f.write(data)
                    if progress_callback:
                        progress_callback(dl, total_length)
                        
        # Make executable
        st = os.stat(binary_path)
        os.chmod(binary_path, st.st_mode | stat.S_IEXEC)
        return binary_path
    except Exception as e:
        print(f"Failed to download yt-dlp binary: {e}")
        if os.path.exists(binary_path):
            os.remove(binary_path)
        return None

def get_latest_yt_dlp_version():
    """Fetches the latest yt-dlp version from PyPI."""
    try:
        response = requests.get("https://pypi.org/pypi/yt-dlp/json", timeout=5)
        response.raise_for_status()
        data = response.json()
        return data["info"]["version"]
    except Exception as e:
        print(f"Error fetching latest yt-dlp version: {e}")
        return None

def get_local_yt_dlp_version():
    """Runs yt-dlp --version to get the local version."""
    binary_path = get_yt_dlp_executable_path()
    if not os.path.exists(binary_path):
        return None
        
    try:
        result = subprocess.run([binary_path, "--version"], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception as e:
        print(f"Error getting local yt-dlp version: {e}")
        return None

def update_yt_dlp():
    """Updates yt-dlp using its self-updater."""
    binary_path = get_yt_dlp_executable_path()
    if not os.path.exists(binary_path):
        download_yt_dlp_binary()
        return True
    try:
        subprocess.run([binary_path, "-U"], check=True)
        return True
    except Exception as e:
        print(f"Failed to update yt-dlp: {e}")
        return False

def remove_id_from_filenames(directory):
    """
    Scans the given directory for files ending in ` [<id>].ext` (yt-dlp default)
    and renames them to remove the ` [<id>]` part.
    """
    if not os.path.exists(directory):
        return
        
    import re
    # yt-dlp usually appends " [id].ext". 
    # Example: "My Video [aBcDeFgHiJk].mp4"
    # Regex to match the [id] right before the extension
    pattern = re.compile(r"(.*) \[[a-zA-Z0-9_-]+\](\.[a-zA-Z0-9.-]+)$")
    
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            match = pattern.match(filename)
            if match:
                new_name = match.group(1) + match.group(2)
                new_filepath = os.path.join(directory, new_name)
                try:
                    os.rename(filepath, new_filepath)
                    print(f"Renamed: {filename} -> {new_name}")
                except Exception as e:
                    print(f"Error renaming {filename}: {e}")

def fix_vtt_overlap_in_directory(directory):
    """
    Scans the given directory for .vtt files, cleans VTT formatting tags,
    deduplicates scrolling text lines, fixes overlapping subtitles,
    converts them to .srt, and deletes the original .vtt.
    """
    if not os.path.exists(directory):
        return
        
    try:
        import pysubs2
        import re
    except ImportError:
        print("pysubs2 is not installed. Skipping subtitle overlap fix.")
        return
        
    for filename in os.listdir(directory):
        if filename.endswith(".vtt"):
            filepath = os.path.join(directory, filename)
            if os.path.isfile(filepath):
                try:
                    base, _ = os.path.splitext(filepath)
                    output_srt = f"{base}.srt"
                    
                    subs = pysubs2.load(filepath, encoding="utf-8")
                    cleaned_subs = pysubs2.SSAFile()
                    
                    prev_lines = []
                    for i in range(len(subs)):
                        # Clean tags like <00:00:11.480>, <c>, </c>
                        text = re.sub(r'<[^>]+>', '', subs[i].text)
                        # Replace \N with \n
                        text = text.replace(r'\N', '\n')
                        
                        curr_lines = [line.strip() for line in text.split('\n') if line.strip()]
                        new_lines = []
                        
                        for line in curr_lines:
                            if line not in prev_lines:
                                new_lines.append(line)
                                
                        prev_lines = curr_lines.copy()
                        
                        subs[i].text = "\n".join(new_lines)
                        if subs[i].text.strip():
                            cleaned_subs.append(subs[i])
                            
                    cleaned_subs.sort()
                    for i in range(len(cleaned_subs) - 1):
                        if cleaned_subs[i].end > cleaned_subs[i+1].start:
                            cleaned_subs[i].end = cleaned_subs[i+1].start - 1
                            
                    cleaned_subs.save(output_srt, encoding="utf-8")
                    print(f"Fixed overlap and converted to SRT: {filename} -> {os.path.basename(output_srt)}")
                    
                    os.remove(filepath)
                except Exception as e:
                    print(f"Error fixing subtitle overlap for {filename}: {e}")

def export_subtitles_to_text(directory):
    """
    Scans the directory for .srt and .vtt files, and extracts their raw text
    into a .txt file, stripping formatting and deduplicating lines.
    """
    if not os.path.exists(directory):
        return
        
    try:
        import pysubs2
        import re
    except ImportError:
        print("pysubs2 is not installed. Skipping text export.")
        return
        
    for filename in os.listdir(directory):
        if filename.endswith(".srt") or filename.endswith(".vtt"):
            filepath = os.path.join(directory, filename)
            if os.path.isfile(filepath):
                try:
                    base, ext = os.path.splitext(filepath)
                    output_txt = f"{base}.txt"
                    
                    subs = pysubs2.load(filepath, encoding="utf-8")
                    
                    lines = []
                    prev_lines = []
                    for sub in subs:
                        text = re.sub(r'<[^>]+>', '', sub.text)
                        text = text.replace(r'\N', '\n')
                        
                        curr_lines = [line.strip() for line in text.split('\n') if line.strip()]
                        for line in curr_lines:
                            if line not in prev_lines:
                                lines.append(line)
                        prev_lines = curr_lines.copy()
                        
                    with open(output_txt, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(lines))
                        
                    print(f"Exported subtitle text to: {os.path.basename(output_txt)}")
                except Exception as e:
                    print(f"Error exporting text for {filename}: {e}")
