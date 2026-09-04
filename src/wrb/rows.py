"""Day-row localisation for training crops (G4.0).

The G3 zoom geometry (`wrb.zoom.row_band_geometry`) assumes evenly pitched
day rows between two ruled borders and pads each band by 1.8x to survive
that assumption being approximate. That padding is fine for a *re-read*
flagger but poisons a *training* crop: the M4 smoke test (docs/g4-model-choice.md
section 8) showed a 1.8x band catching two rows and the model copying the
neighbour. Volumes 15/16 (Santa-Cruz) also interleave "Déc." decade-summary
rows and a "Mez" row between the day rows, so even pitch is simply wrong there.

This module reads the actual text lines off the page instead:

1. Otsu-binarise a narrow probe window (day-number + first barometer
   column) - narrow so page skew cannot smear neighbouring rows together,
   Otsu because the fixed thresholds of G3 counted paper grain as ink (210)
   or lost volume 14's light strokes (paper mode - 70);
2. mask out vertical rules / scan edges (columns that are ink over a large
   share of the page height) so the row profile only sees glyphs;
3. row pitch candidates = autocorrelation maxima of the profile (the day rows
   are the most repeated structure on the page; harmonics also score, so
   several candidates are tried);
4. row centres = local maxima of the smoothed profile; the day rows are the
   longest chain of centres with near-uniform pitch that does not cross a
   horizontal rule (rules bound the table body: header above, footnotes
   below), after removing isolated single peaks bridged by ~2-pitch gaps
   (Déc./Mez summary rows) and an ink-sparse units line ("mm mm o o");
5. exactly `day_count` rows must remain, else the page is REFUSED with a
   diagnosis. A refused page goes to human review, never into training.

Pure PIL, deterministic, no network.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from PIL import Image

from wrb.zoom import _TABLE_X_FRAC

COL_MASK_FRAC = 0.22       # a column is a rule/edge if ink over > this fraction of page height
COL_MASK_DILATE = 3        # px either side of a masked column
PROBE_X_FRAC = (0.13, 0.22)  # narrow window (day-number + first barometer column)
DAY_COL_SEARCH_X_FRAC = (0.09, 0.26)  # the day-number column (between the first two vertical rules) is found in here
RULE_CELL_FILL = 0.7       # a 20-px cell counts as rule if >= this fraction of it is ink
RULE_THR_FRAC = 0.5        # rules print lighter than digits: rule threshold = thr + frac * (paper mode - thr)
DAY_COL_MIN_FRAC = 0.1     # chain-end row is not a day row if its day-column ink < this x median (a lone '1' is thin; the units line is exactly 0)
SKEW_ANGLES = [a / 10 for a in range(-15, 16)]  # degrees tried by `estimate_skew` (coarse)
RIGHT_X_FRAC = (0.48, 0.60)  # second probe window for the fine skew: vapor/humidity columns (dense digits every row)
FINE_SKEW_MAX_DY = 14        # px of vertical offset searched between the two windows
PITCH_RANGE = (12, 80)     # px; autocorrelation lags searched for the row pitch
WEAK_PEAK_FRAC = 0.15      # peaks below this x median peak height are noise
CHAIN_GAP_RANGE = (0.8, 1.2)  # consecutive-centre gap / pitch allowed inside the day chain (typeset rows are very regular)
ISOLATED_MAX_GAP = 3.4     # x pitch: a lone peak with gaps up to this on both sides is a summary row
UNITS_INK_FRAC = 0.45      # chain end is the units line if its peak < this x median chain peak
RULE_MIN_FRAC = 0.35       # a y-line is a horizontal rule if > this fraction of the table width is ink


@dataclass
class RowLocation:
    day_boxes: list[tuple[int, int, int, int]]   # one (x0, y0, x1, y1) per day, in day order (deskewed coords)
    peaks: list[int]                             # every row-centre candidate found (y)
    dropped: dict[str, list[int]] = field(default_factory=dict)
    pitch: float = 0.0
    ink_threshold: int = 0
    skew_deg: float = 0.0
    rules: list[int] = field(default_factory=list)
    day_col: tuple[int, int] = (0, 0)
    chain: list[int] = field(default_factory=list)      # row centres kept as day rows (even when count is wrong)
    ok: bool = True
    reason: str = ""


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _smooth(xs: list[float], radius: int) -> list[float]:
    n = len(xs)
    acc = [0.0]
    for v in xs:
        acc.append(acc[-1] + v)
    out = []
    for i in range(n):
        a, b = max(0, i - radius), min(n, i + radius + 1)
        out.append((acc[b] - acc[a]) / (b - a))
    return out


def ink_threshold(gray: Image.Image, box: tuple[int, int, int, int] | None = None) -> int:
    """Otsu threshold over `box` (default: whole image)."""
    region = gray.crop(box) if box else gray
    hist = region.histogram()
    total = sum(hist)
    sum_all = sum(i * h for i, h in enumerate(hist))
    w_b = 0
    sum_b = 0
    best, thr = -1.0, 128
    for i in range(256):
        w_b += hist[i]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += i * hist[i]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        between = w_b * w_f * (m_b - m_f) ** 2
        if between > best:
            best, thr = between, i
    return thr


def row_profile(gray: Image.Image, x0: int, x1: int, thr: int) -> tuple[list[float], list[int]]:
    """Ink fraction per y-line over columns [x0, x1) that are not vertical
    rules / scan edges. Returns (profile, kept_columns)."""
    width, height = gray.size
    bw = gray.point(lambda v: 255 if v < thr else 0, mode="L")
    col = bw.resize((width, 1), Image.BOX).load()
    masked = [col[x, 0] / 255 > COL_MASK_FRAC for x in range(width)]
    keep = [x for x in range(x0, x1)
            if not any(masked[max(0, x - COL_MASK_DILATE):x + COL_MASK_DILATE + 1])]
    if len(keep) < 20:
        return [0.0] * height, keep
    sub = Image.new("L", (len(keep), height))
    src = bw.load()
    dst = sub.load()
    for i, x in enumerate(keep):
        for y in range(height):
            dst[i, y] = src[x, y]
    row = sub.resize((1, height), Image.BOX).load()
    return [row[0, y] / 255 for y in range(height)], keep


def _profile_variance(gray: Image.Image, x0: int, x1: int, thr: int) -> float:
    bw = gray.point(lambda v: 255 if v < thr else 0, mode="L").crop((x0, 0, x1, gray.height))
    col = bw.resize((1, gray.height), Image.BOX).load()
    vals = [col[0, y] for y in range(gray.height)]
    m = sum(vals) / len(vals)
    return sum((v - m) ** 2 for v in vals) / len(vals)


def estimate_skew(gray: Image.Image, thr: int, *, probe_x_frac: tuple[float, float] = PROBE_X_FRAC) -> float:
    """Skew angle (degrees, PIL rotate convention) that maximises the row
    profile variance in the probe window - text lines stack into sharp
    peaks when the page is straight. Half-size copy for speed."""
    small = gray.resize((gray.width // 2, gray.height // 2), Image.BOX)
    x0, x1 = round(probe_x_frac[0] * small.width), round(probe_x_frac[1] * small.width)
    best, best_a = -1.0, 0.0
    for a in SKEW_ANGLES:
        rot = small.rotate(a, resample=Image.BILINEAR, fillcolor=255)
        v = _profile_variance(rot, x0, x1, thr)
        if v > best:
            best, best_a = v, a
    return best_a


def refine_skew(gray: Image.Image, thr: int, *, left: tuple[float, float] = PROBE_X_FRAC,
                right: tuple[float, float] = RIGHT_X_FRAC, max_dy: int = FINE_SKEW_MAX_DY) -> float:
    """Fine skew (degrees, PIL rotate convention) from the vertical offset
    that best aligns the row profile of a RIGHT window onto the LEFT one.
    The coarse variance search is quantised to 0.1 deg and blind to what
    happens 1200 px to the right; smoke2 gold pages 90/142/179 lost their
    tail columns to exactly that (half a row of drift at the right edge)."""
    import math
    w = gray.width
    lx0, lx1 = round(left[0] * w), round(left[1] * w)
    rx0, rx1 = round(right[0] * w), round(right[1] * w)
    pl, _ = row_profile(gray, lx0, lx1, thr)
    pr, _ = row_profile(gray, rx0, rx1, thr)
    ml, mr = sum(pl) / len(pl), sum(pr) / len(pr)
    a = [v - ml for v in pl]
    b = [v - mr for v in pr]
    n = len(a)
    best, best_dy = -1e18, 0
    for dy in range(-max_dy, max_dy + 1):
        c = sum(a[y] * b[y + dy] for y in range(max(0, -dy), min(n, n - dy)))
        if c > best:
            best, best_dy = c, dy
    dx = (rx0 + rx1) / 2 - (lx0 + lx1) / 2
    # right window's rows sit `best_dy` px LOWER on the page than the left's
    # when best_dy > 0 -> the page is rotated clockwise -> PIL rotate(+angle)
    # (counter-clockwise) straightens it.
    return math.degrees(math.atan2(best_dy, dx))


def pitch_candidates(prof: list[float], lo: int = PITCH_RANGE[0], hi: int = PITCH_RANGE[1],
                     keep_frac: float = 0.25) -> list[float]:
    """Row-pitch candidates (px): local maxima of the profile autocorrelation
    over lags [lo, hi] scoring >= keep_frac x the best, best first."""
    n = len(prof)
    m = sum(prof) / n
    x = [v - m for v in prof]
    ac = {lag: sum(x[i] * x[i + lag] for i in range(n - lag)) for lag in range(lo, hi + 1)}
    cands = [lag for lag in range(lo + 1, hi) if ac[lag] >= ac[lag - 1] and ac[lag] > ac[lag + 1]]
    cands.sort(key=lambda lag: -ac[lag])
    cands = cands[:6]  # top local maxima by autocorrelation; harmonics are resolved by the caller
    return [float(c) for c in cands] or [float(max(ac, key=ac.get))]


def find_peaks(prof: list[float], pitch: float) -> list[tuple[int, float]]:
    """Local maxima of the smoothed profile at least 0.6*pitch apart, as
    (y, height). Smoothing radius ~ pitch/5 fuses a row's strokes into one
    hump without fusing neighbouring rows."""
    sm = _smooth(prof, max(2, round(pitch / 5)))
    n = len(sm)
    cand = [y for y in range(1, n - 1) if sm[y] >= sm[y - 1] and sm[y] > sm[y + 1] and sm[y] > 0]
    cand.sort(key=lambda y: -sm[y])
    chosen: list[int] = []
    for y in cand:
        if all(abs(y - c) >= 0.6 * pitch for c in chosen):
            chosen.append(y)
    chosen.sort()
    return [(y, sm[y]) for y in chosen]


def horizontal_rules(gray: Image.Image, x0: int, x1: int, thr: int, *, min_dip: float = 15.0,
                     max_halfwidth: int = 4, cell: int = 20, min_cover: float = 0.85) -> list[int]:
    """y of horizontal rules = THIN, FULL-WIDTH dark lines in the raw grey
    profile (no binarisation: volume 14's rules print lighter than its
    digits and vanish at any text threshold). Per y-line the mean grey over
    the unmasked table columns is compared with the local background
    (max over +-8 px): a rule is a dip deeper than `min_dip` grey levels
    whose >=60%-depth region spans <= 2*max_halfwidth+1 lines; a text row
    is a shallower, ~20-px-wide hump and never qualifies. `thr` only picks
    the column mask."""
    width, height = gray.size
    bw = gray.point(lambda v: 255 if v < thr else 0, mode="L")
    col = bw.resize((width, 1), Image.BOX).load()
    masked = [col[x, 0] / 255 > COL_MASK_FRAC for x in range(width)]
    keep = [x for x in range(x0, x1)
            if not any(masked[max(0, x - COL_MASK_DILATE):x + COL_MASK_DILATE + 1])]
    if len(keep) < 20:
        return []
    sub = Image.new("L", (len(keep), height))
    src = gray.load()
    dst = sub.load()
    for i, x in enumerate(keep):
        for y in range(height):
            dst[i, y] = src[x, y]
    mean = sub.resize((1, height), Image.BOX).load()
    g = [mean[0, y] for y in range(height)]
    ncell = max(1, len(keep) // cell)
    cells = sub.resize((ncell, height), Image.BOX).load()
    out: list[int] = []
    for y in range(height):
        bg = max(g[max(0, y - 8):y + 9])
        dip = bg - g[y]
        if dip < min_dip:
            continue
        if g[y] > min(g[max(0, y - 2):y + 3]):
            continue  # not the local minimum of the dip
        lvl = bg - 0.6 * dip
        a = y
        while a > 0 and g[a - 1] <= lvl:
            a -= 1
        b = y
        while b < height - 1 and g[b + 1] <= lvl:
            b += 1
        if b - a > 2 * max_halfwidth:
            continue
        # the decisive test: a rule is dark in (almost) EVERY cell across the
        # width; a text row leaves column gaps and blank cells light
        cut = bg - 0.5 * dip
        ys = range(max(0, y - 2), min(height, y + 3))  # +-2 px: residual skew across the width
        covered = sum(1 for c in range(ncell) if min(cells[c, yy] for yy in ys) < cut)
        if covered < min_cover * ncell:
            continue
        if out and y - out[-1] <= 3:
            continue
        out.append(y)
    return out


def vertical_rules(gray: Image.Image, thr: int, *, cell: int = 20, min_frac: float = 0.3) -> list[int]:
    """x of vertical rules = columns continuously inked over > min_frac of
    the page height (same cell trick as `horizontal_rules`, transposed)."""
    bw = gray.point(lambda v: 255 if v < thr else 0, mode="L")
    ncell = max(1, gray.height // cell)
    small = bw.resize((gray.width, ncell), Image.BOX)
    px = small.load()
    out: list[int] = []
    for x in range(gray.width):
        full = sum(1 for c in range(ncell) if px[x, c] >= RULE_CELL_FILL * 255)
        if full > min_frac * ncell and not (out and x - out[-1] <= 4):
            out.append(x)
    return out


def day_column(gray: Image.Image, thr: int) -> tuple[int, int]:
    """x-range of the day-number column: the gap between the first two
    vertical rules inside DAY_COL_SEARCH_X_FRAC that is 15-90 px wide.
    Falls back to a fixed window when the rules are not found."""
    w = gray.width
    lo, hi = round(DAY_COL_SEARCH_X_FRAC[0] * w), round(DAY_COL_SEARCH_X_FRAC[1] * w)
    xs = [x for x in vertical_rules(gray, thr) if lo <= x <= hi]
    for a, b in zip(xs, xs[1:]):
        if 15 <= b - a <= 90:
            return a + 4, b - 3
    return round(0.13 * w), round(0.16 * w)


def _chain_for_pitch(peaks: list[tuple[int, float]], pitch: float, rules: list[int], day_count: int,
                     day_prof: list[float]) -> tuple[list[tuple[int, float]], dict[str, list[int]]]:
    dropped: dict[str, list[int]] = {"weak": [], "isolated": [], "units": [], "outside_chain": []}
    if len(peaks) < 2:
        return [], dropped
    med_h = _median([h for _, h in peaks])
    strong = [(y, h) for y, h in peaks if h >= WEAK_PEAK_FRAC * med_h]
    dropped["weak"] = [y for y, h in peaks if h < WEAK_PEAK_FRAC * med_h]
    ys = [y for y, _ in strong]
    lo, hi = CHAIN_GAP_RANGE[0] * pitch, CHAIN_GAP_RANGE[1] * pitch

    def rule_between(a: int, b: int) -> bool:
        return any(a < r < b for r in rules)

    chains: list[list[int]] = [[0]]
    for i in range(1, len(ys)):
        g = ys[i] - ys[i - 1]
        if lo <= g <= hi and not rule_between(ys[i - 1], ys[i]):
            chains[-1].append(i)
        else:
            chains.append([i])
    merged: list[list[int]] = []
    for ch in chains:
        if len(merged) >= 2 and len(merged[-1]) == 1:
            iso = merged[-1][0]
            prev = merged[-2]
            g_up = ys[iso] - ys[prev[-1]]
            g_dn = ys[ch[0]] - ys[iso]
            if (hi < g_up < ISOLATED_MAX_GAP * pitch and hi < g_dn < ISOLATED_MAX_GAP * pitch
                    and not rule_between(ys[prev[-1]], ys[ch[0]])):
                dropped["isolated"].append(ys[iso])
                merged.pop()
                merged[-1] = prev + ch
                continue
        merged.append(ch)
    best = max(merged, key=len)
    chain = [strong[i] for i in best]
    dropped["outside_chain"] = [ys[i] for i in range(len(ys)) if i not in best and ys[i] not in dropped["isolated"]]
    # trim chain ends that are not day rows: (a) no ink in the day-number
    # column (the units line "mm mm o o" has none), (b) an end row separated
    # from its neighbour by a blank line (the trailing Déc. row after day
    # 28-31 sits below extra whitespace).
    r = max(2, round(pitch / 5))
    day_ink = _smooth(day_prof, r)

    def day_col(y: int) -> float:
        return day_ink[min(len(day_ink) - 1, max(0, y))]

    # (a) the units line has NO day-number: anything from a chain end up to
    # and including the last ink-free day-column row within 3 rows of that
    # end is header/units (the rotated "DATA" label above the units line
    # does put ink in the day column, hence "up to and including").
    if len(chain) > day_count:
        med_d = _median([day_col(y) for y, _ in chain])
        head = [i for i in range(min(3, len(chain))) if day_col(chain[i][0]) < DAY_COL_MIN_FRAC * med_d]
        if head:
            cut = head[-1] + 1
            dropped["units"].extend(y for y, _ in chain[:cut]); chain = chain[cut:]
        tail = [i for i in range(max(0, len(chain) - 3), len(chain)) if day_col(chain[i][0]) < DAY_COL_MIN_FRAC * med_d]
        if tail and len(chain) > day_count:
            cut = tail[0]
            dropped["units"].extend(y for y, _ in chain[cut:]); chain = chain[:cut]
    # (b0) a chain-end row within half a pitch of a rule is the rule's own
    # shadow / a footer line, not a day row (day rows keep >= ~0.6 pitch clear)
    near = lambda y: any(abs(y - r) < 0.55 * pitch for r in rules)
    while len(chain) > day_count and near(chain[-1][0]):
        dropped["isolated"].append(chain[-1][0]); chain = chain[:-1]
    while len(chain) > day_count and near(chain[0][0]):
        dropped["units"].append(chain[0][0]); chain = chain[1:]
    # (b) an end row separated from its neighbour by a blank line (the
    # trailing Déc. row after day 28-31 sits below extra whitespace)
    while len(chain) > day_count:
        gaps = [chain[i + 1][0] - chain[i][0] for i in range(len(chain) - 1)]
        med_g = _median(gaps)
        if gaps[-1] > 1.25 * med_g and gaps[-1] >= gaps[0]:
            dropped["isolated"].append(chain[-1][0]); chain = chain[:-1]; continue
        if gaps[0] > 1.25 * med_g:
            dropped["isolated"].append(chain[0][0]); chain = chain[1:]; continue
        break
    return chain, dropped


def locate_day_rows(
    image: Image.Image,
    day_count: int,
    *,
    table_x_frac: tuple[float, float] = _TABLE_X_FRAC,
    probe_x_frac: tuple[float, float] = PROBE_X_FRAC,
    band_frac: float = 1.0,
) -> RowLocation:
    """Find the `day_count` day rows. See the module docstring. Boxes are
    `band_frac * pitch` tall, centred on each row's ink centroid, and span
    `table_x_frac` of the (deskewed) page width."""
    gray = image.convert("L")
    width, height = gray.size
    x0 = max(0, round(table_x_frac[0] * width))
    x1 = min(width, round(table_x_frac[1] * width))
    px0, px1 = round(probe_x_frac[0] * width), round(probe_x_frac[1] * width)
    thr = ink_threshold(gray, (px0, 0, px1, height))
    angle = estimate_skew(gray, thr, probe_x_frac=probe_x_frac)
    if angle:
        gray = gray.rotate(angle, resample=Image.BICUBIC, fillcolor=255)
    fine = refine_skew(gray, thr)
    if abs(fine) > 0.02:
        gray = gray.rotate(fine, resample=Image.BICUBIC, fillcolor=255)
        angle = round(angle + fine, 3)
    prof, _ = row_profile(gray, px0, px1, thr)
    hist = gray.histogram()
    paper = max(range(256), key=lambda v: hist[v])
    rule_thr = round(thr + RULE_THR_FRAC * max(0, paper - thr))
    rules = horizontal_rules(gray, x0, x1, thr)
    dx0, dx1 = day_column(gray, rule_thr)
    day_prof, _ = row_profile(gray, dx0, dx1, thr)

    tried: list[float] = []
    results = []
    for pitch in pitch_candidates(prof):
        peaks = find_peaks(prof, pitch)
        chain, dropped = _chain_for_pitch(peaks, pitch, rules, day_count, day_prof)
        tried.append(pitch)
        results.append((abs(len(chain) - day_count), pitch, peaks, chain, dropped))
    # exact matches first, then the SMALLEST pitch among them: a 2x harmonic
    # can also produce day_count rows by skipping every other line
    best = min(results, key=lambda r: (r[0], r[1])) if results else None
    assert best is not None
    _, pitch, peaks, chain, dropped = best
    loc = RowLocation([], [y for y, _ in peaks], dropped=dropped, pitch=pitch,
                      ink_threshold=thr, skew_deg=angle, rules=rules, day_col=(dx0, dx1), chain=[y for y, _ in chain])
    if len(chain) != day_count:
        loc.ok = False
        loc.reason = (f"chain has {len(chain)} rows, expected {day_count} "
                      f"(peaks={len(peaks)}, isolated={len(dropped['isolated'])}, pitch={pitch}, tried={tried})")
        return loc
    half = band_frac * pitch / 2
    loc.day_boxes = [(x0, max(0, round(y - half)), x1, min(height, round(y + half))) for y, _ in chain]
    return loc


def crop_day_rows(
    image_bytes: bytes, day_count: int, *, scale: float = 2.0, **kw,
) -> tuple[RowLocation, list[bytes]]:
    """PNG crops (one per day, day order) via `locate_day_rows`, taken from
    the DESKEWED page (boxes are in deskewed coordinates); empty list when
    the page fails localisation."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    loc = locate_day_rows(image, day_count, **kw)
    if not loc.ok:
        return loc, []
    if loc.skew_deg:
        image = image.rotate(loc.skew_deg, resample=Image.BICUBIC, fillcolor=(255, 255, 255))
    crops: list[bytes] = []
    for box in loc.day_boxes:
        c = image.crop(box)
        if scale != 1.0:
            c = c.resize((max(1, round(c.width * scale)), max(1, round(c.height * scale))), Image.LANCZOS)
        buf = io.BytesIO()
        c.save(buf, format="PNG")
        crops.append(buf.getvalue())
    return loc, crops
