import hashlib
import json

import numpy as np

from laptop_ai_code import ai_settings_and_thresholds as settings

GROUP_DINOV2 = "dinov2"
GROUP_VISUAL_SUMMARY = "visual_summary"
GROUP_IMAGE_TEXTURE = "image_texture"
GROUP_COLOUR = "colour"

# The one true order. Nothing else in the repository is allowed to reorder it.
GROUP_ORDER = (
    GROUP_DINOV2,
    GROUP_VISUAL_SUMMARY,
    GROUP_IMAGE_TEXTURE,
    GROUP_COLOUR,
)

# What kind of measurement each group needs the robot to have delivered.
MODALITY_CAMERA = "camera"
MODALITY_COLOUR = "colour"


def _modalities_for_groups(groups):
    needed = []
    if {GROUP_DINOV2, GROUP_VISUAL_SUMMARY, GROUP_IMAGE_TEXTURE} & set(groups):
        needed.append(MODALITY_CAMERA)
    if GROUP_COLOUR in groups:
        needed.append(MODALITY_COLOUR)
    return needed


def make_schema(fields, groups):
    return {
        "fields": fields,
        "groups": list(groups),
        "required_modalities": _modalities_for_groups(groups),
        "preprocessing_version": settings.PREPROCESSING_VERSION,
        "dinov2_model": settings.DINOV2_MODEL_NAME,
        "hardware_profile": settings.HARDWARE_PROFILE_NAME,
        "feature_schema_version": settings.FEATURE_SCHEMA_VERSION,
        "dimension": len(fields),
    }


def schema_fingerprint(schema):
    payload = json.dumps(
        {
            "names": [field["name"] for field in schema["fields"]],
            "sources": [field["source"] for field in schema["fields"]],
            "preprocessing_version": schema.get("preprocessing_version", ""),
            "dinov2_model": schema.get("dinov2_model", ""),
            "required_modalities": sorted(schema.get("required_modalities", [])),
            "hardware_profile": schema.get("hardware_profile", ""),
            "feature_schema_version": schema.get("feature_schema_version", ""),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def combine(embedding, visual_summary, texture_values, texture_names, colour_values):
    from laptop_ai_code.get_dinov2_features_from_textile_photo import (
        SUMMARY_FEATURE_NAMES,
        embedding_feature_names,
    )
    from laptop_ai_code.clean_and_prepare_colour_sensor_readings import (
        colour_feature_names,
    )

    groups = [
        (GROUP_DINOV2, embedding_feature_names(int(np.asarray(embedding).size)),
         embedding),
        (GROUP_VISUAL_SUMMARY, SUMMARY_FEATURE_NAMES, visual_summary),
        (GROUP_IMAGE_TEXTURE, texture_names, texture_values),
        (GROUP_COLOUR, colour_feature_names(), colour_values),
    ]

    values = []
    fields = []
    group_names = []

    for group_name, names, group_values in groups:
        group_values = np.asarray(group_values, dtype=np.float64).ravel()
        if len(names) != group_values.size:
            raise ValueError(
                "feature group '%s' gave %d values for %d names"
                % (group_name, group_values.size, len(names))
            )
        group_names.append(group_name)
        for name, value in zip(names, group_values.tolist()):
            fields.append({
                "name": name,
                "position": len(values),
                "source": group_name,
            })
            values.append(float(value))

    vector = np.nan_to_num(
        np.asarray(values, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0
    )
    return vector, make_schema(fields, group_names)


def describe_expected_schema(embedding_size=None):
    from laptop_ai_code.get_dinov2_features_from_textile_photo import (
        SUMMARY_FEATURE_NAMES,
        expected_embedding_size,
    )
    from laptop_ai_code.clean_and_prepare_colour_sensor_readings import (
        colour_feature_names,
    )
    from laptop_ai_code.measure_simple_texture_numbers_from_photo import (
        texture_feature_names,
    )

    if embedding_size is None:
        embedding_size = expected_embedding_size(settings.DINOV2_MODEL_NAME)

    zero_embedding = np.zeros(embedding_size)
    texture_names = texture_feature_names()

    _, schema = combine(
        embedding=zero_embedding,
        visual_summary=np.zeros(len(SUMMARY_FEATURE_NAMES)),
        texture_values=np.zeros(len(texture_names)),
        texture_names=texture_names,
        colour_values=np.zeros(len(colour_feature_names())),
    )
    return schema


def schemas_match(current_schema, model_schema):
    if schema_fingerprint(current_schema) == schema_fingerprint(model_schema):
        return True, ""

    if (current_schema.get("preprocessing_version")
            != model_schema.get("preprocessing_version")):
        return False, (
            "preprocessing version does not match: the model was trained with %s "
            "and this code produces %s"
            % (model_schema.get("preprocessing_version"),
               current_schema.get("preprocessing_version"))
        )

    if current_schema.get("dinov2_model") != model_schema.get("dinov2_model"):
        return False, (
            "DINOv2 model does not match: the model was trained with %s and this "
            "code uses %s"
            % (model_schema.get("dinov2_model"), current_schema.get("dinov2_model"))
        )

    model_needs = set(model_schema.get("required_modalities", []))
    we_have = set(current_schema.get("required_modalities", []))
    if model_needs != we_have:
        return False, (
            "the model needs %s but this robot provides %s"
            % (sorted(model_needs), sorted(we_have))
        )

    if current_schema.get("hardware_profile") != model_schema.get("hardware_profile"):
        return False, (
            "the model was trained on hardware profile %s and this robot is %s"
            % (model_schema.get("hardware_profile"),
               current_schema.get("hardware_profile"))
        )

    if current_schema.get("dimension") != model_schema.get("dimension"):
        return False, (
            "the model expects %s numbers per scan and this code produces %s"
            % (model_schema.get("dimension"), current_schema.get("dimension"))
        )

    current_names = [field["name"] for field in current_schema.get("fields", [])]
    model_names = [field["name"] for field in model_schema.get("fields", [])]
    for position, (ours, theirs) in enumerate(zip(current_names, model_names)):
        if ours != theirs:
            return False, (
                "the columns are in a different order: column %d is '%s' here "
                "and '%s' in the model" % (position, ours, theirs)
            )

    return False, "the feature fingerprints do not match"


def check_vector(vector, schema):
    """Raise if a vector does not match its schema. Used before training and use."""
    vector = np.asarray(vector)
    if vector.ndim != 1:
        raise ValueError("the feature vector must be a flat list, got shape %s"
                         % (vector.shape,))
    if vector.shape[0] != schema["dimension"]:
        raise ValueError(
            "the feature vector has %d values but the schema says %d"
            % (vector.shape[0], schema["dimension"])
        )
    if not np.all(np.isfinite(vector)):
        raise ValueError("the feature vector contains values that are not numbers")
