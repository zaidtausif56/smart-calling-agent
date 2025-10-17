import sqlite3
import pandas as pd
import os
import logging
from config import DATABASE_FILE, PRODUCTS_CSV

logger = logging.getLogger("database")

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
        logger.info(f"Creating new database at {DATABASE_FILE}")

        # Create inventory table (seed from CSV if available)
        if os.path.exists(PRODUCTS_CSV):
            try:
                df = pd.read_csv(PRODUCTS_CSV)
                df.to_sql("inventory", conn, if_exists="replace", index=False)
                logger.info(f"Inventory table initialized from {PRODUCTS_CSV}")
            except Exception as e:
                logger.exception(f"Error loading CSV: {e}")
        else:
            logger.warning("Products.csv not found. Creating empty inventory table.")
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

        # Create orders table with proper schema
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number TEXT NOT NULL,
                product_name TEXT NOT NULL,
                quantity INTEGER DEFAULT 1,
                total_price REAL NOT NULL,
                order_status TEXT DEFAULT 'confirmed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        logger.info("Orders table created.")

    else:
        logger.info(f"Connected to existing database: {DATABASE_FILE}")

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
        logger.exception(f"Inventory query failed: {e}")
        raise


def add_order(phone, product, qty, price):
    """Insert an order for a given phone number."""
    try:
        # Ensure proper data types
        phone = str(phone).strip()
        product = str(product).strip()
        qty = int(qty)
        price = float(price)
        total = price * qty
        
        logger.info(f"Adding order: phone={phone}, product={product}, qty={qty}, price={price}, total={total}")
        
        conn.execute(
            """INSERT INTO orders (phone_number, product_name, quantity, total_price, order_status) 
               VALUES (?, ?, ?, ?, ?)""",
            (phone, product, qty, total, "confirmed")
        )
        conn.commit()
        
        logger.info(f"Order successfully added for {phone}: {qty} x {product} = ₹{total}")
        return True
        
    except Exception as e:
        logger.exception(f"Order insert failed: {e}")
        raise


def get_last_order(phone):
    """Fetch the most recent order for a phone number."""
    try:
        phone = str(phone).strip()
        cur = conn.execute(
            "SELECT * FROM orders WHERE phone_number = ? ORDER BY created_at DESC LIMIT 1",
            (phone,)
        )
        row = cur.fetchone()
        if row:
            order = dict(row)
            logger.info(f"Last order for {phone}: {order}")
            return order
        return None
    except Exception as e:
        logger.exception(f"Error fetching last order: {e}")
        return None
