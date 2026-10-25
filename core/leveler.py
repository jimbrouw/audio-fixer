import os
import numpy as np
import soundfile as sf
from scipy.ndimage import uniform_filter1d
from typing import Optional, Callable


def level_audio(
    input_wav: str,
    output_wav: str,
    target_rms_db: float = -35.0,
    noise_floor_db: float = -55.0,
    max_boost_db: float = 18.0,
    window_sec: float = 0.05,
    attack_ms: float = 25.0,
    release_ms: float = 200.0,
    chunk_frames: int = 48000 * 20,
    progress_cb: Optional[Callable[[float], None]] = None,
):
    """
    Adaptive Speech Leveler & Inverse Dynamics Expansion.
    Detects ducked/quiet speech syllables and lifts them smoothly toward target_rms_db,
    reversing gate ducking and over-compression without boosting room noise.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_wav)), exist_ok=True)

    info = sf.info(input_wav)
    sr = info.samplerate
    total_frames = info.frames
    channels = info.channels
    subtype = info.subtype
    fmt = info.format

    # Time constants for attack / release smoothing
    attack_alpha = float(1.0 - np.exp(-1.0 / (sr * (attack_ms / 1000.0))))
    release_alpha = float(1.0 - np.exp(-1.0 / (sr * (release_ms / 1000.0))))

    target_amp = float(10.0 ** (target_rms_db / 20.0))
    noise_thresh_amp = float(10.0 ** (noise_floor_db / 20.0))
    max_boost_linear = float(10.0 ** (max_boost_db / 20.0))
    win_len = max(1, int(sr * window_sec))

    smoothed_gain = 1.0

    with sf.SoundFile(input_wav) as src, sf.SoundFile(
        output_wav, mode="w", samplerate=sr, channels=channels, subtype=subtype, format=fmt
    ) as dst:
        offset = 0
        while offset < total_frames:
            read_len = min(chunk_frames, total_frames - offset)
            block = src.read(read_len, dtype="float32")
            if len(block) == 0:
                break

            # Calculate RMS envelope on reference channel (ch 0)
            ref_ch = block[:, 0]
            # uniform_filter1d computes the moving average of squares with exact same length
            env_sq = uniform_filter1d(ref_ch ** 2, size=win_len, mode="reflect")
            env = np.sqrt(np.maximum(env_sq, 0.0))

            # Target gain calculation
            speech_mask = env > noise_thresh_amp
            target_gain = np.ones(len(block), dtype=np.float32)
            target_gain[speech_mask] = target_amp / (env[speech_mask] + 1e-6)
            target_gain = np.clip(target_gain, 1.0, max_boost_linear)

            # Smooth gain envelope to prevent clicking or unnatural pumping
            block_gain = np.empty(len(block), dtype=np.float32)
            curr_g = smoothed_gain
            for i in range(len(target_gain)):
                tg = target_gain[i]
                if tg > curr_g:
                    curr_g += attack_alpha * (tg - curr_g)
                else:
                    curr_g += release_alpha * (tg - curr_g)
                block_gain[i] = curr_g
            smoothed_gain = curr_g

            # Apply gain across all channels (block is [N, channels], block_gain is [N, 1])
            processed = block * block_gain[:, np.newaxis]

            # Transparent limiter to avoid digital clipping
            peak = np.max(np.abs(processed))
            if peak > 0.95:
                processed = processed * (0.95 / peak)

            if "PCM_16" in subtype:
                out_block = np.clip(np.round(processed * 32768.0), -32768, 32767).astype(np.int16)
            else:
                out_block = processed

            dst.write(out_block)
            offset += len(block)

            if progress_cb:
                progress_cb(min(1.0, offset / total_frames))
