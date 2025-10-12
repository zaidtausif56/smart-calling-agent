import sqlite3
import pandas as pd
import os
from config import DATABASE_FILE, PRODUCTS_CSV

# Global connection (persistent within process)
conn = None


def init_db():
    """Initialize or connect to persistent SQLite DB.
    If database file doesn't exist, create it and seed from CSV.
    """
    global conn

    first_time = not os.path.exists(DATABASE_FILE)
    conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    if first_time:
        print(f"Creating new database at {DATABASE_FILE}")

        # Create inventory table (seed from CSV if available)
        if os.path.exists(PRODUCTS_CSV):
            try:
                df = pd.read_csv(PRODUCTS_CSV)
                df.to_sql("inventory", conn, if_exists="replace", index=False)
                print(f"Inventory table initialized from {PRODUCTS_CSV}")
            except Exception as e:
                print("Error loading CSV:", e)
        else:
            print("Products.csv not found. Creating empty inventory table.")
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

        # Create orders table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number TEXT,
                product_name TEXT,
                quantity INTEGER,
                total_price REAL,
                order_status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        print("Orders table created.")

    else:
        print(f"Connected to existing database: {DATABASE_FILE}")

    return conn


# --- Database helpers ---

def query_inventory(sql, params=None):
    """Return a DataFrame for a SELECT query against inventory."""
    try:
        if params:
            return pd.read_sql_query(sql, conn, params=params)
        else:
            return pd.read_sql_query(sql, conn)
    except Exception as e:
        print("Inventory query failed:", e)
        raise


def add_order(phone, product, qty, price):
    """Insert or update an order for a given phone number."""
    try:
        total = float(price) * int(qty)
        conn.execute(
            "INSERT INTO orders (phone_number, product_name, quantity, total_price, order_status) VALUES (?, ?, ?, ?, ?)",
            (phone, product, qty, total, "confirmed")
        )
        conn.commit()
        print(f"Order added for {phone}: {qty} x {product}")
    except Exception as e:
        print("Order insert failed:", e)
        raise


def get_last_order(phone):
    """Fetch the most recent order for a phone number."""
    try:
        cur = conn.execute(
            "SELECT * FROM orders WHERE phone_number = ? ORDER BY created_at DESC LIMIT 1",
            (phone,)
        )
        row = cur.fetchone()
        return dict(row) if row else None
    except Exception as e:
        print("Error fetching last order:", e)
        return None
