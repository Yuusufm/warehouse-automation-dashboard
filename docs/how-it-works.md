# How It Works

A plain-English walkthrough of every part of this project: no coding background needed.

---

## 1. The big picture

The project runs in three steps:

1. **Make the data:** `scripts/generate_data.py` makes a year of fake but realistic warehouse data. It's messy on purpose, because real exports from SAP or a WMS always are.
2. **Clean the data:** `scripts/clean_data.py` fixes the mess and saves tidy tables.
3. **Show the data:** Power BI and the Streamlit web app both read the clean tables and turn them into charts.

Cleaning happens **once, in Python**, so Power BI and the web app always show the same numbers.

---

## 2. The tables

Think of each table as an Excel sheet. **"One row per ___"** is the most important thing to know about a table.

| Table | One row per… | Main columns |
|---|---|---|
| `orders` | customer order | OrderDate, Shift, ErrorType, HasError (1/0), OnTime (1/0), ShipStatus |
| `receipts` | delivery from a vendor | Vendor, ExpectedDate, ReceivedDate, ArrivalStatus, DockToStockHours |
| `manual_tasks` | manual job (3 total) | Task, AutomationIdea, OneTimeCost, TimeSavedPct, HoursPerDay |
| `dates` | calendar day | Month, MonthSort, WeekStart |

**Why 1 and 0 instead of Yes/No?** The average of a 1/0 column is the %. The average of `OnTime` = on-time %.

---

## 3. The scripts, block by block

### `generate_data.py`: makes the raw data

| Block | What it does |
|---|---|
| **Settings** | Date range (Oct 2025–Sep 2026), Ontario stat holidays, ~260 orders on a normal day |
| **SEASON / WEEKDAY** | How busy each month and weekday is. November is 25% busier than normal and Mondays are 15% busier |
| **TASKS** | The 3 manual jobs (shipping labels, carrier booking, stock counts), the automation idea for each, its cost, and how much time it should save |
| **VENDORS** | 8 vendors, each with its own chance of delivering early or late |
| **busy** | A "busyness score" for every workday = season × weekday × slow growth × a bit of randomness. Everything else uses this score |
| **Orders** | For each day, makes that day's orders. Busier days mean more late shipments. The evening shift makes a few more mistakes. Some orders ship the same day (early) |
| **Mess it up** | Adds duplicate rows and typo'd quantities, like a real export |
| **Receipts** | ~24 deliveries a day. Each gets an expected date (early, on time or late based on the vendor) and a dock-to-stock time. Dock-to-stock drops after AI packing-slip capture goes live in February, and surprise deliveries take longer |
| **Task log** | The team leads' daily sheet: how many times each manual job was done and how many minutes it took |
| **Backlog** | The automation list, saved like an Excel sheet would export it ("$9,500", "60%") |

`SEED = 7` means the "random" numbers come out the same every run, so results are repeatable.

### `clean_data.py`: fixes the mess

Each block is one cleaning step:

| Step | Problem | Fix |
|---|---|---|
| Remove duplicates | Some orders exported twice | `drop_duplicates()`: 529 removed |
| Remove bad qty | Orders with 0 units | Keep only Units > 0: 198 removed |
| Rename columns | SAP-style names like `LN_CNT` | Rename to `Lines`, etc. |
| Fix dates | WMS uses DD.MM.YYYY | Convert to real dates |
| Decode codes | `D`/`E`, `WI`/`WQ`/`WL` | Turn into Day/Evening, Wrong item, etc. |
| Ship status | Only dates | Compare ship date to promised date → Early / On time / Late |
| Arrival status | Only dates | Compare received date to expected date → Early / On time / Late |
| Dock-to-stock | Two timestamps | Put-away time − received time, in hours. Blank for 71 receipts never closed out |
| Money & % text | `"$9,500"`, `"60%"` | Turn into numbers 9500 and 0.60 |
| Task IDs | `"t02 "` | Trim + uppercase: 21 fixed |
| Missing minutes | Blank cells in the task sheet | Drop the row: 2 removed |
| Hours per day | A year of daily rows | For each job: total minutes ÷ 60 ÷ number of days, saved as `HoursPerDay` |
| Date table | Power BI needs one | One row per day with month and week columns |

---

## 4. The Power BI model (star schema)

```
        dates
     ┌────┴────┐
  orders    receipts          manual_tasks (on its own)
```

- **Fact tables** hold the events: `orders` and `receipts`.
- **Dimension table** `dates` describes when. Picking "November" in a slicer on `dates` filters both fact tables.
- `manual_tasks` stands alone. It's a short list of jobs, not something that happens on a date.

---

## 5. DAX in plain English

A **measure** is a formula that recalculates for whatever is selected (a month, a vendor, a task). All 12 are in [`powerbi/measures.dax`](../powerbi/measures.dax).

| DAX piece | Plain English | Example from this project |
|---|---|---|
| `COUNTROWS`, `SUM`, `AVERAGE` | Count rows / add up / average | `Total Orders = COUNTROWS(orders)` |
| `DIVIDE(a, b)` | a ÷ b, but blank instead of an error if b is 0 | `Late Delivery % = DIVIDE([Late Deliveries], [Total Receipts])` |
| `CALCULATE(measure, filter)` | "Same measure, but only where…" | `Late Deliveries` = Total Receipts where ArrivalStatus = "Late" |
| `SUMX(table, expression)` | Go row by row, work something out, add it up | `Savings per Year`: for each job, hours per day × 250 × % saved |

---

## 6. The automation math

There are only two steps.

**1. Where does the time go?**
Every day, team leads write down how many times each manual job was done and how many minutes it took in total.

Hours per day = total minutes on the job ÷ 60 ÷ number of days

| Job | Times a day | Minutes each | Hours a day |
|---|---|---|---|
| Shipping labels | ~92 | 2.5 | 3.8 |
| Carrier booking | ~61 | 3.0 | 3.1 |
| Stock counts | ~41 | 4.0 | 2.7 |

**2. What should we automate next?**
Each job has an automation idea with a price tag and an expected time saving. For each one, work out how long the savings take to pay back the cost. The shortest payback goes first.

Worked example: **Carrier booking** → send shipments to carriers automatically with Power Automate · costs $7,500 · expected to save 85% of the time

| Step | Math | Result |
|---|---|---|
| Hours per day today | from the task sheet | 3.06 hrs |
| Hours saved per year | 3.06 × 250 workdays × 85% | 650 hrs |
| Savings per year | 650 × $23 average wage | $14,955 |
| Savings per month | $14,955 ÷ 12 | $1,246 |
| Payback | $7,500 ÷ $1,246 | **6.0 months** |

Shipping labels take more time each day, but the label idea costs more ($9,500) and only saves 60%, so it pays back in 8.7 months. Stock counts are last at 9.2 months.

The estimate is **conservative**: it only counts labour time, not the cost of errors the automation also prevents.

---

## 7. The Streamlit app (`app.py`)

| Part | What it does |
|---|---|
| `load()` | Reads the clean CSVs once and caches them so the page is fast. It reloads if the files change |
| `show()` | One function that styles every chart the same way (colours, gridlines, fonts) |
| `mark_go_live()` | Draws the grey "went live" line on the dock-to-stock chart |
| Month filter | A range slider. It filters orders and receipts before any chart is drawn |
| Tabs | One block of code per page (3 pages). Each works out its numbers with pandas, then draws `st.metric` cards and Plotly charts |

Each pandas calculation matches a DAX measure, e.g. `o["OnTime"].mean()` in Python = `On-Time Ship %` in Power BI.

---

## 8. Glossary

| Term | Meaning |
|---|---|
| **WMS** | Warehouse Management System: software that tracks stock, orders and locations |
| **SAP / ERP** | Company-wide business system (orders, inventory, finance). WMS data often comes from or goes to it |
| **KPI** | Key Performance Indicator, a number that shows how well things are going |
| **Putaway** | Moving received stock to its storage location |
| **Dock-to-stock** | Hours from a delivery being unloaded to the stock being on the shelf and usable |
| **Carrier** | The shipping company that picks up the boxes (e.g. Purolator, UPS) |
| **Stock count** | Counting what's actually on a shelf to check it matches the system |
| **Payback period** | How long until savings cover the cost |
| **ROI** | Return on investment: what you get back compared to what you spent |
| **Star schema** | Fact tables in the middle, dimension tables around them |
| **Measure (DAX)** | A formula that recalculates for whatever's selected |
| **pandas / DataFrame** | Python's Excel: a DataFrame is a table you can filter, group and calculate on |
| **Power Automate** | Microsoft's tool for automating workflows (e.g. send data to a carrier website automatically) |

---

## 9. Limitations & next steps

- **The data is simulated.** Next step: point `clean_data.py` at real WMS/SAP exports. The cleaning steps are the same kind of fixes real data needs.
- **The wage is one average ($23/hr).** Real ROI would use each area's actual labour rate.
- **ROI counts labour only.** Adding the cost of each error (re-shipping, customer credits) would make the case stronger.
- **After an automation goes live,** compare the real time saved against the estimate to check it worked.
