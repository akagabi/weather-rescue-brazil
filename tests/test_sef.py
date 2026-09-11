"""SEF (Station Exchange Format) export - the C3S Data Rescue submission format.

Structure per the C3S spec: TSV, one variable per file, 12 header lines given as
name/value pairs in a fixed order, then a header row and one observation per
line with columns year, month, day, hour, minute, period, value, meta.

The value of testing this is that the format is unforgiving and machine-checked:
`dataresqc::check_sef` will reject a file whose header order or column count is
wrong, and the submission is a one-shot.
"""

from wrb.sef import HEADER_KEYS, data_line, header, sef_filename, write_sef


def station(**kw):
    base = {"id": "rio_imperial", "name": "Imperial Observatorio, Rio de Janeiro",
            "lat": -22.895, "lon": -43.183, "alt": 30, "source": "wrb", "link": "NA"}
    return {**base, **kw}


def test_header_has_the_twelve_keys_in_the_documented_order():
    h = header(station(), variable="ta", stat="mean", units="degC", meta="")
    lines = h.strip("\n").split("\n")
    assert len(lines) == 12
    assert [l.split("\t")[0] for l in lines] == list(HEADER_KEYS)
    assert lines[0].split("\t")[1].startswith("SEF") or lines[0].startswith("SEF\t")


def test_the_sef_version_line_carries_a_semantic_version():
    lines = header(station(), variable="ta", stat="mean", units="degC", meta="").strip().split("\n")
    assert lines[0].split("\t") == ["SEF", "1.0.0"]


def test_a_header_value_may_be_NA_but_the_key_stays():
    h = header(station(lat=None, lon=None, alt=None), variable="ta", stat="mean", units="degC", meta="")
    rows = dict(l.split("\t", 1) for l in h.strip().split("\n"))
    assert rows["Lat"] == "NA" and rows["Lon"] == "NA" and rows["Alt"] == "NA"
    assert len(rows) == 12


def test_a_data_line_has_the_eight_documented_columns():
    cols = data_line(1886, 1, 4, 22, 30, "day", 754.44, "").split("\t")
    assert cols == ["1886", "1", "4", "22", "30", "day", "754.44", ""]


def test_a_missing_time_is_written_as_NA_not_zero():
    cols = data_line(1886, 1, 4, None, None, "day", 25.3, "").split("\t")
    assert cols[3] == "NA" and cols[4] == "NA"


def test_a_quality_flag_travels_in_the_meta_column():
    """SEF has no QC flag column: the C3S convention is a meta entry."""
    cols = data_line(1886, 1, 4, None, None, "day", 25.3, "qc=uncertain").split("\t")
    assert cols[7] == "qc=uncertain"


def test_the_filename_follows_the_dataresqc_convention():
    assert sef_filename("wrb", "rio_imperial", "1886-01-01", "1886-01-31", "ta") == \
        "wrb_rio_imperial_1886-01-01_1886-01-31_ta.tsv"


def test_write_sef_emits_header_then_column_row_then_data(tmp_path):
    p = tmp_path / "x.tsv"
    write_sef(p, station(), variable="ta", stat="mean", units="degC",
              rows=[(1886, 1, 4, None, None, "day", 25.3, ""),
                    (1886, 1, 5, None, None, "day", 26.1, "qc=uncertain")])
    lines = p.read_text().split("\n")
    assert len([l for l in lines if l.strip()]) == 12 + 1 + 2
    assert lines[12].split("\t") == ["Year", "Month", "Day", "Hour", "Minute", "Period", "Value", "Meta"]
