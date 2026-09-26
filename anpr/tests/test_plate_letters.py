from anpr_app.vision.plate_letters import ALL_LABELS, DIGITS, LETTERS, PlateNumber


def test_valid_plate_key_and_display():
    plate = PlateNumber("12", "b", "345", "22")
    assert plate.is_valid()
    assert plate.to_key() == "12b34522"
    display = plate.to_display(persian_digits=False)
    assert display == "12 ب 345 ایران 22"


def test_invalid_plates_are_rejected():
    assert not PlateNumber("1", "b", "345", "22").is_valid()  # part1 too short
    assert not PlateNumber("12", "zz", "345", "22").is_valid()  # unknown letter
    assert not PlateNumber("12", "b", "3456", "22").is_valid()  # part2 too long
    assert not PlateNumber("12", "b", "345", "2").is_valid()  # province too short
    assert not PlateNumber("1a", "b", "345", "22").is_valid()  # non-digit


def test_from_labels_builds_expected_plate():
    labels = ["1", "2", "b", "3", "4", "5", "2", "2"]
    plate = PlateNumber.from_labels(labels)
    assert plate == PlateNumber("12", "b", "345", "22")


def test_from_labels_wrong_length_returns_none():
    assert PlateNumber.from_labels(["1", "2"]) is None
    assert PlateNumber.from_labels(["1"] * 9) is None


def test_all_labels_covers_digits_and_letters_exactly_once():
    assert set(ALL_LABELS) == set(DIGITS) | set(LETTERS.keys())
    assert len(ALL_LABELS) == len(DIGITS) + len(LETTERS)
