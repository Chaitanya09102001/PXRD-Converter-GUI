# PXRD Converter

A simple desktop GUI for converting powder X-ray diffraction (PXRD) scan files into plain, portable formats — no instrument software required.

Built for quick, everyday use in the lab: browse to a scan file, click a button, get either a clean `.xy` coordinate file or an Excel spreadsheet ready to paste into Origin.

## Features

- **Browse and convert with one click** — pick a file, get either a clean `.xy` coordinate file or an Excel spreadsheet ready to paste into Origin.
- **Automatic preview** — the pattern (intensity vs 2theta) is plotted inline as soon as the file loads. No separate button needed.
- **Baseline Correction button** — removes the sloping/curved background from the pattern (SNIP algorithm). The preview updates automatically, showing raw / baseline / corrected curves overlaid.
- **Smoothing** — a checkbox + a "level" input (window size in points, like Origin's smoothing points setting — try 5, 10, 15, 25) + a Smooth button. Reduces noise while preserving peak shape (Savitzky-Golay filter). The preview updates automatically when you click Smooth.
- Both processing steps are **entirely optional** — skip them and Convert exports the data exactly as loaded, same as a plain converter with no extra features.
- **Two output formats:**
  - **`.xy`** — plain `2theta  intensity` coordinates, no headers or comments
  - **`.xlsx`** — Excel file with `2Theta` / `Intensity (a.u.)` column headers, ready to select and paste straight into Origin
- **Supported input formats:**
  - `.ras` — Rigaku (e.g. SmartLab)
  - `.brml` — Bruker (DIFFRAC.SUITE)
  - `.xy`, `.xye`, `.dat`, `.txt`, `.csv`, `.uxd` — plain two-column text (passthrough/cleanup)
- Runs conversion in the background so the UI doesn't freeze on large scans
- Clear error messages if a file can't be parsed, instead of silently producing wrong data
- Doesn't leave `__pycache__` folders behind when you run it

## Why this exists

Most instrument software only exports in its own vendor format, and getting data into Excel/Origin usually means manually stripping headers and reformatting columns by hand. This tool does that in two clicks, and skips vendor formats that can't be verified — see [Notes on format support](#notes-on-format-support) below.

## Installation

Requires Python 3.

```bash
pip install customtkinter openpyxl matplotlib numpy
```

(`customtkinter` is optional — the app falls back to plain `tkinter` if it isn't installed. `numpy` is required for baseline correction and smoothing, and is normally already installed as a matplotlib dependency.)

## Usage

```bash
python pxrd_converter_gui.py
```

1. Click **Browse...** and select a `.ras`, `.brml`, or plain-text scan file — the pattern previews automatically
2. *(Optional)* Click **Baseline Correction** to remove the background — preview updates automatically, showing raw / baseline / corrected curves
3. *(Optional)* Check **Smoothing**, enter a level (window size in points — try 15 to start), click **Smooth** — preview updates automatically. Unchecking the box removes smoothing again.
4. Click **Convert to .xy** or **Convert to Excel (.xlsx)** — exports whatever is currently shown in the preview (raw, baseline-corrected, smoothed, or both combined)
5. Choose where to save — done

Baseline correction and smoothing can be used together (in either order) or skipped entirely — if you skip both, Convert exports the data exactly as loaded, no processing applied. The output filename gets a `_corrected` and/or `_smoothed` suffix so it's clear what's in the file.

To start over from scratch, click **Browse...** again (even to reselect the same file) — this resets both baseline correction and smoothing back off.

## Files

| File | Purpose |
|---|---|
| `pxrd_converter_gui.py` | The GUI application — run this |
| `xrd_parsers.py` | Format-parsing logic, imported by the GUI |
| `baseline.py` | Baseline correction (SNIP algorithm), imported by the GUI |
| `smoothing.py` | Smoothing (Savitzky-Golay filter), imported by the GUI |

Keep all four files in the same folder.

## About baseline correction and smoothing

Both are optional processing steps — if you just want the data exactly as your instrument recorded it, skip them and Convert exports the raw file untouched.

- **Baseline correction** uses the SNIP (Statistics-sensitive Non-linear Iterative Peak-clipping) algorithm — a standard background-removal method for diffraction/spectroscopy data. It estimates a smooth curve that follows the slowly-varying background without being pulled up by sharp peaks, then subtracts it. No manual region selection needed.
- **Smoothing** uses a Savitzky-Golay filter — fits a local polynomial across a moving window (the "level" you enter), which reduces noise while preserving peak height, position, and width much better than a simple moving average. This is the same method used by Origin and most spectroscopy software. Larger levels smooth more aggressively but can start to broaden or flatten real peaks — 5–25 is a typical range; start small and increase only if needed.

## Notes on format support

- `.ras` and `.brml` parsing were verified byte-for-byte against real reference exports, not just written to spec.
- `.raw` (Bruker/Siemens binary) is intentionally **not** supported. It's a legacy/proprietary format rarely used by current instrument software — if your facility can export `.ras` or `.brml` instead (most can), use that.
- If a file fails to parse, please open an issue with a sample file (or a snippet) so the parser can be extended.

## License

MIT License active.
