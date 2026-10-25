#!/usr/bin/env python3
"""
Audio Fixer - Automated Rodecaster USB Multi-track Glitch & Pop Repair Tool
===========================================================================
Detects and repairs synchronized USB packet distortion spikes, buffer drops,
and sample glitches across multi-track Rodecaster/OBS audio recordings.
"""

import os
import sys
import argparse
import time
from typing import List

from core.engine import AudioFixerEngine, GlitchEvent


def print_banner():
    banner = r"""
   ___            _ _         _____ _                 
  / _ \          | (_)       |  ___(_)                
 / /_\ \_   _  __| |_  ___   | |_   ___  _____ _ __   
 |  _  | | | |/ _` | |/ _ \  |  _| | \ \/ / _ \ '__|  
 | | | | |_| | (_| | | (_) | | |   | |>  <  __/ |     
 \_| |_/\__,_|\__,_|_|\___/  \_|   |_/_/\_\___|_|     
   Multi-track USB Glitch & Distortion Repair Engine
"""
    print(banner)


def format_size(bytes_val: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


def collect_audio_files(inputs: List[str]) -> List[str]:
    valid_exts = {'.wav', '.wave', '.aif', '.aiff', '.flac'}
    audio_files = []
    for inp in inputs:
        if os.path.isdir(inp):
            for root, _, files in os.walk(inp):
                for f in sorted(files):
                    if not f.startswith('.') and os.path.splitext(f)[1].lower() in valid_exts:
                        audio_files.append(os.path.join(root, f))
        elif os.path.isfile(inp):
            if os.path.splitext(inp)[1].lower() in valid_exts:
                audio_files.append(inp)
    return sorted(list(set(audio_files)))


def main():
    parser = argparse.ArgumentParser(
        description="Automated Rodecaster USB Multi-track Glitch & Distortion Repair Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan and repair all files in a recording folder (outputs to folder_CLEANED)
  python3 audio_fixer.py "/Volumes/Extreme SSD/21 OCT 2026/2026-10-21_17-35-23_RECORDING"

  # Scan only (preview detected glitches without rendering)
  python3 audio_fixer.py --scan-only "/path/to/recording"

  # Repair in-place with automatic .original.wav backups (ideal for Premiere Pro)
  python3 audio_fixer.py --in-place "/path/to/recording"

  # Launch the Mac Graphical User Interface
  python3 audio_fixer.py --gui
        """
    )
    parser.add_argument("paths", nargs="*", help="Folder path or WAV audio file paths to process")
    parser.add_argument("-o", "--output-dir", help="Directory where cleaned audio files will be saved")
    parser.add_argument("-s", "--scan-only", action="store_true", help="Only scan and report glitches; do not render")
    parser.add_argument("-i", "--in-place", action="store_true", help="Replace original files directly (creates .bak backups)")
    parser.add_argument("-t", "--threshold", type=float, default=3500.0, help="Spike curvature threshold (default: 3500)")
    parser.add_argument("-l", "--level", action="store_true", default=True, help="Apply adaptive voice leveling & upward expansion (default: True)")
    parser.add_argument("--no-level", dest="level", action="store_false", help="Disable adaptive voice leveling (only repair glitch spikes)")
    parser.add_argument("--gui", action="store_true", help="Launch the Desktop GUI")

    args = parser.parse_args()

    if args.gui or len(sys.argv) == 1:
        # Launch GUI
        try:
            from gui import launch_gui
            launch_gui()
            return
        except ImportError as e:
            if args.gui:
                print(f"Error launching GUI: {e}", file=sys.stderr)
                sys.exit(1)

    if not args.paths:
        parser.print_help()
        sys.exit(1)

    print_banner()

    files = collect_audio_files(args.paths)
    if not files:
        print("[!] No compatible audio files found (.wav, .aif, .flac).")
        sys.exit(1)

    print(f"[*] Found {len(files)} audio track(s) to process:")
    for f in files:
        sz = format_size(os.path.getsize(f))
        print(f"    - {os.path.basename(f)} ({sz})")
    print()

    engine = AudioFixerEngine(curv_threshold=args.threshold)

    # Step 1: Scan
    print("[*] Phase 1: Analyzing audio waveforms and cross-correlating multi-track spikes...")
    t0 = time.time()

    def progress_cb(status: str, frac: float):
        bar_len = 30
        filled = int(round(bar_len * frac))
        bar = "=" * filled + "-" * (bar_len - filled)
        sys.stdout.write(f"\r    [{bar}] {frac*100:5.1f}% | {status:<35}")
        sys.stdout.flush()

    events = engine.detect_glitches(files, progress_cb=progress_cb)
    print()
    t_scan = time.time() - t0

    print(f"\n[+] Analysis complete in {t_scan:.2f}s!")
    print(f"[+] Total glitch events detected: {len(events)}")

    if not events and not args.level:
        print("    Congratulations! No distortion spikes or packet glitches detected.")
        return

    print("\n" + "=" * 80)
    print(f"{'#':<3} | {'Timestamp':<12} | {'Frame Range':<24} | {'Span':<7} | {'Tracks':<8} | {'Peak Level'}")
    print("-" * 80)
    for idx, e in enumerate(events, 1):
        tracks_str = f"{len(e.tracks_involved)}/{len(files)}"
        print(f"{idx:<3} | {e.formatted_time:<12} | {f'{e.start_frame}..{e.end_frame}':<24} | {f'{e.span_samples} smp':<7} | {tracks_str:<8} | {e.peak_amplitude:.0f} ({(e.peak_amplitude/32768)*100:.1f}%)")
    print("=" * 80)

    if args.scan_only:
        print("\n[*] Scan-only mode enabled. No audio files were modified.")
        return

    # Step 2: Determine output destinations
    print("\n[*] Phase 2: Rendering cleaned WAV files with Hermite cubic spline & silence ducking...")
    
    first_input = args.paths[0]
    if args.output_dir:
        out_dir = os.path.abspath(args.output_dir)
    elif args.in_place:
        out_dir = None
    elif os.path.isdir(first_input):
        out_dir = os.path.abspath(first_input.rstrip("/\\") + "_CLEANED")
    else:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(first_input)), "CLEANED")

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        print(f"[+] Output directory: {out_dir}")

    t_render_start = time.time()

    for idx, src_path in enumerate(files, 1):
        fname = os.path.basename(src_path)
        print(f"\n[{idx}/{len(files)}] Processing {fname}...")

        if args.in_place:
            bak_path = src_path + ".original.wav"
            tmp_path = src_path + ".tmp.wav"
            if not os.path.exists(bak_path):
                print(f"    - Creating safety backup: {os.path.basename(bak_path)}")
                os.rename(src_path, bak_path)
                real_src = bak_path
            else:
                real_src = bak_path

            dst_path = src_path
        else:
            real_src = src_path
            dst_path = os.path.join(out_dir, fname)

        def file_progress(frac: float):
            bar_len = 30
            filled = int(round(bar_len * frac))
            bar = "=" * filled + "-" * (bar_len - filled)
            sys.stdout.write(f"\r    [{bar}] {frac*100:5.1f}% | Rendering cleaned audio")
            sys.stdout.flush()

        engine.render_cleaned_file(real_src, dst_path, events, progress_cb=file_progress)
        print()
        print(f"    -> Successfully rendered: {dst_path}")

        if args.level:
            print(f"    -> Applying adaptive voice leveling & upward expansion...")
            from core.leveler import level_audio
            tmp_level = dst_path + ".level_tmp.wav"
            level_audio(dst_path, tmp_level)
            os.replace(tmp_level, dst_path)
            print(f"    -> Successfully leveled: {dst_path}")

    t_total = time.time() - t_render_start
    print(f"\n[+] All {len(files)} files successfully cleaned and exported in {t_total:.2f}s!")
    if out_dir:
        print(f"[+] Cleaned audio folder: {out_dir}")
    print("[+] Audio glitch repair finished successfully.")


if __name__ == "__main__":
    main()
