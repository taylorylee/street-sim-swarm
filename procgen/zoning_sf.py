"""Official San Francisco zoning from DataSF ("Zoning Map - Zoning Districts", id 3i4a-hu95).

Fields used: zoning_sim (simplified code, e.g. "NCT-3"), districtna (full name),
gen (general category), the_geom (MultiPolygon, WGS84).
Dataset page: https://data.sf.gov/d/3i4a-hu95
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import transform
from shapely.validation import make_valid

from .zoning import Zone

SODA_URL = "https://data.sf.gov/resource/3i4a-hu95.geojson"

# Zoning code -> (generator zone type, typical built height range in meters).
# Heights are typical for the district, not legal limits; legal limits live in the
# separate Height and Bulk Districts layer.
CODE_RULES = [
    (r"^P$",           "open_space",              (0, 0)),
    (r"^RH-1",         "residential_house",       (7, 10)),
    (r"^RH-2",         "residential_house",       (8, 12)),
    (r"^RH-3",         "residential_house",       (9, 13)),
    (r"^RM-1",         "residential_mixed",       (9, 13)),
    (r"^RM-2",         "residential_mixed",       (10, 16)),
    (r"^RM-[34]",      "residential_mixed",       (13, 24)),
    (r"^RTO",          "residential_mixed",       (10, 16)),
    (r"^RC",           "residential_mixed",       (13, 26)),
    (r"^NC-1|^NCT-1",  "neighborhood_commercial", (8, 12)),
    (r"^NC-2|^NCT-2",  "neighborhood_commercial", (9, 14)),
    (r"^NC-3|^NCT-3",  "neighborhood_commercial", (11, 20)),
    (r"^NC|^NCT|^NCD", "neighborhood_commercial", (9, 16)),
    (r"^C-3",          "residential_mixed",       (25, 80)),
    (r"^C-2|^C-M",     "neighborhood_commercial", (10, 20)),
    (r"^JTN|^JAPAN",   "civic",                   (9, 18)),
]
DEFAULT_RULE = ("residential_mixed", (9, 16))


def classify(code: str) -> tuple[str, tuple[float, float]]:
    code = (code or "").upper().strip()
    for pat, ztype, h in CODE_RULES:
        if re.search(pat, code):
            return ztype, h
    return DEFAULT_RULE


def fetch_sf_zoning(bbox: tuple[float, float, float, float], out_path: Path) -> Path:
    """Download zoning polygons intersecting (south, west, north, east) as GeoJSON."""
    s, w, n, e = bbox
    wkt = f"POLYGON(({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))"
    q = urllib.parse.urlencode({"$where": f"intersects(the_geom, '{wkt}')", "$limit": 5000})
    req = urllib.request.Request(f"{SODA_URL}?{q}", headers={"User-Agent": "gatherground-procgen/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out_path.write_bytes(r.read())
    return out_path


def load_sf_zoning(path: str | Path, projector) -> list[Zone]:
    gj = json.loads(Path(path).read_text())
    proj = lambda x, y, z=None: projector(y, x)  # GeoJSON is (lon, lat)
    zones = []
    for f in gj["features"]:
        if not f.get("geometry"):
            continue
        p = f.get("properties", {})
        code = p.get("zoning_sim") or p.get("zoning") or ""
        ztype, h = classify(code)
        poly = make_valid(transform(proj, shape(f["geometry"])))
        z = Zone(name=f"{code} ({p.get('districtna', '').title()})".strip(), type=ztype,
                 polygon=poly, priority=0)
        z.height_override = h
        z.code = code
        zones.append(z)
    return zones
