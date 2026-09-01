from wrb.gold import Sheet, Row, validate_sheet

def make(rows, totals=None, cols=("tmax", "tmin")):
    return Sheet(source="hdbn", bib="364568", page=1, station="Rio - Obs. Imperial",
                 period="1870-05", columns=list(cols), rows=rows, printed_totals=totals)

def test_tmax_ge_tmin_violation_detected():
    s = make([Row(date="1870-05-01", cells={"tmax": 20.0, "tmin": 25.0}, flags={})])
    assert any("tmax" in v and "tmin" in v for v in validate_sheet(s))

def test_printed_total_checksum():
    rows = [Row(date=f"1870-05-{d:02d}", cells={"tmax": 20.0, "tmin": 10.0}, flags={}) for d in (1, 2)]
    ok = validate_sheet(make(rows, totals={"tmax_mean": 20.0}))
    assert ok == []
    bad = validate_sheet(make(rows, totals={"tmax_mean": 27.0}))   # row-shift symptom
    assert any("printed" in v for v in bad)

def test_physical_range():
    s = make([Row(date="1870-05-01", cells={"tmax": 61.0, "tmin": 10.0}, flags={})])
    assert any("range" in v for v in validate_sheet(s))

def test_printed_total_malformed_key_no_underscore():
    rows = [Row(date="1870-05-01", cells={"tmax": 20.0, "tmin": 10.0}, flags={})]
    s = make(rows, totals={"tmax": 20.0})  # malformed: no underscore, no _mean/_sum
    violations = validate_sheet(s)
    assert len(violations) > 0, "malformed key should produce a violation"
    assert any("malformed" in v and "tmax" in v for v in violations), "violation should mention the key and 'malformed'"

def test_printed_total_sum_branch():
    # Test _sum branch (currently only _mean is covered in other tests)
    rows = [Row(date=f"1870-05-{d:02d}", cells={"precip": 5.0}, flags={}) for d in (1, 2)]
    ok = validate_sheet(make(rows, totals={"precip_sum": 10.0}, cols=("precip",)))
    assert ok == [], f"correct sum should pass, got {ok}"
    bad = validate_sheet(make(rows, totals={"precip_sum": 27.0}, cols=("precip",)))
    assert any("printed" in v for v in bad), "wrong sum should be flagged"
