-- Railway Reservation System - Database Schema (15 tables)
-- SQLite compatible. Matches the ER diagram loosely; some tables dropped/merged per requirement.

PRAGMA foreign_keys = ON;

-- 1. USERS - registered persons who book tickets
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name        VARCHAR(100) NOT NULL,
    email       VARCHAR(100) UNIQUE NOT NULL,
    phone       VARCHAR(20),
    password    VARCHAR(255) NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. STATIONS - railway stations
CREATE TABLE IF NOT EXISTS stations (
    station_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    station_name   VARCHAR(100) NOT NULL,
    station_code   VARCHAR(10) UNIQUE NOT NULL,
    city           VARCHAR(100),
    state          VARCHAR(100)
);

-- 3. TRAINS - master train info
CREATE TABLE IF NOT EXISTS trains (
    train_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    train_name               VARCHAR(100) NOT NULL,
    train_number             VARCHAR(20) UNIQUE NOT NULL,
    source_station_id        INTEGER NOT NULL,
    destination_station_id   INTEGER NOT NULL,
    running_days             VARCHAR(100),
    total_seats              INTEGER DEFAULT 100,
    FOREIGN KEY (source_station_id) REFERENCES stations(station_id),
    FOREIGN KEY (destination_station_id) REFERENCES stations(station_id)
);

-- 4. TRAIN_STOPS - intermediate stations a train halts at
CREATE TABLE IF NOT EXISTS train_stops (
    stop_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    train_id           INTEGER NOT NULL,
    station_id         INTEGER NOT NULL,
    sequence_no        INTEGER NOT NULL,
    arrival_time       TIME,
    departure_time     TIME,
    halt_duration      INTEGER,
    day_offset         INTEGER DEFAULT 0,
    distance_from_source INTEGER,
    FOREIGN KEY (train_id) REFERENCES trains(train_id),
    FOREIGN KEY (station_id) REFERENCES stations(station_id)
);

-- 5. COACH_CLASSES - class of travel
CREATE TABLE IF NOT EXISTS coach_classes (
    class_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    class_code   VARCHAR(10) NOT NULL,
    class_name   VARCHAR(50) NOT NULL,
    fare_per_km  NUMERIC(6,2)
);

-- 6. COACHES - coaches attached to a train
CREATE TABLE IF NOT EXISTS coaches (
    coach_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    train_id     INTEGER NOT NULL,
    coach_number VARCHAR(20),
    total_seats  INTEGER DEFAULT 72,
    FOREIGN KEY (train_id) REFERENCES trains(train_id)
);

-- 7. SEATS - individual seats (always available; no berth variations)
CREATE TABLE IF NOT EXISTS seats (
    seat_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    train_id     INTEGER NOT NULL,
    coach_id     INTEGER NOT NULL,
    class_id     INTEGER NOT NULL,
    seat_number  VARCHAR(10) NOT NULL,
    berth_type   VARCHAR(20) DEFAULT 'Seat',
    fare_per_km  NUMERIC(6,2),
    FOREIGN KEY (train_id) REFERENCES trains(train_id),
    FOREIGN KEY (coach_id) REFERENCES coaches(coach_id),
    FOREIGN KEY (class_id) REFERENCES coach_classes(class_id)
);
-- 8. TRAIN_RUNS - a specific run of a train on a date
CREATE TABLE IF NOT EXISTS train_runs (
    run_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    train_id               INTEGER NOT NULL,
    run_date               DATE NOT NULL,
    journey_date           DATE,
    source_station         VARCHAR(100),
    destination_station    VARCHAR(100),
    ncr_status             VARCHAR(50),
    FOREIGN KEY (train_id) REFERENCES trains(train_id)
);

-- 9. BOOKINGS - booking header per PNR
CREATE TABLE IF NOT EXISTS bookings (
    booking_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL,
    train_id         INTEGER NOT NULL,
    run_id           INTEGER NOT NULL,
    pnr              VARCHAR(20) UNIQUE NOT NULL,
    booking_status   VARCHAR(20) DEFAULT 'Confirmed',
    refund_reward    NUMERIC(8,2) DEFAULT 0,
    booked_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (train_id) REFERENCES trains(train_id),
    FOREIGN KEY (run_id) REFERENCES train_runs(run_id)
);

-- 10. PASSENGERS - passengers on a booking
CREATE TABLE IF NOT EXISTS passengers (
    passenger_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL,
    name             VARCHAR(100) NOT NULL,
    age              INTEGER,
    gender           CHAR(1),
    id_proof_type    VARCHAR(50),
    id_proof_no      VARCHAR(50),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- 11. TICKETS - ticket per passenger per booking
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    pnr_id           INTEGER NOT NULL,
    passenger_id     INTEGER NOT NULL,
    run_id           INTEGER NOT NULL,
    seat_id          INTEGER NOT NULL,
    fare             NUMERIC(8,2),
    cancellation     VARCHAR(20),
    cancelled_at     TIMESTAMP,
    refund_reward    NUMERIC(8,2) DEFAULT 0,
    FOREIGN KEY (pnr_id) REFERENCES bookings(booking_id),
    FOREIGN KEY (passenger_id) REFERENCES passengers(passenger_id),
    FOREIGN KEY (run_id) REFERENCES train_runs(run_id),
    FOREIGN KEY (seat_id) REFERENCES seats(seat_id)
);

-- 12. PAYMENTS - payment records (demo only, no gateway)
CREATE TABLE IF NOT EXISTS payments (
    payment_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    pnr_id           INTEGER NOT NULL,
    amount           NUMERIC(8,2),
    payment_mode     VARCHAR(50),
    payment_status   VARCHAR(20) DEFAULT 'Paid',
    transaction_ref  VARCHAR(100),
    paid_by          VARCHAR(100),
    paid_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pnr_id) REFERENCES bookings(booking_id)
);

-- 13. FEEDBACK - user rating of train precision (out of 5)
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pnr_id               INTEGER NOT NULL,
    user_id              INTEGER NOT NULL,
    rating               INTEGER CHECK (rating >= 1 AND rating <= 5),
    feedback_type        VARCHAR(50),
    description          TEXT,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_by_staff_id INTEGER,
    FOREIGN KEY (pnr_id) REFERENCES bookings(booking_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- 14. TRAIN_LIVE_STATUS - live running status of a train run
CREATE TABLE IF NOT EXISTS train_live_status (
    live_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    train_id             INTEGER NOT NULL,
    run_id               INTEGER NOT NULL,
    current_station_id   INTEGER NOT NULL,
    next_station_id      INTEGER NOT NULL,
    last_station_id      INTEGER NOT NULL,
    next_arrival         DATETIME,
    next_departure       DATETIME,
    delay_minutes_next   INTEGER DEFAULT 0,
    current_status       VARCHAR(100),
    last_updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (train_id) REFERENCES trains(train_id),
    FOREIGN KEY (run_id) REFERENCES train_runs(run_id),
    FOREIGN KEY (current_station_id) REFERENCES stations(station_id),
    FOREIGN KEY (next_station_id) REFERENCES stations(station_id),
    FOREIGN KEY (last_station_id) REFERENCES stations(station_id)
);

-- 15. NOTIFICATIONS - alerts to users
CREATE TABLE IF NOT EXISTS notifications (
    notification_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id            INTEGER NOT NULL,
    message            TEXT NOT NULL,
    type               VARCHAR(50) DEFAULT 'info',
    is_read            INTEGER DEFAULT 0,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

