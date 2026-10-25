import os
import sys
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List

from core.engine import AudioFixerEngine, GlitchEvent


class AudioFixerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Audio Fixer - Rodecaster USB Glitch & Pop Repair")
        self.root.geometry("860x650")
        self.root.minsize(720, 500)

        self.engine = AudioFixerEngine()
        self.selected_files: List[str] = []
        self.detected_events: List[GlitchEvent] = []
        self.is_processing = False

        self._setup_style()
        self._build_ui()

    def _setup_style(self):
        self.style = ttk.Style(self.root)
        # Use native aqua theme on Mac
        if "aqua" in self.style.theme_names():
            self.style.theme_use("aqua")

    def _build_ui(self):
        # Header frame
        header_frame = ttk.Frame(self.root, padding="15 15 15 5")
        header_frame.pack(fill=tk.X)

        title_lbl = ttk.Label(
            header_frame,
            text="Rodecaster Multi-Track USB Audio Fixer",
            font=("System", 18, "bold")
        )
        title_lbl.pack(anchor=tk.W)

        subtitle_lbl = ttk.Label(
            header_frame,
            text="Automatically detect and repair synchronized USB packet drops, clipping spikes, and 1-sample distortion glitches.",
            font=("System", 12)
        )
        subtitle_lbl.pack(anchor=tk.W, pady=(2, 10))

        # Folder selection frame
        input_frame = ttk.LabelFrame(self.root, text=" 1. Select Recording Folder or Tracks ", padding="10")
        input_frame.pack(fill=tk.X, padx=15, pady=5)

        self.path_var = tk.StringVar()
        entry = ttk.Entry(input_frame, textvariable=self.path_var, font=("System", 12))
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        btn_browse_folder = ttk.Button(input_frame, text="Browse Folder...", command=self._browse_folder)
        btn_browse_folder.pack(side=tk.LEFT, padx=2)

        btn_browse_files = ttk.Button(input_frame, text="Select Files...", command=self._browse_files)
        btn_browse_files.pack(side=tk.LEFT, padx=2)

        # File summary label
        self.file_summary_var = tk.StringVar(value="No files loaded.")
        lbl_file_summary = ttk.Label(input_frame, textvariable=self.file_summary_var, foreground="#555555")
        lbl_file_summary.pack(anchor=tk.W, pady=(8, 0))

        # Output options frame
        opt_frame = ttk.LabelFrame(self.root, text=" 2. Export Mode ", padding="10")
        opt_frame.pack(fill=tk.X, padx=15, pady=5)

        self.export_mode_var = tk.StringVar(value="cleaned_folder")
        rb_cleaned = ttk.Radiobutton(
            opt_frame,
            text="Create Cleaned Folder (e.g. recording_CLEANED) [Safest, Non-destructive]",
            variable=self.export_mode_var,
            value="cleaned_folder"
        )
        rb_cleaned.pack(anchor=tk.W, pady=2)

        rb_inplace = ttk.Radiobutton(
            opt_frame,
            text="In-Place Repair (Overwrites original WAV, preserves .original.wav backup - best for Premiere Pro)",
            variable=self.export_mode_var,
            value="in_place"
        )
        rb_inplace.pack(anchor=tk.W, pady=2)

        ttk.Separator(opt_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)
        self.level_var = tk.BooleanVar(value=True)
        cb_level = ttk.Checkbutton(
            opt_frame,
            text="Also apply Adaptive Voice Leveling & Inverse Expansion (Reverses ducking/gate choke on quiet mics)",
            variable=self.level_var
        )
        cb_level.pack(anchor=tk.W, pady=2)

        # Actions and table frame
        action_frame = ttk.Frame(self.root, padding="15 5 15 5")
        action_frame.pack(fill=tk.X)

        self.btn_scan = ttk.Button(action_frame, text="🔍 Scan for Glitches", command=self._start_scan)
        self.btn_scan.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_repair = ttk.Button(action_frame, text="⚡ Repair & Export Audio", command=self._start_repair, state=tk.DISABLED)
        self.btn_repair.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_reveal = ttk.Button(action_frame, text="📂 Reveal in Finder", command=self._reveal_in_finder, state=tk.DISABLED)
        self.btn_reveal.pack(side=tk.LEFT)

        # Glitch table
        table_frame = ttk.LabelFrame(self.root, text=" 3. Detected Audio Glitches ", padding="5")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        cols = ("num", "time", "span", "tracks", "peak")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("num", text="#")
        self.tree.heading("time", text="Timestamp")
        self.tree.heading("span", text="Duration")
        self.tree.heading("tracks", text="Multi-track Sync")
        self.tree.heading("peak", text="Peak Distortion Level")

        self.tree.column("num", width=40, anchor=tk.CENTER)
        self.tree.column("time", width=120, anchor=tk.CENTER)
        self.tree.column("span", width=100, anchor=tk.CENTER)
        self.tree.column("tracks", width=140, anchor=tk.CENTER)
        self.tree.column("peak", width=160, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Progress bar & status
        status_frame = ttk.Frame(self.root, padding="15 5 15 15")
        status_frame.pack(fill=tk.X)

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(status_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))

        self.status_var = tk.StringVar(value="Ready. Select a folder to begin.")
        lbl_status = ttk.Label(status_frame, textvariable=self.status_var, font=("System", 11))
        lbl_status.pack(anchor=tk.W)

        self.last_output_dir = ""

    def _browse_folder(self):
        f = filedialog.askdirectory(title="Select Recording Folder")
        if f:
            self.path_var.set(f)
            self._load_files_from_path(f)

    def _browse_files(self):
        files = filedialog.askopenfilenames(
            title="Select WAV Tracks",
            filetypes=[("Audio Files", "*.wav *.wave *.flac *.aif *.aiff")]
        )
        if files:
            first_dir = os.path.dirname(files[0])
            self.path_var.set(first_dir)
            self.selected_files = sorted(list(files))
            self._update_file_summary()

    def _load_files_from_path(self, path: str):
        valid_exts = {'.wav', '.wave', '.aif', '.aiff', '.flac'}
        found = []
        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                for f in sorted(files):
                    if not f.startswith('.') and os.path.splitext(f)[1].lower() in valid_exts:
                        found.append(os.path.join(root, f))
        elif os.path.isfile(path):
            if os.path.splitext(path)[1].lower() in valid_exts:
                found.append(path)
        self.selected_files = found
        self._update_file_summary()

    def _update_file_summary(self):
        if not self.selected_files:
            self.file_summary_var.set("No valid audio files found in directory.")
            self.btn_scan.config(state=tk.DISABLED)
            self.btn_repair.config(state=tk.DISABLED)
            return

        names = [os.path.basename(f) for f in self.selected_files]
        sample_names = ", ".join(names[:3])
        if len(names) > 3:
            sample_names += f" (+{len(names)-3} more)"
        self.file_summary_var.set(f"Loaded {len(self.selected_files)} track(s): {sample_names}")
        self.btn_scan.config(state=tk.NORMAL)
        self.btn_repair.config(state=tk.DISABLED)
        self.btn_reveal.config(state=tk.DISABLED)
        # Clear previous events
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _start_scan(self):
        if not self.selected_files or self.is_processing:
            return
        self.is_processing = True
        self.btn_scan.config(state=tk.DISABLED)
        self.btn_repair.config(state=tk.DISABLED)
        self.btn_reveal.config(state=tk.DISABLED)

        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)

        def worker():
            def prog_cb(status, frac):
                self.root.after(0, lambda: self.status_var.set(status))
                self.root.after(0, lambda: self.progress_var.set(frac * 100))

            try:
                events = self.engine.detect_glitches(self.selected_files, progress_cb=prog_cb)
                self.detected_events = events
                self.root.after(0, self._scan_finished)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Scan Error", str(e)))
                self.root.after(0, self._reset_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _scan_finished(self):
        self.is_processing = False
        self.btn_scan.config(state=tk.NORMAL)
        self.progress_var.set(100)

        n = len(self.detected_events)
        if n == 0:
            self.status_var.set("Scan complete: No distortion glitches detected!")
            messagebox.showinfo("Scan Result", "No audio glitches or clipping spikes found in the loaded tracks.")
            return

        self.status_var.set(f"Scan complete: Found {n} synchronized glitch events.")
        self.btn_repair.config(state=tk.NORMAL)

        # Populate tree
        total_tracks = len(self.selected_files)
        for idx, e in enumerate(self.detected_events, 1):
            tracks_str = f"{len(e.tracks_involved)}/{total_tracks} tracks"
            peak_str = f"{e.peak_amplitude:.0f} ({(e.peak_amplitude/32768)*100:.1f}% FS)"
            self.tree.insert(
                "",
                tk.END,
                values=(idx, e.formatted_time, f"{e.span_samples} samples", tracks_str, peak_str)
            )

    def _start_repair(self):
        if not self.selected_files or not self.detected_events or self.is_processing:
            return

        mode = self.export_mode_var.get()
        first_input = self.selected_files[0]
        if mode == "cleaned_folder":
            base_dir = os.path.dirname(first_input)
            out_dir = base_dir.rstrip("/\\") + "_CLEANED"
            os.makedirs(out_dir, exist_ok=True)
            self.last_output_dir = out_dir
        else:
            self.last_output_dir = os.path.dirname(first_input)
            out_dir = None

        self.is_processing = True
        self.btn_scan.config(state=tk.DISABLED)
        self.btn_repair.config(state=tk.DISABLED)
        self.btn_reveal.config(state=tk.DISABLED)

        def worker():
            try:
                total_files = len(self.selected_files)
                for f_idx, src_path in enumerate(self.selected_files):
                    fname = os.path.basename(src_path)

                    if mode == "in_place":
                        bak_path = src_path + ".original.wav"
                        if not os.path.exists(bak_path):
                            os.rename(src_path, bak_path)
                            real_src = bak_path
                        else:
                            real_src = bak_path
                        dst_path = src_path
                    else:
                        real_src = src_path
                        dst_path = os.path.join(out_dir, fname)

                    def f_prog(frac):
                        overall = ((f_idx + frac) / total_files) * 100
                        self.root.after(0, lambda: self.progress_var.set(overall))
                        self.root.after(0, lambda: self.status_var.set(
                            f"Rendering [{f_idx+1}/{total_files}]: {fname} ({frac*100:.1f}%)"
                        ))

                    self.engine.render_cleaned_file(real_src, dst_path, self.detected_events, progress_cb=f_prog)

                    if self.level_var.get():
                        from core.leveler import level_audio
                        self.root.after(0, lambda: self.status_var.set(f"Leveling dialogue: {fname}..."))
                        tmp_level = dst_path + ".lvl_tmp.wav"
                        level_audio(dst_path, tmp_level)
                        os.replace(tmp_level, dst_path)

                self.root.after(0, self._repair_finished)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Repair Error", str(e)))
                self.root.after(0, self._reset_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _repair_finished(self):
        self.is_processing = False
        self.btn_scan.config(state=tk.NORMAL)
        self.btn_repair.config(state=tk.NORMAL)
        self.btn_reveal.config(state=tk.NORMAL)
        self.progress_var.set(100)
        self.status_var.set("All audio files repaired and rendered successfully!")

        msg = f"Successfully repaired {len(self.detected_events)} glitch events across {len(self.selected_files)} files!\n\nDestination: {self.last_output_dir}"
        messagebox.showinfo("Audio Repair Complete", msg)

    def _reveal_in_finder(self):
        if self.last_output_dir and os.path.exists(self.last_output_dir):
            subprocess.run(["open", self.last_output_dir])

    def _reset_ui(self):
        self.is_processing = False
        self.btn_scan.config(state=tk.NORMAL)
        self.btn_repair.config(state=tk.NORMAL if self.detected_events else tk.DISABLED)


def launch_gui():
    root = tk.Tk()
    app = AudioFixerApp(root)

    # Native macOS drag-and-drop document handler
    def open_mac_doc(*args):
        for path in args:
            if path and os.path.exists(path):
                app.path_var.set(path)
                app._load_files_from_path(path)
                break

    try:
        root.createcommand("::tk::mac::OpenDocument", open_mac_doc)
    except Exception:
        pass

    # Check if a path was passed via command line (or dragged onto app)
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        target = sys.argv[1]
        app.path_var.set(target)
        app._load_files_from_path(target)
    else:
        default_rec = "/Volumes/Extreme SSD/21 OCT 2026/2026-10-21_17-35-23_RECORDING"
        if os.path.exists(default_rec):
            app.path_var.set(default_rec)
            app._load_files_from_path(default_rec)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
