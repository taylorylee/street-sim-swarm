"""Export a built city to web/city.json for the place-twin viewer.

  python -m procgen.export_web --osm data/fillmore_real.osm.json --lots out/fillmore.lots.geojson \
      --event "O'Farrell Street" "Fillmore Street" "Steiner Street" --out web/city.json

--event names the event street and the two cross streets that bound the event block.
"""
import argparse
import json

from shapely.geometry import LineString, shape
from shapely.ops import unary_union

from .osm_parse import load_osm


def ring(geom):
    g = shape(geom)
    g = max(getattr(g, "geoms", [g]), key=lambda x: x.area)
    return [[round(x, 1), round(y, 1)] for x, y in list(g.exterior.coords)[:-1]]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--osm", required=True)
    ap.add_argument("--lots", required=True, help="*.lots.geojson from procgen.build")
    ap.add_argument("--event", nargs=3, metavar=("STREET", "CROSS_A", "CROSS_B"), required=True)
    ap.add_argument("--out", default="web/city.json")
    a = ap.parse_args(argv)

    sc = load_osm(a.osm)
    lots = json.load(open(a.lots))
    buildings = [{"p": ring(f["geometry"]), "h": round(f["properties"]["height_m"], 1),
                  "s": f["properties"]["height_source"][0],
                  "z": (f["properties"]["zone"] or "").split(" ")[0]} for f in lots["features"]]
    ext = unary_union([f.geom for f in sc.buildings]).envelope.buffer(25, join_style=2)
    roads = []
    for f in sc.roads:
        g = f.geom.intersection(ext)
        for line in getattr(g, "geoms", [g]):
            if line.geom_type == "LineString" and line.length > 1:
                roads.append({"n": f.tags.get("name", ""),
                              "c": [[round(x, 1), round(y, 1)] for x, y in line.coords]})
    parks = []
    for f in sc.parks:
        for p in getattr(f.geom, "geoms", [f.geom]):
            if p.geom_type == "Polygon":
                parks.append([[round(x, 1), round(y, 1)] for x, y in list(p.exterior.coords)[:-1]])

    def street(name):
        return unary_union([LineString(r["c"]) for r in roads if r["n"] == name])

    main_st, xa, xb = (street(n) for n in a.event)
    pa, pb = main_st.intersection(xa).centroid, main_st.intersection(xb).centroid
    if pa.is_empty or pb.is_empty:
        raise SystemExit("Event streets do not intersect inside this area; check the names.")
    out = {"buildings": buildings, "roads": roads, "parks": parks,
           "event": [[round(pa.x, 1), round(pa.y, 1)], [round(pb.x, 1), round(pb.y, 1)]],
           "event_street": a.event[0]}
    json.dump(out, open(a.out, "w"), separators=(",", ":"))
    print(f"wrote {a.out}: {len(buildings)} buildings, {len(roads)} road segments")


if __name__ == "__main__":
    main()
