import pytest

from model_training_and_testing.split_dataset_without_mixing_same_textile import (
    TextileAppearsInTwoSplits,
    check_no_textile_is_in_two_splits,
    describe_split,
    split_by_textile,
)


def make_a_dataset(handmade_count=8, machine_count=8, areas_each=5):
    labels = []
    textile_ids = []

    for number in range(handmade_count):
        for _area in range(areas_each):
            labels.append("handmade")
            textile_ids.append("H%03d" % number)

    for number in range(machine_count):
        for _area in range(areas_each):
            labels.append("machine")
            textile_ids.append("M%03d" % number)

    return labels, textile_ids


def test_no_textile_ends_up_in_two_splits():
    labels, textile_ids = make_a_dataset()
    split = split_by_textile(labels, textile_ids)

    train = set(split["train_textiles"])
    validation = set(split["validation_textiles"])
    test = set(split["test_textiles"])

    assert not (train & validation)
    assert not (train & test)
    assert not (validation & test)


def test_every_scan_area_of_one_textile_lands_in_the_same_split():
    labels, textile_ids = make_a_dataset()
    split = split_by_textile(labels, textile_ids)

    where = {}
    for name, rows in (("train", split["train_rows"]),
                       ("validation", split["validation_rows"]),
                       ("test", split["test_rows"])):
        for row in rows:
            textile_id = textile_ids[row]
            if textile_id in where:
                assert where[textile_id] == name, (
                    "textile %s has scan areas in both %s and %s"
                    % (textile_id, where[textile_id], name)
                )
            else:
                where[textile_id] = name


def test_every_scan_area_is_used_exactly_once():
    labels, textile_ids = make_a_dataset()
    split = split_by_textile(labels, textile_ids)

    all_rows = (list(split["train_rows"]) + list(split["validation_rows"])
                + list(split["test_rows"]))

    assert sorted(all_rows) == list(range(len(textile_ids)))


def test_both_classes_appear_in_training():
    labels, textile_ids = make_a_dataset()
    split = split_by_textile(labels, textile_ids)

    label_by_textile = dict(zip(textile_ids, labels))
    training_labels = {label_by_textile[t] for t in split["train_textiles"]}

    assert training_labels == {"handmade", "machine"}


def test_the_same_split_comes_out_every_time():
    labels, textile_ids = make_a_dataset()

    first = split_by_textile(labels, textile_ids, random_seed=42)
    second = split_by_textile(labels, textile_ids, random_seed=42)

    assert first["train_textiles"] == second["train_textiles"]
    assert first["test_textiles"] == second["test_textiles"]


def test_a_textile_labelled_both_ways_is_caught_and_named():
    labels = ["handmade", "machine", "handmade", "machine"]
    textile_ids = ["H001", "H001", "M001", "M001"]

    with pytest.raises(TextileAppearsInTwoSplits) as raised:
        split_by_textile(labels, textile_ids)

    assert "more than one class" in str(raised.value)


def test_the_leakage_check_actually_catches_leakage():
    with pytest.raises(TextileAppearsInTwoSplits):
        check_no_textile_is_in_two_splits(["H001", "H002"], [], ["H001"])


def test_the_leakage_check_passes_when_there_is_none():
    check_no_textile_is_in_two_splits(["H001"], ["H002"], ["H003"])


def test_a_tiny_dataset_still_holds_something_back():
    labels, textile_ids = make_a_dataset(
        handmade_count=2, machine_count=2, areas_each=3
    )
    split = split_by_textile(labels, textile_ids)

    assert len(split["train_textiles"]) >= 2
    assert len(split["test_textiles"]) >= 2


def test_the_summary_counts_textiles_and_areas_separately():
    labels, textile_ids = make_a_dataset(
        handmade_count=8, machine_count=8, areas_each=5
    )
    summary = describe_split(split_by_textile(labels, textile_ids))

    total_textiles = sum(summary["textiles"].values())
    total_areas = sum(summary["scan_areas"].values())

    assert total_textiles == 16
    assert total_areas == 80
