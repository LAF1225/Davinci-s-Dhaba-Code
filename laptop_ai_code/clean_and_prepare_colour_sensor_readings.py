import numpy as np

from laptop_ai_code import ai_settings_and_thresholds as settings


def calibration_is_usable(dark, white):
    if not dark or not white:
        return False
    if len(dark) != len(white):
        return False

    dark_values = np.asarray(dark, dtype=np.float64)
    white_values = np.asarray(white, dtype=np.float64)
    separation = white_values - dark_values
    return bool(np.all(separation >= settings.MINIMUM_WHITE_MINUS_DARK))


def calculate_reflectance(sample, dark, white):
    sample_values = np.asarray(sample, dtype=np.float64)

    if dark is not None and len(dark) == len(sample_values):
        dark_values = np.asarray(dark, dtype=np.float64)
    else:
        dark_values = np.zeros_like(sample_values)

    if white is not None and len(white) == len(sample_values):
        white_values = np.asarray(white, dtype=np.float64)
    else:
        white_values = np.ones_like(sample_values)

    bottom = (white_values - dark_values) + settings.CALIBRATION_EPSILON

    with np.errstate(divide="ignore", invalid="ignore"):
        reflectance = (sample_values - dark_values) / bottom
    reflectance = np.nan_to_num(reflectance, nan=0.0, posinf=0.0, neginf=0.0)

    return np.clip(
        reflectance,
        settings.CALIBRATION_CLAMP_MINIMUM,
        settings.CALIBRATION_CLAMP_MAXIMUM,
    )


def check_raw_reading(channels):
    reasons = []

    if not channels:
        return ["colour_missing"]

    values = np.asarray(channels, dtype=np.float64)

    if not np.all(np.isfinite(values)):
        reasons.append("colour_non_finite")
    if (np.any(values < settings.COLOUR_SENSOR_RAW_MINIMUM)
            or np.any(values > settings.COLOUR_SENSOR_RAW_MAXIMUM)):
        reasons.append("colour_out_of_range")
    # Every channel identical usually means a stuck I2C bus, not a genuinely
    # grey textile.
    if values.size > 1 and float(np.ptp(values)) == 0.0:
        reasons.append("colour_constant_vector")
    if values.size != settings.COLOUR_SENSOR_CHANNEL_COUNT:
        reasons.append("colour_channel_count_mismatch")

    return reasons


def calibrate_reading(channels, dark=None, white=None, require_calibration=True):
    raw = [float(value) for value in channels]
    reasons = check_raw_reading(raw)

    references_usable = calibration_is_usable(dark, white)
    if not references_usable:
        reasons.append("colour_uncalibrated")

    calibrated = calculate_reflectance(raw, dark, white)
    if references_usable and len(calibrated) > 1:
        raw_values = np.asarray(raw, dtype=np.float64)
        calibrated_flat = float(np.ptp(calibrated)) == 0.0
        raw_varied = raw_values.size > 1 and float(np.ptp(raw_values)) > 0.0
        if calibrated_flat and raw_varied:
            reasons.append("colour_calibration_degenerate")

    fatal_problems = {
        "colour_missing",
        "colour_non_finite",
        "colour_constant_vector",
        "colour_out_of_range",
        "colour_channel_count_mismatch",
        "colour_calibration_degenerate",
    }
    if require_calibration:
        fatal_problems = fatal_problems | {"colour_uncalibrated"}

    return {
        "ok": len(set(reasons) & fatal_problems) == 0,
        "reasons": reasons,
        "raw": raw,
        "calibrated": [float(value) for value in calibrated],
        "calibrated_with": {"dark": dark, "white": white},
    }

def colour_feature_names():
    channel_count = settings.COLOUR_SENSOR_CHANNEL_COUNT
    if channel_count <= 0:
        return []

    names = []

    if settings.USE_NORMALISED_BANDS:
        names += ["colour_band_%d" % index for index in range(channel_count)]

    if settings.USE_ADJACENT_DIFFERENCES and channel_count > 1:
        names += ["colour_adjdiff_%d" % index for index in range(channel_count - 1)]

    if settings.USE_BAND_RATIOS:
        names += ["colour_ratio_%d_%d" % (pair[0], pair[1])
                  for pair in settings.BAND_RATIO_PAIRS]

    if settings.USE_SECOND_DIFFERENCE and channel_count > 2:
        names += ["colour_deriv2_%d" % index for index in range(channel_count - 2)]

    if settings.USE_SUMMARY_STATISTICS:
        names += [
            "colour_mean",
            "colour_std",
            "colour_min",
            "colour_max",
            "colour_range",
            "colour_slope",
            "colour_argmax",
        ]

    return names


def get_colour_features(calibrated_channels):
    channel_count = settings.COLOUR_SENSOR_CHANNEL_COUNT
    if channel_count <= 0:
        return np.zeros(0, dtype=np.float64)

    values = np.asarray(list(calibrated_channels), dtype=np.float64)
    if values.size < channel_count:
        values = np.pad(values, (0, channel_count - values.size))
    elif values.size > channel_count:
        values = values[:channel_count]

    features = []

    if settings.USE_NORMALISED_BANDS:
        features.extend(values.tolist())

    if settings.USE_ADJACENT_DIFFERENCES and channel_count > 1:
        features.extend(np.diff(values).tolist())

    if settings.USE_BAND_RATIOS:
        for pair in settings.BAND_RATIO_PAIRS:
            first, second = int(pair[0]), int(pair[1])
            if 0 <= first < values.size and 0 <= second < values.size:
                ratio = values[first] / (values[second] + settings.CALIBRATION_EPSILON)
                features.append(float(ratio))
            else:
                features.append(0.0)

    if settings.USE_SECOND_DIFFERENCE and channel_count > 2:
        features.extend(np.diff(values, n=2).tolist())

    if settings.USE_SUMMARY_STATISTICS:
        if values.size > 1:
            positions = np.arange(values.size, dtype=np.float64)
            slope = float(np.polyfit(positions, values, 1)[0])
        else:
            slope = 0.0
        features.extend([
            float(values.mean()),
            float(values.std()),
            float(values.min()),
            float(values.max()),
            float(np.ptp(values)),
            slope,
            float(int(np.argmax(values))),
        ])

    return np.nan_to_num(
        np.asarray(features, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0
    )
