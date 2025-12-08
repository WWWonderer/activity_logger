import argparse
import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path
from datetime import datetime

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

def month_file(year: int, month: int) -> Path:
    return LOG_DIR / f"activity_{year}_{month:02d}.parquet"

def read_month(year: int, month: int) -> pd.DataFrame:
    path = month_file(year, month)
    if not path.exists():
        raise FileNotFoundError(f"No log file for {year}-{month:02d}: {path}")
    return pd.read_parquet(path)

def get_last_n_rows(year: int, month: int, n: int = 1):
    """Read the last N rows efficiently using PyArrow."""
    path = month_file(year, month)
    if not path.exists():
        print(f"[no file] {path}")
        return None

    pf = pq.ParquetFile(path)
    if pf.num_row_groups == 0:
        print("[empty file]")
        return None

    rows_remaining = n
    dfs = []

    # Read row groups from the end backwards
    for rg_idx in reversed(range(pf.num_row_groups)):
        table = pf.read_row_group(rg_idx)
        num_rows = table.num_rows
        if num_rows == 0:
            continue

        if rows_remaining <= num_rows:
            # Take only needed rows from the end
            subset = table.slice(num_rows - rows_remaining, rows_remaining).to_pandas()
            dfs.append(subset)
            break
        else:
            dfs.append(table.to_pandas())
            rows_remaining -= num_rows

        if rows_remaining <= 0:
            break

    if not dfs:
        print("[no rows found]")
        return None

    # Since we collected from the end backward, reverse to restore order
    df_last = pd.concat(reversed(dfs), ignore_index=True)
    return df_last.tail(n)

def main():
    parser = argparse.ArgumentParser(description="Read monthly activity logs.")
    parser.add_argument("--year", type=int, help="Year of the log file (e.g., 2025)")
    parser.add_argument("--month", type=int, help="Month of the log file (1-12)")
    parser.add_argument("--last", type=int, nargs="?", const=1,
                        help="Print the last N rows (default: 1 if no number given)")
    args = parser.parse_args()

    # Default to current year/month
    if args.year is None or args.month is None:
        now = datetime.now()
        year, month = now.year, now.month
    else:
        year, month = args.year, args.month

    print(f"📘 Reading logs for {year}-{month:02d} ...")

    try:
        if args.last:
            df_last = get_last_n_rows(year, month, args.last)
            if df_last is not None:
                print(f"\nLast {len(df_last)} rows:\n")
                print(df_last)
        else:
            df = read_month(year, month)
            print(df.head())
            print(f"\nTotal rows: {len(df)}")
    except FileNotFoundError as e:
        print(e)

if __name__ == "__main__":
    main()
