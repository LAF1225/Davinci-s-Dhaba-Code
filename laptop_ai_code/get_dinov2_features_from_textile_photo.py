import os
import threading

import cv2
import numpy as np

from laptop_ai_code import ai_settings_and_thresholds as settings

# The five numbers appended after the average embedding, in this order.
SUMMARY_FEATURE_NAMES = [
    "vis_tile_count",
    "vis_mean_pairwise_distance",
    "vis_embedding_dispersion",
    "vis_embedding_norm",
    "vis_max_tile_deviation",
]

# The model is loaded once and reused. torch is imported inside the loader so
# the rest of the code still runs on a laptop without torch installed.
_model = None
_torch = None
_load_error = None
_embedding_size = 0
_load_lock = threading.Lock()


def _load_model():
    global _model, _torch, _load_error, _embedding_size

    import torch

    _torch = torch

    os.makedirs(settings.DINOV2_WEIGHTS_FOLDER, exist_ok=True)
    # torch.hub caches both the repository snapshot and the weights here, so a
    # laptop that has run once can work with no internet afterwards.
    os.environ["TORCH_HOME"] = settings.DINOV2_WEIGHTS_FOLDER
    torch.hub.set_dir(os.path.join(settings.DINOV2_WEIGHTS_FOLDER, "hub"))

    local_copy = os.path.join(
        settings.DINOV2_WEIGHTS_FOLDER, "hub", "facebookresearch_dinov2_main"
    )

    if os.path.exists(local_copy):
        model = torch.hub.load(
            local_copy, settings.DINOV2_MODEL_NAME, source="local", pretrained=True
        )
    else:
        model = torch.hub.load(
            settings.DINOV2_REPOSITORY,
            settings.DINOV2_MODEL_NAME,
            pretrained=True,
            trust_repo=True,
        )

    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    model.to(settings.DINOV2_DEVICE)

    _model = model
    _embedding_size = int(getattr(model, "embed_dim", 384))


def make_sure_model_is_loaded():
    global _load_error

    if _model is not None or _load_error is not None:
        return

    with _load_lock:
        if _model is not None or _load_error is not None:
            return
        try:
            _load_model()
        except Exception as error:
            # The laptop must stay usable without DINOv2: raw scans can still
            # be collected. What must never happen is a made up prediction.
            _load_error = "%s: %s" % (type(error).__name__, error)


def dinov2_is_available():
    make_sure_model_is_loaded()
    return _model is not None


def why_dinov2_is_not_available():
    make_sure_model_is_loaded()
    if _model is not None:
        return ""
    return _load_error or "not loaded"


def embedding_size():
    make_sure_model_is_loaded()
    if _embedding_size:
        return _embedding_size
    return expected_embedding_size(settings.DINOV2_MODEL_NAME)


def expected_embedding_size(model_name):
    for suffix, size in (("vits14", 384), ("vitb14", 768),
                         ("vitl14", 1024), ("vitg14", 1536)):
        if suffix in model_name:
            return size
    return 384


def embedding_feature_names(size):
    return ["dino_%04d" % index for index in range(size)]


def cut_photo_into_tiles(photo):
    reasons = []
    height, width = photo.shape[:2]
    tile_size = settings.TILE_SIZE_PIXELS

    if height < tile_size or width < tile_size:
        reasons.append("image_smaller_than_tile")
        candidates = [photo]
    else:
        overlap = max(0.0, min(0.9, settings.TILE_OVERLAP))
        step = max(1, int(round(tile_size * (1.0 - overlap))))
        candidates = []
        for y in range(0, height - tile_size + 1, step):
            for x in range(0, width - tile_size + 1, step):
                candidates.append(photo[y:y + tile_size, x:x + tile_size])

    kept = []
    for tile in candidates:
        gray = cv2.cvtColor(tile, cv2.COLOR_BGR2GRAY)
        variation = float(gray.std())
        if variation < settings.BACKGROUND_TILE_BRIGHTNESS_VARIATION:
            continue
        kept.append((variation, tile))

    if not kept:
        reasons.append("all_tiles_background")
        return [], reasons

    # When there are more tiles than we have time for, keep the most textured
    # ones, because those carry the thread structure we care about.
    kept.sort(key=lambda item: item[0], reverse=True)
    budget = max(1, settings.MAXIMUM_TILES_PER_PHOTO)
    selected = [tile for _, tile in kept[:budget]]
    if len(kept) > budget:
        reasons.append("tiles_truncated_to_budget")
    return selected, reasons


def prepare_tile_for_network(tile):
    """Resize one tile to the network input size and normalise it."""
    # DINOv2 uses a patch size of 14, so the side has to be a multiple of 14.
    side = max(14, (settings.DINOV2_INPUT_SIZE_PIXELS // 14) * 14)
    resized = cv2.resize(tile, (side, side), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

    # The usual ImageNet mean and standard deviation, which is what the
    # pretrained weights expect.
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    deviation = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    normalised = (rgb - mean) / deviation
    return np.transpose(normalised, (2, 0, 1))


def embed_tiles(tiles):
    """Run the frozen network over a list of tiles."""
    make_sure_model_is_loaded()
    if _model is None:
        raise RuntimeError("DINOv2 is not available: %s" % _load_error)

    batch = np.stack([prepare_tile_for_network(tile) for tile in tiles])
    tensor = _torch.from_numpy(batch).to(settings.DINOV2_DEVICE)

    with _torch.inference_mode():
        output = _model(tensor)

    embeddings = output.detach().cpu().numpy().astype(np.float64)
    if embeddings.ndim > 2:
        # Some backbones return a grid of tokens. Flatten to one row per tile.
        embeddings = embeddings.reshape(embeddings.shape[0], -1)
    return embeddings


def summarise_tiles(tile_embeddings, average_embedding):
    """Five numbers describing how much the tiles disagreed with each other.

    A textile whose tiles look very different from one another is showing local
    variation, and that is exactly what the scanner wants to know about.
    """
    count = int(tile_embeddings.shape[0])

    if count > 1:
        lengths = np.linalg.norm(tile_embeddings, axis=1, keepdims=True) + 1e-12
        unit_vectors = tile_embeddings / lengths
        similarity = unit_vectors @ unit_vectors.T
        upper_triangle = similarity[np.triu_indices(count, k=1)]
        mean_pairwise_distance = float(1.0 - upper_triangle.mean())

        deviations = np.linalg.norm(tile_embeddings - average_embedding, axis=1)
        dispersion = float(deviations.mean())
        largest_deviation = float(deviations.max())
    else:
        mean_pairwise_distance = 0.0
        dispersion = 0.0
        largest_deviation = 0.0

    return np.array(
        [
            float(count),
            mean_pairwise_distance,
            dispersion,
            float(np.linalg.norm(average_embedding)),
            largest_deviation,
        ],
        dtype=np.float64,
    )


def get_features_from_photo(photo):
    tiles, reasons = cut_photo_into_tiles(photo)

    if len(tiles) < max(1, settings.MINIMUM_USABLE_TILES):
        reasons.append("insufficient_valid_tiles")
        return {
            "ok": False,
            "embedding": np.zeros(0),
            "summary": np.zeros(len(SUMMARY_FEATURE_NAMES)),
            "tile_embeddings": np.zeros((0, 0)),
            "tile_count": len(tiles),
            "reasons": reasons,
        }

    tile_embeddings = embed_tiles(tiles)
    average_embedding = tile_embeddings.mean(axis=0)
    summary = summarise_tiles(tile_embeddings, average_embedding)

    return {
        "ok": True,
        "embedding": average_embedding,
        "summary": summary,
        "tile_embeddings": tile_embeddings,
        "tile_count": len(tiles),
        "reasons": reasons,
    }
