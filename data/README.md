Local TPC-H Parquet files go here (generated, never committed):

    python scripts/make_local_tpch.py --scale 0.01   # tests
    python scripts/make_local_tpch.py --scale 1      # independent ground truth (same data as Snowflake TPCH_SF1)

They are used only for offline tests and for computing evaluation answers independently of Snowflake.
