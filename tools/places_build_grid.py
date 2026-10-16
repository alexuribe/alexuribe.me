"""Build a compact dot-matrix world for the places background.

Inputs: world-atlas countries-50m.json (TopoJSON, lon/lat), places.json.
Output JSON:
  step, lon0, lat1 (grid origin), cols, rows,
  land:    [[col, row, visited 0/1], ...]
  photos:  [[col, row, level 1..4], ...]   cells that hold photos, by log count
  home:    [col, row]
"""
import json
import math
import sys

topo_path, places_path, out = sys.argv[1:4]
STEP = 1.5
LON0, LON1, LAT0, LAT1 = -180.0, 180.0, -56.0, 78.0

# ISO 3166 alpha-2 -> numeric ids used by world-atlas
ISO_NUM = {"US": "840", "MX": "484", "GT": "320", "CA": "124", "CN": "156", "GB": "826", "FR": "250",
           "DE": "276", "IT": "380", "ES": "724", "CH": "756", "CR": "188", "AR": "032", "HU": "348",
           "HK": "344", "GR": "300", "SK": "703", "IS": "352", "IN": "356", "NL": "528",
           "NP": "524", "AT": "040", "CL": "152", "PE": "604", "CZ": "203"}

# Places the GeoNames match missed, placed by hand (0.1 degree is plenty here).
MANUAL = {
    ("US", "Washington, D.C."): (-77.0, 38.9), ("US", "North Atlanta"): (-84.3, 33.9),
    ("US", "Waikoloa Village"): (-155.8, 19.9), ("US", "Saint Petersburg"): (-82.6, 27.8),
    ("IT", "Milano"): (9.2, 45.5), ("US", "Borough of Queens"): (-73.8, 40.7),
    ("HU", "Budapest IX. keruelet"): (19.1, 47.5), ("MX", "Cuajimalpa"): (-99.3, 19.4),
    ("US", "Fort Lewis"): (-122.6, 47.1), ("US", "Sandy City"): (-111.9, 40.6),
    ("CN", "Zhonghuping"): (110.5, 29.3), ("ES", "City Center"): (-3.7, 40.4),
    ("CA", "Lake Louise"): (-116.2, 51.4), ("MX", "San Miguel de Cozumel"): (-86.9, 20.5),
    ("CN", "Wangcun"): (109.9, 28.9),
}

topo = json.load(open(topo_path))
sx, sy = topo["transform"]["scale"]
tx, ty = topo["transform"]["translate"]
arcs = []
for arc in topo["arcs"]:
    x = y = 0
    pts = []
    for dx, dy in arc:
        x += dx
        y += dy
        pts.append((x * sx + tx, y * sy + ty))
    arcs.append(pts)


def ring(idx):
    pts = []
    for i in idx:
        a = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts.extend(a if not pts else a[1:])
    return pts


def unwrap(pts):
    # Rings that cross the antimeridian jump from +180 to -180. Shift the western
    # side by +360 so the ring is continuous; country_at also tests lon + 360.
    if max(p[0] for p in pts) - min(p[0] for p in pts) > 180:
        return [(x + 360 if x < 0 else x, y) for x, y in pts]
    return pts


countries = []  # (id, [(bbox, outer, holes)])
for g in topo["objects"]["countries"]["geometries"]:
    if g.get("arcs") is None:
        continue
    polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
    shapes = []
    for poly in polys:
        rings = [unwrap(ring(r)) for r in poly]
        outer = rings[0]
        xs = [p[0] for p in outer]
        ys = [p[1] for p in outer]
        shapes.append(((min(xs), min(ys), max(xs), max(ys)), outer, rings[1:]))
    countries.append((str(g.get("id")), shapes))


def inside(px, py, pts):
    hit = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            hit = not hit
        j = i
    return hit


def country_at(lon, lat):
    for cid, shapes in countries:
        for (x0, y0, x1, y1), outer, holes in shapes:
            for x in (lon, lon + 360):
                if x0 <= x <= x1 and y0 <= lat <= y1 and inside(x, lat, outer) and not any(inside(x, lat, h) for h in holes):
                    return cid
    return None


visited_ids = {ISO_NUM[c] for c in json.load(open(places_path))["countries"] if c in ISO_NUM}
cols = int((LON1 - LON0) / STEP)
rows = int((LAT1 - LAT0) / STEP)
land = {}
for r in range(rows):
    lat = LAT1 - (r + 0.5) * STEP
    for c in range(cols):
        lon = LON0 + (c + 0.5) * STEP
        cid = country_at(lon, lat)
        if cid:
            land[(c, r)] = 1 if cid in visited_ids else 0


def cell(lon, lat):
    return (min(cols - 1, max(0, int((lon - LON0) / STEP))), min(rows - 1, max(0, int((LAT1 - lat) / STEP))))


data = json.load(open(places_path))
for cc, region, place, n in data.get("misses", []):
    if (cc, place) in MANUAL:
        lon, lat = MANUAL[(cc, place)]
        data["places"].append([lon, lat, n, cc, 0, 0])
    else:
        print("still unplaced:", cc, place, n)
weights = {}
for lon, lat, n, cc, *_ in data["places"]:
    k = cell(lon, lat)
    weights[k] = weights.get(k, 0) + n
# small countries the grid missed still get their dot
for k in weights:
    land.setdefault(k, 1)
    land[k] = 1


def level(n):
    return 1 if n < 10 else 2 if n < 100 else 3 if n < 1000 else 4


home = cell(-122.33, 47.61)
json.dump({
    "step": STEP, "lon0": LON0, "lat1": LAT1, "cols": cols, "rows": rows,
    "land": [[c, r, v] for (c, r), v in sorted(land.items())],
    "photos": [[c, r, level(n)] for (c, r), n in sorted(weights.items())],
    "home": list(home),
}, open(out, "w"), separators=(",", ":"))
print(f"grid {cols}x{rows}; land dots {len(land)} (visited {sum(land.values())}); photo cells {len(weights)}")
