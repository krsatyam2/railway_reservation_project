import os
import random
import string
import sqlite3
import datetime
from datetime import date, timedelta
from flask import Flask, request, jsonify, send_from_directory, session
from werkzeug.security import generate_password_hash, check_password_hash
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder="static")
app.secret_key = os.getenv("SECRET_KEY", "railreserve-dbms-lab-local-secret-2026")

DB_PATH = os.path.join(os.path.dirname(__file__), "database.sqlite")
RAILRADAR_API_KEY = os.getenv("RAILRADAR_API_KEY", "").strip()
RAILRADAR_BASE_URL = os.getenv("RAILRADAR_BASE_URL", "https://api.railradar.in/v1").rstrip("/")
# If user provided live-status in URL, extract base:
if "/live-status" in RAILRADAR_BASE_URL:
    RAILRADAR_BASE_URL = RAILRADAR_BASE_URL.replace("/live-status", "")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def verify_password(stored_password, provided_password):
    """Verify password against Werkzeug hash with fallback to plain-text for legacy demo entries."""
    if not stored_password or not provided_password:
        return False
    try:
        if check_password_hash(stored_password, provided_password):
            return True
    except Exception:
        pass
    return stored_password == provided_password


def get_current_user(conn=None):
    """Fetch logged in user profile from SQLite users table based on Flask session."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    close_conn = False
    if conn is None:
        conn = get_db()
        close_conn = True
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id, name, email, phone, created_at FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        if close_conn:
            conn.close()


def ensure_coach_and_seats(conn, train_id):
    """Ensures a train has coach and seats created in SQLite."""
    cur = conn.cursor()
    cur.execute("SELECT coach_id FROM coaches WHERE train_id = ?", (train_id,))
    coach = cur.fetchone()
    if coach:
        coach_id = coach["coach_id"]
    else:
        cur.execute("INSERT INTO coaches (train_id, coach_number, total_seats) VALUES (?, 'A1', 72)", (train_id,))
        coach_id = cur.lastrowid

    # Check seats
    cur.execute("SELECT COUNT(*) AS cnt FROM seats WHERE train_id = ?", (train_id,))
    if cur.fetchone()["cnt"] == 0:
        # Get coach classes
        classes = cur.execute("SELECT class_id, fare_per_km FROM coach_classes").fetchall()
        if not classes:
            cur.execute("INSERT INTO coach_classes(class_code, class_name, fare_per_km) VALUES ('SL','Sleeper',2.5),('3A','AC 3-Tier',4.5),('2A','AC 2-Tier',6.5),('CC','AC Chair Car',5.0)")
            classes = cur.execute("SELECT class_id, fare_per_km FROM coach_classes").fetchall()

        seat_no = 1
        for c in classes:
            for _ in range(18):
                cur.execute(
                    "INSERT INTO seats (train_id, coach_id, class_id, seat_number, berth_type, fare_per_km) VALUES (?, ?, ?, ?, 'Seat', ?)",
                    (train_id, coach_id, c["class_id"], str(seat_no), c["fare_per_km"])
                )
                seat_no += 1
    conn.commit()
    return coach_id


def ensure_run_exists(conn, train_id, journey_date=None):
    """Ensures train_runs entry exists for this train on journey_date."""
    if not journey_date:
        journey_date = date.today().isoformat()
    cur = conn.cursor()
    cur.execute(
        "SELECT run_id FROM train_runs WHERE train_id = ? AND (run_date = ? OR journey_date = ?)",
        (train_id, journey_date, journey_date)
    )
    row = cur.fetchone()
    if row:
        return row["run_id"]

    # Fetch train source and dest names
    t_info = cur.execute("""
        SELECT t.train_name, s1.station_name AS src, s2.station_name AS dst
        FROM trains t
        LEFT JOIN stations s1 ON t.source_station_id = s1.station_id
        LEFT JOIN stations s2 ON t.destination_station_id = s2.station_id
        WHERE t.train_id = ?
    """, (train_id,)).fetchone()

    src_name = t_info["src"] if t_info and t_info["src"] else "Origin"
    dst_name = t_info["dst"] if t_info and t_info["dst"] else "Destination"

    cur.execute(
        "INSERT INTO train_runs (train_id, run_date, journey_date, source_station, destination_station, ncr_status) VALUES (?, ?, ?, ?, ?, 'Normal')",
        (train_id, journey_date, journey_date, src_name, dst_name)
    )
    run_id = cur.lastrowid

    # Check if train_live_status exists for this run
    cur.execute("SELECT live_id FROM train_live_status WHERE run_id = ?", (run_id,))
    if not cur.fetchone():
        s_src = cur.execute("SELECT source_station_id, destination_station_id FROM trains WHERE train_id = ?", (train_id,)).fetchone()
        src_id = s_src["source_station_id"] if s_src else 1
        dst_id = s_src["destination_station_id"] if s_src else 1
        delay = random.choice([0, 0, 5, 10, 15, 20])
        status_text = f"Delayed by {delay} min" if delay else "Running on time"
        cur.execute("""
            INSERT INTO train_live_status
            (train_id, run_id, current_station_id, next_station_id, last_station_id, next_arrival, next_departure, delay_minutes_next, current_status, last_updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now', '+30 minutes'), ?, ?, datetime('now'))
        """, (train_id, run_id, src_id, dst_id, dst_id, delay, status_text))

    conn.commit()
    return run_id


def sync_train_to_db(conn, train_data, journey_date=None):
    """
    Given a train dict from RailRadar API, ensure it exists in SQLite trains table,
    along with stations, coaches, seats, and runs.
    Returns SQLite train_id.
    """
    cur = conn.cursor()
    t_obj = train_data.get("train", {})
    tnum = str(t_obj.get("number", "")).strip()
    tname = t_obj.get("name", f"Train {tnum}")
    run_days_list = t_obj.get("runDays", ["Daily"])
    running_days = ", ".join(run_days_list) if isinstance(run_days_list, list) else str(run_days_list)
    total_seats = 100

    # Ensure source & destination stations
    from_info = train_data.get("from", {})
    to_info = train_data.get("to", {})

    from_code = from_info.get("code", "SRC")
    from_name = from_info.get("name", from_code)
    from_city = from_info.get("city", from_name)

    to_code = to_info.get("code", "DST")
    to_name = to_info.get("name", to_code)
    to_city = to_info.get("city", to_name)

    # Upsert stations
    cur.execute("INSERT OR IGNORE INTO stations (station_name, station_code, city, state) VALUES (?, ?, ?, 'India')",
                (from_name, from_code, from_city))
    cur.execute("SELECT station_id FROM stations WHERE station_code = ?", (from_code,))
    src_id = cur.fetchone()["station_id"]

    cur.execute("INSERT OR IGNORE INTO stations (station_name, station_code, city, state) VALUES (?, ?, ?, 'India')",
                (to_name, to_code, to_city))
    cur.execute("SELECT station_id FROM stations WHERE station_code = ?", (to_code,))
    dst_id = cur.fetchone()["station_id"]

    # Upsert train
    cur.execute("SELECT train_id FROM trains WHERE train_number = ?", (tnum,))
    existing = cur.fetchone()
    if existing:
        train_id = existing["train_id"]
    else:
        cur.execute(
            "INSERT INTO trains (train_name, train_number, source_station_id, destination_station_id, running_days, total_seats) VALUES (?, ?, ?, ?, ?, ?)",
            (tname, tnum, src_id, dst_id, running_days, total_seats)
        )
        train_id = cur.lastrowid

    ensure_coach_and_seats(conn, train_id)
    ensure_run_exists(conn, train_id, journey_date)

    return train_id


def fetch_railradar_between(source_code, dest_code):
    """Call RailRadar API for trains between stations."""
    if not RAILRADAR_API_KEY:
        return None
    url = f"https://api.railradar.in/v1/trains/between/{source_code}/{dest_code}"
    headers = {
        "Authorization": f"Bearer {RAILRADAR_API_KEY}",
        "User-Agent": "RailReserve/1.0"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success") and "data" in data and "trains" in data["data"]:
                return data["data"]["trains"]
    except Exception as e:
        print(f"[RailRadar between API error] {e}")
    return None


def fetch_railradar_live(train_number):
    """Call RailRadar live train status API."""
    if not RAILRADAR_API_KEY:
        return None
    url = f"https://api.railradar.in/v1/trains/{train_number}/live"
    headers = {
        "Authorization": f"Bearer {RAILRADAR_API_KEY}",
        "User-Agent": "RailReserve/1.0"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=6)
        if resp.status_code == 200:
            res_json = resp.json()
            if res_json.get("success") and "data" in res_json:
                d = res_json["data"]
                delay = d.get("delayMinutes", 0) or 0
                status_raw = d.get("status", "running")

                if status_raw == "completed":
                    status_text = "Journey Completed"
                elif delay > 0:
                    status_text = f"Delayed by {delay} min"
                else:
                    status_text = "Running on time"

                # Stations
                prev_halt = d.get("previousHalt") or {}
                last_station = prev_halt.get("stationName") or prev_halt.get("stationCode") or "N/A"

                curr_loc = d.get("currentLocation") or {}
                curr_station = curr_loc.get("stationName") or curr_loc.get("stationCode") or (f"Near {last_station}" if last_station != "N/A" else "In Transit")

                next_halt = d.get("nextHalt") or {}
                next_station = next_halt.get("stationName") or next_halt.get("stationCode") or "Destination"

                # Calculate precision rating (5.0 max down to 2.0 based on delay)
                if delay <= 0:
                    rating = 5.0
                elif delay <= 15:
                    rating = 4.6
                elif delay <= 30:
                    rating = 4.0
                elif delay <= 60:
                    rating = 3.4
                elif delay <= 120:
                    rating = 2.8
                else:
                    rating = 2.0

                return {
                    "train_id": d.get("trainNumber", train_number),
                    "train_name": d.get("trainName", f"Train {train_number}"),
                    "current_status": status_text,
                    "delay_minutes": delay,
                    "last_station": last_station,
                    "current_station": curr_station,
                    "next_station": next_station,
                    "next_arrival": curr_loc.get("status", "On route"),
                    "next_departure": "Scheduled",
                    "avg_delay_minutes": delay,
                    "precision_rating": rating,
                    "source_api": True
                }
    except Exception as e:
        print(f"[RailRadar live API error] {e}")
    return None


# ===================== ROUTES =====================

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/stations")
def get_stations():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT station_id, station_name, station_code, city, state FROM stations ORDER BY station_name ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)


def get_train_rating_info(conn, train_id):
    """Calculate aggregated passenger rating and review count from SQLite feedback table."""
    cur = conn.cursor()
    cur.execute("""
        SELECT AVG(f.rating) AS avg_rating, COUNT(f.feedback_id) AS total_reviews
        FROM feedback f
        JOIN bookings b ON f.pnr_id = b.booking_id
        WHERE b.train_id = ?
    """, (train_id,))
    r = cur.fetchone()
    if r and r["avg_rating"] is not None:
        return round(float(r["avg_rating"]), 1), int(r["total_reviews"])
    return 4.8, 0


@app.route("/api/trains")
def search_trains():
    src_code = request.args.get("source", "").strip().upper()
    dst_code = request.args.get("dest", "").strip().upper()
    journey_date = request.args.get("date", "").strip() or date.today().isoformat()

    if not src_code or not dst_code:
        return jsonify({"error": "source and dest parameters are required"}), 400

    conn = get_db()
    results = []

    # 1. Try RailRadar API first
    api_trains = fetch_railradar_between(src_code, dst_code)
    if api_trains:
        for t in api_trains:
            t_obj = t.get("train", {})
            tnum = str(t_obj.get("number", ""))
            tname = t_obj.get("name", f"Train {tnum}")
            run_days_list = t_obj.get("runDays", ["Daily"])
            running_days = ", ".join(run_days_list) if isinstance(run_days_list, list) else str(run_days_list)

            # Sync to SQLite so foreign keys are completely valid
            train_id = sync_train_to_db(conn, t, journey_date)

            from_name = t.get("from", {}).get("name", src_code)
            to_name = t.get("to", {}).get("name", dst_code)

            rating, reviews_count = get_train_rating_info(conn, train_id)

            results.append({
                "train_id": train_id,
                "train_name": tname,
                "train_number": tnum,
                "source_name": from_name,
                "dest_name": to_name,
                "running_days": running_days,
                "total_seats": 100,
                "source_api": True,
                "rating": rating,
                "reviews_count": reviews_count
            })

    # 2. If API yielded results, return them
    if results:
        conn.close()
        return jsonify(results)

    # 3. Fallback to SQLite Database
    cur = conn.cursor()

    # Query 3a: Direct matching source and destination
    query_direct = """
        SELECT t.train_id, t.train_name, t.train_number, t.running_days, t.total_seats,
               s1.station_name AS source_name, s2.station_name AS dest_name
        FROM trains t
        JOIN stations s1 ON t.source_station_id = s1.station_id
        JOIN stations s2 ON t.destination_station_id = s2.station_id
        WHERE (s1.station_code = ? AND s2.station_code = ?)
    """
    rows = cur.execute(query_direct, (src_code, dst_code)).fetchall()

    # Query 3b: Intermediate stops route
    if not rows:
        query_stops = """
            SELECT DISTINCT t.train_id, t.train_name, t.train_number, t.running_days, t.total_seats,
                   s1.station_name AS source_name, s2.station_name AS dest_name
            FROM trains t
            JOIN train_stops st1 ON t.train_id = st1.train_id
            JOIN stations s1 ON st1.station_id = s1.station_id
            JOIN train_stops st2 ON t.train_id = st2.train_id
            JOIN stations s2 ON st2.station_id = s2.station_id
            WHERE s1.station_code = ? AND s2.station_code = ? AND st1.sequence_no < st2.sequence_no
        """
        rows = cur.execute(query_stops, (src_code, dst_code)).fetchall()

    # Query 3c: If still empty (e.g. demo stations without direct route in 6 seeded trains),
    # provide available trains between these stations by linking or scheduling so demo never breaks!
    if not rows:
        # Check if stations exist in DB
        s_src = cur.execute("SELECT station_id, station_name FROM stations WHERE station_code = ?", (src_code,)).fetchone()
        s_dst = cur.execute("SELECT station_id, station_name FROM stations WHERE station_code = ?", (dst_code,)).fetchone()
        if s_src and s_dst:
            # Auto-create a scheduled express service between these two stations for demo
            service_number = f"EXP-{src_code[:2]}{dst_code[:2]}"
            service_name = f"{s_src['station_name']} - {s_dst['station_name']} Superfast"
            cur.execute("SELECT train_id FROM trains WHERE train_number = ?", (service_number,))
            existing_t = cur.fetchone()
            if not existing_t:
                cur.execute(
                    "INSERT INTO trains (train_name, train_number, source_station_id, destination_station_id, running_days, total_seats) VALUES (?, ?, ?, ?, 'Daily', 100)",
                    (service_name, service_number, s_src["station_id"], s_dst["station_id"])
                )
                tid = cur.lastrowid
            else:
                tid = existing_t["train_id"]
            ensure_coach_and_seats(conn, tid)
            ensure_run_exists(conn, tid, journey_date)
            rows = cur.execute(query_direct, (src_code, dst_code)).fetchall()

    for r in rows:
        tid = r["train_id"]
        ensure_coach_and_seats(conn, tid)
        ensure_run_exists(conn, tid, journey_date)
        rating, reviews_count = get_train_rating_info(conn, tid)
        results.append({
            "train_id": r["train_id"],
            "train_name": r["train_name"],
            "train_number": r["train_number"],
            "source_name": r["source_name"],
            "dest_name": r["dest_name"],
            "running_days": r["running_days"] or "Daily",
            "total_seats": r["total_seats"] or 100,
            "source_api": False,
            "rating": rating,
            "reviews_count": reviews_count
        })

    conn.close()
    return jsonify(results)


@app.route("/api/live-status")
def live_status():
    tnum = request.args.get("train_number", "").strip()
    if not tnum:
        return jsonify({"error": "train_number parameter required"}), 400

    conn = get_db()
    cur = conn.cursor()

    # Look up train in DB
    cur.execute("""
        SELECT t.train_id, t.train_name, t.train_number,
               s1.station_name AS src_name, s2.station_name AS dst_name
        FROM trains t
        LEFT JOIN stations s1 ON t.source_station_id = s1.station_id
        LEFT JOIN stations s2 ON t.destination_station_id = s2.station_id
        WHERE t.train_number = ?
    """, (tnum,))
    db_train = cur.fetchone()

    # 1. Try RailRadar API
    api_status = fetch_railradar_live(tnum)

    # Make sure we have train & run_id in DB
    train_id = None
    if db_train:
        train_id = db_train["train_id"]
    else:
        # If API gave train info, insert train to DB
        tname = api_status["train_name"] if api_status else f"Train {tnum}"
        cur.execute("SELECT station_id FROM stations LIMIT 2")
        st_rows = cur.fetchall()
        src_id = st_rows[0]["station_id"] if len(st_rows) > 0 else 1
        dst_id = st_rows[1]["station_id"] if len(st_rows) > 1 else 1
        cur.execute(
            "INSERT INTO trains (train_name, train_number, source_station_id, destination_station_id, running_days, total_seats) VALUES (?, ?, ?, ?, 'Daily', 100)",
            (tname, tnum, src_id, dst_id)
        )
        train_id = cur.lastrowid
        ensure_coach_and_seats(conn, train_id)

    run_id = ensure_run_exists(conn, train_id, date.today().isoformat())

    # Calculate precision rating from SQLite feedback table
    feedback_avg, feedback_count = get_train_rating_info(conn, train_id)
    has_user_feedback = (feedback_count > 0)

    if api_status:
        api_status["run_id"] = run_id
        api_status["train_id"] = train_id
        if has_user_feedback:
            api_status["precision_rating"] = feedback_avg
        api_status["total_reviews"] = feedback_count
        conn.close()
        return jsonify(api_status)

    # 2. Fallback to SQLite train_live_status
    cur.execute("""
        SELECT tls.*,
               s_curr.station_name AS current_name,
               s_next.station_name AS next_name,
               s_last.station_name AS last_name
        FROM train_live_status tls
        LEFT JOIN stations s_curr ON tls.current_station_id = s_curr.station_id
        LEFT JOIN stations s_next ON tls.next_station_id = s_next.station_id
        LEFT JOIN stations s_last ON tls.last_station_id = s_last.station_id
        WHERE tls.train_id = ?
        ORDER BY tls.last_updated_at DESC LIMIT 1
    """, (train_id,))
    ls = cur.fetchone()

    if ls:
        delay = ls["delay_minutes_next"] or 0
        default_rating = 5.0 if delay == 0 else max(2.0, round(5.0 - (delay / 15.0), 1))
        precision_rating = feedback_avg if has_user_feedback else default_rating

        result = {
            "train_id": train_id,
            "run_id": run_id,
            "train_number": tnum,
            "train_name": db_train["train_name"] if db_train else f"Train {tnum}",
            "current_status": ls["current_status"] or ("Running on time" if delay == 0 else f"Delayed by {delay} min"),
            "delay_minutes": delay,
            "last_station": ls["last_name"] or "Source",
            "current_station": ls["current_name"] or "In Transit",
            "next_station": ls["next_name"] or "Next Station",
            "next_arrival": ls["next_arrival"] or "10:30 AM",
            "next_departure": ls["next_departure"] or "10:45 AM",
            "avg_delay_minutes": delay,
            "precision_rating": precision_rating,
            "total_reviews": feedback_count,
            "source_api": False
        }
    else:
        result = {
            "train_id": train_id,
            "run_id": run_id,
            "train_number": tnum,
            "train_name": db_train["train_name"] if db_train else f"Train {tnum}",
            "current_status": "Running on time",
            "delay_minutes": 0,
            "last_station": db_train["src_name"] if db_train else "Origin",
            "current_station": db_train["src_name"] if db_train else "Origin",
            "next_station": db_train["dst_name"] if db_train else "Destination",
            "next_arrival": "On Schedule",
            "next_departure": "On Schedule",
            "avg_delay_minutes": 0,
            "precision_rating": feedback_avg if has_user_feedback else 4.8,
            "total_reviews": feedback_count,
            "source_api": False
        }

    conn.close()
    return jsonify(result)


@app.route("/api/book", methods=["POST"])
def book_ticket():
    data = request.get_json() or {}
    train_id = data.get("train_id")
    run_id = data.get("run_id")
    passenger_name = data.get("passenger_name", "").strip()
    passenger_age = data.get("passenger_age", 25)
    passenger_gender = data.get("passenger_gender", "M").upper()
    phone = data.get("phone", "").strip()
    email = data.get("email", "").strip() or f"{phone}@demo.in"
    id_proof_type = data.get("id_proof_type", "Aadhaar")
    id_proof_no = data.get("id_proof_no", "1234-5678-9012")

    if not train_id or not run_id or not passenger_name or not phone:
        return jsonify({"error": "train_id, run_id, passenger_name, and phone are required"}), 400

    conn = get_db()
    cur = conn.cursor()

    # 1. User management
    logged_in_id = session.get("user_id")
    if logged_in_id:
        user_id = logged_in_id
    else:
        cur.execute("SELECT user_id FROM users WHERE LOWER(email) = ? OR phone = ?", (email.lower(), phone))
        user_row = cur.fetchone()
        if user_row:
            user_id = user_row["user_id"]
        else:
            hashed_demo_pw = generate_password_hash("demo123")
            cur.execute(
                "INSERT INTO users (name, email, phone, password) VALUES (?, ?, ?, ?)",
                (passenger_name, email, phone, hashed_demo_pw)
            )
            user_id = cur.lastrowid

    # 2. PNR generation
    pnr = "RR" + "".join(random.choices(string.digits, k=8))

    # 3. Create Booking
    cur.execute(
        "INSERT INTO bookings (user_id, train_id, run_id, pnr, booking_status) VALUES (?, ?, ?, ?, 'Confirmed')",
        (user_id, train_id, run_id, pnr)
    )
    booking_id = cur.lastrowid

    # 4. Passenger record
    cur.execute(
        "INSERT INTO passengers (user_id, name, age, gender, id_proof_type, id_proof_no) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, passenger_name, passenger_age, passenger_gender, id_proof_type, id_proof_no)
    )
    passenger_id = cur.lastrowid

    # 5. Seat assignment
    # Find already booked seats for this run
    cur.execute("SELECT seat_id FROM tickets WHERE run_id = ? AND (cancellation IS NULL OR cancellation = 'Active')", (run_id,))
    booked_seat_ids = [r["seat_id"] for r in cur.fetchall()]

    ensure_coach_and_seats(conn, train_id)
    cur.execute("SELECT seat_id, seat_number, fare_per_km FROM seats WHERE train_id = ?", (train_id,))
    all_seats = cur.fetchall()

    assigned_seat = None
    for s in all_seats:
        if s["seat_id"] not in booked_seat_ids:
            assigned_seat = s
            break

    if not assigned_seat:
        # Generate an additional seat
        seat_num = f"S-{len(all_seats) + 1}"
        cur.execute("SELECT coach_id FROM coaches WHERE train_id = ? LIMIT 1", (train_id,))
        cid = cur.fetchone()["coach_id"]
        cur.execute(
            "INSERT INTO seats (train_id, coach_id, class_id, seat_number, berth_type, fare_per_km) VALUES (?, ?, 1, ?, 'Seat', 4.5)",
            (train_id, cid, seat_num)
        )
        assigned_seat_id = cur.lastrowid
        assigned_seat_number = seat_num
        fare = 520.0
    else:
        assigned_seat_id = assigned_seat["seat_id"]
        assigned_seat_number = assigned_seat["seat_number"]
        fare = float(assigned_seat["fare_per_km"] or 4.5) * 120.0

    # 6. Ticket record
    cur.execute(
        "INSERT INTO tickets (pnr_id, passenger_id, run_id, seat_id, fare, cancellation) VALUES (?, ?, ?, ?, ?, 'Active')",
        (booking_id, passenger_id, run_id, assigned_seat_id, fare)
    )

    # 7. Payment record
    tx_ref = "TXN" + "".join(random.choices(string.digits + string.ascii_uppercase, k=10))
    cur.execute(
        "INSERT INTO payments (pnr_id, amount, payment_mode, payment_status, transaction_ref, paid_by) VALUES (?, ?, 'UPI/Demo', 'Paid', ?, ?)",
        (booking_id, fare, tx_ref, passenger_name)
    )

    # 8. Notification record
    notif_msg = f"Booking Confirmed! PNR: {pnr}, Seat: {assigned_seat_number}, Fare: Rs.{fare:.2f}."
    cur.execute(
        "INSERT INTO notifications (user_id, message, type) VALUES (?, ?, 'booking')",
        (user_id, notif_msg)
    )

    conn.commit()

    # Fetch train details for confirmation response
    t_info = cur.execute("""
        SELECT t.train_name, t.train_number, tr.run_date,
               s1.station_name AS src_name, s2.station_name AS dst_name
        FROM train_runs tr
        JOIN trains t ON tr.train_id = t.train_id
        LEFT JOIN stations s1 ON t.source_station_id = s1.station_id
        LEFT JOIN stations s2 ON t.destination_station_id = s2.station_id
        WHERE tr.run_id = ?
    """, (run_id,)).fetchone()

    response = {
        "pnr": pnr,
        "booking_id": booking_id,
        "train_name": t_info["train_name"] if t_info else "Express",
        "train_number": t_info["train_number"] if t_info else "N/A",
        "source": t_info["src_name"] if t_info else "Source",
        "destination": t_info["dst_name"] if t_info else "Destination",
        "date": t_info["run_date"] if t_info else date.today().isoformat(),
        "seat": str(assigned_seat_number),
        "fare": round(fare, 2),
        "status": "Confirmed",
        "passenger": passenger_name
    }

    conn.close()
    return jsonify(response)


@app.route("/api/booking/<pnr>")
def get_booking(pnr):
    pnr = pnr.strip()
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT b.booking_id, b.pnr, b.booking_status, b.booked_at,
               t.train_id, t.train_name, t.train_number, tr.run_date,
               s1.station_name AS src_name, s2.station_name AS dst_name,
               p.name AS passenger_name, p.age, p.gender,
               st.seat_number, tk.fare, pay.payment_status,
               f.feedback_id, f.rating AS user_rating, f.feedback_type, f.description AS user_comment, f.created_at AS feedback_date
        FROM bookings b
        JOIN trains t ON b.train_id = t.train_id
        JOIN train_runs tr ON b.run_id = tr.run_id
        LEFT JOIN stations s1 ON t.source_station_id = s1.station_id
        LEFT JOIN stations s2 ON t.destination_station_id = s2.station_id
        LEFT JOIN tickets tk ON b.booking_id = tk.pnr_id
        LEFT JOIN passengers p ON tk.passenger_id = p.passenger_id
        LEFT JOIN seats st ON tk.seat_id = st.seat_id
        LEFT JOIN payments pay ON b.booking_id = pay.pnr_id
        LEFT JOIN feedback f ON b.booking_id = f.pnr_id
        WHERE b.pnr = ?
    """, (pnr,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": f"Booking with PNR {pnr} not found"}), 404

    return jsonify({
        "booking_id": row["booking_id"],
        "pnr": row["pnr"],
        "status": row["booking_status"],
        "train_id": row["train_id"],
        "train_name": row["train_name"],
        "train_number": row["train_number"],
        "source": row["src_name"],
        "destination": row["dst_name"],
        "date": row["run_date"],
        "passenger": row["passenger_name"],
        "seat": row["seat_number"],
        "fare": row["fare"],
        "payment": row["payment_status"],
        "booked_at": row["booked_at"],
        "has_feedback": row["feedback_id"] is not None,
        "user_rating": row["user_rating"],
        "feedback_type": row["feedback_type"],
        "user_comment": row["user_comment"],
        "feedback_date": row["feedback_date"]
    })


@app.route("/api/feedback", methods=["POST"])
def submit_feedback():
    data = request.get_json() or {}
    pnr = data.get("pnr")
    rating = data.get("rating")
    comment = data.get("comment", "").strip()
    feedback_type = data.get("feedback_type", "Overall Experience").strip()

    if rating is None or not (1 <= int(rating) <= 5):
        return jsonify({"error": "Rating must be an integer between 1 and 5"}), 400

    conn = get_db()
    cur = conn.cursor()

    logged_in_id = session.get("user_id")
    booking_id = None
    train_id = None
    train_name = "Train"
    user_id = logged_in_id or 1

    if pnr:
        cur.execute("""
            SELECT b.booking_id, b.user_id, b.train_id, t.train_name, t.train_number
            FROM bookings b
            JOIN trains t ON b.train_id = t.train_id
            WHERE b.pnr = ?
        """, (pnr.strip(),))
        b = cur.fetchone()
        if b:
            booking_id = b["booking_id"]
            train_id = b["train_id"]
            train_name = b["train_name"]
            if not logged_in_id:
                user_id = b["user_id"]

    if not booking_id:
        tnum = data.get("train_number")
        if tnum:
            t_row = cur.execute("SELECT train_id, train_name FROM trains WHERE train_number = ?", (str(tnum).strip(),)).fetchone()
            if t_row:
                train_id = t_row["train_id"]
                train_name = t_row["train_name"]
                b_cand = cur.execute("SELECT booking_id, user_id FROM bookings WHERE train_id = ? ORDER BY booking_id DESC LIMIT 1", (train_id,)).fetchone()
                if b_cand:
                    booking_id = b_cand["booking_id"]
                    if not logged_in_id:
                        user_id = b_cand["user_id"]
                else:
                    # Ensure run and booking for this train so feedback links directly to this train in SQLite
                    run_id = ensure_run_exists(conn, train_id)
                    pnr_demo = f"FB{random.randint(10000000, 99999999)}"
                    cur.execute(
                        "INSERT INTO bookings (user_id, train_id, run_id, pnr, booking_status) VALUES (?, ?, ?, ?, 'Completed')",
                        (user_id, train_id, run_id, pnr_demo)
                    )
                    booking_id = cur.lastrowid

    if not booking_id:
        cur.execute("""
            SELECT b.booking_id, b.user_id, b.train_id, t.train_name
            FROM bookings b
            JOIN trains t ON b.train_id = t.train_id
            ORDER BY b.booking_id DESC LIMIT 1
        """)
        b = cur.fetchone()
        if b:
            booking_id = b["booking_id"]
            train_id = b["train_id"]
            train_name = b["train_name"]
            if not logged_in_id:
                user_id = b["user_id"]
        else:
            booking_id = 1
            train_id = 1

    # Check if feedback already exists for this booking
    cur.execute("SELECT feedback_id FROM feedback WHERE pnr_id = ?", (booking_id,))
    existing_fb = cur.fetchone()

    if existing_fb:
        cur.execute("""
            UPDATE feedback
            SET rating = ?, feedback_type = ?, description = ?, created_at = datetime('now')
            WHERE feedback_id = ?
        """, (int(rating), feedback_type, comment, existing_fb["feedback_id"]))
        action = "updated"
    else:
        cur.execute("""
            INSERT INTO feedback (pnr_id, user_id, rating, feedback_type, description, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (booking_id, user_id, int(rating), feedback_type, comment))
        action = "recorded"

    conn.commit()

    # Recalculate train average rating immediately
    new_avg, total_reviews = get_train_rating_info(conn, train_id)

    # Add notification for user
    cur.execute("""
        INSERT INTO notifications (user_id, message, type)
        VALUES (?, ?, 'feedback')
    """, (user_id, f"Feedback {action} for {train_name}! Your rating of {rating}/5 stars updated the train rating to ★ {new_avg}."))
    conn.commit()

    conn.close()

    return jsonify({
        "success": True,
        "action": action,
        "rating": int(rating),
        "train_id": train_id,
        "train_name": train_name,
        "new_train_rating": new_avg,
        "total_reviews": total_reviews,
        "message": f"Thank you! Your feedback was {action}. {train_name} rating is now ★ {new_avg} (based on {total_reviews} passenger ratings)."
    })


@app.route("/api/feedback/<pnr>")
def get_pnr_feedback(pnr):
    """Retrieve existing feedback for a specific PNR."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT f.feedback_id, f.rating, f.feedback_type, f.description, f.created_at,
               b.pnr, t.train_id, t.train_name, t.train_number
        FROM feedback f
        JOIN bookings b ON f.pnr_id = b.booking_id
        JOIN trains t ON b.train_id = t.train_id
        WHERE b.pnr = ?
    """, (pnr.strip(),))
    fb = cur.fetchone()
    conn.close()

    if fb:
        return jsonify({"has_feedback": True, "feedback": dict(fb)})
    return jsonify({"has_feedback": False, "feedback": None})


@app.route("/api/trains/<int:train_id>/feedback")
def get_train_feedback(train_id):
    """Retrieve recent passenger feedback and ratings for a train."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT f.feedback_id, f.rating, f.feedback_type, f.description, f.created_at,
               b.pnr, p.name AS passenger_name
        FROM feedback f
        JOIN bookings b ON f.pnr_id = b.booking_id
        LEFT JOIN tickets tk ON b.booking_id = tk.pnr_id
        LEFT JOIN passengers p ON tk.passenger_id = p.passenger_id
        WHERE b.train_id = ?
        ORDER BY f.created_at DESC LIMIT 10
    """, (train_id,))
    feedbacks = [dict(r) for r in cur.fetchall()]

    rating, total_reviews = get_train_rating_info(conn, train_id)
    conn.close()
    return jsonify({
        "train_id": train_id,
        "average_rating": rating,
        "total_reviews": total_reviews,
        "reviews": feedbacks
    })


# ===================== AUTH & USER ROUTES (LOCAL SQLITE DEMO) =====================

@app.route("/api/auth/register", methods=["POST"])
def register():
    """Register a new user directly in SQLite users table."""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    phone = data.get("phone", "").strip()
    password = data.get("password", "").strip()

    if not name:
        return jsonify({"error": "Full name is required"}), 400
    if not email or "@" not in email:
        return jsonify({"error": "A valid email address is required"}), 400
    if not password:
        return jsonify({"error": "Password is required"}), 400
    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters long"}), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM users WHERE LOWER(email) = ?", (email,))
    if cur.fetchone():
        conn.close()
        return jsonify({"error": f"An account with email '{email}' already exists in SQLite database"}), 400

    hashed_pw = generate_password_hash(password)
    cur.execute(
        "INSERT INTO users (name, email, phone, password) VALUES (?, ?, ?, ?)",
        (name, email, phone, hashed_pw)
    )
    user_id = cur.lastrowid

    # Create a welcome notification in SQLite notifications table
    cur.execute(
        "INSERT INTO notifications (user_id, message, type) VALUES (?, ?, 'account')",
        (user_id, f"Welcome to RailReserve, {name}! Your local SQLite user account is active.")
    )
    conn.commit()

    # Log in user immediately via session
    session["user_id"] = user_id

    user = {
        "user_id": user_id,
        "name": name,
        "email": email,
        "phone": phone
    }
    conn.close()
    return jsonify({
        "success": True,
        "message": f"Account created successfully for {name}! (Stored in SQLite users table)",
        "user": user
    })


@app.route("/api/auth/login", methods=["POST"])
def login():
    """Log in an existing user using SQLite users table & Flask session."""
    data = request.get_json() or {}
    identifier = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not identifier or not password:
        return jsonify({"error": "Email/phone and password are required"}), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT user_id, name, email, phone, password, created_at FROM users WHERE LOWER(email) = ? OR phone = ?",
        (identifier, identifier)
    )
    user_row = cur.fetchone()

    if not user_row or not verify_password(user_row["password"], password):
        conn.close()
        return jsonify({"error": "Invalid credentials. Please check your email and password."}), 401

    session["user_id"] = user_row["user_id"]

    user = {
        "user_id": user_row["user_id"],
        "name": user_row["name"],
        "email": user_row["email"],
        "phone": user_row["phone"],
        "created_at": user_row["created_at"]
    }
    conn.close()
    return jsonify({
        "success": True,
        "message": f"Welcome back, {user['name']}!",
        "user": user
    })


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    """Log out current user by clearing session."""
    session.pop("user_id", None)
    return jsonify({"success": True, "message": "Logged out successfully"})


@app.route("/api/auth/me")
def get_me():
    """Return currently authenticated user from session and SQLite."""
    user = get_current_user()
    if user:
        return jsonify({"authenticated": True, "user": user})
    return jsonify({"authenticated": False, "user": None})


@app.route("/api/my-bookings")
def get_my_bookings():
    """Fetch all bookings for the currently authenticated user from SQLite."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required. Please log in to view your bookings."}), 401

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT b.booking_id, b.pnr, b.booking_status, b.booked_at,
               t.train_id, t.train_name, t.train_number, tr.run_date,
               s1.station_name AS src_name, s2.station_name AS dst_name,
               p.name AS passenger_name, p.age, p.gender,
               st.seat_number, tk.fare, pay.payment_status,
               f.feedback_id, f.rating AS user_rating, f.feedback_type, f.description AS user_comment, f.created_at AS feedback_date
        FROM bookings b
        JOIN trains t ON b.train_id = t.train_id
        JOIN train_runs tr ON b.run_id = tr.run_id
        LEFT JOIN stations s1 ON t.source_station_id = s1.station_id
        LEFT JOIN stations s2 ON t.destination_station_id = s2.station_id
        LEFT JOIN tickets tk ON b.booking_id = tk.pnr_id
        LEFT JOIN passengers p ON tk.passenger_id = p.passenger_id
        LEFT JOIN seats st ON tk.seat_id = st.seat_id
        LEFT JOIN payments pay ON b.booking_id = pay.pnr_id
        LEFT JOIN feedback f ON b.booking_id = f.pnr_id
        WHERE b.user_id = ?
        ORDER BY b.booking_id DESC
    """, (user["user_id"],))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)


@app.route("/api/my-notifications")
def get_my_notifications():
    """Fetch notifications for the authenticated user."""
    user = get_current_user()
    if not user:
        return jsonify([])

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT notification_id, message, type, is_read, created_at
        FROM notifications
        WHERE user_id = ?
        ORDER BY created_at DESC LIMIT 10
    """, (user["user_id"],))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)


@app.route("/api/health")
def health():
    conn = get_db()
    cur = conn.cursor()
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    conn.close()
    return jsonify({
        "status": "healthy",
        "tables_count": len(tables),
        "railradar_key_present": bool(RAILRADAR_API_KEY)
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
