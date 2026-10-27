import numpy as np
import pandas as pd
from pathlib import Path

# Settings
SEED = 7
START = "2025-10-01"
END = "2026-09-30"
BASE_ORDERS = 260
RAW = Path(__file__).resolve().parents[1] / "data" / "raw"

# Ontario stat holidays (warehouse closed)
HOLIDAYS = [
    "2025-10-13", "2025-12-25", "2025-12-26", "2026-01-01", "2026-02-16",
    "2026-04-03", "2026-05-18", "2026-07-01", "2026-08-03", "2026-09-07",
]

# How busy each month is (1.0 = normal)
SEASON = {10: 1.10, 11: 1.25, 12: 0.95, 1: 0.85, 2: 0.90, 3: 1.00,
          4: 1.00, 5: 1.05, 6: 1.05, 7: 0.85, 8: 0.85, 9: 1.05}

# Mon is busiest, Fri is slowest
WEEKDAY = {0: 1.15, 1: 1.05, 2: 1.00, 3: 0.95, 4: 0.85}

# AI packing-slip capture went live (speeds up receiving)
DOC_CAPTURE_LIVE = "2026-02-02"

# Manual tasks team leads flagged + the automation idea for each
# per_day and minutes are only used to fake the task log
TASKS = [
    {"id": "T01", "task": "Shipping labels", "area": "Shipping",
     "idea": "Auto-print labels when an order is packed", "type": "Software",
     "cost": 9500, "est_saving": 0.60, "per_day": 90, "minutes": 2.5},
    {"id": "T02", "task": "Carrier booking", "area": "Shipping",
     "idea": "Send shipments to carriers automatically with Power Automate", "type": "Software",
     "cost": 7500, "est_saving": 0.85, "per_day": 60, "minutes": 3.0},
    {"id": "T03", "task": "Stock counts", "area": "Inventory",
     "idea": "Handheld scanners that update the WMS", "type": "Hardware",
     "cost": 6000, "est_saving": 0.50, "per_day": 40, "minutes": 4.0},
]

# Vendors: (chance they show up early, chance they show up late)
VENDORS = {
    "Contoso Industrial": (0.05, 0.06),
    "Fabrikam Electric": (0.08, 0.22),
    "Northwind Components": (0.10, 0.10),
    "Litware Plastics": (0.04, 0.15),
    "Proseware Steel": (0.06, 0.28),
    "Tailspin Packaging": (0.12, 0.08),
    "Wide World Fasteners": (0.07, 0.12),
    "Adventure Works Bearings": (0.05, 0.05),
}

rng = np.random.default_rng(SEED)
workday = pd.offsets.CustomBusinessDay(holidays=HOLIDAYS)
days = pd.date_range(START, END, freq=workday)
RAW.mkdir(parents=True, exist_ok=True)

# How busy each day is: season x weekday x slow growth x noise
busy = {}
for i, day in enumerate(days):
    growth = 1 + 0.08 * i / len(days)
    busy[day] = SEASON[day.month] * WEEKDAY[day.weekday()] * growth * rng.normal(1, 0.05)

# Orders
order_frames = []
next_order = 500001
for day in days:
    n = rng.poisson(BASE_ORDERS * busy[day])
    shift = np.where(rng.random(n) < 0.6, "D", "E")
    lines = 1 + rng.poisson(2.2, n)
    qty = lines * rng.integers(1, 7, n)

    # Busier days = more late shipments
    late_chance = 0.03 + max(0, busy[day] - 1) * 0.30
    days_late = np.where(rng.random(n) < late_chance, rng.integers(1, 3, n), 0)
    promised = day + workday
    ship_options = [promised + k * workday for k in range(3)]
    ship = [ship_options[k] for k in days_late]

    # Evening shift makes a few more mistakes
    err_mult = np.where(shift == "E", 1.3, 1.0)
    roll = rng.random(n) / err_mult
    err = np.select([roll < 0.010, roll < 0.018, roll < 0.031],
                    ["WI", "WQ", "WL"], default="")

    order_frames.append(pd.DataFrame({
        "ORD_NO": np.arange(next_order, next_order + n),
        "ORD_DT": day.strftime("%d.%m.%Y"),
        "PRMS_DT": promised.strftime("%d.%m.%Y"),
        "SHIP_DT": [d.strftime("%d.%m.%Y") for d in ship],
        "SHIFT_CD": shift,
        "LN_CNT": lines,
        "QTY": qty,
        "ERR_CD": err,
    }))
    next_order += n

orders = pd.concat(order_frames, ignore_index=True)

# Some on-time orders actually go out the same day (early)
on_time = orders["SHIP_DT"] == orders["PRMS_DT"]
early = on_time & (rng.random(len(orders)) < 0.15)
orders.loc[early, "SHIP_DT"] = orders.loc[early, "ORD_DT"]

# Mess it up like a real export: qty typos + rows exported twice
typos = orders.sample(frac=0.003, random_state=SEED).index
orders.loc[typos, "QTY"] = 0
orders = pd.concat([orders, orders.sample(frac=0.008, random_state=SEED + 1)])
orders = orders.sort_values("ORD_NO")
orders.to_csv(RAW / "wms_orders_export.csv", index=False)

# Inbound deliveries from vendors
receipt_rows = []
next_receipt = 700001
for day in days:
    for _ in range(rng.poisson(24 * busy[day])):
        vendor = rng.choice(list(VENDORS))
        early_chance, late_chance = VENDORS[vendor]

        # When it was supposed to show up vs the day it did
        roll = rng.random()
        if roll < early_chance:
            expected = day + int(rng.integers(1, 3)) * workday
        elif roll < early_chance + late_chance:
            expected = day - int(rng.integers(1, 4)) * workday
        else:
            expected = day

        # Dock-to-stock: faster after AI document capture, slower for surprise deliveries
        hours = 6.5 if day < pd.Timestamp(DOC_CAPTURE_LIVE) else 4.2
        if expected != day:
            hours += 1.5
        hours *= (0.85 + 0.15 * busy[day]) * rng.lognormal(0, 0.25)

        received = day + pd.Timedelta(minutes=7 * 60 + int(rng.integers(0, 7 * 60)))
        put_away = received + pd.Timedelta(hours=hours)
        # A few receipts never got closed out in the system
        put_text = put_away.strftime("%d.%m.%Y %H:%M") if rng.random() > 0.01 else ""

        receipt_rows.append({
            "RCPT_NO": next_receipt,
            "VENDOR": vendor,
            "EXP_DT": expected.strftime("%d.%m.%Y"),
            "RCV_TS": received.strftime("%d.%m.%Y %H:%M"),
            "PUT_TS": put_text,
            "LN_CNT": 1 + rng.poisson(6),
        })
        next_receipt += 1

pd.DataFrame(receipt_rows).to_csv(RAW / "wms_receipts_export.csv", index=False)

# Team leads' sheet tracking time spent on manual tasks
task_rows = []
for day in days:
    for t in TASKS:
        times = max(1, round(t["per_day"] * busy[day] * rng.normal(1, 0.10)))
        minutes = times * t["minutes"] * rng.normal(1, 0.08)

        # Typos in the task id + the odd blank
        task_id = t["id"]
        if rng.random() < 0.02:
            task_id = task_id.lower() + " "

        task_rows.append({
            "Date": day.strftime("%Y-%m-%d"),
            "Task ID": task_id,
            "Times Done": times,
            "Minutes": round(minutes) if rng.random() > 0.005 else None,
        })

pd.DataFrame(task_rows).to_csv(RAW / "task_tracking_sheet.csv", index=False)

# Automation backlog the CI team keeps in Excel
backlog_rows = []
for t in TASKS:
    backlog_rows.append({
        "Task ID": t["id"],
        "Task": t["task"],
        "Area": t["area"],
        "Automation Idea": t["idea"],
        "Type": t["type"],
        "One-Time Cost": f"${t['cost']:,}",
        "Est. Time Saved": f"{t['est_saving']:.0%}",
    })

pd.DataFrame(backlog_rows).to_csv(RAW / "automation_backlog.csv", index=False)

print(f"workdays:  {len(days)}")
print(f"orders:    {len(orders):,}")
print(f"receipts:  {len(receipt_rows):,}")
print(f"task log:  {len(task_rows):,}")
