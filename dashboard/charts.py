import json
import math
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
with open(CONFIG_DIR / "color_scheme.json") as f:
    COLOR_CONFIG = json.load(f)

def split_cross_midnight_sessions(df):
    split_rows = []

    for _, row in df.iterrows():
        start = row["start_time"]
        end = row["end_time"]

        if start.date() != end.date():
            # First segment: until 23:59:59 of start day
            end_of_day = datetime.combine(start.date(), datetime.max.time()).replace(hour=23, minute=59, second=59, microsecond=0)
            first_part = row.copy()
            first_part["end_time"] = end_of_day
            first_part["duration_sec"] = (end_of_day - start).total_seconds()
            split_rows.append(first_part)

            # Second segment: from 00:00:00 of next day
            next_day = datetime.combine(end.date(), datetime.min.time())
            second_part = row.copy()
            second_part["start_time"] = next_day
            second_part["duration_sec"] = (end - next_day).total_seconds()
            split_rows.append(second_part)
        else:
            split_rows.append(row)

    return pd.DataFrame(split_rows).reset_index(drop=True)

def generate_daily_timeline(df_day, selected_date):
    if df_day.empty:
        return go.Figure().update_layout(
            title="",
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            annotations=[
                dict(
                    text=f"No data for {_get_day_label(selected_date)}",
                    xref="paper", yref="paper",
                    showarrow=False,
                    font=dict(size=18)
                )
            ]
        )

    df_day = split_cross_midnight_sessions(df_day)
    fig = px.timeline(
        df_day,
        x_start="start_time",
        x_end="end_time",
        y=["Your Day"] * len(df_day),
        color="activity_id",
        color_discrete_map=COLOR_CONFIG['category_colors'],
        custom_data=["app", "title", "category", "duration_min"]
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]} | %{customdata[1]}</b><br>"
            "Category: %{customdata[2]}<br>"
            "Duration: %{customdata[3]:.1f} min<extra></extra>"
        )
    )
    fig.update_layout(
        margin=dict(l=80, r=100, t=30, b=40),
        title=f"",
        xaxis_title="Time of Day",
        yaxis_title="",
        height=200,
        showlegend=True,
        legend_title_text=""
    )
    selected_date_dt = pd.to_datetime(selected_date).normalize()
    fig.update_xaxes(
        range=[
            selected_date_dt,
            selected_date_dt + pd.Timedelta(hours=24)
        ],
        tickformat="%H:%M",
        dtick=7200000
    )
    fig.update_yaxes(showticklabels=False, autorange="reversed")
    return fig

def _get_day_label(selected_date_str: str) -> str:
    selected_date = datetime.fromisoformat(selected_date_str).date()
    return selected_date.strftime('%Y %b %d')

def _get_week_label(selected_date_str: str) -> str:
    selected_date = datetime.fromisoformat(selected_date_str).date()
    week_start = selected_date - timedelta(days=selected_date.weekday())
    week_end = week_start + timedelta(days=6)
    return f"{week_start.strftime('%Y %b %d')} – {week_end.strftime('%b %d')}"

def _format_minutes_with_hours(minutes: float) -> str:
    hours = minutes / 60
    if hours.is_integer():
        hours_str = f"{int(hours)}h"
    else:
        hours_str = f"{hours:.1f}h"
    return f"{int(minutes)}m ({hours_str})"

def _build_minute_ticks(max_minutes: float, step: int = 60):
    if max_minutes <= 0:
        max_minutes = step
    max_tick = int(math.ceil(max_minutes / step) * step)
    tickvals = list(range(0, max_tick + 1, step))
    ticktext = [_format_minutes_with_hours(v) for v in tickvals]
    return tickvals, ticktext

def generate_weekly_summary(df_week, selected_date):
    if df_week.empty:
        week_label = _get_week_label(selected_date)
        return go.Figure().update_layout(
            title="",
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            annotations=[
                dict(
                    text=f"No data for {week_label}",
                    xref="paper", yref="paper",
                    showarrow=False,
                    font=dict(size=18)
                )
            ]
        )

    df_week = split_cross_midnight_sessions(df_week)
    df = df_week.copy()
    df = df.sort_values("start_time")
    df["day_label"] = df["start_time"].dt.strftime("%a") # For Y-axis
    df["duration_min"] = df["duration_sec"] / 60

    # Convert to time-of-day anchored to the same dummy date (e.g., 2000-01-01)
    anchor_date = pd.Timestamp("2000-01-01")
    df["time_start"] = anchor_date + df["start_time"].dt.time.apply(lambda t: pd.Timedelta(hours=t.hour, minutes=t.minute, seconds=t.second))
    df["time_end"] = anchor_date + df["end_time"].dt.time.apply(lambda t: pd.Timedelta(hours=t.hour, minutes=t.minute, seconds=t.second))

    # Use productivity color only
    df["productivity"] = df["is_productive"].map({True: "productive", False: "unproductive"})

    fig = px.timeline(
        df,
        x_start="time_start",
        x_end="time_end",
        y="day_label",
        color="productivity",
        color_discrete_map=COLOR_CONFIG['productivity_colors'],
        hover_data=["app", "title", "start_time", "duration_min"],
        custom_data=["app", "title", "start_time", "duration_min"]
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]} | %{customdata[1]}</b><br>"
            "Start: %{customdata[2]|%H:%M}<br>"
            "Duration: %{customdata[3]:.1f} min<extra></extra>"
        )
    )
    fig.update_layout(
        margin=dict(l=80, r=100, t=30, b=40),
        title=f"{_get_week_label(selected_date)}",
        yaxis_title="",
        height=400,
        font=dict(size=12),
        showlegend=True,
    )
    fig.update_xaxes(
        tickformat="%H:%M",
        range=[anchor_date, anchor_date + pd.Timedelta(hours=24)],
        title_text="",
        showgrid=True,
        ticks="outside",
        tickangle=0,
        dtick=7200000
    )
    fig.update_yaxes(autorange="reversed")  # Earliest day on top

    return fig

def generate_cumulative_weekly_summary(df_week, selected_date):
    if df_week.empty:
        week_label = _get_week_label(selected_date)
        return go.Figure().update_layout(
            title="",
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            annotations=[
                dict(
                    text=f"No data for {week_label}",
                    xref="paper", yref="paper",
                    showarrow=False,
                    font=dict(size=18)
                )
            ]
        )

    df = split_cross_midnight_sessions(df_week)
    df["day_label"] = df["start_time"].dt.strftime("%a")
    df["date"] = df["start_time"].dt.date
    df["duration_min"] = df["duration_sec"] / 60
    df["productivity"] = df["is_productive"].map({True: "productive", False: "unproductive"})

    # Group by day + productivity
    summary = (
        df.groupby(["day_label", "date", "productivity"])["duration_min"]
        .sum()
        .reset_index()
    )

    fig = px.bar(
        summary,
        x="day_label",
        y="duration_min",
        color="productivity",
        custom_data=["date"],
        color_discrete_map=COLOR_CONFIG['productivity_colors'],
        labels={"duration_min": "Study Time (min)", "day_label": "Day"},
        category_orders={
            "day_label": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            "productivity": ["productive", "unproductive"]
        }
    )

    fig.update_traces(
        hovertemplate="%{x}: %{y:.2f} min<br>%{customdata[0]}"
    )
    max_total = (
        summary.groupby(["day_label", "date"])["duration_min"]
        .sum()
        .max()
    )
    max_total = 0 if pd.isna(max_total) else max_total
    tickvals, ticktext = _build_minute_ticks(max_total, step=60)

    fig.update_yaxes(
        tickmode="array",
        tickvals=tickvals,
        ticktext=ticktext,
        title="Minutes",
        rangemode="tozero",
        automargin=True
    )
    fig.update_layout(
        barmode="group",
        height=450,
        showlegend=True,
        margin=dict(l=80, r=100, t=30, b=40),
        yaxis_title="",
        xaxis_title="",
        font=dict(size=12),
        title_x=0.0,
        bargap=0.05
    )

    return fig

def generate_monthly_summary(df_month, selected_date):
    if df_month.empty:
        month_label = pd.to_datetime(selected_date).strftime('%Y %b')
        return go.Figure().update_layout(
            title="",
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            annotations=[
                dict(
                    text=f"No data for {month_label}",
                    xref="paper", yref="paper",
                    showarrow=False,
                    font=dict(size=18)
                )
            ]
        )

    df = split_cross_midnight_sessions(df_month)
    df = df.sort_values("start_time")
    df["date_label"] = df["start_time"].dt.strftime("%Y-%m-%d")
    df["duration_min"] = df["duration_sec"] / 60
    df["productivity"] = df["is_productive"].map({True: "productive", False: "unproductive"})

    # Convert to time-of-day anchored to the same dummy date (e.g., 2000-01-01)
    anchor_date = pd.Timestamp("2000-01-01")
    df["time_start"] = anchor_date + df["start_time"].dt.time.apply(lambda t: pd.Timedelta(hours=t.hour, minutes=t.minute, seconds=t.second))
    df["time_end"] = anchor_date + df["end_time"].dt.time.apply(lambda t: pd.Timedelta(hours=t.hour, minutes=t.minute, seconds=t.second))

    fig = px.timeline(
        df,
        x_start="time_start",
        x_end="time_end",
        y="date_label",
        color="productivity",
        color_discrete_map=COLOR_CONFIG['productivity_colors'],
        hover_data=["app", "title", "start_time", "duration_min"],
        custom_data=["app", "title", "start_time", "duration_min"]
    )

    fig.update_traces(
        hovertemplate="<b>%{customdata[0]} | %{customdata[1]}</b><br>"
                      "Start: %{customdata[2]|%H:%M}<br>"
                      "Duration: %{customdata[3]:.1f} min<extra></extra>"
    )
    fig.update_layout(
        margin=dict(l=80, r=100, t=30, b=40),
        title=f"{pd.to_datetime(selected_date).strftime('%Y %B')}",
        yaxis_title="",
        height=600,
        font=dict(size=12),
        showlegend=True
    )
    fig.update_xaxes(
        tickformat="%H:%M",
        range=[anchor_date, anchor_date + pd.Timedelta(hours=24)],
        title_text="",
        showgrid=True,
        ticks="outside",
        tickangle=0,
        dtick=7200000
    )
    fig.update_yaxes(autorange="reversed")
    return fig

def generate_cumulative_monthly_summary(df_month, selected_date):
    if df_month.empty:
        month_label = pd.to_datetime(selected_date).strftime('%Y %b')
        return go.Figure().update_layout(
            title="",
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            annotations=[
                dict(
                    text=f"No data for {month_label}",
                    xref="paper", yref="paper",
                    showarrow=False,
                    font=dict(size=18)
                )
            ]
        )

    df = split_cross_midnight_sessions(df_month)
    df["date"] = df["start_time"].dt.date
    df["day"] = df["start_time"].dt.day
    df["duration_min"] = df["duration_sec"] / 60
    df["productivity"] = df["is_productive"].map({True: "productive", False: "unproductive"})

    summary = (
        df.groupby(["day", "date", "productivity"])["duration_min"]
        .sum()
        .reset_index()
    )

    fig = px.bar(
        summary,
        x="day",
        y="duration_min",
        color="productivity",
        custom_data=["date"],
        color_discrete_map=COLOR_CONFIG['productivity_colors'],
        labels={"duration_min": "Study Time (min)", "day": "Day of Month"},
        category_orders={"productivity": ["productive", "unproductive"]}
    )

    fig.update_traces(
        hovertemplate="Day %{x}: %{y:.2f} min<br>%{customdata[0]}"
    )
    max_total = (
        summary.groupby(["day", "date"])["duration_min"]
        .sum()
        .max()
    )
    max_total = 0 if pd.isna(max_total) else max_total
    tickvals, ticktext = _build_minute_ticks(max_total, step=60)

    fig.update_yaxes(
        tickmode="array",
        tickvals=tickvals,
        ticktext=ticktext,
        title="Minutes",
        rangemode="tozero",
        automargin=True
    )
    fig.update_layout(
        barmode="group",
        height=450,
        showlegend=True,
        margin=dict(l=80, r=100, t=30, b=40),
        yaxis_title="",
        xaxis_title="",
        font=dict(size=12),
        title_x=0.0,
        bargap=0.05
    )
    return fig
