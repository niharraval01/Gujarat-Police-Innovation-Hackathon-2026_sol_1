"""
seed_data.py — seeds the registry with ~50 cameras spread across Gujarat
districts (matching the hackathon's "onboard ~50 cameras" test-case scale)
and a representative watchlist, per the brief's explicit allowance for
teams to "create and use representative datasets".
"""

import random
import db

# (district, city, base_lat, base_lon)
SITES = [
    ("Valsad", "Valsad", 20.5992, 72.9342),
    ("Dahod", "Dahod", 22.8331, 74.2593),
    ("Gir Somnath", "Veraval", 20.9077, 70.3661),
    ("Jamnagar", "Jamnagar", 22.4707, 70.0577),
    ("Devbhoomi Dwarka", "Dwarka", 22.2394, 68.9678),
    ("Ahmedabad", "Ahmedabad", 23.0225, 72.5714),
    ("Surat", "Surat", 21.1702, 72.8311),
    ("Vadodara", "Vadodara", 22.3072, 73.1812),
    ("Rajkot", "Rajkot", 22.3039, 70.8022),
    ("Bhavnagar", "Bhavnagar", 21.7645, 72.1519),
    ("Junagadh", "Junagadh", 21.5222, 70.4579),
    ("Gandhinagar", "Gandhinagar", 23.2156, 72.6369),
    ("Anand", "Anand", 22.5645, 72.9289),
    ("Bharuch", "Bharuch", 21.7051, 73.0000),
    ("Navsari", "Navsari", 20.9467, 72.9520),
    ("Mehsana", "Mehsana", 23.5880, 72.3693),
    ("Patan", "Patan", 23.8493, 72.1266),
    ("Morbi", "Morbi", 22.8173, 70.8378),
    ("Porbandar", "Porbandar", 21.6417, 69.6293),
    ("Kutch", "Bhuj", 23.2419, 69.6669),
    ("Surendranagar", "Surendranagar", 22.7280, 71.6379),
    ("Panchmahal", "Godhra", 22.7772, 73.6151),
    ("Ankleshwar", "Ankleshwar", 21.6266, 73.0104),
    ("Amreli", "Amreli", 21.6032, 71.2213),
    ("Botad", "Botad", 22.1704, 71.6660),
]

DEPARTMENTS = ["Home", "Food & Civil Supplies", "RTO", "Municipal Corporation"]
SITE_KIND_BY_DEPT = {
    "Home": ["Police Chowki", "Traffic Signal Junction", "Toll Naka", "Highway Checkpoint"],
    "Food & Civil Supplies": ["PDS Shop", "FCI Godown", "Ration Warehouse"],
    "RTO": ["RTO Office", "Testing Track", "Vehicle Checkpoint"],
    "Municipal Corporation": ["Market Chowk", "Bus Terminus", "Municipal Ward Office"],
}
VENDORS = ["Hikvision", "Dahua", "CP Plus", "Honeywell", "Bosch"]
VMS_PLATFORMS = ["HikCentral", "DSS Pro", "Milestone XProtect", "Genetec Security Center"]
CONNECTIVITY = ["fiber", "fiber", "fiber", "4G", "4G", "satellite"]  # weighted toward fiber


def generate_cameras(n=50, seed=42):
    rng = random.Random(seed)
    cameras = []
    for i in range(n):
        district, city, lat, lon = SITES[i % len(SITES)]
        dept = DEPARTMENTS[i % len(DEPARTMENTS)]
        kind = rng.choice(SITE_KIND_BY_DEPT[dept])
        jitter = lambda v: v + rng.uniform(-0.05, 0.05)
        cameras.append({
            "camera_id": f"GJ-{district[:3].upper()}-{i+1:03d}",
            "name": f"{city} {kind} Cam-{i+1}",
            "department": dept,
            "vendor": rng.choice(VENDORS),
            "vms_platform": rng.choice(VMS_PLATFORMS),
            "lat": round(jitter(lat), 5),
            "lon": round(jitter(lon), 5),
            "district": district,
            "camera_type": "ANPR-dedicated" if dept == "Home" and rng.random() < 0.4 else "fixed",
            "connectivity": rng.choice(CONNECTIVITY),
            "storage_days": rng.choice([7, 15, 30]),
        })
    return cameras


WATCHLIST_VEHICLES = [
    ("GJ06AB1234", "stolen", "VAHAN", "Reported stolen — Ahmedabad, 12 Aug 2026"),
    ("GJ18CD5678", "wanted", "eGujCop", "Vehicle linked to open FIR #2026/4471"),
    ("GJ01XY9999", "blacklisted", "manual", "Repeated overloading violations"),
    ("GJ27PQ0001", "suspect", "eGujCop", "Flagged in ongoing surveillance case"),
    ("GJ05LM4321", "stolen", "VAHAN", "Reported stolen — Surat, 03 Aug 2026"),
]

WATCHLIST_PERSONS = [
    ("P-1001", "Unidentified Suspect A", "wanted", 1, "eGujCop", "Wanted in theft case #2026/1187"),
    ("P-1002", "Missing Person B", "missing", 2, "manual", "Reported missing — family contacted via helpline"),
]


def seed_all(reset=True):
    db.init_db(reset=reset)
    for cam in generate_cameras():
        db.upsert_camera(cam)
    for plate, reason, src, notes in WATCHLIST_VEHICLES:
        db.add_watchlist_vehicle(plate, reason, src, notes)
    for pid, name, reason, label, src, notes in WATCHLIST_PERSONS:
        db.add_watchlist_person(pid, name, reason, label, src, notes)
    print(f"Seeded {len(db.list_cameras())} cameras, "
          f"{len(db.list_watchlist_vehicles())} vehicle watchlist entries, "
          f"{len(db.list_watchlist_persons())} person watchlist entries.")


if __name__ == "__main__":
    seed_all()
