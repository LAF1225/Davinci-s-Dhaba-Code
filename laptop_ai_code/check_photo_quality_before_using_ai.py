import cv2
import numpy as np

from laptop_ai_code import ai_settings_and_thresholds as settings


def decode_photo(photo_bytes):
    """Turn JPEG bytes into an OpenCV BGR image, or None if it is not an image."""
    if not photo_bytes:
        return None
    buffer = np.frombuffer(photo_bytes, dtype=np.uint8)
    return cv2.imdecode(buffer, cv2.IMREAD_COLOR)


def measure_sharpness(gray_photo):
    """Variance of the Laplacian. A higher number means a sharper photo."""
    return float(cv2.Laplacian(gray_photo, cv2.CV_64F).var())


def measure_local_contrast(gray_photo, grid=8):
    height, width = gray_photo.shape[:2]
    step_y = max(1, height // grid)
    step_x = max(1, width // grid)

    tile_means = []
    for y in range(0, height, step_y):
        for x in range(0, width, step_x):
            tile = gray_photo[y:y + step_y, x:x + step_x]
            if tile.size:
                tile_means.append(float(tile.mean()))

    if not tile_means:
        return 0.0
    return float(np.std(tile_means))


def check_photo(photo_bytes):
    reasons = []
    measurements = {}

    photo = decode_photo(photo_bytes)
    if photo is None:
        result = {
            "passed": False,
            "reason": "image_decode_failed",
            "all_reasons": ["image_decode_failed"],
            "measurements": {},
            "width": 0,
            "height": 0,
        }
        return result, None

    height, width = photo.shape[:2]
    measurements["width"] = float(width)
    measurements["height"] = float(height)

    if (width < settings.MINIMUM_PHOTO_WIDTH_PIXELS
            or height < settings.MINIMUM_PHOTO_HEIGHT_PIXELS):
        reasons.append("image_too_small")

    gray = cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY)

    sharpness = measure_sharpness(gray)
    measurements["blur_variance"] = sharpness
    if sharpness < settings.MINIMUM_SHARPNESS:
        reasons.append("image_blur")

    mean_brightness = float(gray.mean())
    brightness_variation = float(gray.std())
    measurements["mean_luminance"] = mean_brightness
    measurements["std_luminance"] = brightness_variation

    if mean_brightness < settings.MAXIMUM_MEAN_BRIGHTNESS_FOR_TOO_DARK:
        reasons.append("underexposed")
    if mean_brightness > settings.MINIMUM_MEAN_BRIGHTNESS_FOR_TOO_BRIGHT:
        reasons.append("overexposed")

    total_pixels = float(gray.size)
    dark_clipped = float((gray <= 2).sum()) / total_pixels
    bright_clipped = float((gray >= 253).sum()) / total_pixels
    measurements["dark_clipped_fraction"] = dark_clipped
    measurements["bright_clipped_fraction"] = bright_clipped

    if dark_clipped > settings.MAXIMUM_CLIPPED_PIXEL_FRACTION:
        reasons.append("shadow_clipping")
    if bright_clipped > settings.MAXIMUM_CLIPPED_PIXEL_FRACTION:
        reasons.append("highlight_clipping")

    if brightness_variation < settings.MINIMUM_BRIGHTNESS_VARIATION:
        reasons.append("low_contrast")

    measurements["local_contrast"] = measure_local_contrast(gray)

    result = {
        "passed": len(reasons) == 0,
        "reason": reasons[0] if reasons else "ok",
        "all_reasons": reasons,
        "measurements": measurements,
        "width": width,
        "height": height,
    }
    return result, photo
