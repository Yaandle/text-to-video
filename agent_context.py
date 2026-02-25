"""
agent_context.py
----------------
Provides the selection agent with full context on available animation
components and picks the right one given a parsed data section.

Used by animation_visualiser.py. Will be replaced by an LLM call in a
future iteration — for now the logic is rule-based and deterministic,
using the same rules declared in component_catalogue.json so the two
stay in sync.
"""

import json
import os
import re
from typing import Optional

# ---------------------------------------------------------------------------
# Catalogue loading
# ---------------------------------------------------------------------------

_CATALOGUE_PATH = os.path.join(os.path.dirname(__file__), "component_catalogue.json")
_catalogue: Optional[dict] = None


def load_catalogue() -> dict:
    """Load and cache the component catalogue from disk."""
    global _catalogue
    if _catalogue is None:
        with open(_CATALOGUE_PATH, "r", encoding="utf-8") as f:
            _catalogue = json.load(f)
    return _catalogue


def get_component_by_id(component_id: str) -> Optional[dict]:
    """Return a single component entry by its id field."""
    cat = load_catalogue()
    for comp in cat["components"]:
        if comp["id"] == component_id:
            return comp
    return None


def list_components() -> list[dict]:
    """Return all component entries."""
    return load_catalogue()["components"]


# ---------------------------------------------------------------------------
# Data-string parsing helpers
# ---------------------------------------------------------------------------

def parse_data_string(component_id: str, data_string: str) -> dict:
    """
    Parse the marker data string into a structured dict ready to pass to
    the Node renderer as JSON.

    Each component has its own format; this dispatcher routes to the
    correct parser.
    """
    data_string = data_string.strip()
    parsers = {
        "line_animated":    _parse_line_data,
        "scatter_animated": _parse_scatter_data,
        "pie_animated":     _parse_pie_data,
    }
    parser = parsers.get(component_id)
    if parser is None:
        raise ValueError(f"No parser registered for component '{component_id}'")
    return parser(data_string)


def _kv_pairs(data_string: str) -> dict:
    """
    Naive key:value splitter that handles values containing '|' or ','
    by splitting only on the first ':' per token.

    Tokens are split on comma ONLY when the comma is between top-level keys,
    not inside a series value.  We do a simple pass: split on ',<word>+:'
    boundaries using regex.
    """
    # Split on boundaries where a comma precedes a word followed by ':'
    tokens = re.split(r',(?=[a-zA-Z_][a-zA-Z0-9_]*:)', data_string)
    result = {}
    for token in tokens:
        idx = token.index(':')
        key = token[:idx].strip()
        val = token[idx+1:].strip()
        result[key] = val
    return result


def _parse_line_data(data_string: str) -> dict:
    """
    Format: title:<title>,x:<x1>|<x2>|...,
            series1:<label>:<v1>|<v2>|...,
            series2:<label>:<v1>|<v2>|...   (optional)
    """
    kv = _kv_pairs(data_string)
    result = {
        "title": kv.get("title", ""),
        "theme": kv.get("theme", "dark"),
        "yAxisLabel": kv.get("yAxisLabel", ""),
        "xAxis": kv["x"].split("|"),
        "series": [],
    }
    for key in ("series1", "series2"):
        if key in kv:
            parts = kv[key].split(":", 1)
            label = parts[0]
            values = [float(v) for v in parts[1].split("|")]
            result["series"].append({"label": label, "data": values})
    return result


def _parse_scatter_data(data_string: str) -> dict:
    """
    Format: title:<title>,xlabel:<label>,ylabel:<label>,
            series1:<label>:<x1>,<y1>|<x2>,<y2>|...,
            series2:...  (optional)
    """
    kv = _kv_pairs(data_string)
    result = {
        "title": kv.get("title", ""),
        "theme": kv.get("theme", "dark"),
        "xAxisLabel": kv.get("xlabel", ""),
        "yAxisLabel": kv.get("ylabel", ""),
        "series": [],
    }
    for key in ("series1", "series2", "series3"):
        if key in kv:
            parts = kv[key].split(":", 1)
            label = parts[0]
            points = []
            for pair in parts[1].split("|"):
                x_str, y_str = pair.split(",")
                points.append({"x": float(x_str), "y": float(y_str)})
            result["series"].append({"label": label, "data": points})
    return result


def _parse_pie_data(data_string: str) -> dict:
    """
    Format: title:<title>,variant:<pie|donut>,data:<label>:<val>,<label>:<val>,...
    """
    kv = _kv_pairs(data_string)
    raw_data = kv.get("data", "")
    # data segment uses comma-separated label:value pairs
    segments = []
    for item in raw_data.split(","):
        item = item.strip()
        if ":" in item:
            lbl, val = item.rsplit(":", 1)
            segments.append({"label": lbl.strip(), "value": float(val.strip())})
    return {
        "title": kv.get("title", ""),
        "theme": kv.get("theme", "dark"),
        "variant": kv.get("variant", "donut"),
        "data": segments,
    }


# ---------------------------------------------------------------------------
# Component selection agent
# ---------------------------------------------------------------------------

# Heuristic signals used to route to the correct chart type
_TIME_WORDS = re.compile(
    r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|'
    r'january|february|march|april|june|july|august|september|october|november|december|'
    r'q1|q2|q3|q4|20\d\d|19\d\d|month|year|quarter|week|day)\b',
    re.IGNORECASE,
)
_PROPORTION_WORDS = re.compile(
    r'\b(share|percent|%|proportion|allocation|breakdown|split|distribution|'
    r'budget|portion|segment|slice)\b',
    re.IGNORECASE,
)
_CORRELATION_WORDS = re.compile(
    r'\b(vs|versus|correlation|relationship|scatter|compared to|against|'
    r'spend|return|impact|effect)\b',
    re.IGNORECASE,
)


def select_component(section_text: str, data_string: str) -> str:
    """
    Given the surrounding narrative text and raw data string from a marker,
    return the best component_id from the catalogue.

    This implements the rule set declared in component_catalogue.json
    agent_selection_rules so the two stay in sync.

    In a future iteration this function will call an LLM with the full
    catalogue as context instead of running heuristics.

    Returns a component_id string.
    """
    combined = f"{section_text} {data_string}"

    # R2: bivariate correlation → scatter
    if _CORRELATION_WORDS.search(combined):
        return "scatter_animated"

    # R3: proportional / part-of-whole → pie
    if _PROPORTION_WORDS.search(combined):
        return "pie_animated"

    # R1: time axis detected → line
    if _TIME_WORDS.search(combined):
        return "line_animated"

    # R5: default fallback
    return "line_animated"


def resolve_animation(
    section_text: str,
    data_string: str,
    explicit_component_id: Optional[str] = None,
) -> tuple[str, dict, dict]:
    """
    Main entry point for animation_visualiser.py.

    Parameters
    ----------
    section_text        : The narrative text surrounding the marker.
    data_string         : Raw data string extracted from inside the marker.
    explicit_component_id : If the marker specifies a component directly
                            (e.g. [VisualiseAnimation:pie_animated]) this
                            overrides auto-selection.

    Returns
    -------
    component_id    : The selected component identifier.
    component_meta  : Full component entry from the catalogue.
    parsed_data     : Structured data dict ready to pass to the renderer.
    """
    cat = load_catalogue()

    # Select component
    if explicit_component_id and explicit_component_id != "auto":
        component_id = explicit_component_id
    else:
        component_id = select_component(section_text, data_string)

    component_meta = get_component_by_id(component_id)
    if component_meta is None:
        raise ValueError(
            f"Component '{component_id}' not found in catalogue. "
            f"Available: {[c['id'] for c in cat['components']]}"
        )

    parsed_data = parse_data_string(component_id, data_string)

    return component_id, component_meta, parsed_data


# ---------------------------------------------------------------------------
# CLI helper — print catalogue summary for prompt drafting
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cat = load_catalogue()
    print(f"\n{'='*60}")
    print("ANIMATION COMPONENT CATALOGUE")
    print(f"{'='*60}")
    for comp in cat["components"]:
        print(f"\n  [{comp['id']}]  {comp['display_name']}")
        print(f"  Library : {comp['library']}")
        print(f"  Best for: {', '.join(comp['best_for'][:2])} ...")
        print(f"  Example : {comp['data_string_example'][:60]}...")
    print(f"\n{'='*60}")
    print("MARKER SYNTAX")
    print(f"{'='*60}")
    print(f"  {cat['marker_syntax']}")
    print(f"\n  Auto-select:  [VisualiseAnimation:auto] <data> [/VisualiseAnimation]")
    print(f"  Explicit:     [VisualiseAnimation:pie_animated] <data> [/VisualiseAnimation]")
    print()