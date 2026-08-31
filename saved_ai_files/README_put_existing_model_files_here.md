# saved_ai_files

Trained models and the DINOv2 weights live here. Nothing in this folder is
source code, so most of it is in `.gitignore`.

## What goes in here

```
saved_ai_files/
  dinov2_weights/          the frozen DINOv2 backbone, cached
    hub/
      facebookresearch_dinov2_main/
      checkpoints/
        dinov2_vits14_pretrain.pth
  active_model/            the model the laptop server actually uses
    classifier.joblib
    feature_schema.json
    metadata.json
    metrics.json
    reference_embeddings.npz
  v0.2.0/                  a trained model, before you switch it on
  scans.db                 the scan record database, made automatically
  scan_photos/             raw photos as they arrive, made automatically
```

## The DINOv2 weights

The first run downloads `dinov2_vits14` from torch hub, which needs internet
once. After that the laptop works offline.

If you have the previous repository checked out, copying its cache is quicker
and needs no internet:

```
E:\WRO Textile Analyser\data\weights\hub   ->   saved_ai_files\dinov2_weights\hub
```

## A trained model

One model is one folder, and the five files in it belong together:

| File | What it is |
| --- | --- |
| `classifier.joblib` | the StandardScaler and the SVM, as one sklearn Pipeline |
| `feature_schema.json` | what every column of the feature vector means |
| `metadata.json` | what it was trained on, which textiles, and when |
| `metrics.json` | how well it scored, per scan area and per textile |
| `reference_embeddings.npz` | the verified reference textiles it was built with |

There is no separate scaler file. The scaler is the first step inside
`classifier.joblib`, which is how the previous repository did it, so that it
can never be forgotten when the model is used.

Keep the five together. A scaler separated from its SVM, or an SVM separated
from the column layout it was trained on, will still run and will still produce
confident looking numbers that mean nothing.

## Switching a model on

Training writes to `saved_ai_files/<version>/`. It does **not** switch it on.
To use it:

1. copy or rename that folder to `saved_ai_files/active_model/`
2. restart the laptop server

Switching models is always something a person did on purpose.

## If it refuses to load

The server prints the reason at startup and `/api/v1/health` repeats it. The
usual ones:

- **the feature layout does not match** - the code now builds a different
  vector than the model was trained on. Retrain. Do not turn the check off
- **there is no active_model folder** - normal on a fresh checkout
- **a file is missing** - the message says which one

## What is NOT here

There is no model trained on real textiles yet. The old repository's only saved
model was trained on synthetic demo data for the gantry robot with an eight
channel spectrometer, and would be refused here even if it were copied in. See
`project_notes/things_i_still_need_from_the_old_repository.md`.
