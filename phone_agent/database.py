# database.py
import sqlite3
import pandas as pd
from config import DATABASE_FILE, PRODUCTS_CSV
import os

# Create/connect persistent DB
conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
conn.row_factory = sqlite3.Row

def init_db():
    """Create inventory and orders tables, and populate inventory from CSV if present."""
    try:
        # Inventory table (replace with CSV contents)
        if os.path.exists(PRODUCTS_CSV):
            df = pd.read_csv(PRODUCTS_CSV)
            df.to_sql("inventory", conn, if_exists="replace", index=False)
        else:
            # If no CSV, create a minimal inventory table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                "Product Name" TEXT,
                Category TEXT,
                Brand TEXT,
                "Price in Rupees" REAL,
                Stock INTEGER,
                Description TEXT
            );
            """)
            conn.commit()

        # Orders table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            phone_number TEXT PRIMARY KEY,
            product_name TEXT,
            quantity INTEGER,
            total_price REAL,
            order_status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.commit()
    except Exception as e:
        print("DB init error:", e)

# --- Database helpers ---
def query_inventory(sql, params=None):
    """Return a pandas DataFrame for a select query against inventory.
       Use params for safe substitution where possible."""
    try:
        if params:
            return pd.read_sql_query(sql, conn, params=params)
        else:
            return pd.read_sql_query(sql, conn)
    except Exception as e:
        raise

def add_order(phone, product, qty, price):
    try:
        total = float(price) * int(qty)
        conn.execute(
            "REPLACE INTO orders (phone_number, product_name, quantity, total_price, order_status) VALUES (?, ?, ?, ?, ?)",
            (phone, product, qty, total, "confirmed")
        )
        conn.commit()
    except Exception as e:
        raise

def get_last_order(phone):
    cur = conn.execute("SELECT * FROM orders WHERE phone_number = ? ORDER BY created_at DESC LIMIT 1", (phone,))
    row = cur.fetchone()
    return dict(row) if row else None
