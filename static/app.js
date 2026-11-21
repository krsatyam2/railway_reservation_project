const API = ""; // same origin

let selectedRating = 0;
let currentUser = null;

document.addEventListener("DOMContentLoaded", () => {
  const dateInput = document.getElementById("bdate");
  if (dateInput) {
    dateInput.valueAsDate = new Date();
  }
  loadStations();
  checkAuth();
});

function show(id) {
  document.querySelectorAll("main section").forEach(s => (s.style.display = "none"));
  const target = document.getElementById(id);
  if (target) target.style.display = "block";
  if (id === "home") updateHomeUserBanner();
  if (id === "book") {
    loadStations();
    updateBookingAuthNotice();
  }
  if (id === "mybookings") loadMyBookings();
  if (id === "auth") renderAuthSection();
}

async function loadStations() {
  try {
    const res = await fetch(`${API}/api/stations`);
    const stations = await res.json();
    const sel = (id) => {
      const el = document.getElementById(id);
      if (!el) return;
      const currentVal = el.value;
      el.innerHTML = stations.map(s => `<option value="${s.station_code}">${s.station_name} (${s.station_code})</option>`).join("");
      if (currentVal) el.value = currentVal;
    };
    sel("bsrc");
    sel("bdest");
    // Default different stations if both NDLS
    const destEl = document.getElementById("bdest");
    if (destEl && destEl.options.length > 1 && destEl.selectedIndex === 0) {
      destEl.selectedIndex = 1;
    }
  } catch (err) {
    console.error("Failed to load stations:", err);
  }
}

async function searchTrains() {
  const src = document.getElementById("bsrc").value;
  const dest = document.getElementById("bdest").value;
  const date = document.getElementById("bdate").value;
  const list = document.getElementById("trainlist");
  
  if (src === dest) {
    list.innerHTML = `<div class="result" style="color:#b91c1c;"><b>Please select two different stations for source and destination.</b></div>`;
    return;
  }

  list.innerHTML = "<p style='color:#0284c7;font-weight:600;'>Searching trains via RailRadar API & Database...</p>";
  
  try {
    const res = await fetch(`${API}/api/trains?source=${encodeURIComponent(src)}&dest=${encodeURIComponent(dest)}&date=${encodeURIComponent(date)}`);
    const trains = await res.json();
    
    if (res.status !== 200 || !trains || !trains.length) {
      list.innerHTML = `<div class="result">No trains found between ${src} and ${dest} on ${date}.</div>`;
      return;
    }

    let html = `<table>
      <thead>
        <tr>
          <th>Train</th>
          <th>Number</th>
          <th>Route</th>
          <th>Rating</th>
          <th>Source</th>
          <th>Days</th>
          <th>Seats</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>`;

    for (const t of trains) {
      const badge = t.source_api 
        ? `<span class="badge live">Live API</span>` 
        : `<span class="badge db">Seeded DB</span>`;
      
      const safeName = escapeHtml(t.train_name);
      const safeNum = escapeHtml(t.train_number);
      const ratingVal = t.rating ? t.rating : 4.8;
      const reviewsText = t.reviews_count ? `${t.reviews_count} reviews` : 'Initial';

      html += `<tr>
        <td><b>${safeName}</b></td>
        <td><code>${safeNum}</code></td>
        <td>${escapeHtml(t.source_name)} &rarr; ${escapeHtml(t.dest_name)}</td>
        <td>
          <span style="color:#f59e0b;font-weight:700;">★ ${ratingVal}</span><br>
          <small style="color:#64748b;">(${reviewsText})</small>
        </td>
        <td>${badge}</td>
        <td><small>${t.running_days}</small></td>
        <td>${t.total_seats}</td>
        <td><button class="btn" style="padding:6px 14px;font-size:13px;" onclick="bookTrain(${t.train_id}, '${safeName}', '${safeNum}')">Book</button></td>
      </tr>`;
    }
    html += "</tbody></table>";
    list.innerHTML = html;
  } catch (err) {
    list.innerHTML = `<div class="result" style="color:#b91c1c;">Error searching trains: ${err.message}</div>`;
  }
}

function bookTrain(train_id, train_name, train_number) {
  document.getElementById("btrain_id").value = train_id;
  document.getElementById("btraininfo").textContent = `— ${train_name} (${train_number})`;
  document.getElementById("bookingform").style.display = "block";
  document.getElementById("bookresult").innerHTML = "";

  // Auto-fill logged-in user details if available
  if (currentUser) {
    if (currentUser.name) document.getElementById("pname").value = currentUser.name;
    if (currentUser.phone) document.getElementById("pphone").value = currentUser.phone;
    if (currentUser.email) document.getElementById("pemail").value = currentUser.email;
  }

  document.getElementById("bookingform").scrollIntoView({ behavior: 'smooth' });
}

async function bookTicket(e) {
  e.preventDefault();
  const train_id = +document.getElementById("btrain_id").value;
  const date = document.getElementById("bdate").value;
  const tinfo = document.getElementById("btraininfo").textContent;
  const trainMatch = tinfo.match(/\(([^)]+)\)/);
  const tnum = trainMatch ? trainMatch[1] : "";
  
  const box = document.getElementById("bookresult");
  box.innerHTML = "<p style='color:#0284c7;font-weight:600;'>Processing reservation & assigning seat...</p>";

  // Resolve today's run_id via live status endpoint
  let run_id = null;
  try {
    const ls = await fetch(`${API}/api/live-status?train_number=${encodeURIComponent(tnum)}`);
    const lsd = await ls.json();
    if (lsd && lsd.run_id) run_id = lsd.run_id;
  } catch (err) {
    console.error("Live status error:", err);
  }

  if (!run_id) {
    box.innerHTML = `<div class="result" style="color:#b91c1c;">Could not resolve train schedule for ${date}. Please try again.</div>`;
    return;
  }

  const payload = {
    train_id,
    run_id,
    passenger_name: document.getElementById("pname").value.trim(),
    passenger_age: +document.getElementById("page").value,
    passenger_gender: document.getElementById("pgen").value,
    phone: document.getElementById("pphone").value.trim(),
    email: document.getElementById("pemail").value.trim(),
    id_proof_type: "Aadhaar",
    id_proof_no: document.getElementById("pid").value.trim() || "XXXX-XXXX-1234"
  };

  try {
    const res = await fetch(`${API}/api/book`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const d = await res.json();
    if (res.status !== 200) {
      box.innerHTML = `<div class="result" style="color:#b91c1c;">Booking failed: ${d.error || 'Server error'}</div>`;
      return;
    }

    box.innerHTML = `
      <div class="result" style="border-left: 4px solid #10b981;">
        <span class="status-badge ok" style="float:right;">${d.status}</span>
        <b>🎉 Booking Confirmed!</b><br>
        <b>PNR:</b> <span class="pnr">${d.pnr}</span><br>
        <b>Train:</b> ${escapeHtml(d.train_name)} (${escapeHtml(d.train_number)})<br>
        <b>Route:</b> ${escapeHtml(d.source)} &rarr; ${escapeHtml(d.destination)} &nbsp;|&nbsp; <b>Date:</b> ${d.date}<br>
        <b>Passenger:</b> ${escapeHtml(d.passenger)} &nbsp;|&nbsp; <b>Seat:</b> ${d.seat} &nbsp;|&nbsp; <b>Fare:</b> ₹${d.fare}
      </div>
      <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">
        <button class="btn" onclick="show('mybookings')">View in My Bookings</button>
        <button class="btn secondary" onclick="document.getElementById('tnum').value='${d.train_number}'; show('status'); checkStatus();">Check Live Status</button>
        <button class="btn secondary" onclick="openRating('${d.pnr}', '${escapeHtml(d.train_name)}')">Rate Precision</button>
        <button class="btn secondary" onclick="document.getElementById('pnrinput').value='${d.pnr}'; show('pnr'); checkPnr();">View PNR Details</button>
      </div>
    `;
    document.getElementById("bookform").reset();
  } catch (err) {
    box.innerHTML = `<div class="result" style="color:#b91c1c;">Network error: ${err.message}</div>`;
  }
}

async function checkStatus() {
  const tnum = document.getElementById("tnum").value.trim();
  if (!tnum) {
    alert("Please enter a train number (e.g. 12301, 12001)");
    return;
  }
  const box = document.getElementById("statusresult");
  const reviewsBox = document.getElementById("train-reviews-box");
  if (reviewsBox) reviewsBox.style.display = "none";
  box.innerHTML = "<p style='color:#0284c7;font-weight:600;'>Fetching live status and passenger ratings from database...</p>";

  try {
    const res = await fetch(`${API}/api/live-status?train_number=${encodeURIComponent(tnum)}`);
    const d = await res.json();
    if (res.status !== 200) {
      box.innerHTML = `<div class="result" style="color:#b91c1c;">Error: ${d.error || 'Failed to fetch status'}</div>`;
      return;
    }

    const badgeClass = d.delay_minutes > 0 ? "delay" : "ok";
    const badgeText = d.delay_minutes > 0 ? `${d.delay_minutes} min late` : "On time";
    const sourceBadge = d.source_api ? '<span class="badge live">Live RailRadar API</span>' : '<span class="badge db">Seeded DB Data</span>';

    const starsHtml = [1,2,3,4,5].map(i => `<span class="${i <= Math.round(d.precision_rating) ? 'active':''}">★</span>`).join("");

    box.innerHTML = `
      <div class="result" style="border-left: 4px solid #0284c7;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <b>${d.current_status}</b>
          <div>
            <span class="status-badge ${badgeClass}">${badgeText}</span>
            ${sourceBadge}
          </div>
        </div>
        <b>Train:</b> ${escapeHtml(d.train_name || ('Train ' + tnum))} (${tnum}) &nbsp;|&nbsp; <b>Run ID:</b> ${d.run_id}<br>
        <b>Previous Station:</b> ${escapeHtml(d.last_station)} &nbsp;|&nbsp; <b>Current Location:</b> ${escapeHtml(d.current_station)} &nbsp;|&nbsp; <b>Next Halt:</b> ${escapeHtml(d.next_station)}<br>
        <b>Next Arrival:</b> ${d.next_arrival} &nbsp;|&nbsp; <b>Next Departure:</b> ${d.next_departure}<br>
        <b>Delay:</b> ${d.avg_delay_minutes} min &nbsp;|&nbsp; <b>Precision & Passenger Rating:</b> <span style="font-weight:700;color:#f59e0b;font-size:15px;">★ ${d.precision_rating} / 5</span> <small style="color:#64748b;">(${d.total_reviews || 0} reviews)</small>
        <div class="stars" style="margin:8px 0 0 0;display:flex;">${starsHtml}</div>
      </div>
      <button class="btn" style="margin-top:12px;background:#f59e0b;" onclick="openRating(null, '${escapeHtml(d.train_name || 'Train ' + tnum)}', null, null, null, '${tnum}')">⭐ Rate This Train / Journey</button>
    `;

    // Fetch and show recent passenger reviews for this train
    loadTrainReviews(d.train_id);
  } catch (err) {
    box.innerHTML = `<div class="result" style="color:#b91c1c;">Network error: ${err.message}</div>`;
  }
}

async function loadTrainReviews(trainId) {
  const reviewsBox = document.getElementById("train-reviews-box");
  const reviewsList = document.getElementById("train-reviews-list");
  const countBadge = document.getElementById("train-reviews-count");
  if (!reviewsBox || !reviewsList || !trainId) return;

  try {
    const res = await fetch(`${API}/api/trains/${trainId}/feedback`);
    const data = await res.json();

    if (data.reviews && data.reviews.length > 0) {
      if (countBadge) countBadge.textContent = `${data.reviews.length} passenger review${data.reviews.length > 1 ? 's' : ''}`;
      let html = "";
      for (const rev of data.reviews) {
        const starStr = "★".repeat(rev.rating) + "☆".repeat(5 - rev.rating);
        html += `
          <div class="review-card">
            <div class="review-header">
              <div>
                <span class="review-passenger">👤 ${escapeHtml(rev.passenger_name || 'Passenger')}</span>
                <span class="review-badge" style="margin-left:6px;">${escapeHtml(rev.feedback_type || 'Journey')}</span>
              </div>
              <span class="review-stars">${starStr} (${rev.rating}/5)</span>
            </div>
            ${rev.description ? `<div class="review-body">"${escapeHtml(rev.description)}"</div>` : ''}
            <div class="review-date" style="margin-top:4px;">Date: ${rev.created_at || 'Recent'}</div>
          </div>
        `;
      }
      reviewsList.innerHTML = html;
      reviewsBox.style.display = "block";
    } else {
      reviewsBox.style.display = "none";
    }
  } catch (err) {
    console.error("Failed to load train reviews:", err);
  }
}

async function checkPnr() {
  const pnr = document.getElementById("pnrinput").value.trim().toUpperCase();
  if (!pnr) {
    alert("Please enter a valid PNR number");
    return;
  }
  const box = document.getElementById("pnrresult");
  box.innerHTML = "<p style='color:#0284c7;font-weight:600;'>Fetching booking details from SQLite database...</p>";

  try {
    const res = await fetch(`${API}/api/booking/${encodeURIComponent(pnr)}`);
    const d = await res.json();
    if (res.status !== 200) {
      box.innerHTML = `<div class="result" style="color:#b91c1c;">${d.error || 'PNR Not Found'}</div>`;
      return;
    }

    const feedbackNotice = d.has_feedback
      ? `<div style="margin-top:10px;padding:8px 12px;background:#fef3c7;border-radius:6px;border:1px solid #fde68a;">
           <b style="color:#b45309;">Your Journey Rating:</b> <span style="color:#b45309;font-weight:700;">★ ${d.user_rating} / 5 (${escapeHtml(d.feedback_type || 'Experience')})</span>
           ${d.user_comment ? `<br><small style="color:#78350f;">"${escapeHtml(d.user_comment)}"</small>` : ''}
         </div>`
      : '';

    const rateBtn = d.has_feedback
      ? `<button class="btn secondary" onclick="openRating('${d.pnr}', '${escapeHtml(d.train_name)}', ${d.user_rating}, '${escapeHtml(d.user_comment || '')}', '${escapeHtml(d.feedback_type || '')}')">Edit Review</button>`
      : `<button class="btn" style="background:#f59e0b;" onclick="openRating('${d.pnr}', '${escapeHtml(d.train_name)}')">⭐ Rate This Journey</button>`;

    box.innerHTML = `
      <div class="result" style="border-left: 4px solid #0284c7;">
        <span class="status-badge ok" style="float:right;">${d.status}</span>
        <b>PNR:</b> <span class="pnr">${d.pnr}</span><br>
        <b>Train:</b> ${escapeHtml(d.train_name)} (${escapeHtml(d.train_number)})<br>
        <b>Route:</b> ${escapeHtml(d.source)} &rarr; ${escapeHtml(d.destination)} &nbsp;|&nbsp; <b>Date:</b> ${d.date}<br>
        <b>Passenger:</b> ${escapeHtml(d.passenger || 'N/A')} &nbsp;|&nbsp; <b>Seat:</b> ${d.seat} &nbsp;|&nbsp; <b>Fare:</b> ₹${d.fare}<br>
        <b>Payment Status:</b> <span class="status-badge ok" style="padding:2px 6px;">${d.payment}</span> &nbsp;|&nbsp; <b>Booked At:</b> ${d.booked_at}
        ${feedbackNotice}
      </div>
      <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">
        <button class="btn secondary" onclick="document.getElementById('tnum').value='${d.train_number}'; show('status'); checkStatus();">Track Train Live Status</button>
        ${rateBtn}
      </div>
    `;
  } catch (err) {
    box.innerHTML = `<div class="result" style="color:#b91c1c;">Network error: ${err.message}</div>`;
  }
}

// ===================== FEEDBACK & RATING MODAL SYSTEM =====================

let modalCurrentRating = 5;

function openFeedbackModal(pnr, trainName, existingRating, existingComment, feedbackType, trainNumber) {
  openRating(pnr, trainName, existingRating, existingComment, feedbackType, trainNumber);
}

function openRating(pnr, trainName, existingRating, existingComment, feedbackType, trainNumber) {
  const modal = document.getElementById("feedback-modal");
  if (!modal) return;

  const pnrInput = document.getElementById("fb-pnr");
  const trainInput = document.getElementById("fb-train-info");
  const typeSelect = document.getElementById("fb-type");
  const commentText = document.getElementById("fb-comment");
  const submitBtn = document.getElementById("fb-submit-btn");
  const alertBox = document.getElementById("modal-feedback-alert");

  if (alertBox) alertBox.innerHTML = "";

  pnrInput.value = pnr || (trainNumber ? trainNumber : "");
  trainInput.value = trainName ? trainName : (trainNumber ? `Train ${trainNumber}` : "Selected Train");

  modalCurrentRating = existingRating ? Number(existingRating) : 5;
  renderModalStars();

  if (typeSelect && feedbackType) typeSelect.value = feedbackType;
  if (commentText) commentText.value = existingComment || "";

  if (submitBtn) {
    submitBtn.textContent = existingRating ? "Update Journey Rating" : "Submit Journey Rating";
  }

  modal.style.display = "flex";
}

function closeFeedbackModal() {
  const modal = document.getElementById("feedback-modal");
  if (modal) modal.style.display = "none";
}

function handleModalBackdropClick(e) {
  if (e.target && e.target.id === "feedback-modal") {
    closeFeedbackModal();
  }
}

function renderModalStars() {
  const container = document.getElementById("modal-stars");
  if (!container) return;
  container.innerHTML = "";

  const starDescriptions = [
    "",
    "1 - Poor (Delays / Major Issues)",
    "2 - Fair (Below Average)",
    "3 - Good (Average Experience)",
    "4 - Very Good (Punctual & Clean)",
    "5 - Excellent (Highly Recommended)"
  ];

  for (let i = 1; i <= 5; i++) {
    const s = document.createElement("span");
    s.textContent = "★";
    s.style.color = i <= modalCurrentRating ? "#f59e0b" : "#cbd5e1";
    s.style.transition = "color 0.15s";
    s.style.userSelect = "none";
    s.onclick = () => {
      modalCurrentRating = i;
      renderModalStars();
    };
    s.onmouseenter = () => {
      updateModalStarHover(i);
    };
    s.onmouseleave = () => {
      renderModalStars();
    };
    container.appendChild(s);
  }

  const descEl = document.getElementById("star-desc");
  if (descEl) descEl.textContent = starDescriptions[modalCurrentRating] || "";
}

function updateModalStarHover(hoverIdx) {
  const container = document.getElementById("modal-stars");
  if (!container) return;
  const spans = container.querySelectorAll("span");
  spans.forEach((span, idx) => {
    span.style.color = (idx + 1) <= hoverIdx ? "#f59e0b" : "#cbd5e1";
  });
}

async function submitFeedbackForm(e) {
  e.preventDefault();
  const pnrVal = document.getElementById("fb-pnr").value.trim().toUpperCase();
  const comment = document.getElementById("fb-comment").value.trim();
  const feedbackType = document.getElementById("fb-type").value;
  const alertBox = document.getElementById("modal-feedback-alert");

  if (!pnrVal) {
    alertBox.innerHTML = `<div class="alert alert-error">❌ Please enter a PNR or Train Number.</div>`;
    return false;
  }

  alertBox.innerHTML = "<p style='color:#0284c7;font-weight:600;'>Recording rating in SQLite feedback table & updating train precision...</p>";

  const payload = {
    rating: modalCurrentRating,
    comment: comment,
    feedback_type: feedbackType
  };

  // Determine if pnrVal is a PNR or train number
  if (pnrVal.startsWith("RR") || pnrVal.startsWith("PNR") || pnrVal.startsWith("FB") || pnrVal.length >= 8) {
    payload.pnr = pnrVal;
  } else {
    payload.train_number = pnrVal;
  }

  try {
    const res = await fetch(`${API}/api/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const d = await res.json();

    if (res.status !== 200) {
      alertBox.innerHTML = `<div class="alert alert-error">❌ ${escapeHtml(d.error || 'Submission failed')}</div>`;
      return false;
    }

    alertBox.innerHTML = `
      <div class="alert alert-success">
        ✔ <b>${escapeHtml(d.message)}</b><br>
        <span style="font-size:12px;color:#166534;">New Train Precision: <b>★ ${d.new_train_rating} / 5</b> (${d.total_reviews} reviews)</span>
      </div>
    `;

    setTimeout(() => {
      closeFeedbackModal();
      // If user is currently looking at My Bookings, refresh it!
      const myBookingsSec = document.getElementById("mybookings");
      if (myBookingsSec && myBookingsSec.style.display !== "none") {
        loadMyBookings();
      }
      // If user is on Live Status and checked this train, refresh status!
      const statusSec = document.getElementById("status");
      const tnumInput = document.getElementById("tnum");
      if (statusSec && statusSec.style.display !== "none" && tnumInput && tnumInput.value) {
        checkStatus();
      }
    }, 1200);
  } catch (err) {
    alertBox.innerHTML = `<div class="alert alert-error">❌ Network error: ${escapeHtml(err.message)}</div>`;
  }
  return false;
}

function escapeHtml(t) {
  if (!t) return "";
  return String(t).replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" })[c]);
}

// ===================== AUTH & SESSION MANAGEMENT (LOCAL SQLITE) =====================

async function checkAuth() {
  try {
    const res = await fetch(`${API}/api/auth/me`);
    const data = await res.json();
    if (res.status === 200 && data.authenticated && data.user) {
      currentUser = data.user;
    } else {
      currentUser = null;
    }
  } catch (err) {
    console.error("Auth check failed:", err);
    currentUser = null;
  }
  updateNavAuth();
  updateHomeUserBanner();
  updateBookingAuthNotice();
}

function updateNavAuth() {
  const loginBtn = document.getElementById("nav-login-btn");
  const userInfo = document.getElementById("nav-user-info");
  const userName = document.getElementById("nav-user-name");
  const myBookingsNav = document.getElementById("nav-mybookings");

  if (currentUser) {
    if (loginBtn) loginBtn.style.display = "none";
    if (userInfo) userInfo.style.display = "inline-flex";
    if (userName) userName.textContent = currentUser.name || "User";
    if (myBookingsNav) myBookingsNav.style.display = "inline-block";
  } else {
    if (loginBtn) loginBtn.style.display = "inline-block";
    if (userInfo) userInfo.style.display = "none";
    if (myBookingsNav) myBookingsNav.style.display = "none";
  }
}

function updateHomeUserBanner() {
  const el = document.getElementById("home-user-banner");
  if (!el) return;
  if (currentUser) {
    el.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
        <div>
          👋 <b>Hello, ${escapeHtml(currentUser.name)}!</b> You are logged in under User ID <code>#${currentUser.user_id}</code>.
          <br><small style="color:#475569;">All reservations made are linked to your profile in SQLite <code>database.sqlite</code>.</small>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button class="btn" style="padding:6px 14px;font-size:13px;" onclick="show('book')">Book a Ticket</button>
          <button class="btn secondary" style="padding:6px 14px;font-size:13px;margin:0;" onclick="show('mybookings')">My Bookings</button>
          <button class="btn secondary" style="padding:6px 14px;font-size:13px;margin:0;" onclick="show('auth')">View Profile</button>
        </div>
      </div>
    `;
    el.style.display = "block";
  } else {
    el.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
        <div>
          🔑 <b>DBMS Lab Demonstration Authentication Active</b><br>
          <small style="color:#475569;">Simple local authentication powered directly by SQLite's <code>users</code> table — no external database required.</small>
        </div>
        <div style="display:flex;gap:8px;">
          <button class="btn" style="padding:6px 14px;font-size:13px;" onclick="show('auth')">Sign In / Register</button>
        </div>
      </div>
    `;
    el.style.display = "block";
  }
}

function updateBookingAuthNotice() {
  const el = document.getElementById("book-auth-banner");
  if (!el) return;
  if (currentUser) {
    el.innerHTML = `👤 <b>Booking as: ${escapeHtml(currentUser.name)}</b> (<code>${escapeHtml(currentUser.email)}</code>) &bull; User ID: <code>#${currentUser.user_id}</code>. Ticket will be attached to your account.`;
    // Pre-fill fields if empty or holding defaults
    const pname = document.getElementById("pname");
    const pphone = document.getElementById("pphone");
    const pemail = document.getElementById("pemail");
    if (pname && (!pname.value || pname.value === "Full Name")) pname.value = currentUser.name || "";
    if (pphone && (!pphone.value || pphone.value === "9876543210")) pphone.value = currentUser.phone || "";
    if (pemail && (!pemail.value || pemail.value === "passenger@example.com")) pemail.value = currentUser.email || "";
  } else {
    el.innerHTML = `ℹ️ <b>Guest Mode:</b> You are not currently logged in. <a href="#" onclick="show('auth')" style="color:#0284c7;font-weight:600;text-decoration:underline;">Sign In or Register</a> to save tickets to your SQLite profile, or continue booking as guest.`;
  }
}

function switchAuthTab(tab) {
  const loginTab = document.getElementById("tab-login");
  const regTab = document.getElementById("tab-register");
  const loginBtn = document.getElementById("tab-login-btn");
  const regBtn = document.getElementById("tab-reg-btn");
  const alertBox = document.getElementById("auth-alert");

  if (alertBox) alertBox.innerHTML = "";

  if (tab === "register") {
    if (loginTab) loginTab.style.display = "none";
    if (regTab) regTab.style.display = "block";
    if (loginBtn) loginBtn.classList.remove("active");
    if (regBtn) regBtn.classList.add("active");
  } else {
    if (loginTab) loginTab.style.display = "block";
    if (regTab) regTab.style.display = "none";
    if (loginBtn) loginBtn.classList.add("active");
    if (regBtn) regBtn.classList.remove("active");
  }
}

function fillDemoCredentials() {
  const emailInput = document.getElementById("login-email");
  const pwdInput = document.getElementById("login-password");
  if (emailInput) emailInput.value = "demo@rail.in";
  if (pwdInput) pwdInput.value = "demo123";
}

function renderAuthSection() {
  const loggedInBox = document.getElementById("auth-logged-in-box");
  const formsBox = document.getElementById("auth-forms-box");
  const alertBox = document.getElementById("auth-alert");
  if (alertBox) alertBox.innerHTML = "";

  if (currentUser) {
    if (loggedInBox) loggedInBox.style.display = "block";
    if (formsBox) formsBox.style.display = "none";

    const uid = document.getElementById("profile-uid");
    const name = document.getElementById("profile-name");
    const email = document.getElementById("profile-email");
    const phone = document.getElementById("profile-phone");
    const created = document.getElementById("profile-created");

    if (uid) uid.textContent = currentUser.user_id;
    if (name) name.textContent = currentUser.name;
    if (email) email.textContent = currentUser.email;
    if (phone) phone.textContent = currentUser.phone || "N/A";
    if (created) created.textContent = currentUser.created_at || "N/A";
  } else {
    if (loggedInBox) loggedInBox.style.display = "none";
    if (formsBox) formsBox.style.display = "block";
    switchAuthTab("login");
  }
}

async function handleLogin(e) {
  e.preventDefault();
  const email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value;
  const alertBox = document.getElementById("auth-alert");

  alertBox.innerHTML = "<p style='color:#0284c7;font-weight:600;'>Authenticating against SQLite users table...</p>";

  try {
    const res = await fetch(`${API}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password })
    });
    const d = await res.json();

    if (res.status !== 200) {
      alertBox.innerHTML = `<div class="alert alert-error">❌ ${escapeHtml(d.error || 'Login failed')}</div>`;
      return;
    }

    currentUser = d.user;
    updateNavAuth();
    updateHomeUserBanner();
    updateBookingAuthNotice();
    renderAuthSection();

    alertBox.innerHTML = `<div class="alert alert-success">✔ ${escapeHtml(d.message)}</div>`;
    setTimeout(() => {
      show("mybookings");
    }, 800);
  } catch (err) {
    alertBox.innerHTML = `<div class="alert alert-error">❌ Network error: ${escapeHtml(err.message)}</div>`;
  }
}

async function handleRegister(e) {
  e.preventDefault();
  const name = document.getElementById("reg-name").value.trim();
  const email = document.getElementById("reg-email").value.trim();
  const phone = document.getElementById("reg-phone").value.trim();
  const password = document.getElementById("reg-password").value;
  const alertBox = document.getElementById("auth-alert");

  alertBox.innerHTML = "<p style='color:#0284c7;font-weight:600;'>Creating record in SQLite users table...</p>";

  try {
    const res = await fetch(`${API}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, email, phone, password })
    });
    const d = await res.json();

    if (res.status !== 200) {
      alertBox.innerHTML = `<div class="alert alert-error">❌ ${escapeHtml(d.error || 'Registration failed')}</div>`;
      return;
    }

    currentUser = d.user;
    updateNavAuth();
    updateHomeUserBanner();
    updateBookingAuthNotice();
    renderAuthSection();

    alertBox.innerHTML = `<div class="alert alert-success">✔ ${escapeHtml(d.message)}</div>`;
    setTimeout(() => {
      show("mybookings");
    }, 1000);
  } catch (err) {
    alertBox.innerHTML = `<div class="alert alert-error">❌ Network error: ${escapeHtml(err.message)}</div>`;
  }
}

async function logout() {
  try {
    await fetch(`${API}/api/auth/logout`, { method: "POST" });
  } catch (err) {
    console.error("Logout network error:", err);
  }
  currentUser = null;
  updateNavAuth();
  updateHomeUserBanner();
  updateBookingAuthNotice();
  show("auth");
  renderAuthSection();
  const alertBox = document.getElementById("auth-alert");
  if (alertBox) {
    alertBox.innerHTML = `<div class="alert alert-info">ℹ️ You have logged out successfully.</div>`;
  }
}

async function loadMyBookings() {
  const box = document.getElementById("mybookings-list");
  if (!box) return;

  if (!currentUser) {
    box.innerHTML = `
      <div class="result" style="border-left: 4px solid #f59e0b;">
        <b>Authentication Required:</b> Please <button class="btn" style="padding:4px 10px;font-size:12px;margin-left:6px;" onclick="show('auth')">Sign In</button> to view your booking history from the local SQLite database.
      </div>
    `;
    return;
  }

  box.innerHTML = "<p style='color:#0284c7;font-weight:600;'>Querying SQLite bookings & tickets tables for your User ID...</p>";

  try {
    const res = await fetch(`${API}/api/my-bookings`);
    const bookings = await res.json();

    if (res.status !== 200) {
      box.innerHTML = `<div class="result" style="color:#b91c1c;">Error: ${escapeHtml(bookings.error || 'Failed to fetch bookings')}</div>`;
      return;
    }

    if (!bookings || bookings.length === 0) {
      box.innerHTML = `
        <div class="result" style="text-align:center;padding:28px 16px;">
          <p style="font-size:16px;color:#64748b;margin:0 0 14px 0;">No reservations found in SQLite for <b>${escapeHtml(currentUser.name)}</b> (User ID: #${currentUser.user_id}).</p>
          <button class="btn" onclick="show('book')">🚆 Book Your First Ticket</button>
        </div>
      `;
      return;
    }

    let html = `<table>
      <thead>
        <tr>
          <th>PNR</th>
          <th>Train</th>
          <th>Route</th>
          <th>Journey Date</th>
          <th>Passenger</th>
          <th>Seat</th>
          <th>Fare</th>
          <th>Status</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>`;

    for (const b of bookings) {
      const safePnr = escapeHtml(b.pnr);
      const safeTrain = escapeHtml(b.train_name);
      const safeNum = escapeHtml(b.train_number);
      const safeRoute = `${escapeHtml(b.src_name || 'Origin')} &rarr; ${escapeHtml(b.dst_name || 'Destination')}`;

      html += `<tr>
        <td><span class="pnr" style="font-size:13px;">${safePnr}</span></td>
        <td><b>${safeTrain}</b><br><small style="color:#64748b;">${safeNum}</small></td>
        <td>${safeRoute}</td>
        <td>${b.run_date || 'N/A'}</td>
        <td>${escapeHtml(b.passenger_name || 'N/A')}<br><small style="color:#64748b;">Age ${b.age || '-'}, ${b.gender || '-'}</small></td>
        <td><b>${escapeHtml(b.seat_number || 'Auto')}</b></td>
        <td>₹${b.fare || 0}</td>
        <td><span class="status-badge ok">${escapeHtml(b.booking_status || 'Confirmed')}</span></td>
        <td>
          <button class="btn secondary" style="padding:4px 8px;font-size:12px;margin:2px;" onclick="document.getElementById('tnum').value='${safeNum}'; show('status'); checkStatus();" title="Track Live">Track</button>
          ${b.user_rating 
            ? `<span class="badge" style="background:#fef3c7;color:#b45309;display:block;margin:3px 0;">★ ${b.user_rating}/5 Rated</span>
               <button class="btn secondary" style="padding:3px 8px;font-size:11px;margin:2px;" onclick="openRating('${safePnr}', '${safeTrain}', ${b.user_rating}, '${escapeHtml(b.user_comment || '')}', '${escapeHtml(b.feedback_type || '')}')">Edit Review</button>`
            : `<button class="btn" style="padding:4px 8px;font-size:12px;margin:2px;background:#f59e0b;" onclick="openRating('${safePnr}', '${safeTrain}')">⭐ Rate Journey</button>`}
        </td>
      </tr>`;
    }

    html += `</tbody></table>`;
    box.innerHTML = html;
  } catch (err) {
    box.innerHTML = `<div class="result" style="color:#b91c1c;">Network error: ${escapeHtml(err.message)}</div>`;
  }
}
