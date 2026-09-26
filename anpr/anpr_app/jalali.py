"""Gregorian <-> Jalali (Shamsi) date conversion, with no third-party dependency.

The forward conversion (gregorian_to_jalali) implements the well-known
public-domain Jalaali algorithm. The backward conversion is derived from it
by binary search over Gregorian ordinals, which guarantees the two
directions are always exact inverses of each other rather than relying on a
second, independently-derived formula.
"""

from __future__ import annotations

from datetime import date, datetime

_PERSIAN_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]

_PERSIAN_WEEKDAYS = {
    0: "دوشنبه", 1: "سه‌شنبه", 2: "چهارشنبه", 3: "پنجشنبه",
    4: "جمعه", 5: "شنبه", 6: "یکشنبه",
}

_DIGIT_MAP = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def to_persian_digits(text: str) -> str:
    return text.translate(_DIGIT_MAP)


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        - 80
        + gd
        + g_d_m[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + (days % 31)
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    """Inverse of gregorian_to_jalali, found by binary search over ordinals."""
    target = (jy, jm, jd)

    lo = date(1600, 1, 1).toordinal()
    hi = date(2400, 1, 1).toordinal()
    while lo < hi:
        mid = (lo + hi) // 2
        d = date.fromordinal(mid)
        if gregorian_to_jalali(d.year, d.month, d.day) < target:
            lo = mid + 1
        else:
            hi = mid
    result = date.fromordinal(lo)
    return result.year, result.month, result.day


def format_jalali_date(dt: datetime, persian_digits: bool = True) -> str:
    jy, jm, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
    weekday = _PERSIAN_WEEKDAYS[dt.weekday()]
    text = f"{weekday} {jd} {_PERSIAN_MONTHS[jm - 1]} {jy}"
    return to_persian_digits(text) if persian_digits else text


def format_jalali_datetime(dt: datetime, persian_digits: bool = True) -> str:
    date_part = format_jalali_date(dt, persian_digits=persian_digits)
    time_part = dt.strftime("%H:%M:%S")
    if persian_digits:
        time_part = to_persian_digits(time_part)
    return f"{date_part} - ساعت {time_part}"


def format_jalali_compact(dt: datetime) -> str:
    """e.g. 1404/07/04 14:32:05 (Western digits, sortable-ish, for exports)."""
    jy, jm, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d} {dt.strftime('%H:%M:%S')}"
