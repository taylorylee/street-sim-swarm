"""CLI: OSM + zoning splines -> low-poly city (.glb), lot manifest (.geojson), preview (.png).

Examples
  # fetch live OSM for a bbox (south west north east), then build
  python -m procgen.build --bbox 37.7800 -122.4420 37.7866 -122.4255 --zones zones/fillmore.json --out out/fillmore

  # build from a local .osm / Overpass JSON file
  python -m procgen.build --osm data/fillmore.osm --zones zones/fillmore.json --out out/fillmore
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from shapely.geometry import mapping

from .generate import build_city
from .osm_parse import Projector, fetch_overpass, load_osm
from .render import render_axo
from .zoning import load_zones
from .zoning_sf import fetch_sf_zoning, load_sf_zoning


def scene_bbox(osm_path):
    from .osm_parse import _read
    nodes, _ = _read(Path(osm_path))
    la = [p[0] for p in nodes.values()]; lo = [p[1] for p in nodes.values()]
    return (min(la), min(lo), max(la), max(lo))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--osm", help=".osm XML or Overpass JSON file")
    src.add_argument("--bbox", nargs=4, type=float, metavar=("S", "W", "N", "E"))
    zsrc = ap.add_mutually_exclusive_group(required=True)
    zsrc.add_argument("--zones", help="hand-drawn zoning spline JSON")
    zsrc.add_argument("--sf-zoning", nargs="?", const="fetch", metavar="GEOJSON",
                      help="official SF zoning: a downloaded GeoJSON, or no value to fetch from DataSF")
    ap.add_argument("--out", required=True, help="output path prefix")
    ap.add_argument("--seed", default="gatherground")
    ap.add_argument("--no-infill", action="store_true", help="only extrude real OSM buildings")
    ap.add_argument("--azimuth", type=float, default=-38)
    ap.add_argument("--elevation", type=float, default=42)
    a = ap.parse_args(argv)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    osm_path = Path(a.osm) if a.osm else fetch_overpass(tuple(a.bbox), out.with_suffix(".osm.json"))

    scene = load_osm(osm_path)
    proj = Projector(*scene.origin)
    if a.zones:
        zones = load_zones(a.zones, proj)
    else:
        zpath = Path(a.sf_zoning) if a.sf_zoning != "fetch" else None
        if zpath is None:
            bbox = tuple(a.bbox) if a.bbox else scene_bbox(osm_path)
            zpath = fetch_sf_zoning(bbox, out.with_suffix(".zoning.geojson"))
        zones = load_sf_zoning(zpath, proj)
    city, inst, blocks, streets, parks = build_city(scene, zones, a.seed, not a.no_infill)

    city.export(out.with_suffix(".glb"))
    feats = [{"type": "Feature", "geometry": mapping(i.footprint),
              "properties": {"kind": i.kind, "height_m": round(i.height, 2), "zone": i.zone,
                            "height_source": i.height_source}}
             for i in inst]
    out.with_suffix(".lots.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "crs_note": f"local meters, origin {scene.origin}",
         "features": feats}))
    render_axo(city, out.with_suffix(".png"), a.azimuth, a.elevation)

    n_osm = sum(i.kind == "osm" for i in inst)
    from collections import Counter
    srcs = Counter(i.height_source for i in inst)
    print("height sources: " + ", ".join(f"{k}={v}" for k, v in srcs.items()))
    print(f"blocks={len(blocks)} osm_buildings={n_osm} procedural={len(inst) - n_osm} "
          f"faces={len(city.faces)}")
    print(f"wrote {out.with_suffix('.glb')}, {out.with_suffix('.lots.geojson')}, {out.with_suffix('.png')}")


if __name__ == "__main__":
    main()
