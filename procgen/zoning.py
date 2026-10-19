"""Zoning splines: smooth Catmull-Rom centerlines buffered into zone polygons.

A zone is defined by a few control points plus a width. Each zone carries rules
(height range, lot size, setback, coverage, building kit) that drive generation.
Zones are defined in JSON in lat/lon, so they can be drawn on any map.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

# Rules per zone type. Heights in meters, lot sizes in meters.
ZONE_RULES = {
    "neighborhood_commercial": dict(height=(9, 16), lot=(8, 14), depth=(24, 36),
                                    setback=0.0, coverage=0.95,
                                    kit=["box", "stepped", "parapet"]),
    "residential_house": dict(height=(7, 11), lot=(7, 10), depth=(22, 34),
                              setback=2.5, coverage=0.9,
                              kit=["gable", "box", "bay"]),
    "residential_mixed": dict(height=(10, 22), lot=(10, 18), depth=(24, 38),
                              setback=1.0, coverage=0.90,
                              kit=["box", "stepped", "bay", "parapet"]),
    "civic": dict(height=(8, 14), lot=(25, 45), depth=(25, 45),
                  setback=4.0, coverage=0.70, kit=["box", "stepped"]),
    "open_space": dict(height=(0, 0), lot=(0, 0), depth=(0, 0),
                       setback=0.0, coverage=0.0, kit=[]),
}


def catmull_rom(points: np.ndarray, samples_per_seg: int = 16, alpha: float = 0.5) -> np.ndarray:
    """Centripetal Catmull-Rom through all control points (no overshoot or cusps)."""
    p = np.asarray(points, dtype=float)
    if len(p) < 3:
        return p
    p = np.vstack([2 * p[0] - p[1], p, 2 * p[-1] - p[-2]])
    out = []
    for i in range(len(p) - 3):
        p0, p1, p2, p3 = p[i:i + 4]
        t0 = 0.0
        t1 = t0 + np.linalg.norm(p1 - p0) ** alpha + 1e-9
        t2 = t1 + np.linalg.norm(p2 - p1) ** alpha + 1e-9
        t3 = t2 + np.linalg.norm(p3 - p2) ** alpha + 1e-9
        for t in np.linspace(t1, t2, samples_per_seg, endpoint=False):
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    out.append(p[-2])
    return np.array(out)


@dataclass
class Zone:
    name: str
    type: str
    polygon: Polygon
    centerline: LineString | None = None
    priority: int = 0

    @property
    def rules(self) -> dict:
        r = dict(ZONE_RULES[self.type])
        h = getattr(self, "height_override", None)
        if h and h[1] > 0:
            r["height"] = h
        return r


def zone_from_spline(name, ztype, ctrl_xy, width_m, closed=False, priority=0) -> Zone:
    pts = catmull_rom(np.asarray(ctrl_xy), samples_per_seg=20)
    if closed:  # closed spline = smooth area boundary
        poly = Polygon(pts).buffer(0)
        return Zone(name, ztype, poly, poly.exterior, priority)
    line = LineString(pts)
    return Zone(name, ztype, line.buffer(width_m / 2, cap_style=2, join_style=1), line, priority)


def load_zones(path: str | Path, projector) -> list[Zone]:
    """JSON: {"zones":[{"name","type","width_m","closed","priority","points":[[lat,lon],...]}]}"""
    spec = json.loads(Path(path).read_text())
    zones = []
    for z in spec["zones"]:
        xy = [projector(lat, lon) for lat, lon in z["points"]]
        zones.append(zone_from_spline(z["name"], z["type"], xy, z.get("width_m", 60),
                                      z.get("closed", False), z.get("priority", 0)))
    return sorted(zones, key=lambda z: -z.priority)


def zone_at(zones: list[Zone], geom) -> Zone | None:
    """Highest-priority zone containing the geometry's centroid."""
    c = geom.centroid
    for z in zones:
        if z.polygon.contains(c):
            return z
    return None


def zones_union(zones):
    return unary_union([z.polygon for z in zones])
