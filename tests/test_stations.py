"""Coordinates as the Revista prints them, and the two ways to misread them.

Every line here was read off a scan of the `RESUMO MENSAL DAS OBSERVAÇÕES
SIMULTANEAS` form in docIds 15 and 16; the page each came from is named.
The assertions are against the modern position of the same place, which is
what makes them a proof rather than a restatement: the printed longitudes are
measured from Rio, and a parser that forgot that would put São Paulo in the
Atlantic.
"""
import pytest

from wrb.stations import RIO_LONGITUDE, parse_angle, parse_header, to_greenwich

# printed line -> (modern lat, modern lon) of the same place
PRINTED = {
    # doc 16 page 41
    "Estação, S. Paulo; Observador, Alberto Loefgren; Latitude, 23°36' S; "
    "Longitude, 3°28' W; Hora local, 8h29m27s; Alt. do Bar. 735m42":
        (-23.55, -46.63),
    # doc 15 page 126
    "Estação, Maceió; Observador, Pedro Rodrigues Soares; Latitude, 9°,38'; "
    "Longitude, 0h,30m E; Hora local, 9h,36m; Altura do Barometro, 10m":
        (-9.67, -35.73),
    "Estação, Ponte B. de Macedo; Observador, Manoel Villarouco; "
    "Latit., 8°3'54'' S; Long., 0h33m11s4 E; Hora local, 9h40m; "
    "Alt. do Bar., 2m,87": (-8.05, -34.88),
    # doc 16 page 41
    "Estação, Bahia (Capital); Observador, Dr. R. A. Pereira Guimarães; "
    "Latitude, S 12°58'27''; Long., E 4°37'40''; Hora local, 9h25m30s; "
    "Alt. do Bar. 64m": (-12.97, -38.51),
    "Estação, Santa Cruz; Observador, J. N. C. Lousada; Latitude, 22°,56'; "
    "Longitude, 2m W; Hora local, 9h,9m; Alt. do Bar. 26m": (-22.92, -43.68),
}


@pytest.mark.parametrize("line,expected", list(PRINTED.items()))
def test_printed_coordinates_land_on_the_place(line, expected):
    want_lat, want_lon = expected
    h = parse_header(line)
    lat = h["lat_deg"] if h["lat_hemisphere"] else -abs(h["lat_deg"])
    assert lat == pytest.approx(want_lat, abs=0.15), h["fields"]["station"]
    assert h["lon_deg"] == pytest.approx(want_lon, abs=0.15), h["fields"]["station"]


def test_longitudes_are_measured_from_rio_not_greenwich():
    """3°28' W of Rio is São Paulo; 3°28' W of Greenwich is Spain."""
    assert to_greenwich(parse_angle("3°28' W")) == pytest.approx(-46.64, abs=0.01)
    assert RIO_LONGITUDE == pytest.approx(-43.1725, abs=0.001)


def test_minutes_of_time_are_not_arcminutes():
    """Santa Cruz prints `2m W`: half a degree, not two arcminutes."""
    assert parse_angle("2m W") == pytest.approx(-0.5, abs=1e-9)
    assert parse_angle("0h,30m E") == pytest.approx(7.5, abs=1e-9)


def test_a_comma_after_the_degree_mark_is_a_separator():
    """`9°,38'` is 9 degrees 38 minutes - reading it as 9.0 lost Maceió 38'."""
    assert parse_angle("9°,38'") == pytest.approx(9 + 38 / 60, abs=1e-9)


def test_hemisphere_letter_on_either_side():
    assert parse_angle("23°36' S") == pytest.approx(-23.6, abs=1e-9)
    assert parse_angle("S 12°58'27''") == pytest.approx(-12.9742, abs=1e-3)


def test_a_missing_hemisphere_is_reported_not_assumed():
    """Maceió's line prints no N/S at all; the page does not say south."""
    h = parse_header("Estação, Maceió; Latitude, 9°,38'; Longitude, 0h,30m E")
    assert h["lat_hemisphere"] is None
    assert h["lat_deg"] > 0


def test_a_ship_has_no_coordinate():
    """The Cruzador Almirante Barroso observed between Recife and São Luís."""
    h = parse_header(
        "Estação, Cruzador Almirante Barroso; Observador, 2º tenente A. Silvado; "
        "Latitude, var ; Longitude, var.; Hora local, var.; Alt. do Bar., 2m,5")
    assert h["moves"] and h["lat_deg"] is None and h["lon_deg"] is None
    assert h["bar_alt_m"] == 2
