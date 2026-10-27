"""
Pure-Python language helpers for Indian legal drafting.

Written by hand instead of pulling in num2words etc. These rules are
specific (lakh/crore grouping, "Rupees ... Only", "27th day of October")
and small enough that owning them is clearer than configuring a library.
"""

from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven",
         "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _below_hundred(n: int) -> str:
    if n < 20:
        return _ONES[n]
    return (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")).strip()


def _below_thousand(n: int) -> str:
    h, r = divmod(n, 100)
    parts = []
    if h:
        parts.append(_ONES[h] + " Hundred")
    if r:
        parts.append(_below_hundred(r))
    return " ".join(parts)


def number_to_words_indian(n: int) -> str:
    """12_50_000 -> 'Twelve Lakh Fifty Thousand'.

    Indian system: groups are 3 digits (hundreds), then 2-digit groups for
    thousand, lakh and crore. Anything over 99 crore recurses into "X Crore",
    so 1,00,00,00,000 reads "One Hundred Crore", as Indian pleadings write it.
    """
    if n == 0:
        return "Zero"
    if n < 0:
        return "Minus " + number_to_words_indian(-n)
    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thousand, n = divmod(n, 1000)
    parts = []
    if crore:
        parts.append(number_to_words_indian(crore) + " Crore")
    if lakh:
        parts.append(_below_hundred(lakh) + " Lakh")
    if thousand:
        parts.append(_below_hundred(thousand) + " Thousand")
    if n:
        parts.append(_below_thousand(n))
    return " ".join(parts)


def to_decimal(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("₹", "").strip())
    except InvalidOperation:
        return None


def format_inr(amount) -> str:
    """1250000.5 -> '₹12,50,000.50' (Indian digit grouping: 3 then 2s)."""
    d = to_decimal(amount)
    if d is None:
        return ""
    d = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if d < 0 else ""
    whole, frac = f"{abs(d):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{sign}₹{whole}" + (f".{frac}" if frac != "00" else "")


def amount_in_words(amount) -> str:
    """1250000.50 -> 'Rupees Twelve Lakh Fifty Thousand and Paise Fifty Only'."""
    d = to_decimal(amount)
    if d is None:
        return ""
    d = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    rupees = int(d)
    paise = int((d - rupees) * 100)
    text = "Rupees " + number_to_words_indian(rupees)
    if paise:
        text += " and Paise " + number_to_words_indian(paise)
    return text + " Only"


def ordinal(n: int) -> str:
    # 11th/12th/13th are the classic exception to the 1st/2nd/3rd rule.
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def parse_date(value) -> dt.date | None:
    if isinstance(value, dt.date):
        return value
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def legal_date(value) -> str:
    """2026-10-27 -> '27th day of October, 2026' (verification/affidavit style)."""
    d = parse_date(value)
    return f"{ordinal(d.day)} day of {d.strftime('%B')}, {d.year}" if d else ""


def short_date(value) -> str:
    """2026-10-27 -> '27.10.2026' (the usual style inside pleadings)."""
    d = parse_date(value)
    return d.strftime("%d.%m.%Y") if d else ""


def simple_interest(principal, rate_pa, start, end) -> Decimal:
    """Simple interest on actual days / 365, the convention Indian courts use in
    money suits, unless a contract says otherwise (out of scope here)."""
    p, r = to_decimal(principal), to_decimal(rate_pa)
    s, e = parse_date(start), parse_date(end)
    if p is None or r is None or not s or not e or e <= s:
        return Decimal("0")
    days = (e - s).days
    return (p * r * days / Decimal(36500)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def join_names(names: list[str]) -> str:
    """['A','B','C'] -> 'A, B and C'."""
    names = [n for n in names if n]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]
