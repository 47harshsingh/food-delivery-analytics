"""Create the schema and bulk-load the CSVs into MySQL.

    python scripts/load_mysql.py --user root
    (password is prompted; or set MYSQL_PWD)

Needs local_infile enabled on the server:  SET GLOBAL local_infile = 1;
"""

import argparse
import getpass
import os
import time
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[1]
# load order respects foreign keys
TABLES = ["zones", "restaurants", "delivery_partners", "promotions", "customers", "orders", "order_items"]


def run_sql_file(cur, path):
    sql = Path(path).read_text(encoding="utf-8")
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    for stmt in "\n".join(lines).split(";"):
        if stmt.strip():
            cur.execute(stmt)


def load_table(cur, table, data_dir):
    path = (data_dir / f"{table}.csv").resolve().as_posix()
    header = (data_dir / f"{table}.csv").open(encoding="utf-8").readline().strip().split(",")
    set_clause = ""
    if table == "orders":
        # organic orders have an empty promo_id; it must load as NULL, not 0
        header = ["@promo_id" if c == "promo_id" else c for c in header]
        set_clause = "SET promo_id = NULLIF(@promo_id, '')"
    cols = ", ".join(header)
    cur.execute(f"""
        LOAD DATA LOCAL INFILE '{path}' INTO TABLE {table}
        CHARACTER SET utf8mb4
        FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
        LINES TERMINATED BY '\\n'
        IGNORE 1 LINES ({cols}) {set_clause}
    """)
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    loaded = cur.fetchone()[0]
    # LOAD DATA LOCAL turns bad rows into warnings instead of errors, so check the count
    with (data_dir / f"{table}.csv").open(encoding="utf-8") as f:
        expected = sum(1 for _ in f) - 1
    if loaded != expected:
        raise RuntimeError(f"{table}: loaded {loaded:,} of {expected:,} rows")
    return loaded


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=3306)
    ap.add_argument("--user", default="root")
    ap.add_argument("--data", default=str(ROOT / "data"))
    args = ap.parse_args()
    password = os.environ.get("MYSQL_PWD") or getpass.getpass("MySQL password: ")

    conn = pymysql.connect(host=args.host, port=args.port, user=args.user, password=password,
                           local_infile=True, autocommit=True)
    with conn.cursor() as cur:
        run_sql_file(cur, ROOT / "sql" / "01_schema.sql")
        cur.execute("SET foreign_key_checks = 0")
        for t in TABLES:
            t0 = time.time()
            n = load_table(cur, t, Path(args.data))
            print(f"{t:<18} {n:>9,} rows  ({time.time() - t0:.1f}s)")
        cur.execute("SET foreign_key_checks = 1")
        run_sql_file(cur, ROOT / "sql" / "02_views.sql")
    conn.close()


if __name__ == "__main__":
    main()
