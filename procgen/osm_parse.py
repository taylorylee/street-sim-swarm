"""Parse OpenStreetMap data (.osm XML or Overpass JSON) into local-meter geometry.

Outputs plain shapely geometry in a local tangent-plane frame (meters, origin at
the bbox center), so everything downstream is unit-consistent.
"""
from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from shapely.geometry import LineString, Polygon
from shapely.validation import make_valid

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
LEVEL_HEIGHT_M = 3.2


@dataclass
class Feature:
    geom: object
    tags: dict = field(default_factory=dict)


@dataclass
class OSMScene:
    buildings: list[Feature]
    parks: list[Feature]
    roads: list[Feature]
    origin: tuple[float, float]  # (lat, lon)


class Projector:
    """Equirectangular projection around an origin. Accurate to <0.1% at block scale."""

    def __init__(self, lat0: float, lon0: float):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = 111_320.0 * math.cos(math.radians(lat0))
        self.ky = 110_574.0

    def __call__(self, lat: float, lon: float) -> tuple[float, float]:
        return ((lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky)


def overpass_query(south: float, west: float, north: float, east: float) -> str:
    bb = f"{south},{west},{north},{east}"
    return (
        f"[out:json][timeout:60];("
        f'way["building"]({bb});'
        f'way["leisure"~"park|garden|playground"]({bb});'
        f'way["landuse"~"grass|recreation_ground"]({bb});'
        f'way["highway"~"primary|secondary|tertiary|residential|unclassified|living_street|pedestrian"]({bb});'
        f");out body;>;out skel qt;"
    )


def fetch_overpass(bbox: tuple[float, float, float, float], out_path: Path) -> Path:
    """Download raw OSM for (south, west, north, east) and cache it as JSON."""
    import urllib.parse
    import urllib.request

    data = urllib.parse.urlencode({"data": overpass_query(*bbox)}).encode()
    req = urllib.request.Request(OVERPASS_URL, data=data,
                                 headers={"User-Agent": "gatherground-procgen/0.1"})
    with urllib.request.urlopen(req, timeout=90) as r:
        out_path.write_bytes(r.read())
    return out_path


def _read(path: Path):
    """Return (nodes{id:(lat,lon)}, ways[(tags, [node ids])])."""
    text = path.read_text(encoding="utf-8")
    nodes, ways = {}, []
    if text.lstrip().startswith("{"):
        for el in json.loads(text)["elements"]:
            if el["type"] == "node":
                nodes[el["id"]] = (el["lat"], el["lon"])
            elif el["type"] == "way":
                ways.append((el.get("tags", {}), el["nodes"]))
    else:
        root = ET.fromstring(text)
        for n in root.iter("node"):
            nodes[int(n.get("id"))] = (float(n.get("lat")), float(n.get("lon")))
        for w in root.iter("way"):
            tags = {t.get("k"): t.get("v") for t in w.iter("tag")}
            ways.append((tags, [int(nd.get("ref")) for nd in w.iter("nd")]))
    return nodes, ways


def building_height(tags: dict, default_levels: float | None = None) -> float | None:
    """Height in meters from height / building:levels tags, else None."""
    h = tags.get("height")
    if h:
        try:
            return float(h.replace("m", "").strip())
        except ValueError:
            pass
    lv = tags.get("building:levels") or default_levels
    if lv:
        try:
            return float(lv) * LEVEL_HEIGHT_M + 1.0
        except ValueError:
            pass
    return None


def load_osm(path: str | Path) -> OSMScene:
    nodes, ways = _read(Path(path))
    if not nodes:
        raise ValueError(f"No nodes found in {path}")
    lats = [p[0] for p in nodes.values()]
    lons = [p[1] for p in nodes.values()]
    lat0, lon0 = (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2
    proj = Projector(lat0, lon0)

    buildings, parks, roads = [], [], []
    for tags, refs in ways:
        pts = [proj(*nodes[r]) for r in refs if r in nodes]
        if len(pts) < 2:
            continue
        closed = len(refs) > 3 and refs[0] == refs[-1]
        if "building" in tags and closed:
            poly = make_valid(Polygon(pts))
            if poly.area > 4:
                buildings.append(Feature(poly, tags))
        elif closed and (tags.get("leisure") in {"park", "garden", "playground"}
                         or tags.get("landuse") in {"grass", "recreation_ground"}):
            parks.append(Feature(make_valid(Polygon(pts)), tags))
        elif "highway" in tags:
            roads.append(Feature(LineString(pts), tags))
    return OSMScene(buildings, parks, roads, (lat0, lon0))
