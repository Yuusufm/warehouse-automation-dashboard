import pandas as pd
from pathlib import Path

# Folders
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"
CLEAN.mkdir(parents=True, exist_ok=True)

# Lookups for the codes the WMS spits out
SHIFTS = {"D": "Day", "E": "Evening"}
ERRORS = {"WI": "Wrong item", "WQ": "Wrong quantity", "WL": "Wrong label"}


def save(df, name):
    df.to_csv(CLEAN / name, index=False, date_format="%Y-%m-%d")
    print(f"  saved {name} ({len(df):,} rows)")


# Orders
orders = pd.read_csv(RAW / "wms_orders_export.csv", dtype={"ERR_CD": str})
before = len(orders)

# Remove rows that were exported twice
orders = orders.drop_duplicates()
dupes = before - len(orders)

# Remove qty typos (0 units)
bad_qty = (orders["QTY"] <= 0).sum()
orders = orders[orders["QTY"] > 0]

# Rename SAP-style columns to plain English
orders = orders.rename(columns={
    "ORD_NO": "OrderID", "ORD_DT": "OrderDate", "PRMS_DT": "PromisedDate",
    "SHIP_DT": "ShipDate", "SHIFT_CD": "Shift", "LN_CNT": "Lines",
    "QTY": "Units", "ERR_CD": "ErrorType",
})

# WMS exports dates as DD.MM.YYYY
for col in ["OrderDate", "PromisedDate", "ShipDate"]:
    orders[col] = pd.to_datetime(orders[col], format="%d.%m.%Y")

# Turn codes into words
orders["Shift"] = orders["Shift"].map(SHIFTS)
orders["ErrorType"] = orders["ErrorType"].map(ERRORS).fillna("No error")

# 1 = yes, 0 = no (so the average is the %)
orders["HasError"] = (orders["ErrorType"] != "No error").astype(int)
orders["OnTime"] = (orders["ShipDate"] <= orders["PromisedDate"]).astype(int)

# Early / On time / Late vs the promised date (early still counts as on time above)
orders["ShipStatus"] = "On time"
orders.loc[orders["ShipDate"] < orders["PromisedDate"], "ShipStatus"] = "Early"
orders.loc[orders["ShipDate"] > orders["PromisedDate"], "ShipStatus"] = "Late"

# Receipts (inbound deliveries)
receipts = pd.read_csv(RAW / "wms_receipts_export.csv")
receipts = receipts.rename(columns={
    "RCPT_NO": "ReceiptID", "VENDOR": "Vendor", "EXP_DT": "ExpectedDate",
    "RCV_TS": "ReceivedAt", "PUT_TS": "PutAwayAt", "LN_CNT": "Lines",
})
receipts["ExpectedDate"] = pd.to_datetime(receipts["ExpectedDate"], format="%d.%m.%Y")
for col in ["ReceivedAt", "PutAwayAt"]:
    receipts[col] = pd.to_datetime(receipts[col], format="%d.%m.%Y %H:%M")
receipts["ReceivedDate"] = receipts["ReceivedAt"].dt.normalize()

# Early / On time / Late vs the date the vendor promised
receipts["ArrivalStatus"] = "On time"
receipts.loc[receipts["ReceivedDate"] < receipts["ExpectedDate"], "ArrivalStatus"] = "Early"
receipts.loc[receipts["ReceivedDate"] > receipts["ExpectedDate"], "ArrivalStatus"] = "Late"

# Dock-to-stock = hours from truck unloaded to stock on the shelf
# (blank if it was never closed out in the system)
open_receipts = receipts["PutAwayAt"].isna().sum()
receipts["DockToStockHours"] = ((receipts["PutAwayAt"] - receipts["ReceivedAt"]).dt.total_seconds() / 3600).round(2)
receipts = receipts[["ReceiptID", "Vendor", "ExpectedDate", "ReceivedDate", "Lines",
                     "ArrivalStatus", "DockToStockHours"]]

# Automation backlog
tasks = pd.read_csv(RAW / "automation_backlog.csv")
tasks = tasks.rename(columns={
    "Task ID": "TaskID", "Automation Idea": "AutomationIdea", "Type": "AutomationType",
    "One-Time Cost": "OneTimeCost", "Est. Time Saved": "TimeSavedPct",
})

# "$9,500" -> 9500 and "60%" -> 0.60
tasks["OneTimeCost"] = tasks["OneTimeCost"].str.replace(r"[$,]", "", regex=True).astype(int)
tasks["TimeSavedPct"] = tasks["TimeSavedPct"].str.rstrip("%").astype(float) / 100

# Manual task log
log = pd.read_csv(RAW / "task_tracking_sheet.csv")
log = log.rename(columns={"Task ID": "TaskID", "Times Done": "Occurrences", "Minutes": "MinutesSpent"})
log["Date"] = pd.to_datetime(log["Date"])

# Fix ids typed like "t02 "
messy_ids = (log["TaskID"] != log["TaskID"].str.strip().str.upper()).sum()
log["TaskID"] = log["TaskID"].str.strip().str.upper()

# Drop days where minutes weren't filled in
missing_minutes = log["MinutesSpent"].isna().sum()
log = log.dropna(subset=["MinutesSpent"])
log["MinutesSpent"] = log["MinutesSpent"].astype(int)

# Hours per day each task takes (used for the payback math)
per_day = log.groupby("TaskID").agg(Minutes=("MinutesSpent", "sum"), Days=("Date", "nunique"))
per_day["HoursPerDay"] = (per_day["Minutes"] / 60 / per_day["Days"]).round(2)
tasks = tasks.merge(per_day["HoursPerDay"], left_on="TaskID", right_index=True)

# Date table (one row per calendar day)
dates = pd.DataFrame({"Date": pd.date_range(orders["OrderDate"].min(), orders["OrderDate"].max())})
dates["Year"] = dates["Date"].dt.year
dates["Month"] = dates["Date"].dt.strftime("%b %Y")
dates["MonthSort"] = dates["Year"] * 100 + dates["Date"].dt.month
dates["WeekStart"] = dates["Date"] - pd.to_timedelta(dates["Date"].dt.day_of_week, unit="D")

print("Cleaning summary")
print(f"  duplicate orders removed:  {dupes}")
print(f"  bad qty orders removed:    {bad_qty}")
print(f"  receipts never closed out: {open_receipts}")
print(f"  task ids fixed:            {messy_ids}")
print(f"  task rows w/o minutes:     {missing_minutes}")
print()

save(orders, "orders.csv")
save(receipts, "receipts.csv")
save(tasks, "manual_tasks.csv")
save(dates, "dates.csv")
