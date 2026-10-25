import os
import math
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable
import numpy as np
import soundfile as sf
from scipy.interpolate import CubicSpline


@dataclass
class GlitchEvent:
    start_frame: int
    end_frame: int
    span_samples: int
    time_seconds: float
    tracks_involved: List[str] = field(default_factory=list)
    peak_amplitude: float = 0.0

    @property
    def formatted_time(self) -> str:
        mins = int(self.time_seconds // 60)
        secs = self.time_seconds % 60
        hours = mins // 60
        mins = mins % 60
        if hours > 0:
            return f"{hours:02d}:{mins:02d}:{secs:06.3f}"
        return f"{mins:02d}:{secs:06.3f}"


class AudioFixerEngine:
    def __init__(
        self,
        curv_threshold: float = 3500.0,
        cluster_window: int = 30,
        pad_samples: int = 8,
        silence_threshold: float = 25.0,
    ):
        """
        curv_threshold: Curvature threshold in 16-bit PCM scale (3500 ~ 0.1068 in float32)
        cluster_window: Sample window to cluster coincident spikes across tracks
        pad_samples: Clean anchor samples on each side for spline interpolation
        silence_threshold: If surrounding samples RMS is below this, duck to 0
        """
        self.curv_threshold = curv_threshold
        self.cluster_window = cluster_window
        self.pad_samples = pad_samples
        self.silence_threshold = silence_threshold

    def find_spikes_in_file(
        self,
        filepath: str,
        chunk_frames: int = 48000 * 20,
        progress_cb: Optional[Callable[[float], None]] = None,
    ) -> List[int]:
        """Scan a single WAV file for high-curvature spikes."""
        spikes = []
        with sf.SoundFile(filepath) as f:
            sr = f.samplerate
            total = f.frames
            channels = f.channels
            offset = 0
            overlap = 64
            prev = np.zeros((0, channels), dtype=np.int16)

            while offset < total:
                read_len = min(chunk_frames, total - offset)
                block = f.read(read_len, dtype="int16")
                if len(block) == 0:
                    break

                full = np.vstack([prev, block]) if len(prev) else block

                for ch in range(channels):
                    x = full[:, ch].astype(np.float32)
                    curv = np.abs(x[1:-1] - 0.5 * (x[:-2] + x[2:]))
                    peaks = np.where(curv > self.curv_threshold)[0]
                    for idx in peaks:
                        spikes.append(offset + idx - len(prev) + 1)

                prev = block[-overlap:]
                offset += read_len
                if progress_cb:
                    progress_cb(min(1.0, offset / total))

        return sorted(list(set(spikes)))

    def detect_glitches(
        self,
        filepaths: List[str],
        progress_cb: Optional[Callable[[str, float], None]] = None,
    ) -> List[GlitchEvent]:
        """
        Detect glitches across one or multiple audio files.
        If multiple files are provided, leverages multi-track cross-correlation.
        """
        if not filepaths:
            return []

        file_spikes: Dict[str, List[int]] = {}
        for idx, fp in enumerate(filepaths):
            fname = os.path.basename(fp)
            def sub_prog(frac):
                if progress_cb:
                    overall = (idx + frac) / len(filepaths)
                    progress_cb(f"Scanning {fname}...", overall)

            spikes = self.find_spikes_in_file(fp, progress_cb=sub_prog)
            file_spikes[fp] = spikes

        # Get sample rate and total frames from first file
        info = sf.info(filepaths[0])
        sr = info.samplerate

        # Merge all spikes into clusters
        all_unique_spikes = sorted(list(set([s for spikes in file_spikes.values() for s in spikes])))
        raw_clusters: List[List[int]] = []
        for s in all_unique_spikes:
            if not raw_clusters or s - raw_clusters[-1][-1] > self.cluster_window:
                raw_clusters.append([s])
            else:
                raw_clusters[-1].append(s)

        is_multitrack = len(filepaths) > 1
        events: List[GlitchEvent] = []

        for cluster in raw_clusters:
            c_start = cluster[0]
            c_end = cluster[-1]

            tracks_involved = []
            for fp in filepaths:
                spikes = file_spikes[fp]
                if any(abs(s - c_start) <= self.cluster_window for s in spikes):
                    tracks_involved.append(os.path.basename(fp))

            # Multi-track filtering:
            # If multiple tracks are provided, require multi-track consensus (>= 2 tracks)
            # OR an extreme single-track anomaly (span >= 4 samples with very high curvature)
            if is_multitrack and len(tracks_involved) < 2 and len(cluster) < 4:
                continue

            # Standard Rodecaster USB packet glitches span ~12-14 samples.
            # Add a safety margin of 1 sample on each side.
            event_start = max(0, c_start - 1)
            event_end = c_end + 2

            # Find peak amplitude across involved tracks in this window
            peak_amp = 0.0
            for fp in filepaths:
                try:
                    with sf.SoundFile(fp) as f:
                        f.seek(max(0, event_start - 2))
                        chunk = f.read(event_end - event_start + 4, dtype="int16")
                        if len(chunk) > 0:
                            peak_amp = max(peak_amp, float(np.max(np.abs(chunk))))
                except Exception:
                    pass

            events.append(
                GlitchEvent(
                    start_frame=event_start,
                    end_frame=event_end,
                    span_samples=event_end - event_start,
                    time_seconds=event_start / sr,
                    tracks_involved=tracks_involved,
                    peak_amplitude=peak_amp,
                )
            )

        if progress_cb:
            progress_cb("Scan complete.", 1.0)

        return events

    def repair_block(
        self,
        audio: np.ndarray,
        block_start_frame: int,
        glitches_in_block: List[GlitchEvent],
    ) -> np.ndarray:
        """
        Repairs glitches located inside audio array.
        audio: 2D numpy array (frames, channels), dtype int16 or float32
        block_start_frame: absolute frame number of audio[0]
        """
        repaired = audio.copy()
        n_frames = len(audio)
        is_int16 = (audio.dtype == np.int16)

        for g in glitches_in_block:
            rel_start = max(0, g.start_frame - block_start_frame)
            rel_end = min(n_frames, g.end_frame - block_start_frame)
            if rel_start >= rel_end:
                continue

            pad = self.pad_samples
            left_anchor_start = max(0, rel_start - pad)
            right_anchor_end = min(n_frames, rel_end + pad)

            for ch in range(audio.shape[1]):
                # Check surrounding energy
                left_check = audio[max(0, rel_start - 16):rel_start, ch].astype(np.float64)
                right_check = audio[rel_end:min(n_frames, rel_end + 16), ch].astype(np.float64)

                left_max = np.max(np.abs(left_check)) if len(left_check) else 0.0
                right_max = np.max(np.abs(right_check)) if len(right_check) else 0.0

                # Silence threshold check (scaled appropriately)
                thresh = self.silence_threshold if is_int16 else (self.silence_threshold / 32768.0)

                if left_max <= thresh and right_max <= thresh:
                    # Gated silence: smooth zero ducking
                    repaired[rel_start:rel_end, ch] = 0
                else:
                    # Active audio: Hermite cubic spline interpolation across the gap
                    x_fit = np.concatenate([
                        np.arange(left_anchor_start, rel_start),
                        np.arange(rel_end, right_anchor_end),
                    ])
                    if len(x_fit) >= 4:
                        y_fit = audio[x_fit, ch].astype(np.float64)
                        cs = CubicSpline(x_fit, y_fit)
                        x_interp = np.arange(rel_start, rel_end)
                        y_interp = cs(x_interp)
                        if is_int16:
                            repaired[rel_start:rel_end, ch] = np.clip(
                                np.round(y_interp), -32768, 32767
                            ).astype(np.int16)
                        else:
                            repaired[rel_start:rel_end, ch] = np.clip(
                                y_interp, -1.0, 1.0
                            ).astype(np.float32)

        return repaired

    def render_cleaned_file(
        self,
        src_filepath: str,
        dst_filepath: str,
        events: List[GlitchEvent],
        chunk_frames: int = 48000 * 20,
        progress_cb: Optional[Callable[[float], None]] = None,
    ):
        """
        Renders a cleaned WAV file using streaming chunked I/O.
        Ensures exact header, format, samplerate, and channel preservation.
        """
        # Ensure destination directory exists
        os.makedirs(os.path.dirname(os.path.abspath(dst_filepath)), exist_ok=True)

        with sf.SoundFile(src_filepath) as src:
            sr = src.samplerate
            channels = src.channels
            subtype = src.subtype
            fmt = src.format
            total_frames = src.frames

            # Prepare writer with identical audio properties
            with sf.SoundFile(
                dst_filepath,
                mode="w",
                samplerate=sr,
                channels=channels,
                subtype=subtype,
                format=fmt,
            ) as dst:
                offset = 0
                # Filter events relevant to this file duration
                relevant_events = [e for e in events if e.end_frame > 0 and e.start_frame < total_frames]

                while offset < total_frames:
                    read_len = min(chunk_frames, total_frames - offset)
                    block = src.read(read_len, dtype="int16" if "PCM_16" in subtype else "float32")
                    if len(block) == 0:
                        break

                    block_end = offset + len(block)
                    # Find events that fall into this block
                    block_events = [
                        e for e in relevant_events
                        if not (e.end_frame <= offset or e.start_frame >= block_end)
                    ]

                    if block_events:
                        block = self.repair_block(block, offset, block_events)

                    dst.write(block)
                    offset += len(block)

                    if progress_cb:
                        progress_cb(min(1.0, offset / total_frames))
