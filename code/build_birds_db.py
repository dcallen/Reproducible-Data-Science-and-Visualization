"""
Build birds.sqlite: a nest box / bird breeding study practice database,
covering nest boxes, weather logs, a unified birds table (adults +
hatchlings), nests, morphometrics, hormones, GPS trackers/deployments/
fixes (including swaps and losses), and gut microbiome OTU data.
"""
import sqlite3
import random
from datetime import date, datetime, timedelta

random.seed(7)

DB_PATH = "birds.sqlite"
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# ---------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------

cur.executescript("""
DROP TABLE IF EXISTS otu_reads;
DROP TABLE IF EXISTS otus;
DROP TABLE IF EXISTS gps_fixes;
DROP TABLE IF EXISTS deployments;
DROP TABLE IF EXISTS trackers;
DROP TABLE IF EXISTS hormones;
DROP TABLE IF EXISTS morphometrics;
DROP TABLE IF EXISTS nests;
DROP TABLE IF EXISTS weather_logs;
DROP TABLE IF EXISTS nest_boxes;
DROP TABLE IF EXISTS birds;

CREATE TABLE nest_boxes (
    box_id INTEGER PRIMARY KEY,
    location_type TEXT NOT NULL CHECK (location_type IN ('farmland', 'residential', 'forest')),
    site_name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL
);

CREATE TABLE birds (
    bird_id INTEGER PRIMARY KEY,
    band_id TEXT NOT NULL UNIQUE,
    sex TEXT CHECK (sex IN ('male', 'female')),
    entry_stage TEXT NOT NULL CHECK (entry_stage IN ('adult', 'hatchling')),
    natal_nest_id INTEGER REFERENCES nests(nest_id),
    first_tagged_date TEXT NOT NULL
);

CREATE TABLE nests (
    nest_id INTEGER PRIMARY KEY,
    box_id INTEGER NOT NULL REFERENCES nest_boxes(box_id),
    season_year INTEGER NOT NULL,
    female_id INTEGER REFERENCES birds(bird_id),
    male_id INTEGER REFERENCES birds(bird_id),
    lay_date TEXT NOT NULL,
    clutch_size INTEGER NOT NULL,
    hatch_date TEXT
);

CREATE TABLE weather_logs (
    log_id INTEGER PRIMARY KEY,
    box_id INTEGER NOT NULL REFERENCES nest_boxes(box_id),
    timestamp TEXT NOT NULL,
    temperature_c REAL,
    light_lux REAL,
    precipitation_mm REAL,
    wind_speed_ms REAL
);

CREATE TABLE morphometrics (
    record_id INTEGER PRIMARY KEY,
    bird_id INTEGER NOT NULL REFERENCES birds(bird_id),
    measurement_date TEXT NOT NULL,
    mass_g REAL,
    wing_length_mm REAL,
    tarsus_length_mm REAL
);

CREATE TABLE hormones (
    sample_id INTEGER PRIMARY KEY,
    bird_id INTEGER NOT NULL REFERENCES birds(bird_id),
    sample_date TEXT NOT NULL,
    prolactin REAL,
    corticosterone REAL
);

CREATE TABLE trackers (
    tracker_id INTEGER PRIMARY KEY,
    tracker_model TEXT NOT NULL
);

CREATE TABLE deployments (
    deployment_id INTEGER PRIMARY KEY,
    bird_id INTEGER NOT NULL REFERENCES birds(bird_id),
    tracker_id INTEGER NOT NULL REFERENCES trackers(tracker_id),
    deployed_date TEXT NOT NULL,
    retrieved_date TEXT
);

CREATE TABLE gps_fixes (
    fix_id INTEGER PRIMARY KEY,
    tracker_id INTEGER NOT NULL REFERENCES trackers(tracker_id),
    timestamp TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL
);

CREATE TABLE otus (
    otu_id INTEGER PRIMARY KEY,
    dna_sequence TEXT NOT NULL,
    phylum TEXT,
    class TEXT,
    order_name TEXT,
    family TEXT,
    genus TEXT,
    species TEXT
);

CREATE TABLE otu_reads (
    read_id INTEGER PRIMARY KEY,
    sample_id INTEGER NOT NULL,
    bird_id INTEGER NOT NULL REFERENCES birds(bird_id),
    otu_id INTEGER NOT NULL REFERENCES otus(otu_id),
    read_count INTEGER NOT NULL
);
""")

# ---------------------------------------------------------------------
# Nest boxes
# ---------------------------------------------------------------------

BOXES = [
    (1,  "farmland",    "Miller Farm North",     41.021, -77.812),
    (2,  "farmland",    "Miller Farm South",     41.018, -77.809),
    (3,  "farmland",    "Bald Eagle Valley Farm", 41.055, -77.901),
    (4,  "residential", "Maplewood Cul-de-sac",  40.798, -77.860),
    (5,  "residential", "Oakview Backyard",      40.802, -77.855),
    (6,  "residential", "Elm Street Park",       40.795, -77.871),
    (7,  "forest",      "Rothrock Trailhead",    40.869, -77.972),
    (8,  "forest",      "Bear Meadows East",     40.845, -77.901),
    (9,  "forest",      "Bear Meadows West",     40.843, -77.915),
]
cur.executemany("INSERT INTO nest_boxes VALUES (?,?,?,?,?)", BOXES)

# ---------------------------------------------------------------------
# Birds, nests, morphometrics, hormones
# We build two seasons (2023, 2024). Season 1 adults are all newly
# tagged (unknown origin). Some season-1 hatchlings return as tagged
# season-2 adults, to exercise the unified birds table / natal_nest_id.
# ---------------------------------------------------------------------

birds = []          # (bird_id, band_id, sex, entry_stage, natal_nest_id, first_tagged_date)
nests = []          # (nest_id, box_id, season_year, female_id, male_id, lay_date, clutch_size, hatch_date)
morphometrics = []  # (record_id, bird_id, measurement_date, mass_g, wing_length_mm, tarsus_length_mm)
hormones = []       # (sample_id, bird_id, sample_date, prolactin, corticosterone)

bird_id = 1
nest_id = 1
record_id = 1
hsample_id = 1

season1_hatchlings = []  # bird_ids of season-1 hatchlings, candidates to return in season 2

def add_bird(band_id, sex, entry_stage, natal_nest_id, first_tagged_date):
    global bird_id
    b = (bird_id, band_id, sex, entry_stage, natal_nest_id, first_tagged_date)
    birds.append(b)
    bird_id += 1
    return b[0]

def add_morph(bird, mdate, base_mass, base_wing, base_tarsus):
    global record_id
    mass = round(base_mass + random.uniform(-1, 1), 1)
    wing = round(base_wing + random.uniform(-2, 2), 1)
    tarsus = round(base_tarsus + random.uniform(-1, 1), 1)
    morphometrics.append((record_id, bird, mdate, mass, wing, tarsus))
    record_id += 1

def add_hormones(bird, sdate):
    global hsample_id
    prolactin = round(random.uniform(5, 60), 1)
    cort = round(random.uniform(1, 25), 1)
    hormones.append((hsample_id, bird, sdate, prolactin, cort))
    hsample_id += 1

season_start_dates = {2023: date(2023, 4, 15), 2024: date(2024, 4, 15)}

for season in (2023, 2024):
    season_start = season_start_dates[season]
    for box_id, *_ in BOXES:
        # not every box gets used every season
        if random.random() < 0.15:
            continue

        lay_date = season_start + timedelta(days=random.randint(0, 25))

        # decide the female: reuse a returning season-1 hatchling ~25% of
        # the time in season 2, otherwise tag a new adult
        female_bird_id = None
        male_bird_id = None

        if season == 2024 and season1_hatchlings and random.random() < 0.25:
            female_bird_id = random.choice(season1_hatchlings)
        else:
            female_band = f"F-{season}-{box_id:02d}"
            female_bird_id = add_bird(female_band, "female", "adult", None,
                                       (lay_date - timedelta(days=random.randint(2, 8))).isoformat())
            add_morph(female_bird_id, lay_date.isoformat(), 19.5, 78.0, 17.0)
            add_hormones(female_bird_id, lay_date.isoformat())

        if season == 2024 and season1_hatchlings and random.random() < 0.25:
            candidate = random.choice(season1_hatchlings)
            if candidate != female_bird_id:
                male_bird_id = candidate
        if male_bird_id is None:
            male_band = f"M-{season}-{box_id:02d}"
            male_bird_id = add_bird(male_band, "male", "adult", None,
                                     (lay_date - timedelta(days=random.randint(2, 8))).isoformat())
            add_morph(male_bird_id, lay_date.isoformat(), 20.5, 80.0, 17.5)
            add_hormones(male_bird_id, lay_date.isoformat())

        clutch_size = random.randint(3, 5)
        hatch_date = lay_date + timedelta(days=13)

        this_nest_id = nest_id
        nests.append((nest_id, box_id, season, female_bird_id, male_bird_id,
                      lay_date.isoformat(), clutch_size, hatch_date.isoformat()))
        nest_id += 1

        # a second hormone sample for each parent during chick-rearing
        rearing_date = hatch_date + timedelta(days=7)
        add_hormones(female_bird_id, rearing_date.isoformat())
        add_hormones(male_bird_id, rearing_date.isoformat())
        add_morph(female_bird_id, rearing_date.isoformat(), 18.5, 78.0, 17.0)
        add_morph(male_bird_id, rearing_date.isoformat(), 19.5, 80.0, 17.5)

        # hatchlings: banded/sexed at hatch, measured daily-ish until fledge (~18 days)
        for h in range(clutch_size):
            hatchling_band = f"H-{season}-{box_id:02d}-{h+1}"
            hatchling_sex = random.choice(["male", "female"])
            hbird_id = add_bird(hatchling_band, hatchling_sex, "hatchling",
                               this_nest_id, hatch_date.isoformat())

            if season == 2023:
                season1_hatchlings.append(hbird_id)

            base_mass = 2.0
            for day_offset in range(0, 19, 3):  # measured every ~3 days until fledge
                mdate = hatch_date + timedelta(days=day_offset)
                growth_mass = base_mass + day_offset * 0.9
                growth_wing = 5 + day_offset * 2.8
                growth_tarsus = 6 + day_offset * 0.5
                add_morph(hbird_id, mdate.isoformat(), growth_mass, growth_wing, growth_tarsus)

cur.executemany("INSERT INTO birds VALUES (?,?,?,?,?,?)", birds)
cur.executemany("INSERT INTO nests VALUES (?,?,?,?,?,?,?,?)", nests)
cur.executemany("INSERT INTO morphometrics VALUES (?,?,?,?,?,?)", morphometrics)
cur.executemany("INSERT INTO hormones VALUES (?,?,?,?,?)", hormones)

# ---------------------------------------------------------------------
# Weather logs: a handful of readings per box per season
# ---------------------------------------------------------------------

weather_logs = []
log_id = 1
for box_id, *_ in BOXES:
    for season in (2023, 2024):
        season_start = season_start_dates[season]
        for d in range(0, 45, 3):
            ts = datetime.combine(season_start + timedelta(days=d), datetime.min.time()) + timedelta(hours=9)
            temp = round(random.uniform(8, 24), 1)
            light = round(random.uniform(200, 20000), 0)
            precip = round(max(0, random.gauss(1.5, 3)), 1)
            wind = round(random.uniform(0, 6), 1)
            weather_logs.append((log_id, box_id, ts.isoformat(sep=" "), temp, light, precip, wind))
            log_id += 1

cur.executemany("INSERT INTO weather_logs VALUES (?,?,?,?,?,?,?)", weather_logs)

# ---------------------------------------------------------------------
# Trackers and deployments: adults get tagged at first capture,
# hatchlings get tagged right before fledging (day 18). Some
# deployments are swapped (tracker fails/battery dies, gets replaced),
# and some end in "lost" (tracker falls off, never retrieved). Loss
# rate is deliberately model-dependent, so it's discoverable in the
# data, not just random noise.
# ---------------------------------------------------------------------

TRACKER_MODELS = ["PathTrack nanoFix", "Lotek PinPoint 10", "Druid Wildlife GPS-Tag"]
MODEL_LOSS_RATES = {
    "PathTrack nanoFix": 0.06,
    "Lotek PinPoint 10": 0.08,
    "Druid Wildlife GPS-Tag": 0.28,  # weaker harness, falls off far more often
}
trackers = []
tracker_id = 1

deployments = []
deployment_id = 1

def new_tracker():
    global tracker_id
    model = random.choice(TRACKER_MODELS)
    trackers.append((tracker_id, model))
    t = tracker_id
    tracker_id += 1
    return t, model

def deploy(bird, start_date, planned_days):
    """Deploy a tracker on a bird, with a chance of loss or a mid-way
    swap. Returns a list of (tracker_id, seg_start, seg_end) segments,
    covering the FULL deployment history for this bird (every tracker
    it ever wore), not just the final one. 'Lost' isn't stored as a
    label anywhere — it's just a deployment with no retrieved_date,
    whose gps_fixes happen to stop earlier than a normal retrieval
    would. Students infer loss from that pattern, and infer which
    model is loss-prone from the trackers table."""
    global deployment_id
    t, model = new_tracker()
    loss_rate = MODEL_LOSS_RATES[model]
    outcome_roll = random.random()

    if outcome_roll < loss_rate:
        # tracker lost: never retrieved, fixes just stop partway through
        end = start_date + timedelta(days=random.randint(3, planned_days))
        deployments.append((deployment_id, bird, t, start_date.isoformat(), None))
        deployment_id += 1
        return [(t, start_date, end)]

    elif outcome_roll < loss_rate + 0.18:
        # swapped partway through: first tracker retrieved early, second deployed
        swap_day = random.randint(4, max(5, planned_days // 2))
        retrieve1 = start_date + timedelta(days=swap_day)
        deployments.append((deployment_id, bird, t, start_date.isoformat(), retrieve1.isoformat()))
        deployment_id += 1

        t2, model2 = new_tracker()
        remaining = planned_days - swap_day
        retrieve2 = retrieve1 + timedelta(days=remaining)
        deployments.append((deployment_id, bird, t2, retrieve1.isoformat(), retrieve2.isoformat()))
        deployment_id += 1
        return [(t, start_date, retrieve1), (t2, retrieve1, retrieve2)]

    else:
        retrieve = start_date + timedelta(days=planned_days)
        deployments.append((deployment_id, bird, t, start_date.isoformat(), retrieve.isoformat()))
        deployment_id += 1
        return [(t, start_date, retrieve)]

gps_fixes = []
fix_id = 1

def jittered_point(lat0, lon0, at_nest):
    """A GPS fix near the nest box (tight jitter) or well away from it
    (wide jitter, e.g. a foraging trip)."""
    if at_nest:
        return (lat0 + random.uniform(-0.0008, 0.0008),
                lon0 + random.uniform(-0.0008, 0.0008))
    else:
        dlat = random.uniform(0.008, 0.02) * random.choice([-1, 1])
        dlon = random.uniform(0.008, 0.02) * random.choice([-1, 1])
        return (lat0 + dlat, lon0 + dlon)

def add_fixes(tracker, seg_start, seg_end, box_id):
    """Generic fixes with no nest-attendance signal, used for
    hatchlings (post-fledging dispersal has no 'incubation' concept)."""
    global fix_id
    box = next(b for b in BOXES if b[0] == box_id)
    lat0, lon0 = box[3], box[4]
    n_days = max(1, (seg_end - seg_start).days)
    for d in range(n_days):
        ts = datetime.combine(seg_start, datetime.min.time()) + timedelta(days=d, hours=random.randint(6, 18))
        plat, plon = jittered_point(lat0, lon0, at_nest=random.random() < 0.4)
        gps_fixes.append((fix_id, tracker, ts.isoformat(sep=" "), round(plat, 6), round(plon, 6)))
        fix_id += 1

def add_parent_fixes(tracker, seg_start, seg_end, box_id, sex, incubation_end_date):
    """Parent fixes carry a real nest-attendance signal: during
    incubation (before hatch), females sit the nest much more than
    males. After hatch (chick-rearing), both sexes range more widely
    to forage, so nest-attendance drops for both."""
    global fix_id
    box = next(b for b in BOXES if b[0] == box_id)
    lat0, lon0 = box[3], box[4]
    n_days = max(1, (seg_end - seg_start).days)
    incubating_at_nest_prob = 0.78 if sex == "female" else 0.42
    rearing_at_nest_prob = 0.35 if sex == "female" else 0.25

    for d in range(n_days):
        cur_date = seg_start + timedelta(days=d)
        ts = datetime.combine(cur_date, datetime.min.time()) + timedelta(hours=random.randint(6, 18))
        if cur_date <= incubation_end_date:
            at_nest = random.random() < incubating_at_nest_prob
        else:
            at_nest = random.random() < rearing_at_nest_prob
        plat, plon = jittered_point(lat0, lon0, at_nest)
        gps_fixes.append((fix_id, tracker, ts.isoformat(sep=" "), round(plat, 6), round(plon, 6)))
        fix_id += 1

for n in nests:
    (this_nest_id, box_id, season, female_id, male_id, lay_date_s, clutch_size, hatch_date_s) = n
    lay_date = date.fromisoformat(lay_date_s)
    hatch_date = date.fromisoformat(hatch_date_s)

    for parent_id, sex in ((female_id, "female"), (male_id, "male")):
        segments = deploy(parent_id, lay_date, planned_days=60)
        for (seg_tracker, seg_start, seg_end) in segments:
            add_parent_fixes(seg_tracker, seg_start, seg_end, box_id, sex, hatch_date)

# hatchling trackers, deployed right before fledging
for b in birds:
    (bid, band_id_, sex, entry_stage, natal_nest_id, first_tagged_date) = b
    if entry_stage == "hatchling":
        nest = next(nn for nn in nests if nn[0] == natal_nest_id)
        hatch_date = date.fromisoformat(nest[7])
        fledge_date = hatch_date + timedelta(days=18)
        segments = deploy(bid, fledge_date, planned_days=40)
        for (seg_tracker, seg_start, seg_end) in segments:
            add_fixes(seg_tracker, seg_start, seg_end, nest[1])

cur.executemany("INSERT INTO trackers VALUES (?,?)", trackers)
cur.executemany("INSERT INTO deployments VALUES (?,?,?,?,?)", deployments)
cur.executemany("INSERT INTO gps_fixes VALUES (?,?,?,?,?)", gps_fixes)

# ---------------------------------------------------------------------
# Gut microbiome: OTUs (realistic bacterial taxonomy) + read counts
# ---------------------------------------------------------------------

OTU_TAXA = [
    # (phylum, class, order, family, genus, species)
    ("Firmicutes",      "Clostridia",     "Clostridiales",     "Lachnospiraceae",     None,             None),
    ("Firmicutes",      "Clostridia",     "Clostridiales",     "Ruminococcaceae",     None,             None),
    ("Firmicutes",      "Bacilli",        "Lactobacillales",   "Lactobacillaceae",    "Lactobacillus",  None),
    ("Bacteroidetes",   "Bacteroidia",    "Bacteroidales",     "Bacteroidaceae",      "Bacteroides",    None),
    ("Bacteroidetes",   "Bacteroidia",    "Bacteroidales",     "Prevotellaceae",      "Prevotella",     None),
    ("Proteobacteria",  "Gammaproteobacteria", "Enterobacterales", "Enterobacteriaceae", "Escherichia", "coli"),
    ("Proteobacteria",  "Alphaproteobacteria",  "Rhizobiales",  None,                  None,             None),
    ("Actinobacteria",  "Actinobacteria", "Bifidobacteriales", "Bifidobacteriaceae",  "Bifidobacterium", None),
    ("Actinobacteria",  "Actinobacteria", "Corynebacteriales", "Corynebacteriaceae",  "Corynebacterium", None),
    ("Fusobacteria",    "Fusobacteriia",  "Fusobacteriales",   "Fusobacteriaceae",    None,             None),
    ("Tenericutes",     "Mollicutes",     "Mycoplasmatales",   "Mycoplasmataceae",    "Mycoplasma",     None),
]

BASES = "ACGT"
def random_seq(n=200):
    return "".join(random.choice(BASES) for _ in range(n))

otus = [(i, random_seq(), *taxa) for i, taxa in enumerate(OTU_TAXA, start=1)]
cur.executemany("INSERT INTO otus VALUES (?,?,?,?,?,?,?,?)", otus)

otu_reads = []
oread_id = 1
osample_id = 1

# adults: one sample each, hatchlings: one sample near fledging
for b in birds:
    (bid, band_id_, sex, entry_stage, natal_nest_id, first_tagged_date) = b
    if random.random() < 0.85:  # not every bird got sampled
        n_otus = random.randint(3, 7)
        chosen = random.sample(range(1, len(OTU_TAXA) + 1), n_otus)
        for otu_id in chosen:
            read_count = random.randint(100, 8000)
            otu_reads.append((oread_id, osample_id, bid, otu_id, read_count))
            oread_id += 1
        osample_id += 1

cur.executemany("INSERT INTO otu_reads VALUES (?,?,?,?,?)", otu_reads)

conn.commit()

# ---------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------

for table in ["nest_boxes", "birds", "nests", "weather_logs", "morphometrics",
              "hormones", "trackers", "deployments", "gps_fixes", "otus", "otu_reads"]:
    n = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"{table}: {n} rows")

print("\nDeployments with no retrieved_date (candidates for 'lost'):")
n_lost = cur.execute("SELECT COUNT(*) FROM deployments WHERE retrieved_date IS NULL").fetchone()[0]
print(" ", n_lost)

print("\nBirds with more than one deployment (swaps):")
n_swapped = cur.execute("""
    SELECT COUNT(*) FROM (
        SELECT bird_id FROM deployments GROUP BY bird_id HAVING COUNT(*) > 1
    )
""").fetchone()[0]
print(" ", n_swapped, "birds")

print("\nReturning hatchlings (now tagged as parents in a later nest):")
n_returning = cur.execute("""
    SELECT COUNT(DISTINCT bird_id) FROM (
        SELECT female_id AS bird_id FROM nests WHERE female_id IN
            (SELECT bird_id FROM birds WHERE entry_stage = 'hatchling')
        UNION
        SELECT male_id AS bird_id FROM nests WHERE male_id IN
            (SELECT bird_id FROM birds WHERE entry_stage = 'hatchling')
    )
""").fetchone()[0]
print(" ", n_returning, "birds")

conn.close()
print(f"\nDatabase written to {DB_PATH}")
