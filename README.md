# Warehouse Operations & Automation Dashboard

A Power BI + Python dashboard for a warehouse ops team. Three pages: how shipping is going, how vendor deliveries are going, and which manual jobs are worth automating first.

It's built for team leads who track KPIs in Excel and still lose hours a day to manual work like hand-writing shipping labels.

**Live demo:** _coming soon_

## How to use it

- **Months:** drag the slider to pick a date range. The Shipping and Receiving pages update.
- **Hover** any chart to see exact values.
- The **grey line** on the dock-to-stock chart marks the day AI packing-slip capture went live.

The Automation page always uses the full year.

## Project structure

```
├── app.py                  Streamlit dashboard (live version)
├── scripts/
│   ├── generate_data.py    makes the raw data
│   └── clean_data.py       cleans it
├── data/
│   ├── raw/                messy exports
│   └── clean/              tables Power BI + the app read
├── powerbi/
│   ├── measures.dax        every DAX measure, commented
│   └── theme.json          colours / fonts
├── docs/how-it-works.md
└── screenshots/
```

## Run it yourself

```bash
pip install -r requirements.txt

python scripts/generate_data.py
python scripts/clean_data.py

streamlit run app.py
```
