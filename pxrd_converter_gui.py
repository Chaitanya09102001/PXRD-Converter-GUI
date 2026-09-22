#!/usr/bin/env python3
"""
pxrd_converter_gui.py — Browse a PXRD file (.ras, .brml, .xy, .xye, .dat,
.txt, .csv, .uxd) and convert it with one click to either:
    - a plain .xy file (just 2theta / intensity coordinates, no comments), or
    - an Excel .xlsx file (with "2Theta" / "Intensity (a.u.)" column headers)

The file is previewed automatically (intensity vs 2theta) as soon as it's
loaded -- no separate Preview button needed. Two optional processing steps
are available before converting, and both update the preview automatically:

    - Baseline Correction (SNIP algorithm): removes the sloping/curved
      background from the pattern.
    - Smoothing (Savitzky-Golay filter): reduces noise while preserving
      peak shape. Check the box, set the smoothing "level" (window size in
      points -- like Origin's smoothing points setting; try 5/10/15/25),
      and click Smooth.

Both are optional -- if you skip them, Convert exports the plain
as-loaded data, same as a version of this tool with no processing at all.

Requirements:
    pip install customtkinter openpyxl matplotlib numpy

Usage:
    python pxrd_converter_gui.py
"""

import os
import sys

# Don't create __pycache__ directories/.pyc files when running this script
sys.dont_write_bytecode = True

import threading
import traceback

from xrd_parsers import parse_xrd_file, XRDParseError
from baseline import apply_baseline_correction
from smoothing import apply_smoothing

try:
    import customtkinter as ctk
    USING_CTK = True
except ImportError:
    import tkinter as ctk_fallback
    USING_CTK = False

import tkinter as tk
from tkinter import filedialog, messagebox

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

SUPPORTED_EXTENSIONS = [
    ("PXRD files", "*.ras *.brml *.xy *.xye *.dat *.txt *.csv *.uxd"),
    ("Rigaku RAS", "*.ras"),
    ("Bruker BRML", "*.brml"),
    ("Plain text XY", "*.xy *.xye *.dat *.txt *.csv *.uxd"),
    ("All files", "*.*"),
]

DEFAULT_SMOOTHING_LEVEL = "15"


class PXRDConverterApp:
    def __init__(self):
        if USING_CTK:
            ctk.set_appearance_mode("System")
            ctk.set_default_color_theme("blue")
            self.root = ctk.CTk()
        else:
            self.root = tk.Tk()

        self.root.title("PXRD File Converter")
        self.root.geometry("560x700")
        self.root.resizable(False, False)

        self.input_path = None

        # Cache of the last-parsed raw file: (path, wavelength, data)
        self._cache_path = None
        self._cache_wavelength = None
        self._cache_data = None

        # Processing toggles -- both start off for every newly loaded file
        self._use_baseline = False
        self._baseline_values = None  # for the raw/baseline/corrected overlay
        self._use_smoothing = False
        self._smoothing_level = DEFAULT_SMOOTHING_LEVEL

        self._build_ui()

    # -- small widget helpers -----------------------------------------

    def _label(self, parent, text, **kwargs):
        if USING_CTK:
            return ctk.CTkLabel(parent, text=text, **kwargs)
        return tk.Label(parent, text=text, **kwargs)

    def _button(self, parent, text, command, **kwargs):
        if USING_CTK:
            return ctk.CTkButton(parent, text=text, command=command, **kwargs)
        return tk.Button(parent, text=text, command=command, **kwargs)

    def _frame(self, parent):
        if USING_CTK:
            return ctk.CTkFrame(parent, fg_color="transparent")
        return tk.Frame(parent)

    # -- UI construction ------------------------------------------------

    def _build_ui(self):
        title = self._label(self.root, "PXRD File Converter",
                             font=("Segoe UI", 18, "bold") if USING_CTK else None)
        title.pack(pady=(20, 5))

        subtitle = self._label(
            self.root,
            "Convert .ras / .brml / .xy / .xye / .dat / .txt / .csv / .uxd\n"
            "to a plain .xy file or a 2-column Excel file.",
            justify="center",
        )
        subtitle.pack(pady=(0, 15))

        # -- File picker (top) -------------------------------------------
        self.path_label = self._label(self.root, "No file selected", wraplength=480)
        self.path_label.pack(pady=(0, 5))

        browse_btn = self._button(self.root, "Browse...", self.browse_file, width=200)
        browse_btn.pack(pady=(0, 20))

        # -- Row: Convert to .xy | Convert to Excel | Baseline Correction --
        btn_frame = self._frame(self.root)
        btn_frame.pack(pady=(0, 12))

        if USING_CTK:
            self.xy_btn = ctk.CTkButton(btn_frame, text="Convert to .xy",
                                         command=self.convert_to_xy, width=170, height=42, state="disabled")
            self.xlsx_btn = ctk.CTkButton(btn_frame, text="Convert to Excel (.xlsx)",
                                           command=self.convert_to_xlsx, width=170, height=42, state="disabled")
            self.baseline_btn = ctk.CTkButton(btn_frame, text="Baseline Correction",
                                               command=self.apply_baseline, width=170, height=42, state="disabled")
        else:
            self.xy_btn = tk.Button(btn_frame, text="Convert to .xy",
                                     command=self.convert_to_xy, width=18, height=2, state="disabled")
            self.xlsx_btn = tk.Button(btn_frame, text="Convert to Excel (.xlsx)",
                                       command=self.convert_to_xlsx, width=18, height=2, state="disabled")
            self.baseline_btn = tk.Button(btn_frame, text="Baseline Correction",
                                           command=self.apply_baseline, width=18, height=2, state="disabled")

        self.xy_btn.grid(row=0, column=0, padx=6)
        self.xlsx_btn.grid(row=0, column=1, padx=6)
        self.baseline_btn.grid(row=0, column=2, padx=6)

        # -- Row: [Smoothing checkbox] [level entry] [Smooth button] -------
        smooth_frame = self._frame(self.root)
        smooth_frame.pack(pady=(0, 10))

        self._smoothing_var = tk.BooleanVar(value=False)
        if USING_CTK:
            self.smoothing_check = ctk.CTkCheckBox(
                smooth_frame, text="Smoothing", variable=self._smoothing_var,
                command=self._on_smoothing_toggle, state="disabled"
            )
        else:
            self.smoothing_check = tk.Checkbutton(
                smooth_frame, text="Smoothing", variable=self._smoothing_var,
                command=self._on_smoothing_toggle, state="disabled"
            )
        self.smoothing_check.grid(row=0, column=0, padx=(0, 8))

        self._smoothing_level_var = tk.StringVar(value=DEFAULT_SMOOTHING_LEVEL)
        if USING_CTK:
            self.smoothing_entry = ctk.CTkEntry(
                smooth_frame, textvariable=self._smoothing_level_var, width=60, state="disabled"
            )
        else:
            self.smoothing_entry = tk.Entry(
                smooth_frame, textvariable=self._smoothing_level_var, width=6, state="disabled"
            )
        self.smoothing_entry.grid(row=0, column=1, padx=(0, 8))

        if USING_CTK:
            self.smooth_btn = ctk.CTkButton(
                smooth_frame, text="Smooth", command=self.apply_smoothing_click,
                width=100, state="disabled"
            )
        else:
            self.smooth_btn = tk.Button(
                smooth_frame, text="Smooth", command=self.apply_smoothing_click,
                width=10, state="disabled"
            )
        self.smooth_btn.grid(row=0, column=2)

        self.status_label = self._label(self.root, "", wraplength=500,
                                         text_color="gray" if USING_CTK else None)
        self.status_label.pack(pady=(10, 5))

        # -- Embedded preview plot area --------------------------------
        self.plot_frame = self._frame(self.root)
        if USING_CTK:
            self.plot_frame.configure(fg_color=("gray90", "gray17"))
        self.plot_frame.pack(pady=(5, 15), padx=15, fill="both", expand=True)

        self.figure = Figure(figsize=(5.2, 3.2), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_xlabel("2theta (degrees)")
        self.ax.set_ylabel("Intensity")
        self.ax.text(0.5, 0.5, "Load a file to preview it here",
                     ha="center", va="center", transform=self.ax.transAxes,
                     color="gray", fontsize=9)
        self.figure.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.figure, master=self.plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)

    # -- File selection ----------------------------------------------------

    def browse_file(self):
        path = filedialog.askopenfilename(
            title="Select a PXRD file",
            filetypes=SUPPORTED_EXTENSIONS,
        )
        if not path:
            return
        self.input_path = path
        self.path_label.configure(text=os.path.basename(path))

        # New file -- reset everything back to a clean, unprocessed state
        self._cache_path = None
        self._cache_data = None
        self._cache_wavelength = None
        self._use_baseline = False
        self._baseline_values = None
        self._use_smoothing = False
        self._smoothing_var.set(False)
        self._smoothing_level_var.set(DEFAULT_SMOOTHING_LEVEL)

        self.xy_btn.configure(state="normal")
        self.xlsx_btn.configure(state="normal")
        self.baseline_btn.configure(state="normal")
        self.smoothing_check.configure(state="normal")
        self.smoothing_entry.configure(state="disabled")
        self.smooth_btn.configure(state="disabled")

        self.set_status("Loading preview...")
        self._refresh_preview(status_prefix="Loaded")

    # -- Data pipeline ----------------------------------------------------

    def _get_parsed_data(self, path):
        """Parse `path`, reusing the cached result if it's the same file
        already parsed."""
        if self._cache_path == path and self._cache_data is not None:
            return self._cache_wavelength, self._cache_data
        wavelength, data = parse_xrd_file(path)
        self._cache_path = path
        self._cache_wavelength = wavelength
        self._cache_data = data
        return wavelength, data

    def _compute_active_data(self, path):
        """Applies the current toggles (baseline correction, smoothing) on
        top of the raw parsed data, freshly each time -- so the result is
        always consistent regardless of the order buttons were clicked.
        Returns (wavelength, active_data, baseline_values_or_None)."""
        wavelength, raw_data = self._get_parsed_data(path)
        data = raw_data
        baseline_values = None
        if self._use_baseline:
            data, baseline_values = apply_baseline_correction(data)
        if self._use_smoothing:
            data = apply_smoothing(data, window=self._smoothing_level)
        return wavelength, data, baseline_values

    # -- Baseline correction ----------------------------------------------

    def apply_baseline(self):
        if not self.input_path:
            return
        self._use_baseline = True
        self._refresh_preview(status_prefix="Baseline correction applied")

    # -- Smoothing ----------------------------------------------------

    def _on_smoothing_toggle(self):
        checked = self._smoothing_var.get()
        if checked:
            self.smoothing_entry.configure(state="normal")
            self.smooth_btn.configure(state="normal")
        else:
            self.smoothing_entry.configure(state="disabled")
            self.smooth_btn.configure(state="disabled")
            if self._use_smoothing:
                self._use_smoothing = False
                self._refresh_preview(status_prefix="Smoothing removed")

    def apply_smoothing_click(self):
        if not self.input_path:
            return
        level_text = self._smoothing_level_var.get().strip()
        try:
            level = int(level_text)
            if level < 3:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Invalid smoothing level",
                "Smoothing level must be a whole number of 3 or more "
                "(e.g. 5, 10, 15, 25) -- this is the smoothing window size in points."
            )
            return
        self._smoothing_level = level
        self._use_smoothing = True
        self._refresh_preview(status_prefix=f"Smoothed (window={level})")

    # -- Preview (auto-refreshed, no manual Preview button) ----------------

    def _refresh_preview(self, status_prefix="Updated"):
        if not self.input_path:
            return
        threading.Thread(target=self._do_refresh_preview, args=(status_prefix,), daemon=True).start()

    def _do_refresh_preview(self, status_prefix):
        try:
            wavelength, data, baseline_values = self._compute_active_data(self.input_path)
        except XRDParseError as e:
            self.root.after(0, lambda: self._show_error(str(e)))
            return
        except Exception:
            self.root.after(0, lambda: self._show_error(
                "Unexpected error while processing the file:\n" + traceback.format_exc()
            ))
            return

        two_theta = [d[0] for d in data]
        intensity = [d[1] for d in data]
        fname = os.path.basename(self.input_path)
        wl_text = f", wavelength {wavelength:.5f} A" if wavelength else ""

        tags = []
        if self._use_baseline:
            tags.append("baseline corrected")
        if self._use_smoothing:
            tags.append(f"smoothed, window={self._smoothing_level}")
        tag_text = f" ({', '.join(tags)})" if tags else ""

        raw_y = None
        if self._use_baseline and baseline_values is not None:
            _, raw_data = self._get_parsed_data(self.input_path)
            raw_y = [d[1] for d in raw_data]

        def _draw():
            self.ax.clear()
            if raw_y is not None:
                corrected_label = "corrected" + (" + smoothed" if self._use_smoothing else "")
                self.ax.plot(two_theta, raw_y, linewidth=0.5, color="lightgray", label="raw")
                self.ax.plot(two_theta, baseline_values, linewidth=1.0, color="red", label="baseline")
                self.ax.plot(two_theta, intensity, linewidth=0.8, color="green", label=corrected_label)
                self.ax.legend(fontsize=7)
            else:
                self.ax.plot(two_theta, intensity, linewidth=0.8, color="#1f77b4")
            self.ax.set_xlabel("2theta (degrees)")
            self.ax.set_ylabel("Intensity")
            self.ax.set_title(f"{fname}{wl_text}{tag_text}", fontsize=9)
            self.ax.set_xlim(min(two_theta), max(two_theta))
            self.figure.tight_layout()
            self.canvas.draw()
            self.set_status(f"{status_prefix} -- {len(data)} points{tag_text}")

        self.root.after(0, _draw)

    # -- Conversion ----------------------------------------------------

    def set_status(self, text, is_error=False):
        color = "red" if is_error else ("gray" if USING_CTK else "black")
        if USING_CTK:
            self.status_label.configure(text=text, text_color=color)
        else:
            self.status_label.configure(text=text, fg=color)

    def convert_to_xy(self):
        self._run_conversion(mode="xy")

    def convert_to_xlsx(self):
        self._run_conversion(mode="xlsx")

    def _run_conversion(self, mode):
        if not self.input_path:
            return
        self.set_status("Converting...")
        threading.Thread(target=self._do_convert, args=(mode,), daemon=True).start()

    def _do_convert(self, mode):
        try:
            wavelength, data, _ = self._compute_active_data(self.input_path)
        except XRDParseError as e:
            self.root.after(0, lambda: self._show_error(str(e)))
            return
        except Exception:
            self.root.after(0, lambda: self._show_error(
                "Unexpected error while reading the file:\n" + traceback.format_exc()
            ))
            return

        base, _ = os.path.splitext(self.input_path)
        if self._use_baseline:
            base += "_corrected"
        if self._use_smoothing:
            base += "_smoothed"

        try:
            if mode == "xy":
                out_path = filedialog.asksaveasfilename(
                    title="Save .xy file",
                    defaultextension=".xy",
                    initialfile=os.path.basename(base) + ".xy",
                    filetypes=[("XY file", "*.xy")],
                )
                if not out_path:
                    self.root.after(0, lambda: self.set_status(""))
                    return
                self._write_xy(out_path, data)
            else:
                out_path = filedialog.asksaveasfilename(
                    title="Save Excel file",
                    defaultextension=".xlsx",
                    initialfile=os.path.basename(base) + ".xlsx",
                    filetypes=[("Excel file", "*.xlsx")],
                )
                if not out_path:
                    self.root.after(0, lambda: self.set_status(""))
                    return
                self._write_xlsx(out_path, data)
        except Exception:
            self.root.after(0, lambda: self._show_error(
                "Error while writing the output file:\n" + traceback.format_exc()
            ))
            return

        self.root.after(0, lambda: self._show_success(out_path, len(data)))

    def _write_xy(self, out_path, data):
        # Plain coordinates only, no wavelength line, no comments
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            for two_theta, intensity in data:
                f.write(f"{two_theta:g} {intensity:g}\n")

    def _write_xlsx(self, out_path, data):
        try:
            from openpyxl import Workbook
        except ImportError:
            raise RuntimeError("openpyxl is not installed. Run: pip install openpyxl")

        wb = Workbook()
        ws = wb.active
        ws.title = "PXRD Data"
        ws.append(["2Theta", "Intensity (a.u.)"])
        for two_theta, intensity in data:
            ws.append([two_theta, intensity])
        wb.save(out_path)

    def _show_success(self, out_path, n_points):
        self.set_status(f"Saved {n_points} points -> {os.path.basename(out_path)}")
        messagebox.showinfo("Done", f"Saved {n_points} points to:\n{out_path}")

    def _show_error(self, message):
        self.set_status("Failed.", is_error=True)
        messagebox.showerror("Error", message)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = PXRDConverterApp()
    app.run()
