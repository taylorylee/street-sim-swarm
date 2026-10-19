# sim swarm

<img width="2016" height="1356" alt="fillmore-preview" src="https://github.com/user-attachments/assets/dbe7b98b-8ff2-4508-b692-d2a043b9a74a" />

A place twin of San Francisco's busiest permitted event block: **O'Farrell Street between Fillmore and Steiner** (Fillmore Farmers Market, 64 scheduled market days in current SFMTA permits). It combines real buildings and official zoning with an agent-based foot-traffic model to show how a gathering changes a block.

https://github.com/user-attachments/assets/27048955-93ff-409f-8c42-bee898c4512d

## What's in here
| Path | What it does |
|---|---|
| `procgen/` | Python pipeline: OSM + zoning -> low-poly city (.glb), lot manifest (.geojson), preview (.png) |
| `web/index.html` | Place twin + block impact report (three.js): traffic, spillover, data-source layers |
| `web/model-viewer/` | Simple orbit viewer for any generated .glb |
| `data/` | Fillmore-area OSM extract and DataSF zoning used for the example |

## Quick start
```bash
pip install -r requirements.txt

# 1. Build the city (real OSM + official SF zoning)
python -m procgen.build --osm data/fillmore_real.osm.json --sf-zoning data/fillmore_zoning.geojson --out out/fillmore

# 2. Export for the web twin
python -m procgen.export_web --osm data/fillmore_real.osm.json --lots out/fillmore.lots.geojson \
  --event "O'Farrell Street" "Fillmore Street" "Steiner Street" --out web/city.json

# 3. View
python -m http.server 8000      # then open http://localhost:8000/web/
```
Any other SF area: replace `--osm ...` with `--bbox S W N E` and `--sf-zoning` with no value to fetch both live. Use `--zones procgen/zones/fillmore.json` for hand-drawn zoning splines (sketching, non-SF cities). Add `--no-infill` to show only real buildings.

## Pipeline
1. **Parse OSM** (`osm_parse.py`): buildings, parks, roads, projected to local meters.
2. **Zoning** (`zoning_sf.py`, `zoning.py`): official DataSF districts mapped to generator rules, or Catmull-Rom zoning splines.
3. **Generate** (`generate.py`): street surfaces, blocks, extruded OSM footprints, lot subdivision of empty land, low-poly kit (box, stepped, parapet, gable, bay), park trees. Seeded and deterministic.
4. **Simulate** (`web/index.html`): 1,500 cohort agents, gravity-model destinations, street-network routing, hourly activity curve; market day vs. normal Saturday.

## What is real vs. estimated
| Layer | Status | Source |
|---|---|---|
| Building footprints | Real | OpenStreetMap |
| Building heights | Real where tagged, otherwise estimated from zoning | OSM tags / DataSF zoning |
| Infill buildings | **Not real** (procedural, shown grey-olive) | Generator |
| Zoning | Real | DataSF Zoning Districts (3i4a-hu95) |
| Event block and days | Real | SFMTA Temporary Street Closures (7p5y-sxmu) |
| Foot traffic, spillover | **Estimated**, not yet calibrated | Agent model |

Every building in `*.lots.geojson` carries `height_source`: `osm_tag`, `zone_estimate`, or `procedural`.

## Privacy
Agents are aggregate cohorts, never individuals. No personal data is collected or modeled.

See `DATA_SOURCES.md` for attribution.

