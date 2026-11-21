"""Seed dummy data for the Railway Reservation demo."""
import sqlite3
import random
from datetime import date, timedelta

DB = "database.sqlite"

STATIONS = [
    ("New Delhi", "NDLS", "New Delhi", "Delhi"),
    ("Mumbai Central", "MMCT", "Mumbai", "Maharashtra"),
    ("Howrah Junction", "HWH", "Kolkata", "West Bengal"),
    ("Chennai Central", "MAS", "Chennai", "Tamil Nadu"),
    ("Bengaluru City", "SBC", "Bengaluru", "Karnataka"),
    ("Jaipur", "JP", "Jaipur", "Rajasthan"),
    ("Lucknow", "LKO", "Lucknow", "Uttar Pradesh"),
    ("Patna Junction", "PNBE", "Patna", "Bihar"),
]

TRAINS = [
    ("Rajdhani Express", "12301", "New Delhi", "Howrah Junction", "Mon,Wed,Fri,Sat", 120),
    ("Shatabdi Express", "12001", "New Delhi", "Bengaluru City", "Daily", 90),
    ("Duronto Express", "12215", "Mumbai Central", "Howrah Junction", "Tue,Thu,Sun", 110),
    ("Garib Rath", "12201", "Chennai Central", "New Delhi", "Wed,Sun", 100),
    ("Intercity Express", "12615", "Jaipur", "Lucknow", "Daily", 80),
    ("Express Mail", "14005", "Patna Junction", "Chennai Central", "Mon,Thu", 95),
]

CLASSES = [("SL", "Sleeper", 2.5), ("3A", "AC 3-Tier", 4.5), ("2A", "AC 2-Tier", 6.5), ("CC", "AC Chair Car", 5.0)]


def seed():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = ON")

    # stations
    station_ids = {}
    for name, code, city, state in STATIONS:
        c.execute("INSERT OR IGNORE INTO stations(station_name, station_code, city, state) VALUES (?,?,?,?)",
                  (name, code, city, state))
        c.execute("SELECT station_id FROM stations WHERE station_code=?", (code,))
        station_ids[name] = c.fetchone()[0]

    # coach classes
    class_ids = {}
    for code, name, fare in CLASSES:
        c.execute("INSERT OR IGNORE INTO coach_classes(class_code, class_name, fare_per_km) VALUES (?,?,?)",
                  (code, name, fare))
        c.execute("SELECT class_id FROM coach_classes WHERE class_code=?", (code,))
        class_ids[code] = c.fetchone()[0]

    # trains + coaches + seats + runs + stops + live status
    train_ids = {}
    run_ids = {}
    for idx, (tname, tnum, src, dst, days, total_seats) in enumerate(TRAINS, start=1):
        c.execute("INSERT OR IGNORE INTO trains(train_name, train_number, source_station_id, destination_station_id, running_days, total_seats) VALUES (?,?,?,?,?,?)",
                  (tname, tnum, station_ids[src], station_ids[dst], days, total_seats))
        c.execute("SELECT train_id FROM trains WHERE train_number=?", (tnum,))
        tid = c.fetchone()[0]
        train_ids[tname] = tid

        # coach
        c.execute("INSERT INTO coaches(train_id, coach_number, total_seats) VALUES (?, 'A1', ?)", (tid, 72))
        coach_id = c.lastrowid

        # seats per class
        seat_no = 1
        for ccode in ["SL", "3A", "2A", "CC"]:
            for _ in range(18):
                c.execute("INSERT INTO seats(train_id, coach_id, class_id, seat_number, berth_type, fare_per_km) VALUES (?,?,?,?, 'Seat', (SELECT fare_per_km FROM coach_classes WHERE class_id=?))",
                          (tid, coach_id, class_ids[ccode], f"{seat_no}", class_ids[ccode]))
                seat_no += 1

        # run for today + next 3 days
        for d in range(4):
            run_date = date.today() + timedelta(days=d)
            c.execute("INSERT INTO train_runs(train_id, run_date, journey_date, source_station, destination_station, ncr_status) VALUES (?,?,?,?,?, 'Normal')",
                      (tid, run_date.isoformat(), run_date.isoformat(), src, dst))
            run_ids[(tid, d)] = c.lastrowid

        # stops: source -> 2 intermediate (from station list) -> dest
        intermediates = [s for s in [x[0] for x in STATIONS] if s not in (src, dst)][:2]
        all_stations = [src] + intermediates + [dst]
        seq = 1
        for st in all_stations:
            c.execute("INSERT INTO train_stops(train_id, station_id, sequence_no, arrival_time, departure_time, halt_duration, day_offset, distance_from_source) VALUES (?,?,?,?,?,?,?,?)",
                      (tid, station_ids[st], seq,
                       f"{6+seq}:{seq*13 % 60:02d}:00", f"{6+seq}:{(seq*13+8) % 60:02d}:00", 5, 0, seq * 150))
            seq += 1

        # live status for today's run
        rid = run_ids[(tid, 0)]
        delay = random.choice([0, 0, 0, 5, 10, 15, 20, 30])
        c.execute("INSERT INTO train_live_status(train_id, run_id, current_station_id, next_station_id, last_station_id, next_arrival, next_departure, delay_minutes_next, current_status, last_updated_at) VALUES (?,?,?,?,?,datetime('now'),datetime('now','+30 minutes'),?, ?, datetime('now'))",
                  (tid, rid, station_ids[src], station_ids[all_stations[1]], station_ids[dst], delay,
                   "Delayed by {} min".format(delay) if delay else "Running on time"))

    # demo user
    c.execute("INSERT OR IGNORE INTO users(name, email, phone, password) VALUES ('Demo User', 'demo@rail.in', '9999999999', 'demo123')")

    conn.commit()
    conn.close()
    print("Seeded OK. Tables: 15")


if __name__ == "__main__":
    seed()
