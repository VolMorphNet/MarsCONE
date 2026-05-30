"""Signal smoothing functions for elevation profiles and point clouds.

Provides Savitzky-Golay filtering for profile smoothing and
statistical outlier removal for point data.
"""

from scipy.signal import savgol_filter


def smooth_profile(profile, begin_no, end_no, window=17, degree=3):
    """Smooth elevation profile using Savitzky-Golay filter.

    Parameters
    ----------
    profile : DataFrame
        Profile data with elevation column.
    begin_no : int
        Start index.
    end_no : int
        End index.
    window : int, optional
        Filter window size (default: 17).
    degree : int, optional
        Polynomial degree (default: 3).

    Returns
    -------
    ndarray or None
        Smoothed elevation values or None if filtering fails.
    """
    try:
        return savgol_filter(profile.elevation[begin_no:end_no], window, degree)
    except (ValueError, IndexError):
        return None


def smooth_points(points):
    """Remove statistical outliers from point cloud using standard deviation.

    Parameters
    ----------
    points : Series or DataFrame
        Point data to filter.

    Returns
    -------
    Series, DataFrame or None
        Filtered points or None if operation fails.
    """
    try:
        return points.mask(points.sub(points.mean()).div(points.std()).abs().gt(1))
        # return points.mask(...).interpolate()  # For interpolation
    except (ValueError, TypeError, ZeroDivisionError):
        return None
