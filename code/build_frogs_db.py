"""
Build frogs.sqlite: the practice relational database for the course,
mirroring the 10-table schema shown in Chapter 5.
"""
import sqlite3
import random
from datetime import date, datetime, timedelta

random.seed(42)

DB_PATH = "frogs.sqlite"

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA foreign_keys = ON;")
cur = conn.cursor()

# ---------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------

cur.executescript("""
DROP TABLE IF EXISTS processed_gps_data;
DROP TABLE IF EXISTS raw_gps_data;
DROP TABLE IF EXISTS deployments;
DROP TABLE IF EXISTS tags;
DROP TABLE IF EXISTS diet_asv_reads;
DROP TABLE IF EXISTS diet_asvs;
DROP TABLE IF EXISTS morphometrics;
DROP TABLE IF EXISTS captures;
DROP TABLE IF EXISTS capture_sites;
DROP TABLE IF EXISTS frogs;

CREATE TABLE frogs (
    frog_id INTEGER PRIMARY KEY,
    sex TEXT NOT NULL CHECK (sex IN ('male', 'female')),
    first_capture_date TEXT NOT NULL,
    mortality_date TEXT
);

CREATE TABLE capture_sites (
    site_id INTEGER PRIMARY KEY,
    site_name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL
);

CREATE TABLE captures (
    capture_id INTEGER PRIMARY KEY,
    frog_id INTEGER NOT NULL REFERENCES frogs(frog_id),
    site_id INTEGER NOT NULL REFERENCES capture_sites(site_id),
    capture_date TEXT NOT NULL
);

CREATE TABLE morphometrics (
    record_id INTEGER PRIMARY KEY,
    frog_id INTEGER NOT NULL REFERENCES frogs(frog_id),
    measurement_date TEXT NOT NULL,
    weight_g REAL,
    length_mm REAL
);

CREATE TABLE diet_asvs (
    asv_id INTEGER PRIMARY KEY,
    dna_sequence TEXT NOT NULL,
    order_name TEXT,
    family TEXT,
    genus TEXT,
    species TEXT
);

CREATE TABLE diet_asv_reads (
    read_id INTEGER PRIMARY KEY,
    diet_sample_id INTEGER NOT NULL,
    frog_id INTEGER NOT NULL REFERENCES frogs(frog_id),
    asv_id INTEGER NOT NULL REFERENCES diet_asvs(asv_id),
    read_count INTEGER NOT NULL
);

CREATE TABLE tags (
    tag_id INTEGER PRIMARY KEY,
    tag_model TEXT NOT NULL
);

CREATE TABLE deployments (
    deployment_id INTEGER PRIMARY KEY,
    frog_id INTEGER NOT NULL REFERENCES frogs(frog_id),
    tag_id INTEGER NOT NULL REFERENCES tags(tag_id),
    deployed_date TEXT NOT NULL,
    retrieved_date TEXT
);

CREATE TABLE raw_gps_data (
    reading_id INTEGER PRIMARY KEY,
    tag_id INTEGER NOT NULL REFERENCES tags(tag_id),
    timestamp TEXT NOT NULL,
    raw_lat REAL NOT NULL,
    raw_lon REAL NOT NULL
);

CREATE TABLE processed_gps_data (
    location_id INTEGER PRIMARY KEY,
    frog_id INTEGER NOT NULL REFERENCES frogs(frog_id),
    timestamp TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL
);
""")

# ---------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------

SITES = [
    (1, "Alder Pond",     41.7982, -111.8181),
    (2, "Beaver Creek",   41.8104, -111.7996),
    (3, "Cattail Marsh",  41.7867, -111.8330),
]
cur.executemany("INSERT INTO capture_sites VALUES (?,?,?,?)", SITES)

TAG_MODELS = ["e-obs 2g", "Lotek PinPoint 75", "ATS G5"]
tags = [(i, random.choice(TAG_MODELS)) for i in range(1, 13)]
cur.executemany("INSERT INTO tags VALUES (?,?)", tags)

TAXA_DATA = [
    (1,  "Diptera",        "Chironomidae", None,      None),
    (2,  "Diptera",        "Culicidae",    "Aedes",   None),
    (3,  "Hymenoptera",    "Formicidae",   None,      None),
    (4,  "Coleoptera",     None,           None,      None),
    (5,  "Araneae",        None,           None,      None),
    (6,  "Hemiptera",      "Aphididae",    None,      None),
    (7,  "Diptera",        "Tipulidae",    "Tipula",  None),
    (8,  "Hemiptera",      "Gerridae",     "Gerris",  "remigis"),
    (9,  "Odonata",        None,           None,      None),
    (10, "Ephemeroptera",  None,           None,      None),
    (11, "Collembola",     None,           None,      None),
]
BASES = "ACGT"
def random_seq(n=150):
    return "".join(random.choice(BASES) for _ in range(n))

diet_asvs = [(asv_id, random_seq(), order_, family, genus, species)
             for (asv_id, order_, family, genus, species) in TAXA_DATA]
cur.executemany("INSERT INTO diet_asvs VALUES (?,?,?,?,?,?)", diet_asvs)

# ---------------------------------------------------------------------
# Frogs, captures, morphometrics
# ---------------------------------------------------------------------

N_FROGS = 40
season_start = date(2023, 5, 1)

frogs = []
captures = []
morphometrics = []
diet_sample_ids = []  # (diet_sample_id, frog_id) pairs, one per sample taken

capture_id = 1
record_id = 1
diet_sample_id = 1

for frog_id in range(1, N_FROGS + 1):
    sex = random.choice(["male", "female"])
    first_capture = season_start + timedelta(days=random.randint(0, 40))

    # ~20% chance the frog has a recorded mortality date
    mortality = None
    if random.random() < 0.2:
        mortality = first_capture + timedelta(days=random.randint(20, 120))

    frogs.append((frog_id, sex, first_capture.isoformat(),
                  mortality.isoformat() if mortality else None))

    # 1-4 recapture events per frog
    n_captures = random.randint(1, 4)
    capture_dates = sorted(
        first_capture + timedelta(days=14 * i + random.randint(0, 5))
        for i in range(n_captures)
    )
    # don't let captures occur after mortality
    if mortality:
        capture_dates = [d for d in capture_dates if d <= mortality]
        if not capture_dates:
            capture_dates = [first_capture]

    base_weight = random.uniform(8, 25)
    base_length = random.uniform(45, 90)

    for i, cdate in enumerate(capture_dates):
        site_id = random.choice(SITES)[0]
        captures.append((capture_id, frog_id, site_id, cdate.isoformat()))

        # morphometrics taken at every capture
        weight = round(base_weight + i * random.uniform(0.5, 2.0), 1)
        length = round(base_length + i * random.uniform(0.2, 1.5), 1)
        morphometrics.append((record_id, frog_id, cdate.isoformat(), weight, length))
        record_id += 1

        # diet sample taken at ~60% of captures
        if random.random() < 0.6:
            diet_sample_ids.append((diet_sample_id, frog_id))
            diet_sample_id += 1

        capture_id += 1

cur.executemany("INSERT INTO frogs VALUES (?,?,?,?)", frogs)
cur.executemany("INSERT INTO captures VALUES (?,?,?,?)", captures)
cur.executemany("INSERT INTO morphometrics VALUES (?,?,?,?,?)", morphometrics)

# ---------------------------------------------------------------------
# Diet ASV reads: each diet sample gets 2-5 ASVs detected, with read counts
# ---------------------------------------------------------------------

diet_asv_reads = []
read_id = 1
for sample_id, frog_id in diet_sample_ids:
    n_asvs = random.randint(2, 5)
    chosen = random.sample(range(1, len(TAXA_DATA) + 1), n_asvs)
    for asv_id in chosen:
        read_count = random.randint(50, 5000)
        diet_asv_reads.append((read_id, sample_id, frog_id, asv_id, read_count))
        read_id += 1

cur.executemany("INSERT INTO diet_asv_reads VALUES (?,?,?,?,?)", diet_asv_reads)

# ---------------------------------------------------------------------
# Deployments + GPS data (only a subset of frogs get tagged)
# ---------------------------------------------------------------------

TAGGED_FROG_IDS = random.sample(range(1, N_FROGS + 1), 10)

deployments = []
raw_gps = []
processed_gps = []

deployment_id = 1
reading_id = 1
location_id = 1

for i, frog_id in enumerate(TAGGED_FROG_IDS):
    tag_id = tags[i % len(tags)][0]
    frog_record = next(f for f in frogs if f[0] == frog_id)
    deploy_date = date.fromisoformat(frog_record[2]) + timedelta(days=random.randint(1, 10))
    retrieve_date = deploy_date + timedelta(days=random.randint(15, 45))

    deployments.append((deployment_id, frog_id, tag_id,
                        deploy_date.isoformat(), retrieve_date.isoformat()))

    # simple random walk of GPS fixes around one of the sites
    site = random.choice(SITES)
    lat, lon = site[2], site[3]
    n_fixes = random.randint(10, 20)
    for f in range(n_fixes):
        ts = datetime.combine(deploy_date, datetime.min.time()) + timedelta(
            hours=6 * f + random.randint(0, 3)
        )
        lat += random.uniform(-0.001, 0.001)
        lon += random.uniform(-0.001, 0.001)
        raw_lat = round(lat + random.uniform(-0.0003, 0.0003), 6)  # GPS noise
        raw_lon = round(lon + random.uniform(-0.0003, 0.0003), 6)

        raw_gps.append((reading_id, tag_id, ts.isoformat(sep=" "), raw_lat, raw_lon))
        reading_id += 1

        # processed = cleaned version, one per raw fix here for simplicity
        processed_gps.append((location_id, frog_id, ts.isoformat(sep=" "),
                              round(lat, 6), round(lon, 6)))
        location_id += 1

    deployment_id += 1

cur.executemany("INSERT INTO deployments VALUES (?,?,?,?,?)", deployments)
cur.executemany("INSERT INTO raw_gps_data VALUES (?,?,?,?,?)", raw_gps)
cur.executemany("INSERT INTO processed_gps_data VALUES (?,?,?,?,?)", processed_gps)

conn.commit()

# ---------------------------------------------------------------------
# Sanity check: print row counts
# ---------------------------------------------------------------------

for table in ["frogs", "capture_sites", "captures", "morphometrics",
              "diet_asvs", "diet_asv_reads", "tags", "deployments",
              "raw_gps_data", "processed_gps_data"]:
    n = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"{table}: {n} rows")

conn.close()
print(f"\nDatabase written to {DB_PATH}")
