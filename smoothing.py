"""
smoothing.py — Savitzky-Golay smoothing for PXRD patterns.

Implemented with numpy only (no scipy), to match the lightweight-dependency
approach used for baseline correction. Savitzky-Golay fits a local
polynomial across a moving window, which smooths noise while preserving
peak height/position/width much better than a plain moving average --
similar in spirit to Origin's "Savitzky-Golay" smoothing method, or
comparable in effect to its "Adjacent Averaging" (Points of Window) option.
"""

import numpy as np


def savgol_smooth(intensity, window, polyorder=3):
    """Smooth `intensity` with a Savitzky-Golay filter.

    `window`   : number of points in the smoothing window (this is the
                 "level" the user sets -- e.g. 5, 11, 15, 21). Larger =
                 smoother but can start flattening sharp/narrow peaks.
                 Must be odd; an even value is bumped up by 1.
    `polyorder`: polynomial order fit within each window. Lowered
                 automatically if it's too large for the chosen window.

    Returns a 1D numpy array the same length as `intensity`.
    """
    y = np.asarray(intensity, dtype=float)
    n = len(y)

    window = int(window)
    if window < 3:
        window = 3
    if window % 2 == 0:
        window += 1  # must be odd
    if window > n:
        window = n if n % 2 == 1 else n - 1
        window = max(window, 3)

    polyorder = min(polyorder, window - 1)
    if polyorder < 1:
        polyorder = 1

    half = window // 2
    idx = np.arange(-half, half + 1)
    # Vandermonde design matrix for the local polynomial fit; the smoothing
    # coefficients are the first row of the pseudo-inverse (i.e. the
    # 0th-derivative / value-fit row).
    A = np.vander(idx, polyorder + 1, increasing=True)
    coeffs = np.linalg.pinv(A)[0]

    padded = np.pad(y, (half, half), mode="edge")
    smoothed = np.convolve(padded, coeffs[::-1], mode="valid")
    return smoothed


def apply_smoothing(data, window, polyorder=3):
    """data: list of (two_theta, intensity) tuples.

    Returns a new list of (two_theta, smoothed_intensity) tuples.
    """
    two_theta = [d[0] for d in data]
    intensity = [d[1] for d in data]
    smoothed = savgol_smooth(intensity, window=window, polyorder=polyorder)
    return list(zip(two_theta, smoothed.tolist()))
