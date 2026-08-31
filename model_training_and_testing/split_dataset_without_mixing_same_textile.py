import numpy as np

class TextileAppearsInTwoSplits(Exception):
    pass
def check_no_textile_is_in_two_splits(train_textiles, validation_textiles,
                                      test_textiles):
    """Raise if any textile appears in more than one split."""
    train = set(train_textiles)
    validation = set(validation_textiles)
    test = set(test_textiles)

    problems = []
    if train & validation:
        problems.append("in both train and validation: %s"
                        % sorted(train & validation))
    if train & test:
        problems.append("in both train and test: %s" % sorted(train & test))
    if validation & test:
        problems.append("in both validation and test: %s"
                        % sorted(validation & test))

    if problems:
        raise TextileAppearsInTwoSplits(
            "the same physical textile is in more than one split, so training "
            "must stop. " + "; ".join(problems)
        )


def _textiles_by_class(labels, textile_ids):
    grouped = {}
    for label, textile_id in zip(labels, textile_ids):
        grouped.setdefault(str(label), set()).add(str(textile_id))
    return {label: sorted(ids) for label, ids in grouped.items()}


def split_by_textile(labels, textile_ids, train_fraction=0.70,
                     validation_fraction=0.15, random_seed=42):
    labels = [str(item) for item in labels]
    textile_ids = [str(item) for item in textile_ids]
    labels_per_textile = {}
    for label, textile_id in zip(labels, textile_ids):
        found = labels_per_textile.setdefault(textile_id, [])
        if label not in found:
            found.append(label)

    confused = {
        textile_id: sorted(found)
        for textile_id, found in labels_per_textile.items()
        if len(found) > 1
    }
    if confused:
        raise TextileAppearsInTwoSplits(
            "these textiles are labelled as more than one class, so they "
            "cannot belong to one split: %s. Every scan of one physical "
            "textile has to have the same label."
            % dict(sorted(confused.items())[:5])
        )

    random_numbers = np.random.default_rng(random_seed)

    train_textiles = []
    validation_textiles = []
    test_textiles = []

    for _label, ids in sorted(_textiles_by_class(labels, textile_ids).items()):
        shuffled = list(ids)
        random_numbers.shuffle(shuffled)
        count = len(shuffled)

        if count == 1:
            train_textiles += shuffled
            continue

        if count == 2:
            train_textiles.append(shuffled[0])
            test_textiles.append(shuffled[1])
            continue

        train_count = max(1, int(round(count * train_fraction)))
        validation_count = max(1, int(round(count * validation_fraction)))

        while train_count + validation_count > count - 1:
            if validation_count > 1:
                validation_count -= 1
            else:
                train_count -= 1

        train_textiles += shuffled[:train_count]
        validation_textiles += shuffled[
            train_count:train_count + validation_count]
        test_textiles += shuffled[train_count + validation_count:]

    check_no_textile_is_in_two_splits(
        train_textiles, validation_textiles, test_textiles
    )

    train_set = set(train_textiles)
    validation_set = set(validation_textiles)
    test_set = set(test_textiles)

    train_rows = []
    validation_rows = []
    test_rows = []
    for position, textile_id in enumerate(textile_ids):
        if textile_id in train_set:
            train_rows.append(position)
        elif textile_id in validation_set:
            validation_rows.append(position)
        elif textile_id in test_set:
            test_rows.append(position)

    return {
        "train_rows": np.array(train_rows, dtype=int),
        "validation_rows": np.array(validation_rows, dtype=int),
        "test_rows": np.array(test_rows, dtype=int),
        "train_textiles": sorted(train_set),
        "validation_textiles": sorted(validation_set),
        "test_textiles": sorted(test_set),
    }


def describe_split(split):
    return {
        "textiles": {
            "train": len(split["train_textiles"]),
            "validation": len(split["validation_textiles"]),
            "test": len(split["test_textiles"]),
        },
        "scan_areas": {
            "train": int(split["train_rows"].size),
            "validation": int(split["validation_rows"].size),
            "test": int(split["test_rows"].size),
        },
        "train_textile_ids": sorted(split["train_textiles"]),
        "validation_textile_ids": sorted(split["validation_textiles"]),
        "test_textile_ids": sorted(split["test_textiles"]),
    }


def grouped_cross_validation_folds(labels, textile_ids, folds_wanted=4,
                                   random_seed=42):
    from sklearn.model_selection import StratifiedGroupKFold

    labels = np.asarray([str(item) for item in labels])
    groups = np.asarray([str(item) for item in textile_ids])

    per_class = _textiles_by_class(labels.tolist(), groups.tolist())
    smallest_class = min(len(ids) for ids in per_class.values())
    folds_wanted = max(2, min(folds_wanted, smallest_class))

    splitter = StratifiedGroupKFold(
        n_splits=folds_wanted, shuffle=True, random_state=random_seed
    )

    folds = []
    for train_rows, test_rows in splitter.split(
            np.zeros(len(labels)), labels, groups):
        check_no_textile_is_in_two_splits(
            groups[train_rows], [], groups[test_rows]
        )
        folds.append((train_rows, test_rows))
    return folds
