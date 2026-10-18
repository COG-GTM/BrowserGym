"""Deterministic synthetic HTML pages of a target element-node count."""

from __future__ import annotations

import html
from pathlib import Path

# size name -> target number of element nodes in the document
SIZES: dict[str, int] = {
    "small": 100,
    "medium": 2_000,
    "large": 20_000,
}

_WORDS = (
    "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike "
    "november oscar papa quebec romeo sierra tango uniform victor whiskey xray yankee zulu"
).split()

# Fixed scaffold: html, head, meta, title, style, body, header, h1, form, label, input,
# button, a, span(counter), main  -> 15 elements (script excluded, counted below)
_SCAFFOLD_NODES = 16
# Each card: section, h2, p, span, ul, li x3, label, input, button, a -> 12 elements
_CARD_NODES = 12


def _words(i: int, n: int) -> str:
    return " ".join(_WORDS[(i * 7 + k * 3) % len(_WORDS)] for k in range(n))


def _card(i: int) -> str:
    return (
        f'<section class="card" id="card-{i}">'
        f"<h2>Card {i}: {_words(i, 2)}</h2>"
        f'<p>{_words(i + 1, 8)} <span class="tag">#{i % 13}</span></p>'
        "<ul>"
        f"<li>{_words(i + 2, 3)}</li><li>{_words(i + 3, 3)}</li><li>{_words(i + 4, 3)}</li>"
        "</ul>"
        f'<label for="card-input-{i}">Note {i}</label>'
        f'<input id="card-input-{i}" type="text" value="{html.escape(_words(i, 1))}">'
        f'<button type="button" class="card-btn">Action {i}</button>'
        f'<a href="#card-{(i + 1)}">Next</a>'
        "</section>"
    )


def generate_page(target_nodes: int, title: str = "BrowserGym benchmark page") -> str:
    """Return a static HTML page with roughly ``target_nodes`` element nodes.

    The page always contains the fixed interaction targets ``#bench-input``,
    ``#bench-button`` and ``#bench-link`` used by the step benchmarks. Output is
    fully deterministic for a given ``target_nodes``.
    """
    n_cards = max(0, round((target_nodes - _SCAFFOLD_NODES) / _CARD_NODES))
    cards = "".join(_card(i) for i in range(n_cards))
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title>"
        "<style>body{font-family:sans-serif;margin:8px}"
        ".card{border:1px solid #ccc;margin:4px;padding:4px}"
        "header{position:sticky;top:0;background:#fff}</style>"
        "</head><body>"
        "<header><h1>Benchmark</h1>"
        '<form onsubmit="return false">'
        '<label for="bench-input">Query</label>'
        '<input id="bench-input" type="text" name="q">'
        '<button id="bench-button" type="button" '
        "onclick=\"var c=document.getElementById('bench-counter');"
        'c.textContent=String(Number(c.textContent)+1)">Click me</button>'
        '<a id="bench-link" href="#card-0">Top</a>'
        '<span id="bench-counter">0</span>'
        "</form></header>"
        f"<main>{cards}</main>"
        "<script>window.__bench_ready = true;</script>"
        "</body></html>"
    )


def write_pages(directory: Path, sizes: dict[str, int] | None = None) -> dict[str, Path]:
    """Write one page per size into ``directory`` and return ``{size: path}``."""
    sizes = SIZES if sizes is None else sizes
    directory.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, nodes in sizes.items():
        path = directory / f"{name}.html"
        path.write_text(generate_page(nodes, title=f"BrowserGym benchmark ({name})"), "utf-8")
        out[name] = path
    return out
