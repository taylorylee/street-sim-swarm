"""Write a synthetic .osm test file shaped like the Fillmore / O'Farrell grid.

Only for offline testing: real runs should use --bbox (live Overpass) or an
exported .osm file. Some lots get footprints, the rest are left empty so the
zoning-driven infill has room to work.
"""
import random
import sys

NS = [-122.44102, -122.43889, -122.43676, -122.43463, -122.4325, -122.43037, -122.42824, -122.42611]
EW = [37.7860, 37.7851, 37.7842, 37.7833, 37.7824, 37.7815, 37.7806]


def main(path):
    rnd = random.Random(7)
    nid, wid = [1], [1]
    nodes, ways = [], []

    def node(lat, lon):
        nodes.append(f'<node id="{nid[0]}" lat="{lat:.7f}" lon="{lon:.7f}"/>')
        nid[0] += 1
        return nid[0] - 1

    def way(refs, tags):
        nd = "".join(f'<nd ref="{r}"/>' for r in refs)
        tg = "".join(f'<tag k="{k}" v="{v}"/>' for k, v in tags.items())
        ways.append(f'<way id="{wid[0]}">{nd}{tg}</way>')
        wid[0] += 1

    grid = {(i, j): node(lat, lon) for i, lon in enumerate(NS) for j, lat in enumerate(EW)}
    for j in range(len(EW)):
        way([grid[(i, j)] for i in range(len(NS))], {"highway": "primary" if j == 2 else "residential"})
    for i in range(len(NS)):
        way([grid[(i, j)] for j in range(len(EW))], {"highway": "secondary" if i == 4 else "residential"})

    # a park occupying one block
    p = [node(EW[4] - 0.00012, NS[1] + 0.00015), node(EW[4] - 0.00012, NS[2] - 0.00015),
         node(EW[5] + 0.00012, NS[2] - 0.00015), node(EW[5] + 0.00012, NS[1] + 0.00015)]
    way(p + [p[0]], {"leisure": "park", "name": "Test Park"})

    # partial real footprints along a few block faces
    for i in range(len(NS) - 1):
        for j in range(len(EW) - 1):
            if rnd.random() < 0.45:
                continue
            lat_top = EW[j] - 0.00011
            lon = NS[i] + 0.00016
            while lon < NS[i + 1] - 0.00024:
                w = rnd.uniform(0.00008, 0.00014)
                d = rnd.uniform(0.00015, 0.00024)
                q = [node(lat_top, lon), node(lat_top, lon + w), node(lat_top - d, lon + w), node(lat_top - d, lon)]
                tags = {"building": "yes"}
                if rnd.random() < 0.5:
                    tags["building:levels"] = str(rnd.choice([2, 3, 3, 4]))
                way(q + [q[0]], tags)
                lon += w + 0.00001

    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6">\n'
           + "\n".join(nodes + ways) + "\n</osm>\n")
    open(path, "w").write(xml)
    print(f"wrote {path}: {len(nodes)} nodes, {len(ways)} ways")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/sample_fillmore.osm")
