# scripts/check_access.py
"""Fetch and print robots.txt and terms pages for the sources we intend to script. R$0, read-only."""
import httpx

TARGETS = [
    "https://memoria.bn.gov.br/robots.txt",
    "https://bndigital.bn.gov.br/perguntas-e-respostas/",
    "https://docvirt.com/robots.txt",
]
for url in TARGETS:
    r = httpx.get(url, timeout=30, follow_redirects=True,
                  headers={"User-Agent": "WeatherRescueBrazil/0.1 (research; contact: gabesuit@gmail.com)"})
    print(f"=== {url} [{r.status_code}] ===")
    print(r.text[:4000])
