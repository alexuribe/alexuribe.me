"""Read the v4 Photo locations dump into places.json for build_world.py.

Uses the workbook's own website guidance:
- Cities rows where "Include in my map?" is Yes (lat/lon given)
- Trips and cities rows where Precision is "place" or "area (approx)"
- Countries = the Visited countries sheet
Output: {"countries": [codes], "places": [[lon, lat, photos, cc, source], ...], "misses": []}
"""
import json
import sys

dump, out = sys.argv[1:3]
# Alex confirmed these were not his trips (photos sent by others).
NOT_VISITED = {"IS", "SK"}
sections, cur = {}, None
for line in open(dump, encoding="utf-8"):
    line = line.rstrip("\n")
    if line.startswith("=== sheet: "):
        cur = line[11:].split(" (")[0]
        sections[cur] = []
    elif cur:
        sections[cur].append(line.split("\t"))


def table(name):
    rows = sections[name]
    head = rows[0]
    return [dict(zip(head, r + [""] * (len(head) - len(r)))) for r in rows[1:]]


visited = {}
for r in table("Visited countries"):
    code = r["Code"].strip()
    if len(code) == 2 and code.isalpha() and code not in NOT_VISITED:
        visited[r["Country"].strip()] = code

places, gps_n, album_n, skipped = [], 0, 0, []
for r in table("Cities"):
    if r.get("Include in my map?", "").strip() != "Yes":
        continue
    try:
        lat, lon, n = float(r["Latitude"]), float(r["Longitude"]), int(float(r["Photos"]))
    except ValueError:
        skipped.append(("city", r.get("Nearest place")))
        continue
    if r["Country code"] in NOT_VISITED:
        continue
    places.append([round(lon, 1), round(lat, 1), n, r["Country code"], "gps"])
    gps_n += n

for r in table("Trips and cities"):
    if r.get("Precision", "").strip() not in ("place", "area (approx)"):
        continue
    cc = visited.get(r["Country"].strip())
    try:
        lat, lon, n = float(r["Latitude"]), float(r["Longitude"]), int(float(r["Photos (unique)"]))
    except ValueError:
        skipped.append(("trip", r.get("Place")))
        continue
    places.append([round(lon, 1), round(lat, 1), n, cc or "", "album"])
    album_n += n

json.dump({"countries": sorted(visited.values()), "places": places, "misses": []}, open(out, "w"))
print(f"visited countries: {len(visited)} {sorted(visited.values())}")
print(f"places: {len(places)} (gps photos {gps_n}, album photos {album_n}); skipped rows: {skipped}")
