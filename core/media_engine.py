import subprocess
import wave
import os
import struct
from utils.binary_resolver import get_ffmpeg_path

def generate_waveform_data(video_path, num_peaks=5000):
    """
    Extracts audio from video using FFmpeg, reads the volume peaks,
    and returns a normalized list of values between 0.0 and 1.0.
    """
    temp_wav = "temp_waveform.wav"
    
    # 1. Use FFmpeg to create a lightweight, mono, low-sample-rate WAV file
    command = [
        get_ffmpeg_path(), "-y", "-i", video_path, 
        "-vn",          # No video
        "-ac", "1",     # Mono channel
        "-ar", "8000",  # Low sample rate (faster processing)
        temp_wav
    ]
    
    try:
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except subprocess.CalledProcessError:
        print("Error extracting audio for waveform.")
        return []

    # 2. Read the WAV file to calculate peaks
    peaks = []
    try:
        with wave.open(temp_wav, 'rb') as wav_file:
            n_frames = wav_file.getnframes()
            frames_per_peak = n_frames // num_peaks
            
            # Read the raw audio bytes
            raw_data = wav_file.readframes(n_frames)
            
            # Convert bytes to integers
            unpack_fmt = f"<{n_frames}h" # 16-bit PCM
            audio_samples = struct.unpack(unpack_fmt, raw_data)
            
            # Calculate the maximum volume in each chunk
            for i in range(num_peaks):
                chunk = audio_samples[i * frames_per_peak : (i + 1) * frames_per_peak]
                if chunk:
                    # Use absolute value to get the volume magnitude
                    peak_val = max(abs(max(chunk)), abs(min(chunk)))
                    peaks.append(peak_val)
                    
        # 3. Normalize peaks to be between 0.0 and 1.0
        max_peak = max(peaks) if peaks else 1
        normalized_peaks = [p / max_peak for p in peaks]
        
    except Exception as e:
        print(f"Error reading waveform: {e}")
        normalized_peaks = []
        
    # Cleanup temporary file
    if os.path.exists(temp_wav):
        os.remove(temp_wav)
        
    return normalized_peaks