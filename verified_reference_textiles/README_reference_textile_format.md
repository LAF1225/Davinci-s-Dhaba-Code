# verified_reference_textiles

The textiles ASIL compares a new scan against.

The reference comparison is the second source of evidence, next to the SVM. It
works even before any SVM exists, and it is what stops a textile the robot has
never seen anything like being forced into a confident class.

## How a reference gets here

You do not put files in this folder by hand.

References are built during training, from the textiles that went into the
**training** split, and saved inside the model folder as
`reference_embeddings.npz`. Loading a model loads its references with it.

That is deliberate. A reference bank that lived separately could drift out of
step with the model, and then two things that are supposed to agree about what
a textile looks like would quietly disagree.

Training textiles only. Putting a test textile in the reference bank would let
the model recognise, at test time, a piece of cloth it is supposed to be seeing
for the first time.

## What is stored per reference

| Field | Why |
| --- | --- |
| `textile_id` | so a match can be traced back to a real piece of cloth |
| `label` | handmade or machine |
| `embedding` | the DINOv2 embedding, 384 numbers |
| `scan_id` | which scan area it came from |
| `craft_type` | the tradition, when it is known |
| `verification_level` | how the provenance was established |

The traceability is the point. When the robot says a textile is similar to
`H004`, somebody can go and look at `H004`.

## How the comparison works

Cosine similarity between DINOv2 embeddings. Cosine similarity asks whether two
embeddings point the same way and ignores how long they are, so two photos of
the same weave at different brightness still match.

Each scan is compared with both banks, and the closest few from each are kept.

**If the best match in both banks is below 0.35** the scan is out of domain: it
looks like nothing we have references for. The answer becomes Inconclusive
regardless of how confident the SVM was. A confident classifier on an
unfamiliar textile is confidently wrong.

**If the best match is below 0.55** the answer is inconclusive too, and the
robot is asked to look at a couple of extra areas.

Both numbers are in `laptop_ai_code/ai_settings_and_thresholds.py`.

## What it does not do

One very similar reference does not override everything else. The SVM still
runs, the results from every scan area are still combined, and the reference
similarity is one input among several.

Nearest neighbour matching alone would be a lookup table, and a lookup table
cannot tell you anything about a textile it has not already got.

## Right now

There are no reference textiles, because there are no verified textiles
scanned with this robot yet. Until there are, every scan is out of domain and
every answer is Inconclusive.

That is the honest behaviour and not a fault. `/api/v1/health` on the laptop
says `reference_count: 0` and `what_works: raw collection only`.

## Getting some

1. Collect verified textiles of both kinds with
   `dataset_collection_tools/scan_textiles_and_save_them_for_dataset.py`
2. Train:
   `python -m model_training_and_testing.train_svm_using_saved_textile_scans`
3. The reference bank is built and saved into the model folder automatically
