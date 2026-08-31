import cv2
import numpy as np

from laptop_ai_code import ai_settings_and_thresholds as settings

FEATURE_DESCRIPTIONS = {
    "img_gray_contrast_std": (
        "brightness levels (0 to 255)", "Spread of grayscale brightness"),
    "img_gray_contrast_rms": (
        "ratio", "Spread divided by average brightness"),
    "img_lbp_uniformity": (
        "ratio", "Share of local binary patterns that are uniform"),
    "img_lbp_entropy": (
        "bits", "How mixed the local binary pattern histogram is"),
    "img_edge_density": (
        "ratio", "Share of pixels that Canny marks as an edge"),
    "img_edge_orientation_mean": (
        "radians", "Average direction of the threads"),
    "img_edge_orientation_dispersion": (
        "ratio", "0 means one strong thread direction, 1 means no direction"),
    "img_fft_peak_ratio": (
        "ratio", "Strength of the most repeated pattern spacing"),
    "img_fft_peak_frequency": (
        "cycles per pixel", "Spacing of the most repeated pattern"),
    "img_local_contrast_variability": (
        "brightness levels (0 to 255)",
        "Spread of average brightness across an 8 by 8 grid"),
}


def texture_feature_names():
    names = []
    if settings.USE_GRAY_CONTRAST:
        names += ["img_gray_contrast_std", "img_gray_contrast_rms"]
    if settings.USE_LOCAL_BINARY_PATTERN:
        names += ["img_lbp_uniformity", "img_lbp_entropy"]
    if settings.USE_EDGE_DENSITY:
        names += ["img_edge_density"]
    if settings.USE_EDGE_ORIENTATION:
        names += ["img_edge_orientation_mean", "img_edge_orientation_dispersion"]
    if settings.USE_FOURIER_PERIODICITY:
        names += ["img_fft_peak_ratio", "img_fft_peak_frequency"]
    if settings.USE_LOCAL_CONTRAST_VARIABILITY:
        names += ["img_local_contrast_variability"]
    return names


def _to_analysis_gray(photo):
    gray = cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    longest_side = max(height, width)

    if longest_side > settings.TEXTURE_ANALYSIS_SIZE_PIXELS:
        scale = settings.TEXTURE_ANALYSIS_SIZE_PIXELS / float(longest_side)
        new_size = (max(1, int(round(width * scale))),
                    max(1, int(round(height * scale))))
        gray = cv2.resize(gray, new_size, interpolation=cv2.INTER_AREA)

    return gray


def _local_binary_pattern(gray, points, radius):
    height, width = gray.shape
    gray_float = gray.astype(np.float64)
    codes = np.zeros((height, width), dtype=np.int64)

    for index in range(points):
        angle = 2.0 * np.pi * index / points
        offset_y = -radius * np.sin(angle)
        offset_x = radius * np.cos(angle)
        # Shifting the whole image is far faster than looping over pixels.
        shift_matrix = np.float32([[1, 0, offset_x], [0, 1, offset_y]])
        shifted = cv2.warpAffine(
            gray_float,
            shift_matrix,
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        codes |= ((shifted >= gray_float).astype(np.int64) << index)

    return codes


def _pattern_is_uniform(code, points):
    changes = 0
    for index in range(points):
        this_bit = (code >> index) & 1
        next_bit = (code >> ((index + 1) % points)) & 1
        if this_bit != next_bit:
            changes += 1
    return changes <= 2


def _local_binary_pattern_features(gray, points, radius):
    codes = _local_binary_pattern(gray, points, radius)
    histogram = np.bincount(codes.ravel(), minlength=2 ** points).astype(np.float64)
    total = histogram.sum()
    if total <= 0:
        return 0.0, 0.0

    shares = histogram / total

    uniform_mask = np.array(
        [_pattern_is_uniform(code, points) for code in range(2 ** points)], dtype=bool
    )
    uniformity = float(shares[uniform_mask].sum())

    non_zero = shares[shares > 0]
    entropy = float(-(non_zero * np.log2(non_zero)).sum())
    return uniformity, entropy


def _edge_orientation(gray):
    gradient_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    strength = np.sqrt(gradient_x ** 2 + gradient_y ** 2)

    if strength.sum() <= 0:
        return 0.0, 1.0

    angles = np.arctan2(gradient_y, gradient_x)
    weights = strength / strength.sum()
    doubled = 2.0 * angles

    cosine_part = float((weights * np.cos(doubled)).sum())
    sine_part = float((weights * np.sin(doubled)).sum())

    resultant = float(np.sqrt(cosine_part ** 2 + sine_part ** 2))
    mean_angle = float(np.arctan2(sine_part, cosine_part) / 2.0)
    dispersion = float(1.0 - resultant)
    return mean_angle, dispersion


def _fourier_periodicity(gray):
    working = gray.astype(np.float64)
    working = working - working.mean()

    # A Hann window stops the hard edge of the photo dominating the result.
    window = np.outer(np.hanning(working.shape[0]), np.hanning(working.shape[1]))
    spectrum = np.abs(np.fft.fftshift(np.fft.fft2(working * window))) ** 2

    height, width = spectrum.shape
    centre_y, centre_x = height // 2, width // 2
    y_positions, x_positions = np.indices((height, width))
    radius = np.sqrt(
        (y_positions - centre_y) ** 2 + (x_positions - centre_x) ** 2
    ).astype(np.int64)

    largest_radius = int(min(centre_y, centre_x))
    if largest_radius < 4:
        return 0.0, 0.0

    radial_total = np.bincount(
        radius.ravel(), spectrum.ravel(), minlength=largest_radius + 1
    )
    radial_count = np.bincount(radius.ravel(), minlength=largest_radius + 1)
    profile = (radial_total[:largest_radius]
               / np.maximum(radial_count[:largest_radius], 1))

    # Skip the lowest bins: they carry lighting gradients, not weave spacing.
    start = max(2, int(0.02 * largest_radius))
    search = profile[start:]
    if search.size == 0 or search.mean() <= 0:
        return 0.0, 0.0

    peak_position = int(np.argmax(search))
    peak_value = float(search[peak_position])
    peak_ratio = float(peak_value / (search.mean() + 1e-12))
    peak_frequency = float((peak_position + start) / (2.0 * largest_radius))
    return peak_ratio, peak_frequency


def _local_contrast_variability(gray, grid=8):
    height, width = gray.shape[:2]
    step_y = max(1, height // grid)
    step_x = max(1, width // grid)

    tile_means = []
    for y in range(0, height, step_y):
        for x in range(0, width, step_x):
            tile = gray[y:y + step_y, x:x + step_x]
            if tile.size:
                tile_means.append(float(tile.mean()))

    if not tile_means:
        return 0.0
    return float(np.std(tile_means))


def get_texture_features(photo):
    gray = _to_analysis_gray(photo)
    values = []

    if settings.USE_GRAY_CONTRAST:
        spread = float(gray.std())
        average = float(gray.mean())
        values += [spread, float(spread / (average + 1e-6))]

    if settings.USE_LOCAL_BINARY_PATTERN:
        uniformity, entropy = _local_binary_pattern_features(
            gray,
            settings.LOCAL_BINARY_PATTERN_POINTS,
            settings.LOCAL_BINARY_PATTERN_RADIUS,
        )
        values += [uniformity, entropy]

    if settings.USE_EDGE_DENSITY:
        otsu_level, _ = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        edges = cv2.Canny(gray, max(0.0, 0.5 * otsu_level), otsu_level)
        values += [float((edges > 0).sum()) / float(edges.size)]

    if settings.USE_EDGE_ORIENTATION:
        mean_angle, dispersion = _edge_orientation(gray)
        values += [mean_angle, dispersion]

    if settings.USE_FOURIER_PERIODICITY:
        peak_ratio, peak_frequency = _fourier_periodicity(gray)
        values += [peak_ratio, peak_frequency]

    if settings.USE_LOCAL_CONTRAST_VARIABILITY:
        values += [_local_contrast_variability(gray)]

    array = np.nan_to_num(
        np.asarray(values, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0
    )
    return array, texture_feature_names()
