# callbacks.py
from dash import Input, Output, no_update
import pandas as pd
import datetime
from datetime import timedelta
from pathlib import Path
from dashboard.charts import generate_daily_timeline, generate_weekly_summary, generate_cumulative_weekly_summary, generate_monthly_summary, generate_cumulative_monthly_summary

def load_data(selected_date, log_dir="logs"):
    def make_empty_log_df():
        return pd.DataFrame({
            "start_time":   pd.Series(dtype="datetime64[ns]"),
            "end_time":     pd.Series(dtype="datetime64[ns]"),
            "duration_sec": pd.Series(dtype="Int64"),   # nullable int
            "app":          pd.Series(dtype="string"),
            "title":        pd.Series(dtype="string"),
            "category":     pd.Series(dtype="string"),
            "is_productive":pd.Series(dtype="boolean"),
        })
    try:
        dt = datetime.date.fromisoformat(selected_date)

        # Gather all months in the week
        week_start = dt - datetime.timedelta(days=dt.weekday())
        months_in_week = set()
        for i in range(7):
            day = week_start + datetime.timedelta(days=i)
            months_in_week.add((day.year, day.month))

        # Load data from all relevant monthly files
        dfs = []
        log_root = Path(log_dir)
        for year, month in months_in_week:
            matched = sorted(log_root.glob(f"activity_{year}_{month:02d}*.parquet"))
            if not matched:
                month_label = datetime.date(year, month, 1).strftime('%B %Y')
                print(f"⚠️ No data file for {month_label} ({log_root})")
                continue

            for file_path in matched:
                try:
                    print(f"📄 Loading: {file_path}")
                    df = pd.read_parquet(file_path)
                    df["start_time"] = pd.to_datetime(df["start_time"])
                    df["end_time"] = pd.to_datetime(df["end_time"])
                    dfs.append(df)
                except Exception as exc:
                    print(f"❌ Failed to read {file_path}: {exc}")

        if not dfs:
            return make_empty_log_df()

        return pd.concat(dfs, ignore_index=True)

    except Exception as e:
        print(f"❌ Error loading data for {selected_date}: {e}")
        return make_empty_log_df()

def summarize_by_day(df, selected_date):
    selected_day = datetime.date.fromisoformat(selected_date)
    df_day = df[df["start_time"].dt.date == selected_day]
    return _prepare_summary(df_day)

def summarize_by_week(df, selected_date):
    dt = datetime.date.fromisoformat(selected_date)
    week_start = dt - datetime.timedelta(days=dt.weekday())
    week_end = week_start + datetime.timedelta(days=6)
    df_week = df[(df["start_time"].dt.date >= week_start) & (df["start_time"].dt.date <= week_end)]
    return _prepare_summary(df_week)

def summarize_by_month(df, selected_date):
    dt = datetime.date.fromisoformat(selected_date)
    return df[(df["start_time"].dt.month == dt.month) & (df["start_time"].dt.year == dt.year)]

def _prepare_summary(df_subset):
    if df_subset.empty:
        return df_subset

    df_subset = df_subset.sort_values("start_time")
    df_subset["productive"] = df_subset["is_productive"].apply(lambda x: "productive" if x else "unproductive")
    df_subset["duration_min"] = (df_subset["duration_sec"] / 60).round(1)
    df_subset["activity_id"] = df_subset["category"] + "|" + df_subset["productive"]
    return df_subset

def register_callbacks(app):    
    @app.callback(
        Output("daily-bar", "figure"),
        Output("weekly-timeline", "figure"),
        Output("weekly-bar", "figure"),
        Output("monthly-timeline", "figure"),
        Output("monthly-bar", "figure"),
        Input("date-picker", "date"),
    )
    def update_all_charts(selected_date):
        df_all = load_data(selected_date)
        df_day = summarize_by_day(df_all, selected_date)
        df_week = summarize_by_week(df_all, selected_date)
        df_month = summarize_by_month(df_all, selected_date)
        return (
            generate_daily_timeline(df_day, selected_date),
            generate_weekly_summary(df_week, selected_date), 
            generate_cumulative_weekly_summary(df_week, selected_date),
            generate_monthly_summary(df_month, selected_date),
            generate_cumulative_monthly_summary(df_month, selected_date)
        )

    @app.callback(
        Output("date-picker", "date"),
        Input("weekly-bar", "clickData"),
        prevent_initial_call=True
    )
    def update_date_from_weekly_click(clickData):
        try:
            full_date = clickData["points"][0]["customdata"][0]
            return full_date
        except Exception:
            return no_update
