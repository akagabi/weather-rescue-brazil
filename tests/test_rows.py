"""Row localisation (G4.0) on a SYNTHETIC Revista-style page: header block,
horizontal rules, a units line, 31 evenly pitched day rows with a day
number in a narrow first column, two interleaved 'Déc.' summary rows, a
footer line and free-text notes below. Pure PIL, no network, no model."""

import calendar

from PIL import Image, ImageDraw

from wrb.rows import (
    find_peaks, horizontal_rules, ink_threshold, locate_day_rows, pitch_candidates, row_profile,
)

W, H = 1600, 2400
PITCH = 28
X_TABLE = (int(0.09 * W), int(0.94 * W))
X_DAYCOL = (int(0.135 * W), int(0.165 * W))


def _draw_page(day_count: int = 31, *, dec_rows: bool = True, skew: float = 0.0) -> tuple[Image.Image, list[int]]:
    im = Image.new("L", (W, H), 232)
    dr = ImageDraw.Draw(im)
    x0, x1 = X_TABLE
    # header block: rotated-looking dense text = tall ink band, then a rule
    dr.rectangle((x0 + 60, 520, x1 - 40, 640), fill=120)
    for x in range(x0, x1, 100):
        dr.line((x, 520, x, 1700), fill=170, width=2)  # vertical rules
    dr.line((x0, 500, x1, 500), fill=150, width=3)
    dr.line((x0, 660, x1, 660), fill=150, width=3)       # header bottom rule
    # units line (no day number)
    y = 690
    for x in range(x0 + 120, x1, 110):
        dr.text((x, y - 6), "mm", fill=90)
    y += PITCH
    day_ys: list[int] = []
    for day in range(1, day_count + 1):
        if dec_rows and day in (11, 21):
            y += PITCH  # blank line
            for x in range(x0 + 120, x1, 110):
                dr.text((x, y - 6), "55.55", fill=60)
            dr.text((X_DAYCOL[0] + 2, y - 6), "Dec.", fill=60)
            y += 2 * PITCH
        day_ys.append(y)
        dr.text((X_DAYCOL[0] + 6, y - 7), str(day), fill=60)
        for x in range(x0 + 120, x1, 110):
            dr.text((x, y - 7), "754.44", fill=60)
        y += PITCH
    y += PITCH // 2
    dr.line((x0, y, x1, y), fill=150, width=3)            # table bottom rule
    y += 30
    dr.text((x0 + 20, y - 6), "Das 2 direccoes do vento, a 1a refere-se a frequencia da manha", fill=60)
    y += 40
    dr.line((x0, y, x1, y), fill=150, width=3)
    for i in range(12):                                    # free-text notes, wider pitch
        y += 36
        dr.text((x0 + 20, y - 6), "Dia %d - Ligeiro nevoeiro pela manha e a noite, chuva fina" % (i + 1), fill=60)
    if skew:
        im = im.rotate(skew, resample=Image.BICUBIC, fillcolor=232)
    return im.convert("RGB"), day_ys


def test_locates_all_days_plain_layout():
    im, ys = _draw_page(31, dec_rows=False)
    loc = locate_day_rows(im, 31)
    assert loc.ok, loc.reason
    assert len(loc.day_boxes) == 31
    for (x0, y0, x1, y1), y in zip(loc.day_boxes, ys):
        assert y0 <= y <= y1, (y0, y, y1)
        assert (y1 - y0) <= 1.3 * PITCH


def test_skips_dec_summary_rows():
    im, ys = _draw_page(31, dec_rows=True)
    loc = locate_day_rows(im, 31)
    assert loc.ok, loc.reason
    centres = [(b[1] + b[3]) / 2 for b in loc.day_boxes]
    for c, y in zip(centres, ys):
        assert abs(c - y) <= PITCH / 3, (c, y)


def test_handles_28_day_month_and_skew():
    im, ys = _draw_page(28, dec_rows=True, skew=0.4)
    loc = locate_day_rows(im, 28)
    assert loc.ok, loc.reason
    assert len(loc.day_boxes) == 28
    assert abs(loc.skew_deg) >= 0.2


def test_refuses_when_day_count_impossible():
    im, _ = _draw_page(31, dec_rows=False)
    loc = locate_day_rows(im, 45)
    assert not loc.ok
    assert "expected 45" in loc.reason


def test_rules_and_pitch_primitives():
    im, _ = _draw_page(31, dec_rows=False)
    gray = im.convert("L")
    thr = ink_threshold(gray)
    rules = horizontal_rules(gray, *X_TABLE, thr)
    assert any(abs(r - 660) <= 3 for r in rules)  # header bottom rule found
    assert all(not (700 < r < 1580) for r in rules)  # no rule between the day rows (bottom rule ~1599 is expected)
    prof, _ = row_profile(gray, int(0.13 * W), int(0.22 * W), thr)
    assert PITCH in [round(p) for p in pitch_candidates(prof)]
    peaks = find_peaks(prof, PITCH)
    assert len(peaks) >= 31


def test_day_count_helper_consistency():
    assert calendar.monthrange(1886, 2)[1] == 28
