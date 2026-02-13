import urllib.request
import re

req = urllib.request.Request(
    "https://cggis.cgstate.gov.in/csidc/",
    headers={"User-Agent": "Mozilla/5.0"}
)
html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="replace")

# Save full HTML
with open("data/csidc_page.html", "w", encoding="utf-8") as f:
    f.write(html)

# Find JS files and API URLs
js_files = re.findall(r'src=["\x27](.*?\.js.*?)["\x27]', html)
urls = re.findall(r'https?://[^\s"<>\x27]+', html)

print("=== JS FILES ===")
for j in js_files:
    print(j)

print("\n=== ALL URLS FOUND ===")
for u in sorted(set(urls)):
    print(u)

print("\n=== GEOSERVER / WMS / WFS / API ===")
for u in sorted(set(urls)):
    if any(k in u.lower() for k in ["wms", "wfs", "geoserver", "arcgis", "layer", "ows", "api"]):
        print(u)

# Also search for inline JS config
patterns = [
    r'geoserver[^"]*',
    r'wms[^"]*',
    r'wfs[^"]*',
    r'layers?:\s*["\x27]([^"]*)["\x27]',
    r'workspace[^"]*',
    r'L\.tileLayer\(["\x27]([^"]*)["\x27]',
]
print("\n=== INLINE JS PATTERNS ===")
for pat in patterns:
    matches = re.findall(pat, html, re.IGNORECASE)
    if matches:
        for m in matches[:5]:
            print(f"  {pat[:20]}: {m}")
