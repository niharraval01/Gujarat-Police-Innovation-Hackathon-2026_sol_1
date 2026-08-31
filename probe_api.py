import urllib.request, json

BASE = "http://localhost:8000"
endpoints = [
    "/health",
    "/stats",
    "/alerts?limit=3",
    "/watchlist/vehicles",
    "/watchlist/persons",
    "/cameras/GJ-VAL-001",
    "/vehicles/GJ06AB1234/route",
]

for path in endpoints:
    url = BASE + path
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
            snippet = str(data)[:90]
            print(f"OK  {path:40s} -> {snippet}")
    except Exception as e:
        print(f"ERR {path:40s} -> {e}")
