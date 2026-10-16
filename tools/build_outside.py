"""Build outside/index.html from a Strava export's activities.csv.

Usage: python3 -I tools/build_outside.py ~/Downloads/export_XXXX/activities.csv [~/Downloads/ticks.csv]

Only yearly hour totals per activity family and a few lifetime totals end up in
the page. No names, notes, dates of single activities, or locations are used.
"""
import csv
import html
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NBSP = " "

# Strava activity type -> family shown on the page. Indoor types are left out.
FAMILIES = [
    ("Hiking", {"Hike"}),
    ("Running", {"Run", "Trail Run"}),
    ("Climbing", {"Rock Climb"}),
    ("Skiing", {"Alpine Ski", "Backcountry Ski", "Nordic Ski", "Snowboard"}),
    ("Biking", {"Ride", "E-Bike Ride", "Gravel Ride", "Mountain Bike Ride"}),
    ("Walking", {"Walk"}),
    ("Water", {"Kayaking", "Stand Up Paddling", "Rowing", "Swim", "Canoeing"}),
]
EVEREST_M = 8849


def _great_circle_km(a, b):
    (la1, lo1), (la2, lo2) = [(math.radians(x), math.radians(y)) for x, y in (a, b)]
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


SEATTLE_MIAMI_KM = _great_circle_km((47.61, -122.33), (25.76, -80.19))
FAMILY_OF = {t: name for name, types in FAMILIES for t in types}


def load(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header, data = rows[0], rows[1:]

    def col(name, nth=0):
        return [i for i, h in enumerate(header) if h == name][nth]

    i_date, i_type, i_moving = col("Activity Date"), col("Activity Type"), col("Moving Time")
    i_dist, i_elev = col("Distance", 1), col("Elevation Gain")  # 2nd Distance is meters
    out = []
    for r in data:
        fam = FAMILY_OF.get(r[i_type])
        if not fam:
            continue
        when = None
        for fmt in ("%b %d, %Y, %I:%M:%S %p", "%b %d, %Y, %H:%M:%S"):
            try:
                when = datetime.strptime(r[i_date], fmt)
                break
            except ValueError:
                pass
        if not when:
            continue

        def num(v):
            try:
                return float(v)
            except ValueError:
                return 0.0

        out.append((when, fam, num(r[i_moving]) / 3600, num(r[i_dist]) / 1000, num(r[i_elev])))
    return out


def build(acts):
    years = list(range(min(a[0].year for a in acts), max(a[0].year for a in acts) + 1))
    hours = defaultdict(lambda: defaultdict(float))
    for when, fam, h, _, _ in acts:
        hours[fam][when.year] += h
    peak = max(v for fam in hours.values() for v in fam.values())
    last_year = years[-1]
    last_date = max(a[0] for a in acts)

    rows = []
    for fam, _ in FAMILIES:
        if fam not in hours:
            continue
        total = sum(hours[fam].values())
        bars = []
        for y in years:
            h = hours[fam].get(y, 0.0)
            pct = 0 if h < 0.5 else max(4.0, h / peak * 100)
            note = " so far" if y == last_year else ""
            tip = f"{fam}, {y}{note}: {h:.0f} hours" if h >= 0.5 else f"{fam}, {y}: none"
            cls = "bar now" if y == last_year else "bar"
            bars.append(f'<span class="{cls}" style="height:{pct:.1f}%" title="{html.escape(tip)}"></span>')
        rows.append(
            f'<div class="row"><span class="name">{fam}</span>'
            f'<span class="bars" role="presentation">{"".join(bars)}</span>'
            f'<span class="sum">{total:,.0f}{NBSP}h</span></div>'
        )

    axis = "".join(
        f'<span>{y if y in (years[0], 2020, last_year) else ""}</span>' for y in years
    )

    # Plain table of the same numbers.
    head = "".join(f"<th scope=\"col\">{y}</th>" for y in years)
    body = "".join(
        f'<tr><th scope="row">{fam}</th>'
        + "".join(f"<td>{hours[fam].get(y, 0):.0f}</td>" for y in years)
        + "</tr>"
        for fam, _ in FAMILIES if fam in hours
    )

    n = len(acts)
    days = len({a[0].date() for a in acts})
    km = sum(a[3] for a in acts)
    elev = sum(a[4] for a in acts)
    total_h = sum(a[2] for a in acts)
    return dict(
        rows="\n".join(rows), axis=axis, head=head, body=body,
        first=years[0], last=last_year,
        n=f"{n:,}", days=f"{days:,}", km=f"{km:,.0f}", elev=f"{elev:,.0f}", hours=f"{total_h:,.0f}",
        updated=last_date.strftime("%B %Y"),
        days_full=f"{total_h / 24:.0f}",
        sea_mia=f"{km / SEATTLE_MIAMI_KM:.1f}",
        everests=f"{elev / EVEREST_M:.0f}",
    )


def climbing(path):
    """Summarize a Mountain Project tick export. Only totals reach the site:
    no route names, notes, partners or dates of single climbs."""
    import re
    from collections import Counter
    with open(path, newline="", encoding="utf-8") as f:
        ticks = [r for r in csv.DictReader(f) if r.get("Date")]
    if not ticks:
        return None

    def grade(r):
        m = re.match(r"5\.(\d+)([abcd]?[+-]?)", r["Rating"].strip())
        return (int(m.group(1)), m.group(1) + m.group(2)) if m else (None, None)

    buckets = [("5.12", lambda n: n >= 12), ("5.11", lambda n: n == 11), ("5.10", lambda n: n == 10),
               ("5.9", lambda n: n == 9), ("5.8", lambda n: n == 8), ("5.7 and under", lambda n: n <= 7)]
    led, other = Counter(), Counter()
    hardest = None
    for r in ticks:
        n, label = grade(r)
        if n is None:
            continue
        name = next(b for b, ok in buckets if ok(n))
        is_lead = r["Style"].strip() == "Lead"
        (led if is_lead else other)[name] += 1
        if is_lead and r["Lead Style"].strip() != "Fell/Hung":
            code = int(r["Rating Code"] or 0)
            if hardest is None or code > hardest[0]:
                hardest = (code, "5." + label)

    regions = Counter()
    states, countries = set(), set()
    for r in ticks:
        parts = [x.strip() for x in r["Location"].split(">")]
        if parts[0] == "International":
            countries.add(parts[2] if len(parts) > 2 else parts[1])
        else:
            states.add(parts[0])
        regions[parts[3] if len(parts) > 3 else parts[-1]] += 1
    top = [name for name, _ in regions.most_common(2)]
    if len(top) == 2 and top[0].endswith(" Canyon") and top[1].endswith(" Canyon"):
        a_, b_ = top[0][:-7].split(), top[1][:-7].split()
        if a_[1:] == b_[1:]:  # "Big Cottonwood" + "Little Cottonwood" -> "Big and Little Cottonwood Canyons"
            top = [f"{a_[0]} and {' '.join(b_)} Canyons"]
    years = sorted(int(r["Date"][:4]) for r in ticks)
    where = f"{len(states)} states" + (f" and {', '.join(sorted(countries))}" if countries else "")

    peak = max(led[b] + other[b] for b, _ in buckets) or 1
    rows = []
    for b, _ in buckets:
        l, o = led[b], other[b]
        rows.append(
            f'<div class="prow"><span class="name">{b}</span>'
            f'<span class="pbar" title="{b}: {l} led, {o} top-rope or follow">'
            f'<span class="lead" style="width:{l / peak * 100:.1f}%"></span>'
            f'<span class="other" style="width:{o / peak * 100:.1f}%"></span></span>'
            f'<span class="sum">{l + o}</span></div>'
        )
    return dict(
        n=len(ticks), y0=years[0], y1=years[-1], where=where,
        top=" and ".join(top), hardest=hardest[1] if hardest else "",
        rows="\n".join(rows),
    )


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Playing outside · Alexandre Uribe</title>
<meta name="description" content="Hours outside per year, from Alex Uribe's Strava, {first} to {last}.">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="../favicon.png" type="image/png">
<link rel="apple-touch-icon" href="../apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Schibsted+Grotesk:wght@400;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{--bg:#F6F5F1;--ink:#16181A;--muted:#5C5E5D;--line:#DEDCD5;--bar:#7A7C79}}
@media (prefers-color-scheme:dark){{:root{{--bg:#131415;--ink:#ECEAE4;--muted:#A3A29C;--line:#2C2D2F;--bar:#8E8D88}}}}
*{{box-sizing:border-box}}
html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:var(--bg);color:var(--ink);font:clamp(17px,0.6vw + 14.5px,19px)/1.6 'Schibsted Grotesk',system-ui,sans-serif}}
main{{max-width:calc(36em + 48px);margin:0 auto;padding:72px 24px 64px}}
a{{color:inherit;text-decoration-thickness:1px;text-underline-offset:3px;text-decoration-color:var(--muted)}}
a:hover{{opacity:.7}}
.back{{font:500 13px 'IBM Plex Mono',ui-monospace,monospace;color:var(--muted);text-decoration:none}}
h1{{margin:40px 0 12px;font-size:28px;font-weight:600;letter-spacing:-.015em;line-height:1.2}}
p{{margin:0 0 20px}}
.mono{{font:13px/1.6 'IBM Plex Mono',ui-monospace,monospace;color:var(--muted)}}
.chart{{margin:36px 0 12px}}
.row,.axis{{display:grid;grid-template-columns:7.5rem 1fr 4rem;align-items:end;gap:0 14px}}
.row{{padding:10px 0 0}}
.name{{font-size:15px;line-height:1;padding-bottom:1px}}
.sum{{font:12px/1 'IBM Plex Mono',ui-monospace,monospace;color:var(--muted);text-align:right;font-variant-numeric:tabular-nums;padding-bottom:1px}}
.bars{{display:grid;grid-template-columns:repeat({ncols},minmax(0,1fr));gap:3px;align-items:end;height:34px;border-bottom:1px solid var(--line)}}
.bar{{display:block;background:var(--bar);border-radius:2px 2px 0 0;min-height:0}}
.bar.now{{background:repeating-linear-gradient(135deg,var(--bar) 0 2px,transparent 2px 4px)}}
.axis{{padding-bottom:2px}}
.axis .years{{display:grid;grid-template-columns:repeat({ncols},minmax(0,1fr));gap:3px;font:11px/1 'IBM Plex Mono',ui-monospace,monospace;color:var(--muted);white-space:nowrap}}
.axis .years span:last-child{{text-align:right}}
details{{margin:24px 0 40px}}
summary{{cursor:pointer;font:500 13px 'IBM Plex Mono',ui-monospace,monospace;color:var(--muted)}}
.table{{overflow-x:auto;margin-top:12px}}
table{{border-collapse:collapse;font:12px 'IBM Plex Mono',ui-monospace,monospace;font-variant-numeric:tabular-nums}}
th,td{{padding:4px 8px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}}
th[scope=row]{{text-align:left;font-weight:500}}
th[scope=col]{{color:var(--muted);font-weight:500}}
footer{{margin-top:72px}}\nh2{{margin:56px 0 12px;font-size:20px;font-weight:600;letter-spacing:-.01em}}\n.pyr{{margin:20px 0 12px}}\n.prow{{display:grid;grid-template-columns:7.5rem 1fr 4rem;align-items:center;gap:0 14px;padding:4px 0}}\n.pbar{{display:flex;height:14px;border-left:1px solid var(--line)}}\n.pbar .lead{{background:var(--bar)}}\n.pbar .other{{background:var(--bar);opacity:.35}}\n.prow .sum{{padding:0}}\n@media (max-width:480px){{.prow{{grid-template-columns:6.2rem 1fr 2.4rem;gap:0 10px}}}}
.totals{{list-style:none;margin:0;padding:0}}
.totals li{{padding:2px 0}}
@media (max-width:480px){{.row,.axis{{grid-template-columns:5.6rem 1fr 3.2rem;gap:0 10px}}.name{{font-size:14px}}.bars,.axis .years{{gap:2px}}main{{padding-top:48px}}}}
</style>
</head>
<body>
<main>
<a class="back" href="../">← Alex</a>
<h1>Playing outside</h1>
<p>Hours outside each year, from {first} to now, as logged on Strava. Biking and running came first, then climbing; these days it’s mostly walks.</p>

<div class="chart" aria-label="Hours per year by activity, {first} to {last}. The same numbers are in the table below.">
<div class="axis" aria-hidden="true"><span></span><span class="years">{axis}</span><span></span></div>
{rows}
</div>
<p class="mono">Each bar is one year, on the same scale across rows. {last} is striped because it isn’t over yet.</p>

<details>
<summary>The numbers (hours)</summary>
<div class="table"><table><thead><tr><th></th>{head}</tr></thead><tbody>{body}</tbody></table></div>
</details>

<ul class="totals mono">
<li>{n} activities on {days} days</li>
<li>{hours} hours, about {days_full} full days</li>
<li>{km} km, Seattle to Miami about {sea_mia} times</li>
<li>{elev} m climbed, about {everests} Everests</li>
</ul>

{climb_page}
<footer class="mono">Updated {updated}. Indoor workouts are left out.</footer>
</main>
</body>
</html>
"""


# Fold-out card on the homepage. Injected between markers in index.html.
CARD_CSS = """/* outside-card */
.oc{{display:grid;grid-template-rows:0fr;transition:grid-template-rows .35s ease}}
.oc.open{{grid-template-rows:1fr}}
.oc>div{{min-height:0;overflow:hidden}}
.oc-inner{{border:1px solid var(--line);border-radius:12px;padding:16px 18px 14px;margin:0 0 24px;visibility:hidden;transition:visibility 0s .35s}}
.oc.open .oc-inner{{visibility:visible;transition:visibility 0s}}
.oc .row,.oc .axis{{display:grid;grid-template-columns:6.2rem 1fr 3.4rem;align-items:end;gap:0 12px}}
.oc .row{{padding:7px 0 0}}
.oc .name{{font-size:14px;line-height:1;padding-bottom:1px}}
.oc .sum{{font:11px/1 'IBM Plex Mono',ui-monospace,monospace;color:var(--muted);text-align:right;font-variant-numeric:tabular-nums;padding-bottom:1px}}
.oc .bars{{display:grid;grid-template-columns:repeat({ncols},minmax(0,1fr));gap:3px;align-items:end;height:26px;border-bottom:1px solid var(--line)}}
.oc .bar{{display:block;background:var(--bar);border-radius:2px 2px 0 0}}
.oc .bar.now{{background:repeating-linear-gradient(135deg,var(--bar) 0 2px,transparent 2px 4px)}}
.oc .axis{{padding-bottom:1px}}
.oc .years{{display:grid;grid-template-columns:repeat({ncols},minmax(0,1fr));gap:3px;font:10.5px/1 'IBM Plex Mono',ui-monospace,monospace;color:var(--muted);white-space:nowrap}}
.oc .years span:last-child{{text-align:right}}
.oc-foot{{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 16px;margin:14px 0 0;font:12px/1.5 'IBM Plex Mono',ui-monospace,monospace;color:var(--muted)}}
#outside-toggle[role="button"]{{text-decoration-style:dotted;text-decoration-thickness:1.5px;cursor:pointer}}
@media (prefers-reduced-motion:reduce){{.oc,.oc-inner{{transition:none}}}}
@media (max-width:480px){{.oc .row,.oc .axis{{grid-template-columns:5.2rem 1fr 3rem;gap:0 8px}}.oc .bars,.oc .years{{gap:2px}}.oc-inner{{padding:14px 12px 12px}}}}
/* /outside-card */"""

CARD_HTML = """<!-- outside-card -->
<div class="oc" id="outside-card">
<div><div class="oc-inner" aria-label="Hours outside per year by activity, {first} to {last}">
<div class="axis" aria-hidden="true"><span></span><span class="years">{axis}</span><span></span></div>
{rows}
<p class="oc-foot"><span>{hours} hours since {first} · {last} so far is striped</span><a href="outside/">Numbers</a></p>
</div></div>
</div>
<script>
(function(){{var a=document.getElementById('outside-toggle'),c=document.getElementById('outside-card');if(!a||!c)return;
a.setAttribute('role','button');a.setAttribute('aria-expanded','false');a.setAttribute('aria-controls','outside-card');
function t(e){{e.preventDefault();var o=a.getAttribute('aria-expanded')!=='true';a.setAttribute('aria-expanded',String(o));c.classList.toggle('open',o);}}
a.addEventListener('click',t);a.addEventListener('keydown',function(e){{if(e.key===' ')t(e);}});}})();
</script>
<!-- /outside-card -->"""


def replace_between(text, start, end, new):
    i, j = text.find(start), text.find(end)
    if i < 0 or j < 0:
        raise SystemExit(f"markers {start!r} / {end!r} not found in index.html")
    return text[:i] + new + text[j + len(end):]


def main():
    acts = load(sys.argv[1])
    d = build(acts)
    c = climbing(sys.argv[2]) if len(sys.argv) > 2 else None
    d["climb_page"] = (
        f'<h2>Climbing</h2>\n<p>{c["n"]} routes logged on Mountain Project from {c["y0"]} to {c["y1"]}, '
        f'mostly in {c["top"]}, across {c["where"]}. Hardest lead {c["hardest"]}.</p>\n'
        f'<div class="pyr" aria-label="Routes by grade. Solid is led; light is top-rope or following.">\n{c["rows"]}\n</div>\n'
        f'<p class="mono">Routes by grade. Solid: led. Light: top-rope or following.</p>\n' if c else ""
    )
    ncols = d["last"] - d["first"] + 1
    out = ROOT / "outside" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(TEMPLATE.format(ncols=ncols, **d), encoding="utf-8")

    home = ROOT / "index.html"
    text = home.read_text(encoding="utf-8")
    text = replace_between(text, "/* outside-card */", "/* /outside-card */", CARD_CSS.format(ncols=ncols))
    text = replace_between(text, "<!-- outside-card -->", "<!-- /outside-card -->", CARD_HTML.format(**d))
    home.write_text(text, encoding="utf-8")
    print(f"wrote {out} and the homepage card ({d['n']} activities, {d['first']}-{d['last']})")


if __name__ == "__main__":
    main()
