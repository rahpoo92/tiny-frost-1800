from datetime import date, datetime, timedelta

from anpr_app.jalali import (
    format_jalali_datetime,
    gregorian_to_jalali,
    jalali_to_gregorian,
    to_persian_digits,
)


def test_known_anchor_dates():
    assert gregorian_to_jalali(1979, 2, 11) == (1357, 11, 22)  # 22 Bahman
    assert gregorian_to_jalali(2024, 3, 20) == (1403, 1, 1)  # Nowruz 1403
    assert gregorian_to_jalali(2025, 3, 21) == (1404, 1, 1)  # Nowruz 1404


def test_roundtrip_is_exact_over_a_wide_range():
    d = date(1990, 1, 1)
    for _ in range(200):
        jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
        assert jalali_to_gregorian(jy, jm, jd) == (d.year, d.month, d.day)
        d += timedelta(days=53)


def test_to_persian_digits():
    assert to_persian_digits("2026-09-26") == "۲۰۲۶-۰۹-۲۶"


def test_format_jalali_datetime_uses_persian_digits_by_default():
    text = format_jalali_datetime(datetime(2024, 3, 20, 8, 5, 0))
    assert "۱۴۰۳" in text
    assert "2024" not in text
