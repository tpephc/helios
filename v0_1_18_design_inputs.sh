#!/usr/bin/env bash
# v0_1_18_design_inputs.sh — Run on nexus:~/projects/helios
set -euo pipefail
cd ~/projects/helios

echo "=== A. orders table schema ==="
uv run python -c "
import duckdb
conn = duckdb.connect('data/_storage/helios.duckdb', read_only=True)
for r in conn.execute('DESCRIBE orders').fetchall():
    print(r)
"

echo ""
echo "=== B. orders CHECK constraint + indexes ==="
uv run python -c "
import duckdb
conn = duckdb.connect('data/_storage/helios.duckdb', read_only=True)
# table info
for r in conn.execute(\"SELECT sql FROM duckdb_tables() WHERE table_name='orders'\").fetchall():
    print(r[0])
print()
for r in conn.execute(\"SELECT sql FROM duckdb_tables() WHERE table_name='positions'\").fetchall():
    print(r[0])
print()
print('--- indexes ---')
for r in conn.execute(\"SELECT index_name, sql FROM duckdb_indexes()\").fetchall():
    print(r)
"

echo ""
echo "=== C. positions CHECK constraint ==="
uv run python -c "
import duckdb
conn = duckdb.connect('data/_storage/helios.duckdb', read_only=True)
print(conn.execute(\"SELECT DISTINCT status FROM positions\").fetchall())
"

echo ""
echo "=== D. SCHEMA_SQL in database.py ==="
grep -n "CREATE TABLE\|account_id" data/database.py | head -30

echo ""
echo "=== E. order_journal.py query patterns ==="
grep -n "SELECT\|INSERT\|UPDATE\|DELETE\|WHERE" storage/order_journal.py | head -40

echo ""
echo "=== F. positions storage query patterns ==="
# Find the positions storage file
find . -name "*.py" -path "*/storage/*" | head -10
echo "---"
grep -rn "SELECT\|INSERT\|UPDATE\|DELETE\|WHERE" storage/ --include="*.py" | grep -i "position" | head -30

echo ""
echo "=== G. intraday_monitor position lookup ==="
grep -n "position\|account" scripts/intraday_monitor.py | head -20

echo ""
echo "=== H. reconcile_fills query patterns ==="
grep -n "SELECT\|INSERT\|UPDATE\|WHERE\|account" scripts/reconcile_fills.py 2>/dev/null | head -20 || \
grep -n "SELECT\|INSERT\|UPDATE\|WHERE\|account" execution/reconcile_fills.py 2>/dev/null | head -20 || \
echo "[reconcile_fills not found — check location]"

echo ""
echo "=== I. existing migration files ==="
ls -la data/migrations/ 2>/dev/null || echo "[no migrations dir]"

echo ""
echo "=== J. account_config.py full ==="
cat config/account_config.py

echo ""
echo "=== DONE ==="
