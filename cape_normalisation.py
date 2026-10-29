"""Controlled normalisation of small negative CAPE values from Open-Meteo ECMWF.

CAPE is non-negative by definition, and the training data contains no negative
values. ECMWF open data is 3-hourly, and Open-Meteo interpolates it to hourly
values. In one year of archived forecasts for the site, every negative value fell
between 3-hourly points and below both neighbouring 3-hourly values, i.e. an
interpolation overshoot, usually next to a 0 J/kg point.

Rule (shared by inference and the SMS worker so both use the same value):
  finite CAPE >= 0                         -> unchanged
  finite -TOLERANCE <= CAPE < 0            -> 0.0, status 'normalised'
  below -TOLERANCE, missing, non-numeric,
  NaN or infinite                          -> status 'invalid' (never repaired)

TOLERANCE is a provisional engineering cutoff awaiting evaluation, not a
physically derived limit.
"""
import math
import numbers

CAPE_NEGATIVE_TOLERANCE_J_KG = 50.0
UNCHANGED, NORMALISED, INVALID = 'unchanged', 'normalised', 'invalid'
STATUSES = (UNCHANGED, NORMALISED, INVALID)


def normalise_cape(value):
    """Return (value_to_use, status). value_to_use is None when status is 'invalid'."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return None, INVALID
    number = float(value)
    if not math.isfinite(number):
        return None, INVALID
    if number >= 0:
        return number, UNCHANGED
    if number >= -CAPE_NEGATIVE_TOLERANCE_J_KG:
        return 0.0, NORMALISED
    return None, INVALID


def consistent(reported, raw, status):
    """True if a reported (value, raw, status) triple matches the rule exactly."""
    expected_value, expected_status = normalise_cape(raw)
    if status != expected_status:
        return False
    if status == INVALID:
        return True
    return isinstance(reported, numbers.Real) and not isinstance(reported, bool) and float(reported) == expected_value
