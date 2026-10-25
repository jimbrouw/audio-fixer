# Audio Fixer

**Automated macOS App & CLI tool to repair synchronized RØDECaster/OBS USB packet dropouts and normalize ducked/gated microphone audio.**

---

## What It Solves

1. **Synchronized USB Distortion Spikes / Clicks**:
   When recording multi-track audio over USB into OBS Studio, periodic USB packet boundary dropouts can inject tiny bursts (~12 to 16 samples, < 0.3 ms) of loud distortion / digital clicks across all channels simultaneously (often hitting -6 dBFS / ±16,000 amplitude). Audio Fixer cross-correlates multi-track channels and heals each glitch with **bit-perfect Cubic Hermite Spline Interpolation**.

2. **Ducked / Choked Voices (Noise Gate & Compressor Reversal)**:
   When a microphone's gain is set too low (e.g. Shure SM7B), the speaker's voice falls into the threshold of the RØDECaster's internal APHEX Noise Gate and Compressor, cutting off trailing words and ducking speech. Audio Fixer features an **Adaptive Speech Leveler & Inverse Expander** that lifts quiet and ducked syllables (+6 dB to +18 dB) up to standard broadcast dialogue levels (-23 LUFS / -35 dBFS RMS) without boosting background noise.

---

## Features

- **Native macOS App (`Audio Fixer.app`)**: Double-click to launch, or drag & drop audio files/folders directly onto the app icon.
- **Combined Repair**: Fixes digital distortion spikes AND levels ducked dialogue in a single automated pass.
- **Multi-Track Aware**: Cross-correlates transients across multi-track stems for 100% detection accuracy with 0 false positives.
- **Lossless & Formats**: Preserves 48 kHz, 16-bit / 24-bit / 32-bit float, duration, and channel mapping for seamless Premiere Pro / DaVinci Resolve relinking.
- **Non-Destructive or In-Place**: Export to a `_CLEANED` folder or repair in-place with automatic `.original.wav` backups.

---

## Installation & Requirements

Requires **Python 3.9+** and the following packages:
```bash
pip3 install -r requirements.txt
```

---

## How to Use

### 1. Mac Desktop App (`Audio Fixer.app`)
- Double-click **`Audio Fixer.app`** (or drag a recording folder directly onto the app icon).
- Click **"🔍 Scan for Glitches"** to inspect detected packet dropouts across tracks.
- Check or uncheck **"Also apply Adaptive Voice Leveling"** (enabled by default).
- Click **"⚡ Repair & Export Audio"**.

*(You can also double-click `Launch Audio Fixer.command` or run `python3 gui.py`).*

### 2. Command Line Interface (CLI)

```bash
# 1. Full auto: Repair glitches + level voice into a new folder (_CLEANED)
python3 audio_fixer.py "/path/to/recording_folder"

# 2. Repair in-place (creates safety backups, immediately updating Premiere Pro!)
python3 audio_fixer.py --in-place "/path/to/recording_folder"

# 3. Repair glitches only (skip voice leveling)
python3 audio_fixer.py --no-level "/path/to/recording_folder"

# 4. Preview glitches without rendering (dry run)
python3 audio_fixer.py --scan-only "/path/to/recording_folder"

# 5. Specify a custom output folder
python3 audio_fixer.py -o "/path/to/output" "/path/to/recording_folder"
```

---

## Rebuilding the App Bundle

If you make modifications to the source code, rebuild the native macOS bundle at any time:
```bash
./build_app.sh
```
