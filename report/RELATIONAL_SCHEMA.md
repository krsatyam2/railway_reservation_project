# Relational Schema & Integrity Specification

**System:** RailReserve (Railway Reservation & Live Tracking System)  
**DBMS:** SQLite 3  
**Status:** 3NF / BCNF Normalized  

---

## 1. Relational Schema Representation (Formal Notation)

*In standard database notation, **bold and underline** denotes the **Primary Key (PK)**, and `(FK)` denotes a **Foreign Key** referencing another relation.*

1. **USERS** (**<u>user_id</u>**, name, email, phone, password, created_at)
2. **STATIONS** (**<u>station_id</u>**, station_name, station_code, city, state)
3. **TRAINS** (**<u>train_id</u>**, train_name, train_number, *source_station_id* `[FK->STATIONS]`, *destination_station_id* `[FK->STATIONS]`, running_days, total_seats)
4. **TRAIN_STOPS** (**<u>stop_id</u>**, *train_id* `[FK->TRAINS]`, *station_id* `[FK->STATIONS]`, sequence_no, arrival_time, departure_time, halt_duration, day_offset, distance_from_source)
5. **COACH_CLASSES** (**<u>class_id</u>**, class_code, class_name, fare_per_km)
6. **COACHES** (**<u>coach_id</u>**, *train_id* `[FK->TRAINS]`, coach_number, total_seats)
7. **SEATS** (**<u>seat_id</u>**, *train_id* `[FK->TRAINS]`, *coach_id* `[FK->COACHES]`, *class_id* `[FK->COACH_CLASSES]`, seat_number, berth_type, fare_per_km)
8. **TRAIN_RUNS** (**<u>run_id</u>**, *train_id* `[FK->TRAINS]`, run_date, journey_date, source_station, destination_station, ncr_status)
9. **BOOKINGS** (**<u>booking_id</u>**, *user_id* `[FK->USERS]`, *train_id* `[FK->TRAINS]`, *run_id* `[FK->TRAIN_RUNS]`, pnr, booking_status, refund_reward, booked_at)
10. **PASSENGERS** (**<u>passenger_id</u>**, *user_id* `[FK->USERS]`, name, age, gender, id_proof_type, id_proof_no)
11. **TICKETS** (**<u>ticket_id</u>**, *pnr_id* `[FK->BOOKINGS]`, *passenger_id* `[FK->PASSENGERS]`, *run_id* `[FK->TRAIN_RUNS]`, *seat_id* `[FK->SEATS]`, fare, cancellation, cancelled_at, refund_reward)
12. **PAYMENTS** (**<u>payment_id</u>**, *pnr_id* `[FK->BOOKINGS]`, amount, payment_mode, payment_status, transaction_ref, paid_by, paid_at)
13. **FEEDBACK** (**<u>feedback_id</u>**, *pnr_id* `[FK->BOOKINGS]`, *user_id* `[FK->USERS]`, rating, feedback_type, description, created_at, resolved_by_staff_id)
14. **TRAIN_LIVE_STATUS** (**<u>live_id</u>**, *train_id* `[FK->TRAINS]`, *run_id* `[FK->TRAIN_RUNS]`, *current_station_id* `[FK->STATIONS]`, *next_station_id* `[FK->STATIONS]`, *last_station_id* `[FK->STATIONS]`, next_arrival, next_departure, delay_minutes_next, current_status, last_updated_at)
15. **NOTIFICATIONS** (**<u>notification_id</u>**, *user_id* `[FK->USERS]`, message, type, is_read, created_at)

---

## 2. Referential Integrity & Foreign Key Mapping Matrix

| Dependent Table | Foreign Key Column | Referenced Table | Referenced Column | On Delete / Constraint |
|---|---|---|---|---|
| `trains` | `source_station_id` | `stations` | `station_id` | Enforced FK |
| `trains` | `destination_station_id` | `stations` | `station_id` | Enforced FK |
| `train_stops` | `train_id` | `trains` | `train_id` | Enforced FK |
| `train_stops` | `station_id` | `stations` | `station_id` | Enforced FK |
| `coaches` | `train_id` | `trains` | `train_id` | Enforced FK |
| `seats` | `train_id` | `trains` | `train_id` | Enforced FK |
| `seats` | `coach_id` | `coaches` | `coach_id` | Enforced FK |
| `seats` | `class_id` | `coach_classes` | `class_id` | Enforced FK |
| `train_runs` | `train_id` | `trains` | `train_id` | Enforced FK |
| `bookings` | `user_id` | `users` | `user_id` | Enforced FK |
| `bookings` | `train_id` | `trains` | `train_id` | Enforced FK |
| `bookings` | `run_id` | `train_runs` | `run_id` | Enforced FK |
| `passengers` | `user_id` | `users` | `user_id` | Enforced FK |
| `tickets` | `pnr_id` | `bookings` | `booking_id` | Enforced FK |
| `tickets` | `passenger_id` | `passengers` | `passenger_id` | Enforced FK |
| `tickets` | `run_id` | `train_runs` | `run_id` | Enforced FK |
| `tickets` | `seat_id` | `seats` | `seat_id` | Enforced FK |
| `payments` | `pnr_id` | `bookings` | `booking_id` | Enforced FK |
| `feedback` | `pnr_id` | `bookings` | `booking_id` | Enforced FK |
| `feedback` | `user_id` | `users` | `user_id` | Enforced FK |
| `train_live_status`| `train_id` | `trains` | `train_id` | Enforced FK |
| `train_live_status`| `run_id` | `train_runs` | `run_id` | Enforced FK |
| `train_live_status`| `current_station_id`| `stations` | `station_id` | Enforced FK |
| `train_live_status`| `next_station_id` | `stations` | `station_id` | Enforced FK |
| `train_live_status`| `last_station_id` | `stations` | `station_id` | Enforced FK |
| `notifications` | `user_id` | `users` | `user_id` | Enforced FK |

---

## 3. Functional Dependencies (FDs) & Normal Forms

### Key Functional Dependencies per Entity:

1. **USERS**:
   - `user_id` $\rightarrow$ `{name, email, phone, password, created_at}`
   - `email` $\rightarrow$ `{user_id, name, phone, password, created_at}`
   - *Normal Form:* **BCNF** (All determinants are candidate keys).

2. **STATIONS**:
   - `station_id` $\rightarrow$ `{station_name, station_code, city, state}`
   - `station_code` $\rightarrow$ `{station_id, station_name, city, state}`
   - *Normal Form:* **BCNF**

3. **TRAINS**:
   - `train_id` $\rightarrow$ `{train_name, train_number, source_station_id, destination_station_id, running_days, total_seats}`
   - `train_number` $\rightarrow$ `{train_id, train_name, ...}`
   - *Normal Form:* **BCNF**

4. **TRAIN_STOPS**:
   - `stop_id` $\rightarrow$ `{train_id, station_id, sequence_no, arrival_time, departure_time, halt_duration, day_offset, distance_from_source}`
   - `{train_id, sequence_no}` $\rightarrow$ `{station_id, arrival_time, ...}`
   - *Normal Form:* **BCNF**

5. **BOOKINGS**:
   - `booking_id` $\rightarrow$ `{user_id, train_id, run_id, pnr, booking_status, refund_reward, booked_at}`
   - `pnr` $\rightarrow$ `{booking_id, user_id, train_id, run_id, ...}`
   - *Normal Form:* **BCNF**

6. **TICKETS**:
   - `ticket_id` $\rightarrow$ `{pnr_id, passenger_id, run_id, seat_id, fare, cancellation, cancelled_at, refund_reward}`
   - `{run_id, seat_id}` $\rightarrow$ `{ticket_id, pnr_id, passenger_id}` *(No two active tickets can share the same seat on the same run)*.
   - *Normal Form:* **BCNF**

7. **FEEDBACK**:
   - `feedback_id` $\rightarrow$ `{pnr_id, user_id, rating, feedback_type, description, created_at, resolved_by_staff_id}`
   - Check constraint: $1 \le \text{rating} \le 5$.
   - *Normal Form:* **BCNF**
