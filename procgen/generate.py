"""Procedural instancing: OSM footprints + zoning splines -> low-poly city mesh.

Pipeline
  1. Streets: buffer OSM road centerlines by class width.
  2. Blocks: polygonize the space between streets.
  3. Real buildings: extrude OSM footprints (height from tags, else zone rules).
  4. Infill: carve empty block land inside zones into street-facing lots and
     instance a low-poly kit model per lot (box, stepped, parapet, gable, bay).
  5. Parks: flat olive planes with scattered low-poly trees.
All randomness is seeded per lot, so the same inputs always give the same city.
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass

import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import LineString, Polygon, box
from shapely.ops import polygonize, unary_union

from .osm_parse import OSMScene, building_height
from .palette import PALETTE, rgba
from .zoning import Zone, zone_at

ROAD_WIDTH = {"primary": 22, "secondary": 18, "tertiary": 15, "residential": 12,
              "unclassified": 11, "living_street": 8, "pedestrian": 7}
LIGHT_DIR = np.array([-0.45, -0.75, 0.48])  # sun from upper left, matches the reference
LIGHT_DIR /= np.linalg.norm(LIGHT_DIR)


@dataclass
class Instance:
    kind: str          # "osm" | kit name | "tree"
    footprint: Polygon
    height: float
    zone: str | None
    height_source: str = "procedural"  # osm_tag | zone_estimate | procedural


def _seed(*parts) -> random.Random:
    h = hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()
    return random.Random(int(h[:12], 16))


# ---------- streets and blocks ----------
def street_surface(scene: OSMScene):
    bufs = [f.geom.buffer(ROAD_WIDTH.get(f.tags.get("highway"), 10) / 2, cap_style=2)
            for f in scene.roads]
    return unary_union(bufs) if bufs else Polygon()


def city_blocks(scene: OSMScene, streets, pad: float = 0):
    lines = [f.geom for f in scene.roads]
    bounds = unary_union(lines).bounds if lines else (0, 0, 0, 0)
    frame = box(*bounds).buffer(pad)
    noded = unary_union(lines + [frame.exterior])
    blocks = []
    for p in polygonize(noded):
        b = p.difference(streets).buffer(-0.5).buffer(0.5)
        for g in getattr(b, "geoms", [b]):
            if g.area > 150:
                blocks.append(g)
    return blocks


# ---------- lot subdivision ----------
def subdivide_lots(land: Polygon, rules: dict, rng: random.Random) -> list[Polygon]:
    """Cut land into lots that face the block's long edges (row-house pattern)."""
    if land.is_empty or land.area < 40:
        return []
    mrr = land.minimum_rotated_rectangle
    xs, ys = mrr.exterior.coords.xy
    e = [(xs[i + 1] - xs[i], ys[i + 1] - ys[i]) for i in range(2)]
    long_i = 0 if math.hypot(*e[0]) >= math.hypot(*e[1]) else 1
    ang = math.degrees(math.atan2(e[long_i][1], e[long_i][0]))
    c = land.centroid
    flat = affinity.rotate(land, -ang, origin=c)
    minx, miny, maxx, maxy = flat.bounds
    lots = []
    depth_lo, depth_hi = rules["depth"]
    # two rows of lots: one facing each long street edge
    rows = [(miny, miny + min(rng.uniform(depth_lo, depth_hi), (maxy - miny) / 2)),
            (maxy - min(rng.uniform(depth_lo, depth_hi), (maxy - miny) / 2), maxy)]
    for y0, y1 in rows:
        x = minx
        while x < maxx - 3:
            w = rng.uniform(*rules["lot"])
            cell = box(x, y0, min(x + w, maxx), y1).intersection(flat)
            if not cell.is_empty and cell.area > 25:
                inset = cell.buffer(-rules["setback"] / 2 - 0.35, join_style=2)
                if not inset.is_empty and inset.area > 12:
                    inset = max(getattr(inset, "geoms", [inset]), key=lambda g: g.area)
                    lots.append(affinity.rotate(inset, ang, origin=c))
            x += w
    return lots


# ---------- low-poly kit ----------
def _extrude(poly: Polygon, h: float, z0: float = 0.0) -> trimesh.Trimesh:
    m = trimesh.creation.extrude_polygon(poly.simplify(0.15), max(h, 0.3))
    m.apply_translation([0, 0, z0])
    return m


def _gable_roof(poly: Polygon, z0: float, rise: float) -> trimesh.Trimesh:
    r = poly.minimum_rotated_rectangle
    p = np.array(r.exterior.coords)[:4]
    a, b, c, d = p
    if np.linalg.norm(b - a) < np.linalg.norm(c - b):  # ridge along long axis
        a, b, c, d = b, c, d, a
    m1, m2 = (a + d) / 2, (b + c) / 2
    v = np.array([[*a, z0], [*b, z0], [*c, z0], [*d, z0],
                  [*m1, z0 + rise], [*m2, z0 + rise]])
    f = [[0, 1, 5], [0, 5, 4], [2, 3, 4], [2, 4, 5], [1, 2, 5], [3, 0, 4]]
    return trimesh.Trimesh(v, f, process=True)


def kit_model(kind: str, lot: Polygon, h: float, rng: random.Random) -> list[trimesh.Trimesh]:
    if kind == "box":
        return [_extrude(lot, h)]
    if kind == "parapet":
        base = _extrude(lot, h)
        rim = lot.difference(lot.buffer(-0.5, join_style=2))
        return [base] + ([_extrude(rim, 0.9, h)] if not rim.is_empty else [])
    if kind == "stepped":
        top = lot.buffer(-rng.uniform(1.5, 3.0), join_style=2)
        parts = [_extrude(lot, h * rng.uniform(0.55, 0.7))]
        if not top.is_empty and top.area > 10:
            parts.append(_extrude(max(getattr(top, "geoms", [top]), key=lambda g: g.area),
                                  h * 0.4, parts[0].bounds[1][2]))
        return parts
    if kind == "gable":
        return [_extrude(lot, h), _gable_roof(lot, h, rng.uniform(1.8, 3.2))]
    if kind == "bay":
        base = _extrude(lot, h)
        bay = affinity.scale(lot, 0.45, 0.25, origin=lot.centroid).buffer(0)
        return [base, _extrude(bay, h * 0.9)] if not bay.is_empty else [base]
    return [_extrude(lot, h)]


def tree(x: float, y: float, rng: random.Random) -> trimesh.Trimesh:
    r = rng.uniform(1.2, 2.2)
    t = trimesh.creation.icosphere(subdivisions=0, radius=r)
    t.apply_scale([1, 1, rng.uniform(0.8, 1.1)])
    t.apply_translation([x, y, r + 0.4])
    return t


# ---------- shading ----------
def paint(mesh: trimesh.Trimesh, top_hex, lit_hex, dark_hex) -> trimesh.Trimesh:
    """Bake flat shading into face colors: tops, lit walls and shaded walls."""
    n = mesh.face_normals
    lam = np.clip(n @ LIGHT_DIR, 0, 1)
    top, lit, dark = (np.array(rgba(c), float) for c in (top_hex, lit_hex, dark_hex))
    wall = dark + (lit - dark) * lam[:, None]
    cols = np.where((n[:, 2] > 0.6)[:, None], top, wall)
    mesh.visual.face_colors = cols.astype(np.uint8)
    return mesh


# ---------- main ----------
def build_city(scene: OSMScene, zones: list[Zone], seed: str = "gatherground",
               fill_empty: bool = True):
    # clip roads (Overpass returns whole ways) to the built-up extent
    if scene.buildings:
        ext = unary_union([f.geom for f in scene.buildings]).envelope.buffer(25, join_style=2)
        scene.roads = [type(f)(f.geom.intersection(ext), f.tags) for f in scene.roads
                       if f.geom.intersects(ext)]
        scene.roads = [f for f in scene.roads if f.geom.geom_type == "LineString" and f.geom.length > 1]
    streets = street_surface(scene)
    blocks = city_blocks(scene, streets)
    meshes, instances = [], []

    # ground + streets
    if blocks:
        ground = unary_union(blocks).envelope.buffer(30, join_style=2)
        g = trimesh.creation.extrude_polygon(ground, 0.05)
        g.apply_translation([0, 0, -0.1])
        meshes.append(paint(g, PALETTE["ground"], PALETTE["ground"], PALETTE["ground"]))
    if not streets.is_empty:
        for s in getattr(streets, "geoms", [streets]):
            m = trimesh.creation.extrude_polygon(s, 0.05)
            m.apply_translation([0, 0, -0.06])
            meshes.append(paint(m, PALETTE["street"], PALETTE["street"], PALETTE["street"]))

    parks = unary_union([f.geom for f in scene.parks]) if scene.parks else Polygon()
    # zones marked open_space also become parks
    os_zones = [z.polygon for z in zones if z.type == "open_space"]
    if os_zones:
        parks = unary_union([parks] + [unary_union(blocks).intersection(p) for p in os_zones])

    occupied = []
    for f in scene.buildings:
        if parks.contains(f.geom.centroid):
            continue
        z = zone_at(zones, f.geom)
        h = building_height(f.tags)
        src = "osm_tag" if h is not None else "zone_estimate"
        if h is None:
            rng = _seed(seed, "osm", round(f.geom.centroid.x, 1), round(f.geom.centroid.y, 1))
            lo, hi = z.rules["height"] if z and z.type != "open_space" else (7, 12)
            h = rng.uniform(lo, hi)
        for poly in getattr(f.geom, "geoms", [f.geom]):
            if poly.geom_type != "Polygon":
                continue
            meshes.append(paint(_extrude(poly, h), PALETTE["building"],
                                PALETTE["wall_light"], PALETTE["wall_dark"]))
            instances.append(Instance("osm", poly, h, z.name if z else None, src))
        occupied.append(f.geom.buffer(1.0))
    occupied = unary_union(occupied) if occupied else Polygon()

    # procedural infill inside zones
    if fill_empty:
        for bi, blk in enumerate(blocks):
            z = zone_at(zones, blk)
            if not z or z.type == "open_space" or not z.rules["kit"]:
                continue
            land = blk.intersection(z.polygon).difference(occupied).difference(parks.buffer(1))
            for land_part in getattr(land, "geoms", [land]):
                if land_part.geom_type != "Polygon":
                    continue
                rng = _seed(seed, bi, round(land_part.area))
                for li, lot in enumerate(subdivide_lots(land_part, z.rules, rng)):
                    r = _seed(seed, bi, li, round(lot.centroid.x))
                    if r.random() > z.rules["coverage"]:
                        continue
                    kind = r.choice(z.rules["kit"])
                    h = r.uniform(*z.rules["height"])
                    for m in kit_model(kind, lot, h, r):
                        meshes.append(paint(m, PALETTE["building"],
                                            PALETTE["wall_light"], PALETTE["wall_dark"]))
                    instances.append(Instance(kind, lot, h, z.name, "procedural"))

    # parks + trees
    for pi, p in enumerate(getattr(parks, "geoms", [parks])):
        if p.is_empty or p.geom_type != "Polygon":
            continue
        pm = trimesh.creation.extrude_polygon(p, 0.12)
        meshes.append(paint(pm, PALETTE["park"], PALETTE["park"], PALETTE["park"]))
        rng = _seed(seed, "park", pi)
        n = int(p.area / 90)
        minx, miny, maxx, maxy = p.bounds
        placed = 0
        for _ in range(n * 6):
            if placed >= n:
                break
            x, y = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
            from shapely.geometry import Point
            if p.buffer(-2).contains(Point(x, y)):
                meshes.append(paint(tree(x, y, rng), PALETTE["tree"], PALETTE["tree"],
                                    PALETTE["tree_dark"]))
                placed += 1

    city = trimesh.util.concatenate(meshes)
    return city, instances, blocks, streets, parks
