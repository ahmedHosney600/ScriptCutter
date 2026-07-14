import subprocess
import os

def get_audio_extension(video_path):
    try:
        command = [
            "ffprobe", "-v", "error", 
            "-select_streams", "a:0", 
            "-show_entries", "stream=codec_name", 
            "-of", "default=noprint_wrappers=1:nokey=1", 
            video_path
        ]
        codec = subprocess.check_output(command, text=True).strip().lower()
        mapping = {
            "aac": "m4a",
            "mp3": "mp3",
            "vorbis": "ogg",
            "opus": "opus",
            "flac": "flac",
            "alac": "m4a",
            "pcm_s16le": "wav",
        }
        return mapping.get(codec, "m4a")  # Default to m4a if unknown
    except Exception:
        return "m4a"

def export_clip(video_path, start_time, end_time, output_dir, clip_name, mode, format_type="Video"):
    """
    Calls FFmpeg to cut the video based on the provided timestamps.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    output_path = os.path.join(output_dir, clip_name)
    duration = end_time - start_time
    
    command = [
        "ffmpeg", "-y",             
        "-ss", str(start_time),     
        "-i", video_path,           
        "-t", str(duration)         
    ]
    
    if format_type == "Audio":
        # Extract audio only, use stream copy to preserve original format
        command.extend(["-vn", "-c:a", "copy"])
    else:
        # Video extraction (includes audio)
        if "Fastest" in mode:
            command.extend(["-c", "copy"])
        else:
            command.extend(["-c:v", "libx264", "-preset", "fast", "-c:a", "aac"])
        
    command.append(output_path)
    
    try:
        # Run the command silently in the background
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True, output_path
    except subprocess.CalledProcessError as e:
        return False, str(e)