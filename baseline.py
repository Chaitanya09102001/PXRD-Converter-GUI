"""
baseline.py — Background/baseline correction for PXRD patterns.

Uses the SNIP (Statistics-sensitive Non-linear Iterative Peak-clipping)
algorithm, a standard, widely-used baseline estimation method for
diffraction/spectroscopy data. It works directly on the intensity values,
needs no peak-picking or manual region selection, and only depends on numpy
(no scipy required).

Reference: Ryan, C.G. et al. (1988), "SNIP, a statistics-sensitive
background treatment for the quantitative analysis of PIXE spectra in
geoscience applications", Nucl. Instrum. Methods Phys. Res. B 34, 396-402.
"""

import numpy as np


def snip_baseline(intensity, iterations=40):
    """Estimate a smooth baseline under `intensity` using the SNIP algorithm.

    `intensity` : 1D array-like of counts (must be >= -1, i.e. no large
                  negative values -- ordinary PXRD counts are fine).
    `iterations`: controls how far the baseline can follow slow background
                  curvature. Higher = allows tracking a more slowly-varying
                  background; too high risks eating into broad peaks.
                  40 is a reasonable default for typical PXRD scans.

    Returns a 1D numpy array the same length as `intensity`: the estimated
    baseline (not the corrected data -- subtract this yourself).
    """
    y = np.asarray(intensity, dtype=float)
    n = len(y)

    # LLS (log-log-sqrt) transform: compresses peak heights relative to the
    # background, which is what lets a simple local-minimum clip below
    # follow the background without being dragged up by sharp peaks.
    v = np.log(np.log(np.sqrt(y + 1.0) + 1.0) + 1.0)

    for m in range(1, iterations + 1):
        if 2 * m >= n:
            break
        window_avg = (v[: n - 2 * m] + v[2 * m :]) / 2.0
        v[m : n - m] = np.minimum(v[m : n - m], window_avg)

    # Inverse LLS transform back to intensity units
    baseline = (np.exp(np.exp(v) - 1.0) - 1.0) ** 2 - 1.0
    return baseline


def apply_baseline_correction(data, iterations=40, clip_negative=True):
    """data: list of (two_theta, intensity) tuples.

    Returns (corrected_data, baseline_values) where corrected_data is a new
    list of (two_theta, corrected_intensity) tuples and baseline_values is
    the raw baseline array (useful for an overlay plot).
    """
    two_theta = [d[0] for d in data]
    intensity = [d[1] for d in data]

    baseline = snip_baseline(intensity, iterations=iterations)
    corrected = np.asarray(intensity, dtype=float) - baseline
    if clip_negative:
        corrected = np.clip(corrected, 0, None)

    corrected_data = list(zip(two_theta, corrected.tolist()))
    return corrected_data, baseline
