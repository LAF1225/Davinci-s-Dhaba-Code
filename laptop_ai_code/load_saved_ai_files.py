import json
import os
from datetime import datetime, timezone

import joblib
import numpy as np

from laptop_ai_code import ai_settings_and_thresholds as settings
from laptop_ai_code.combine_photo_and_sensor_features import (
    schema_fingerprint,
    schemas_match,
)


class ModelFilesMissing(Exception):
    pass
class ModelDoesNotMatchThisCode(Exception):
    pass

def _write_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)


def _read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_model_folder(folder, trained_pipeline, schema, results, information,
                      reference_bank=None):
    """Write one complete saved model folder."""
    os.makedirs(folder, exist_ok=True)

    joblib.dump(trained_pipeline, os.path.join(folder, settings.CLASSIFIER_FILE_NAME))

    full_information = dict(information)
    full_information.update({
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "feature_fingerprint": schema_fingerprint(schema),
        "feature_count": schema["dimension"],
        "dinov2_model": schema["dinov2_model"],
        "preprocessing_version": schema["preprocessing_version"],
        "hardware_profile": schema["hardware_profile"],
        "required_modalities": schema["required_modalities"],
        "feature_groups": schema["groups"],
    })

    _write_json(os.path.join(folder, settings.MODEL_INFORMATION_FILE_NAME),
                full_information)
    _write_json(os.path.join(folder, settings.MODEL_RESULTS_FILE_NAME), results)
    _write_json(os.path.join(folder, settings.FEATURE_SCHEMA_FILE_NAME), schema)

    if reference_bank is not None:
        np.savez_compressed(
            os.path.join(folder, settings.REFERENCE_EMBEDDINGS_FILE_NAME),
            **reference_bank,
        )

    return folder


def load_model_folder(folder=None, current_schema=None):
    folder = folder or settings.SAVED_MODEL_FOLDER

    classifier_path = os.path.join(folder, settings.CLASSIFIER_FILE_NAME)
    schema_path = os.path.join(folder, settings.FEATURE_SCHEMA_FILE_NAME)

    if not os.path.isdir(folder):
        raise ModelFilesMissing(
            "there is no saved model folder at %s. Copy a trained model there, "
            "or train one with:\n"
            "    python -m model_training_and_testing.train_svm_using_saved_textile_scans"
            % folder
        )
    if not os.path.exists(classifier_path):
        raise ModelFilesMissing(
            "%s is missing from %s, so there is no classifier to load"
            % (settings.CLASSIFIER_FILE_NAME, folder)
        )
    if not os.path.exists(schema_path):
        raise ModelFilesMissing(
            "%s is missing from %s. Without it there is no way to know what the "
            "columns of the feature vector mean, and the model cannot be used "
            "safely." % (settings.FEATURE_SCHEMA_FILE_NAME, folder)
        )

    schema = _read_json(schema_path)

    if current_schema is not None:
        matches, reason = schemas_match(current_schema, schema)
        if not matches:
            raise ModelDoesNotMatchThisCode(
                "the saved model in %s cannot be used: %s" % (folder, reason)
            )

    pipeline = joblib.load(classifier_path)
    information = _read_json(
        os.path.join(folder, settings.MODEL_INFORMATION_FILE_NAME), {}
    ) or {}
    results = _read_json(
        os.path.join(folder, settings.MODEL_RESULTS_FILE_NAME), {}
    ) or {}

    reference_bank = None
    reference_path = os.path.join(folder, settings.REFERENCE_EMBEDDINGS_FILE_NAME)
    if os.path.exists(reference_path):
        with np.load(reference_path, allow_pickle=True) as payload:
            reference_bank = {key: payload[key] for key in payload.files}

    return {
        "folder": folder,
        "pipeline": pipeline,
        "schema": schema,
        "information": information,
        "results": results,
        "reference_bank": reference_bank,
        "version": str(information.get("model_version", os.path.basename(folder))),
    }


def decision_thresholds_from_model(information):
    raw = information.get("decision_thresholds")
    if not isinstance(raw, dict):
        return None
    try:
        return {
            "handmade_min": float(raw["handmade_min"]),
            "machine_max": float(raw["machine_max"]),
        }
    except (KeyError, TypeError, ValueError):
        return None
