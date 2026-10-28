import pandas as pd
import plotly.express as px
import streamlit as st
from pathlib import Path

DATA = Path(__file__).parent / "data" / "clean"
HOURLY_WAGE = 23  # average warehouse wage (assumption)
WORKDAYS_PER_YEAR = 250
AI_CAPTURE_LIVE = "2026-02-02"  # AI packing-slip capture went live

# Colours (same as the Power BI theme)
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
GREY = "#898781"
INK = "#0b0b0b"
GRID = "#e1e0d9"
STATUS_COLORS = {"Early": AQUA, "On time": BLUE, "Late": ORANGE}

st.set_page_config(page_title="Warehouse Ops Dashboard", page_icon="📦", layout="wide")


@st.cache_data
def load(updated):
    # updated = when the CSVs last changed, so new data isn't stuck in the cache
    orders = pd.read_csv(DATA / "orders.csv", parse_dates=["OrderDate", "PromisedDate", "ShipDate"])
    receipts = pd.read_csv(DATA / "receipts.csv", parse_dates=["ExpectedDate", "ReceivedDate"])
    tasks = pd.read_csv(DATA / "manual_tasks.csv")
    return orders, receipts, tasks


def show(title, fig, height=320):
    # Same clean look on every chart
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(color=INK),
        legend=dict(title_text="", orientation="h", yanchor="bottom", y=1.02, x=0),
        barcornerradius=4,
        bargap=0.35,
    )
    fig.update_xaxes(showgrid=False, linecolor="#c3c2b7", title_text="")
    fig.update_yaxes(gridcolor=GRID, zeroline=False, title_text="")
    fig.update_traces(marker_size=8, selector=dict(type="scatter"))
    fig.update_traces(marker_line_color="white", marker_line_width=1.5, selector=dict(type="bar"))
    st.markdown(f"**{title}**")
    st.plotly_chart(fig, width="stretch")


def mark_go_live(fig, date, text):
    # Grey line + label on the day an automation went live
    fig.add_vline(x=date, line_color=GREY, line_width=1)
    fig.add_annotation(x=date, y=1, yref="paper", text=text, showarrow=False, xanchor="left",
                       font=dict(color=GREY))


orders, receipts, tasks = load(max(f.stat().st_mtime for f in DATA.glob("*.csv")))

st.title("Warehouse Operations & Automation")
st.caption("Simulated data for a mid-sized distribution warehouse · Oct 2025 – Sep 2026")

# Month filter
months = pd.period_range(orders["OrderDate"].min(), orders["OrderDate"].max(), freq="M")
labels = [m.strftime("%b %Y") for m in months]
first, last = st.select_slider("Months", options=labels, value=(labels[0], labels[-1]),
                               help="Applies to the Shipping and Receiving pages")
start = months[labels.index(first)].start_time
end = months[labels.index(last)].end_time

o = orders[orders["OrderDate"].between(start, end)]
rc = receipts[receipts["ReceivedDate"].between(start, end)]

tab1, tab2, tab3 = st.tabs(["Shipping", "Receiving", "Automation"])

# ---------- Shipping ----------
with tab1:
    k = st.columns(3)
    k[0].metric("Orders", f"{len(o):,}")
    k[1].metric("On-Time Shipping", f"{o['OnTime'].mean():.1%}", help="Shipped on or before the promised date")
    k[2].metric("Order Accuracy", f"{1 - o['HasError'].mean():.1%}", help="Orders shipped with no mistakes")

    o = o.assign(Month=o["OrderDate"].dt.to_period("M").dt.to_timestamp())

    left, right = st.columns([2, 1])
    with left:
        monthly = o.groupby("Month").size().reset_index(name="Orders")
        fig = px.bar(monthly, x="Month", y="Orders", color_discrete_sequence=[BLUE])
        show("Orders by month", fig)
    with right:
        by_shift = o.groupby("Shift")["HasError"].mean().reset_index(name="Error Rate")
        fig = px.bar(by_shift, x="Shift", y="Error Rate", color_discrete_sequence=[BLUE])
        fig.update_yaxes(tickformat=".1%", hoverformat=".2%")
        show("Error rate by shift", fig)

    status = o.groupby(["Month", "ShipStatus"]).size().reset_index(name="Orders")
    # Each status as a share of that month's orders
    status["Share"] = status["Orders"] / status.groupby("Month")["Orders"].transform("sum")
    fig = px.bar(status, x="Month", y="Share", color="ShipStatus", color_discrete_map=STATUS_COLORS,
                 category_orders={"ShipStatus": list(STATUS_COLORS)})
    fig.update_yaxes(tickformat=".0%", hoverformat=".1%")
    show("Shipped early / on time / late", fig)
