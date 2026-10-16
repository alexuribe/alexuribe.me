"""Dump an .xlsx (stdlib only): sheet names, then rows as tab-separated text."""
import re, sys, zipfile
import xml.etree.ElementTree as ET
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
z = zipfile.ZipFile(sys.argv[1])
shared = []
if "xl/sharedStrings.xml" in z.namelist():
    for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
        shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
wb = ET.fromstring(z.read("xl/workbook.xml"))
rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
target = {r.get("Id"): r.get("Target") for r in rels}
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10**9
def colnum(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group():
        n = n * 26 + ord(ch) - 64
    return n - 1
for sh in wb.find("m:sheets", NS):
    name = sh.get("name"); rid = sh.get("{%s}id" % NS["r"])
    path = "xl/" + target[rid].lstrip("/").replace("xl/", "")
    root = ET.fromstring(z.read(path))
    rows = root.findall(".//m:sheetData/m:row", NS)
    print(f"=== sheet: {name} ({len(rows)} rows)")
    for row in rows[:limit]:
        vals = {}
        for c in row.findall("m:c", NS):
            v = c.find("m:v", NS); t = c.get("t")
            if t == "s" and v is not None: val = shared[int(v.text)]
            elif t == "inlineStr": val = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
            else: val = v.text if v is not None else ""
            vals[colnum(c.get("r"))] = val or ""
        if vals:
            print("\t".join(vals.get(i, "") for i in range(max(vals) + 1)))
