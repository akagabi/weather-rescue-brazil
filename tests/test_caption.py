"""The caption pass must not let an ephemeris into a weather profile."""
from wrb.caption import is_astronomy, match_period, match_profile


# Read off the actual scans in data/raw/docvirt/11 (an Ephemerides volume).
EPHEMERIS = [
    "SOL.\nMARÇO DE 1855.\nAO MEIO DIA MEDIO NO RIO DE JANEIRO.",
    "MARÇO DE 1855.\nAO MEIO DIA MEDIO NO RIO DE JANEIRO.",
    "LUA.\nFEVEREIRO DE 1853.",
    "AGOSTO DE 1855.\nAO MEIO DIA MEDIO NO RIO DE JANEIRO.",
    "Tempo sideral e ascensão recta, Janeiro de 1854",
    "Observations à la lunette méridienne, Janvier 1883",
    "Passagem meridiana das estrellas, Maio de 1856",
]

WEATHER = [
    "Resumo das observações meteorologicas feitas no Imperial Observatorio "
    "no mez de Julho de 1886",
    "Observações meteorologicas de Corumbá, Setembro de 1889",
    "Observations météorologiques faites à Rio de Janeiro, Avril 1883. Baromètre",
    "Estação de Santa Cruz, Março de 1889",
    "Porto do Maranhão, Dezembro de 1886",
]


def test_ephemeris_captions_are_astronomy():
    for cap in EPHEMERIS:
        assert is_astronomy(cap), cap


def test_weather_captions_are_not_astronomy():
    for cap in WEATHER:
        assert not is_astronomy(cap), cap


def test_the_doc11_caption_no_longer_matches_a_weather_profile():
    """The exact regression: this caption was recorded as revista-rio-1886."""
    cap = "MARÇO DE 1855.\nAO MEIO DIA MEDIO NO RIO DE JANEIRO."
    assert match_profile(cap) is None


def test_weather_captions_still_match_their_profiles():
    assert match_profile(WEATHER[0]) == "revista-rio-1886"
    assert match_profile(WEATHER[1]) == "corumba-1889"
    assert match_profile(WEATHER[2]) == "revista-rio-1886"
    assert match_profile(WEATHER[3]) == "revista-santacruz-1889"
    assert match_profile(WEATHER[4]) == "porto-maranhao-1886"


def test_magnetic_declination_is_not_vetoed():
    """`declinação` alone is a real geophysical observation, not astronomy."""
    assert not is_astronomy("Declinação magnetica, Junho de 1886, Rio de Janeiro")
    assert match_profile("Declinação magnetica, Junho de 1886, Rio de Janeiro") \
        == "revista-rio-1886"


def test_period_parsing_unchanged():
    assert match_period(WEATHER[0]) == "1886-07"
    assert match_period(WEATHER[2]) == "1883-04"
    assert match_period("Resumo do mez de Julho") is None


# --- the shipped regression: "Rio de Janeiro" contains "janeiro" -------------

REAL_CAPTIONS = {
    "Observations météorologiques du mois de Mars 1883. Baromètre réduit à "
    "zéro. DE RIO DE JANEIRO": "1883-03",
    "Observations météorologiques du mois d'Avril 1883. Tempsérature "
    "centigrade. DE RIO DE JANEIRO": "1883-04",
    "Observations météorologiques du mois de Mai 1883. DE RIO DE JANEIRO": "1883-05",
    "Observations météorologiques du mois de Juillet 1883. Rio de Janeiro,"
    " tension de la vapeur": "1883-07",
    "Observations météorologiques du mois d'Août 1883. Rio de Janeiro": "1883-08",
    "DE RIO DE JANEIRO Observations météorologiques du mois d'Octobre 1882.": "1882-10",
    "Observations météorologiques du mois de Novembre 1882. De Rio de Janeiro": "1882-11",
    "Observations météorologiques du mois de Décembre 1882. Tempsérature "
    "centigrade. Rio de Janeiro": "1882-12",
    "Observations météorologiques du mois de Janvier 1882. DE RIO DE JANEIRO": "1882-01",
    "REVISTA DO OBSERVATORIO. Revista climatologica do mez de Setembro de "
    "1889 no Rio de Janeiro": "1889-09",
    "RESUMO DAS OBSERVAÇÕES METEOROLÓGICAS FEITAS EM CUYABÁ NO MEZ DE "
    "JANEIRO DE 1889": "1889-01",
}


def test_place_name_never_decides_the_month():
    for cap, want in REAL_CAPTIONS.items():
        assert match_period(cap) == want, cap


def test_two_months_named_without_an_of_phrase_is_unidentified():
    """Guessing a date is worse than declaring the page unidentified."""
    assert match_period("Maio e Junho de 1886, Rio de Janeiro") is None


def test_two_months_resolve_by_the_of_phrase():
    assert match_period(
        "Observações do mez de Agosto de 1886; comparar com Julho") == "1886-08"


def test_the_moons_geometry_is_astronomy_too():
    """docId 15 page 87 reached the triage as an unidentified weather table."""
    for cap in ["APOGEO, PERIGEO E SEMI-DIAMETRO DA LUA. Perigeo.",
                "DISTANCIAS LUNARES. SETEMBRO DE 1853.",
                "Phases de la lune, Janvier 1883",
                "Fases da Lua - Março de 1889"]:
        assert is_astronomy(cap), cap
    assert match_profile("APOGEO, PERIGEO E SEMI-DIAMETRO DA LUA") is None


def test_a_diameter_that_is_not_the_moons_is_not_vetoed():
    assert not is_astronomy("Diametro do pluviometro, Rio de Janeiro, Maio de 1886")


# --- the Annales caption cannot name its own sheet --------------------------

from wrb.caption import is_annales  # noqa: E402

ANNALES_CAPTIONS = [
    "Observations météorologiques du mois de Septembre 1883 DE RIO DE JANEIRO",
    "Observations météorologiques du mois de Juin 1883",
    "Observations météorologiques do mois de Mars 1883",
    "Observations météorologiques du mois d'Août 1883. Rio de Janeiro",
]


def test_an_annales_caption_matches_no_profile():
    """It was handing them revista-rio-1886 - a Portuguese daily layout from a
    different publication, whose columns are not these columns."""
    for cap in ANNALES_CAPTIONS:
        assert is_annales(cap), cap
        assert match_profile(cap) is None, cap


def test_the_period_still_comes_out_of_it():
    """The month is the one thing the caption CAN say."""
    assert match_period(ANNALES_CAPTIONS[0]) == "1883-09"
    assert match_period(ANNALES_CAPTIONS[2]) == "1883-03"


def test_the_revista_captions_are_untouched():
    for cap, want in [
        ("Resumo das observações meteorologicas feitas no Imperial Observatorio "
         "no mez de Julho de 1886", "revista-rio-1886"),
        ("Observações meteorologicas de Corumbá, Setembro de 1889", "corumba-1889"),
    ]:
        assert not is_annales(cap)
        assert match_profile(cap) == want
