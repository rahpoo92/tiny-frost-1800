"""The Iranian license plate character set and the PlateNumber value object.

A standard Iranian plate reads, left to right: two digits, one Persian
letter, three digits, a divider, then a two-digit province code, e.g.
12 <letter> 345 | 67. Digits on the plate are plain Western numerals; the
letter identifies the plate's category (private, taxi, government,
diplomatic, ...). The exact legal meaning of each letter isn't enforced by
this software -- the set below just needs to cover every letter that can
appear so recognition and data entry both have a slot for it. Add more
entries to LETTERS (and enroll matching character templates, see
tools/enroll.py) if a plate category you see isn't listed yet.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..jalali import to_persian_digits

# slug (ASCII, safe as a dict key / folder name / config value) -> glyph(s)
# exactly as printed on the plate.
LETTERS: dict[str, str] = {
    "alef": "الف",
    "b": "ب",
    "p": "پ",
    "t": "ت",
    "se": "ث",
    "j": "ج",
    "d": "د",
    "z": "ز",
    "s": "س",
    "sh": "ش",
    "sad": "ص",
    "ta": "ط",
    "ein": "ع",
    "f": "ف",
    "gh": "ق",
    "k": "ک",
    "g": "گ",
    "l": "ل",
    "m": "م",
    "n": "ن",
    "v": "و",
    "h": "ه",
    "y": "ی",
    "D": "D",  # پلاک سیاسی/دیپلماتیک
    "S": "S",  # پلاک سیاسی/دیپلماتیک
}

DIGITS: tuple[str, ...] = tuple(str(d) for d in range(10))

# every label the character classifier can be asked to recognize
ALL_LABELS: tuple[str, ...] = DIGITS + tuple(LETTERS.keys())


def is_digits(value: str, length: int) -> bool:
    return len(value) == length and value.isdigit()


@dataclass(frozen=True)
class PlateNumber:
    part1: str  # two digits, e.g. "12"
    letter_slug: str  # key into LETTERS, e.g. "b"
    part2: str  # three digits, e.g. "345"
    province: str  # two digits, e.g. "67"

    def is_valid(self) -> bool:
        return (
            is_digits(self.part1, 2)
            and is_digits(self.part2, 3)
            and is_digits(self.province, 2)
            and self.letter_slug in LETTERS
        )

    @property
    def letter_glyph(self) -> str:
        return LETTERS.get(self.letter_slug, self.letter_slug)

    def to_key(self) -> str:
        """Compact ASCII identifier used as the plate's DB lookup key."""
        return f"{self.part1}{self.letter_slug}{self.part2}{self.province}"

    def to_display(self, persian_digits: bool = True) -> str:
        text = f"{self.part1} {self.letter_glyph} {self.part2} ایران {self.province}"
        return to_persian_digits(text) if persian_digits else text

    @classmethod
    def from_labels(cls, labels: list[str]) -> "PlateNumber | None":
        """Build a PlateNumber from 8 ordered classifier labels, left to right."""
        if len(labels) != 8:
            return None
        part1 = "".join(labels[0:2])
        letter_slug = labels[2]
        part2 = "".join(labels[3:6])
        province = "".join(labels[6:8])
        return cls(part1=part1, letter_slug=letter_slug, part2=part2, province=province)
