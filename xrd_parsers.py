"""
xrd_parsers.py — Shared parsing logic for the PXRD Converter GUI.

Supports:
    .ras   (Rigaku)                -> full support, verified against real files
    .brml  (Bruker, zip of XML)    -> full support, verified against real files
    .xy / .xye / .txt / .dat / .csv / .uxd -> plain two-column text, passthrough
"""

import os
import re
import zipfile
import xml.etree.ElementTree as ET


class XRDParseError(Exception):
    pass


# ---------------------------------------------------------------------------
# .ras (Rigaku)
# ---------------------------------------------------------------------------

def parse_ras(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    wavelength = None
    m = re.search(r'\*HW_XG_WAVE_LENGTH_ALPHA1\s+"([^"]+)"', text)
    if m:
        try:
            wavelength = float(m.group(1))
        except ValueError:
            pass

    data = []
    for block in re.findall(r"\*RAS_INT_START(.*?)\*RAS_INT_END", text, re.DOTALL):
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                data.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue

    if not data:
        raise XRDParseError(f"No RAS_INT_START/END data block found in {os.path.basename(path)}.")

    return wavelength, data


# ---------------------------------------------------------------------------
# .brml (Bruker) -- zip of XML files. Verified against a real file
# (FLP_AC.brml, checked point-by-point against a reference .xy export).
# ---------------------------------------------------------------------------

def _strip_ns(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _find_all(elem, name):
    """Find all descendant elements matching `name`, ignoring XML namespaces."""
    return [e for e in elem.iter() if _strip_ns(e.tag) == name]


def _find_first(elem, name):
    found = _find_all(elem, name)
    return found[0] if found else None


def parse_brml(path):
    try:
        zf = zipfile.ZipFile(path, "r")
    except zipfile.BadZipFile:
        raise XRDParseError(f"{os.path.basename(path)} is not a valid .brml (zip) file.")

    raw_xml_names = sorted(n for n in zf.namelist() if "RawData" in n and n.endswith(".xml"))
    if not raw_xml_names:
        raise XRDParseError(
            f"No RawData*.xml found inside {os.path.basename(path)}. "
            "This doesn't look like a standard Bruker .brml export."
        )

    # Use the first RawData XML (single-scan files only have one)
    with zf.open(raw_xml_names[0]) as f:
        root = ET.fromstring(f.read())

    # Wavelength: Bruker brml stores this as e.g. <WaveLengthAlpha1 Unit="Å" Value="1.5406" />
    wavelength = None
    for tag_name in ("WaveLengthAlpha1", "WaveLengthAverage"):
        el = _find_first(root, tag_name)
        if el is not None and "Value" in el.attrib:
            try:
                wavelength = float(el.attrib["Value"])
                break
            except ValueError:
                pass

    # Find the DataRoute(s) that actually contain measured Datum points
    routes = _find_all(root, "DataRoute")
    chosen_route = None
    for route in routes:
        if _find_all(route, "Datum"):
            chosen_route = route
            break
    if chosen_route is None:
        raise XRDParseError(
            f"Could not find any <Datum> measurement points in {os.path.basename(path)}."
        )

    # Get scan start/increment for the 2theta axis
    start = None
    increment = None
    for axis in _find_all(chosen_route, "ScanAxisInfo"):
        axis_name = axis.attrib.get("AxisName", "")
        if "TwoTheta" in axis_name or "2Theta" in axis_name:
            start_el = _find_first(axis, "Start")
            inc_el = _find_first(axis, "Increment")
            if start_el is not None and start_el.text:
                start = float(start_el.text)
            if inc_el is not None and inc_el.text:
                increment = float(inc_el.text)
            break

    datum_elements = _find_all(chosen_route, "Datum")
    data = []
    if start is not None and increment is not None:
        # Equidistant scan. Each Datum is comma-separated, e.g.:
        #   "<time>,<flag>,<two_theta>,<theta>,<intensity>"
        # Intensity is always the last value; 2theta (3rd value, if present) is
        # used when available and falls back to the computed start+i*increment.
        # Steps that were never measured (e.g. an interrupted/resumed scan) are
        # marked with intensity == -9999 and are skipped.
        for i, datum in enumerate(datum_elements):
            if not datum.text:
                continue
            parts = [p.strip() for p in datum.text.split(",") if p.strip() != ""]
            if not parts:
                continue
            try:
                intensity = float(parts[-1])
            except ValueError:
                continue
            if intensity == -9999:
                continue  # unmeasured / interrupted step
            if len(parts) >= 3:
                try:
                    two_theta = float(parts[2])
                except ValueError:
                    two_theta = start + i * increment
            else:
                two_theta = start + i * increment
            data.append((two_theta, intensity))
    else:
        # Fallback: some brml exports store 2theta explicitly as one of the
        # comma-separated values. Without a confirmed column order we can't
        # guess reliably, so surface a clear error instead of silently
        # guessing wrong.
        raise XRDParseError(
            f"Found Datum points in {os.path.basename(path)} but no TwoTheta "
            "Start/Increment scan info, so 2theta values can't be reconstructed "
            "reliably. Try re-exporting as .ras or .xy from your instrument software."
        )

    if not data:
        raise XRDParseError(f"No usable data points extracted from {os.path.basename(path)}.")

    return wavelength, data


# ---------------------------------------------------------------------------
# Plain two-column text: .xy, .xye, .dat, .txt, .csv, .uxd
# ---------------------------------------------------------------------------

def parse_text_xy(path):
    wavelength = None
    data = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f):
            line = line.strip()
            if not line or line.startswith(("#", "*", "_")):
                continue
            # Allow comma or whitespace separated values
            parts = re.split(r"[,\s]+", line)
            parts = [p for p in parts if p != ""]
            if len(parts) == 1:
                # Likely a lone wavelength value on its own line
                if wavelength is None and line_no < 3:
                    try:
                        wavelength = float(parts[0])
                    except ValueError:
                        pass
                continue
            try:
                x = float(parts[0])
                y = float(parts[1])
            except ValueError:
                continue
            data.append((x, y))

    if not data:
        raise XRDParseError(f"No numeric two-column data found in {os.path.basename(path)}.")

    return wavelength, data


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

PARSERS = {
    ".ras": parse_ras,
    ".brml": parse_brml,
    ".xy": parse_text_xy,
    ".xye": parse_text_xy,
    ".dat": parse_text_xy,
    ".txt": parse_text_xy,
    ".csv": parse_text_xy,
    ".uxd": parse_text_xy,
}


def parse_xrd_file(path):
    """Returns (wavelength_or_None, [(two_theta, intensity), ...])."""
    ext = os.path.splitext(path)[1].lower()
    parser = PARSERS.get(ext)
    if parser is None:
        raise XRDParseError(f"Unsupported file type: {ext or '(no extension)'}")
    return parser(path)
