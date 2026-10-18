# Adding a dataset

DataMind is completely dataset-agnostic. Supporting a new dataset requires only a semantic model YAML configuration file — **zero Python code changes**.

Below is the complete walkthrough demonstrated on our second dataset, **Chinook** (a digital media store database).

---

## The Real Walkthrough: Adding the Chinook Dataset

### 1. Obtain and prepare the data
We download the pinned Chinook SQLite database (`Chinook_Sqlite.sqlite`, pinned commit `7f67772503d71ba90f19283c38e93923addb43fa`, MIT licence) from `github.com/lerocha/chinook-database`:

```bash
python scripts/get_chinook.py
```
This script:
- Verifies the download against its pinned SHA-256 (`7651ba378ac2fcd0dfc3c66fb101f7a7eed3ba39a612ec642b96e20702061f15`).
- Connects strictly in read-only mode via Python's `sqlite3`.
- Exports each of the 11 tables to `data/chinook/*.csv` and `data/chinook/*.parquet` with normalized snake_case identifiers and parsed timestamps.

### 2. Create Snowflake schema and tables
Execute [`snowflake/10_chinook_setup.sql`](file:///Users/kanhaiya_mehta/DataMind/snowflake/10_chinook_setup.sql) in a Snowsight worksheet as `ACCOUNTADMIN`:
- Creates schema `DATAMIND_DB.CHINOOK` owned by `DATAMIND_ADMIN`.
- Creates 11 typed tables (`ALBUM`, `ARTIST`, `CUSTOMER`, `EMPLOYEE`, `GENRE`, `INVOICE`, `INVOICE_LINE`, `MEDIA_TYPE`, `PLAYLIST`, `PLAYLIST_TRACK`, `TRACK`).
- Configures CSV file format `CHINOOK_CSV_FORMAT` and internal stage `CHINOOK_STAGE`.
- Sets up Dynamic Data Masking (`MASK_PHONE`, `MASK_EMAIL`) for customer and employee personal details under `DATAMIND_RESTRICTED`.
- Grants `USAGE` and `SELECT` (including on `FUTURE TABLES`) to `DATAMIND_AGENT` and `DATAMIND_RESTRICTED`.

### 3. Stage and load the data
Execute the loader script to push local CSV files to the Snowflake internal stage and run `COPY INTO`:

```bash
python scripts/load_chinook.py --dry-run   # inspect generated PUT and COPY INTO statements
python scripts/load_chinook.py             # execute load under DATAMIND_ADMIN
```

### 4. Draft and refine the semantic model
Generate an initial draft using schema discovery:
```bash
python -m datamind draft-model --schema CHINOOK --name chinook --out config/datasets/chinook.yaml
```

Then hand-review and refine the configuration ([`config/datasets/chinook.yaml`](file:///Users/kanhaiya_mehta/DataMind/config/datasets/chinook.yaml)):
- **Descriptions and aliases:** Define business descriptions for each entity and column.
- **Role-playing tables:** The `EMPLOYEE` table plays two distinct roles:
  - `support_rep`: An employee assigned to handle customer support (`customer.support_rep_id -> support_rep.employee_id`).
  - `manager`: An employee who manages other employees (`employee.reports_to -> manager.employee_id`).
- **Many-to-many relationships:** `playlist_track` links `playlist` and `track` in a many-to-many relationship. It must **not** be modelled as a many-to-one join from `track` or `playlist`, which would cause fan-out double counting. Questions about playlists query `playlist_track` directly as the root table, joining upward to `playlist` and `track`. Questions about sales (`invoice_line`) do not join to playlists.
- **Verified metrics:** Define metrics with explicit grains and formulas, such as `sales = SUM(invoice_line.unit_price * invoice_line.quantity)`, `track_count`, `customer_count`, `invoice_count`.

### 5. Create the evaluation set
Write [`eval/chinook_dev.yaml`](file:///Users/kanhaiya_mehta/DataMind/eval/chinook_dev.yaml) with 20+ questions across all tiers (`single_table`, `join`, `multi_step`, `time`, `ambiguous`, `not_in_data`, `unsafe`) and hand-verified gold SQL targeting `DATAMIND_DB.CHINOOK.<TABLE>`.

### 6. Verify and test offline
Run the dedicated test suite and eval harness:
```bash
python -m pytest tests/test_chinook.py -v
python -m datamind check-gold --file eval/chinook_dev.yaml --independent duckdb
```

### 7. Run the application on the new dataset
Launch the Streamlit app targeting Chinook:
```bash
DATAMIND_DATASET=config/datasets/chinook.yaml SNOWFLAKE_SCHEMA=CHINOOK streamlit run app/streamlit_app.py
```
