import cv2
import numpy as np

from laptop_ai_code import check_photo_quality_before_using_ai as quality_check


def make_a_photo_that_looks_like_cloth(width=800, height=600, seed=7):
    random_numbers = np.random.default_rng(seed)
    x_positions, y_positions = np.meshgrid(np.arange(width), np.arange(height))

    # A checkerboard of four pixel blocks: warp over weft, roughly.
    weave = (((x_positions // 4) % 2) ^ ((y_positions // 4) % 2)).astype(np.float64)
    gray = 70.0 + 110.0 * weave
    # A little noise, so it is not a perfectly repeating pattern.
    gray += random_numbers.normal(0.0, 8.0, gray.shape)

    gray = np.clip(gray, 0, 255).astype(np.uint8)
    colour = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    return cv2.imencode(".jpg", colour, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes()


def blur_a_photo(photo_bytes):
    photo = cv2.imdecode(np.frombuffer(photo_bytes, np.uint8), cv2.IMREAD_COLOR)
    blurred = cv2.GaussianBlur(photo, (31, 31), 0)
    return cv2.imencode(".jpg", blurred)[1].tobytes()


def test_a_good_photo_passes():
    result, photo = quality_check.check_photo(make_a_photo_that_looks_like_cloth())

    assert result["passed"], "a sharp, well lit photo was rejected: %s" % (
        result["all_reasons"],
    )
    assert result["reason"] == "ok"
    assert photo is not None


def test_a_blurry_photo_is_rejected():
    blurry = blur_a_photo(make_a_photo_that_looks_like_cloth())
    result, _ = quality_check.check_photo(blurry)

    assert not result["passed"]
    assert "image_blur" in result["all_reasons"]


def test_a_photo_that_is_not_an_image_is_rejected():
    result, photo = quality_check.check_photo(b"this is not a JPEG at all")

    assert not result["passed"]
    assert result["reason"] == "image_decode_failed"
    assert photo is None


def test_an_empty_upload_is_rejected():
    result, photo = quality_check.check_photo(b"")

    assert not result["passed"]
    assert photo is None


def test_a_photo_that_is_too_small_is_rejected():
    tiny = np.zeros((100, 100, 3), dtype=np.uint8)
    tiny[::4, :] = 200  # give it some contrast so size is the only complaint
    tiny_bytes = cv2.imencode(".jpg", tiny)[1].tobytes()

    result, _ = quality_check.check_photo(tiny_bytes)

    assert not result["passed"]
    assert "image_too_small" in result["all_reasons"]


def test_a_photo_of_nothing_is_rejected():
    flat = np.full((600, 800, 3), 128, dtype=np.uint8)
    flat_bytes = cv2.imencode(".jpg", flat)[1].tobytes()

    result, _ = quality_check.check_photo(flat_bytes)

    assert not result["passed"]
    assert "low_contrast" in result["all_reasons"]
