"""Morphometric measurement functions for cone analysis.

Provides functions to calculate geometric properties such as elevation,
slope, distance, area, and volume from DEM profile data.
"""

import math

RAD_2_DEG = 360 / (2 * math.pi)


def get_points_by_elevation(elevations, profile, begin_no, end_no):
    """Find profile points where elevation crosses target values.

    Parameters
    ----------
    elevations : list
        Target elevation values to find.
    profile : DataFrame
        Profile data with elevation, x_geo, y_geo columns.
    begin_no : int
        Start index in profile.
    end_no : int
        End index in profile.

    Returns
    -------
    dict
        Mapping of elevation to list of indices where elevation crosses.
    """
    result = []
    if begin_no < end_no <= len(profile) and elevations:
        # elevations eg. [0, 1]
        # returns { 0: [no1, no2, ...], 1: [no3, no5, ...]}]
        result = {}
        for e in elevations:
            result[e] = []

        for idx in range(begin_no, end_no):
            current = profile.elevation[idx]
            next_value = profile.elevation[idx + 1]
            for e in elevations:
                if (current - e) * (next_value - e) <= 0:
                    point = idx if abs(current - e) < abs(next_value - e) else idx + 1
                    # print(f'--- {idx} {e} {current["elevation"]} {next["elevation"]}')
                    result[e].append(point)
    return result


def get_surface_under(profile, begin_no, end_no, is_absolute):
    """Calculate surface area under profile segment (m²).

    Parameters
    ----------
    profile : DataFrame
        Profile data.
    begin_no : int
        Start index.
    end_no : int
        End index.
    is_absolute : bool
        Whether to use absolute elevation values.

    Returns
    -------
    float
        Surface area (m²).
    """
    result = 0
    if begin_no < end_no <= len(profile):
        distance = math.sqrt(
            math.pow(profile.x_geo[begin_no + 1] - profile.x_geo[begin_no], 2)
            + math.pow(profile.y_geo[begin_no + 1] - profile.y_geo[begin_no], 2)
        )
        for idx in range(begin_no, end_no):
            tmp = (
                (profile.elevation[idx] + profile.elevation[idx + 1])
                if is_absolute
                else (profile.elevation[idx + 1]) - (profile.elevation[idx]) * distance
            ) / 2
            result += tmp if tmp > 0 else 0
    return result


def get_distance(profile, begin_no, end_no):
    """Calculate 3D distance between profile points (m).

    Parameters
    ----------
    profile : DataFrame
        Profile data.
    begin_no : int
        Start index.
    end_no : int
        End index.

    Returns
    -------
    float or None
        Distance (m).
    """
    result = None
    if begin_no < end_no <= len(profile):
        result = math.sqrt(
            math.pow(profile.x_geo[end_no] - profile.x_geo[begin_no], 2)
            + math.pow(profile.y_geo[end_no] - profile.y_geo[begin_no], 2)
        )
    return result


def get_slope(profile, begin_no, end_no):
    """Calculate slope angle between profile points (degrees).

    Parameters
    ----------
    profile : DataFrame
        Profile data.
    begin_no : int
        Start index.
    end_no : int
        End index.

    Returns
    -------
    float or None
        Slope angle (degrees).
    """
    result = None
    if begin_no < end_no <= len(profile):
        distance = get_distance(profile, begin_no, end_no)
        slope = (profile.elevation[end_no] - profile.elevation[begin_no]) / distance
        result = math.degrees(math.atan(slope))
    return result


def get_volume(width, profile, begin_no, end_no, is_absolute):
    """Calculate volume under profile (m³).

    Parameters
    ----------
    width : float
        Width of profile (transect width in m).
    profile : DataFrame
        Profile data.
    begin_no : int
        Start index.
    end_no : int
        End index.
    is_absolute : bool
        Whether to use absolute elevation values.

    Returns
    -------
    float
        Volume (m³).
    """
    return width * get_surface_under(profile, begin_no, end_no, is_absolute)
