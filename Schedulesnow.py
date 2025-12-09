import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict, deque
from io import BytesIO
import random

# ==============================
# CONSTANTS
# ==============================

KM_LIMIT = 120.0
MAX_HOURS = 12.0
MAX_ZONE_DEPTH = 2

# NORMAL (GOOD WEATHER) – FIXED gaps as per your last message
NORMAL_GAP = {0: 10, 1: 15, 2: 20}   # distance → minutes

# SNOW MODE – randomized ranges (only when trip touches snowy zones)
SNOW_GAP_RANGES = {
    0: (10, 15),   # same zone
    1: (15, 20),   # 1-hop
    2: (20, 25)    # 2-hop
}

# Zones that trigger snow rules when involved in a link
SNOW_ZONES = {1, 2, 3, 4, 5, 6, 8, 10, 11, 13, 17, 30, 32, 34}

# ==============================
# HELPERS
# ==============================

def parse_time_str(s: str) -> datetime:
    return datetime.strptime(str(s).strip(), "%H:%M:%S")

def safe_read(file):
    file.seek(0)
    return BytesIO(file.read())

def load_trips(uploaded_file) -> pd.DataFrame:
    df = pd.read_csv(safe_read(uploaded_file))
    df["pickup_dt"] = df["First Pickup Time"].apply(parse_time_str)
    df["drop_dt"] = df["Last Dropoff Time"].apply(parse_time_str)
    df = df.sort_values("pickup_dt").reset_index(drop=True)
    return df

def load_zone_graph(uploaded_file) -> dict:
    file_bytes = safe_read(uploaded_file)
    if uploaded_file.name.lower().endswith(".csv"):
        zdf = pd.read_csv(file_bytes)
    else:
        zdf = pd.read_excel(file_bytes)

    neighbors = defaultdict(set)
    for _, row in zdf.iterrows():
        if pd.isna(row.get("Primary Zone")):
            continue
        p = int(row["Primary Zone"])
        neighbors[p].add(p)
        raw = "" if pd.isna(row.get("Backup Zones")) else str(row["Backup Zones"])
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                b = int(part)
                neighbors[p].add(b)
                neighbors[b].add(p)
    return dict(neighbors)

def zone_distance(neighbors: dict, start: int, target: int, max_depth: int = 2):
    start, target = int(start), int(target)
    if start == target:
        return 0
    visited = {start}
    q = deque([(start, 0)])
    while q:
        z, d = q.popleft()
        if d >= max_depth:
            continue
        for nb in neighbors.get(z, ()):
            if nb in visited:
                continue
            visited.add(nb)
            nd = d + 1
            if nb == target:
                return nd
            q.append((nb, nd))
    return None

# ==============================
# SCHEDULING
# ==============================

def build_schedules(trips: pd.DataFrame, neighbors: dict, snow_mode: bool) -> list:
    UNASSIGNED = set(trips.index)
    schedules = []
    sch_id = 1

    while UNASSIGNED:
        idx = min(UNASSIGNED, key=lambda i: trips.loc[i, "pickup_dt"])
        trip_indices = []
        total_km = 0.0
        first_pickup = trips.loc[idx, "pickup_dt"]

        while True:
            trip_indices.append(idx)
            UNASSIGNED.remove(idx)
            total_km += float(trips.loc[idx, "KM"])

            if total_km >= KM_LIMIT - 1e-6:
                break

            prev_drop_time = trips.loc[idx, "drop_dt"]
            prev_drop_zone = int(trips.loc[idx, "Last Dropoff Zone"])

            candidates = []

            for i in UNASSIGNED:
                pick_zone = int(trips.loc[i, "First Pickup Zone"])
                dist = zone_distance(neighbors, prev_drop_zone, pick_zone)
                if dist is None or dist > MAX_ZONE_DEPTH:
                    continue

                # ─── DETERMINE REQUIRED GAP ───
                snow_affected = snow_mode and (prev_drop_zone in SNOW_ZONES or pick_zone in SNOW_ZONES)
                if snow_affected:
                    min_gap = random.randint(*SNOW_GAP_RANGES[dist])
                else:
                    min_gap = NORMAL_GAP[dist]   # 10, 15 or 20 fixed

                min_pickup_time = prev_drop_time + timedelta(minutes=min_gap)
                if trips.loc[i, "pickup_dt"] < min_pickup_time:
                    continue

                # 12-hour rule
                if (trips.loc[i, "drop_dt"] - first_pickup).total_seconds() / 3600 > MAX_HOURS + 1e-6:
                    continue

                # KM rule
                if total_km + float(trips.loc[i, "KM"]) > KM_LIMIT + 1e-6:
                    continue

                candidates.append((i, trips.loc[i, "pickup_dt"]))

            if not candidates:
                break

            candidates.sort(key=lambda x: x[1])
            idx = candidates[0][0]

        schedules.append({"id": f"SCH-{sch_id:03d}", "trip_indices": trip_indices})
        sch_id += 1

    return schedules

# (build_summary and build_details unchanged except justification text updated below)

def build_summary(trips, schedules):
    rows = []
    for s in schedules:
        idxs = s["trip_indices"]
        km = sum(float(trips.loc[i, "KM"]) for i in idxs)
        rows.append({
            "Schedule_ID": s["id"],
            "Trip_Count": len(idxs),
            "Total_KM": round(km, 3),
            "Start_Time": min(trips.loc[i, "pickup_dt"] for i in idxs).strftime("%H:%M"),
            "End_Time": max(trips.loc[i, "drop_dt"] for i in idxs).strftime("%H:%M"),
        })
    return pd.DataFrame(rows)

def build_details(trips, schedules, neighbors, snow_mode):
    rows = []
    for s in schedules:
        sid = s["id"]
        idxs = s["trip_indices"]
        cum_km = 0.0
        for order, idx in enumerate(idxs, 1):
            run = trips.loc[idx, "TTM Number"]
            pickup = trips.loc[idx, "pickup_dt"]
            drop = trips.loc[idx, "drop_dt"]
            pzone = int(trips.loc[idx, "First Pickup Zone"])
            dzone = int(trips.loc[idx, "Last Dropoff Zone"])
            km = float(trips.loc[idx, "KM"])
            cum_km += km

            if order == 1:
                just = "First trip"
            else:
                prev_idx = idxs[order-2]
                prev_dzone = int(trips.loc[prev_idx, "Last Dropoff Zone"])
                prev_dtime = trips.loc[prev_idx, "drop_dt"]
                actual_gap = int((pickup - prev_dtime).total_seconds() / 60)
                dist = zone_distance(neighbors, prev_dzone, pzone)

                snow_link = snow_mode and (prev_dzone in SNOW_ZONES or pzone in SNOW_ZONES)
                if snow_link:
                    r = SNOW_GAP_RANGES[dist]
                    rule = f"{r[0]}–{r[1]} min (snow)"
                else:
                    rule = f"{NORMAL_GAP[dist]} min"

                just = f"{actual_gap} min gap · dist {dist} · {rule}"

            rows.append({
                "Schedule_ID": sid,
                "Trip Order": order,
                "Run Number": run,
                "Pickup Time": pickup.strftime("%H:%M"),
                "Pick Zone": pzone,
                "Dropoff Zone": dzone,
                "Dropoff Time": drop.strftime("%H:%M"),
                "Trip KM": round(km, 3),
                "Schedule Total KM": round(cum_km, 3),
                "Linkage Justification": just,
            })
    return pd.DataFrame(rows)

# ==============================
# STREAMLIT UI
# ==============================

st.title("Driver Schedule Builder – Winter 2025")

snow_mode = st.sidebar.checkbox("Snow Mode Active", value=True)
if snow_mode:
    st.sidebar.success("Snow gaps active on zones 1,2,3,4,5,6,8,10,11,13,17,30,32,34")
else:
    st.sidebar.info("Normal gaps: 10 min (dist 0) · 15 min (dist 1) · 20 min (dist 2)")

# Zone file cache
if "neighbors" not in st.session_state:
    st.session_state.neighbors = None

if st.session_state.neighbors is None:
    zfile = st.file_uploader("Upload zone file (CSV/XLSX) – upload once", type=["csv","xlsx"])
    if zfile:
        with st.spinner("Loading zones..."):
            st.session_state.neighbors = load_zone_graph(zfile)
        st.success("Zone graph cached!")
else:
    st.info("Zone graph loaded")
    if st.button("Reload zone file"):
        st.session_state.neighbors = None
        st.rerun()

trips_file = st.file_uploader("Upload today's trips CSV", type="csv")

if st.button("Build Schedules", type="primary") and trips_file and st.session_state.neighbors:
    with st.spinner("Building schedules..."):
        trips_df = load_trips(trips_file)
        schedules = build_schedules(trips_df, st.session_state.neighbors, snow_mode)
        summary = build_summary(trips_df, schedules)
        details = build_details(trips_df, schedules, st.session_state.neighbors, snow_mode)

    st.success(f"Generated {len(schedules)} schedules from {len(trips_df)} trips")

    st.subheader("Summary")
    st.dataframe(summary, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button("Summary CSV", summary.to_csv(index=False).encode(), "summary.csv", "text/csv")
    with c2:
        st.download_button("Details CSV", details.to_csv(index=False).encode(), "details.csv", "text/csv")
    with c3:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            summary.to_excel(writer, sheet_name="Summary", index=False)
            details.to_excel(writer, sheet_name="Details", index=False)
        st.download_button("Both as Excel", output.getvalue(), "schedules_full.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with st.expander("Full Details"):
        st.dataframe(details, use_container_width=True)

else:
    if not trips_file:
        st.info("Upload trips CSV")
    if not st.session_state.neighbors:
        st.info("Upload zone file first")

st.caption("Stay warm out there!")
