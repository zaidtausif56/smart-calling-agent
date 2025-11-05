import sqlite3
import pandas as pd
import os
import logging
import uuid
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

        # Create orders table with proper schema (using UUID for id)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                phone_number TEXT NOT NULL,
                product_name TEXT NOT NULL,
                quantity INTEGER DEFAULT 1,
                total_price REAL NOT NULL,
                delivery_address TEXT,
                order_status TEXT DEFAULT 'confirmed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        logger.info("Orders table created.")

    else:
        logger.info(f"Connected to existing database: {DATABASE_FILE}")
        
        # Migration: Add delivery_address column if it doesn't exist
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(orders)")
            columns = {col[1]: col[2] for col in cursor.fetchall()}  # {column_name: type}
            
            if 'delivery_address' not in columns:
                logger.info("Adding delivery_address column to orders table")
                conn.execute("ALTER TABLE orders ADD COLUMN delivery_address TEXT")
                conn.commit()
                logger.info("Migration completed: delivery_address column added")
            
            # Migration: Convert id column from INTEGER to TEXT (UUID)
            # Check if id column is INTEGER type
            if 'id' in columns and columns['id'].upper() == 'INTEGER':
                logger.info("Migrating orders table from INTEGER id to UUID...")
                
                # Create new orders table with UUID
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS orders_new (
                        id TEXT PRIMARY KEY,
                        phone_number TEXT NOT NULL,
                        product_name TEXT NOT NULL,
                        quantity INTEGER DEFAULT 1,
                        total_price REAL NOT NULL,
                        delivery_address TEXT,
                        order_status TEXT DEFAULT 'confirmed',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Copy data from old table to new table with UUID generation
                cursor.execute("SELECT id, phone_number, product_name, quantity, total_price, delivery_address, order_status, created_at FROM orders ORDER BY id")
                old_orders = cursor.fetchall()
                
                for old_order in old_orders:
                    new_uuid = str(uuid.uuid4())
                    conn.execute(
                        """INSERT INTO orders_new (id, phone_number, product_name, quantity, total_price, delivery_address, order_status, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (new_uuid, old_order[1], old_order[2], old_order[3], old_order[4], old_order[5], old_order[6], old_order[7])
                    )
                
                # Drop old table and rename new table
                conn.execute("DROP TABLE orders")
                conn.execute("ALTER TABLE orders_new RENAME TO orders")
                conn.commit()
                
                logger.info(f"Migration completed: Converted {len(old_orders)} orders to UUID format")
                
        except Exception as e:
            logger.exception(f"Migration error: {e}")

    return conn


# --- Database helpers ---

def get_db_connection():
    """Return the database connection. Initialize if needed."""
    global conn
    if conn is None:
        init_db()
    return conn


def query_inventory(sql, params=None):
    """Return a DataFrame for a SELECT query against inventory."""
    try:
        db_conn = get_db_connection()
        if params:
            return pd.read_sql_query(sql, db_conn, params=params)
        else:
            return pd.read_sql_query(sql, db_conn)
    except Exception as e:
        logger.exception(f"Inventory query failed: {e}")
        raise


def add_order(phone, product, qty, price, address=None):
    """Insert an order for a given phone number with delivery address. Returns the UUID of the new order."""
    try:
        db_conn = get_db_connection()
        
        # Ensure proper data types
        phone = str(phone).strip()
        product = str(product).strip()
        qty = int(qty)
        price = float(price)
        total = price * qty
        address = str(address).strip() if address else None
        
        # Generate UUID for the order
        order_id = str(uuid.uuid4())
        
        logger.info(f"Adding order: id={order_id}, phone={phone}, product={product}, qty={qty}, price={price}, total={total}, address={address}")
        
        db_conn.execute(
            """INSERT INTO orders (id, phone_number, product_name, quantity, total_price, delivery_address, order_status) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (order_id, phone, product, qty, total, address, "confirmed")
        )
        db_conn.commit()
        
        logger.info(f"Order successfully added for {phone}: {qty} x {product} = ₹{total} to {address} (ID: {order_id})")
        return order_id
        
    except Exception as e:
        logger.exception(f"Order insert failed: {e}")
        raise


def get_last_order(phone):
    """Fetch the most recent order for a phone number."""
    try:
        db_conn = get_db_connection()
        phone = str(phone).strip()
        cur = db_conn.execute(
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


def get_orders_by_phone(phone):
    """Fetch all orders for a phone number."""
    try:
        db_conn = get_db_connection()
        phone = str(phone).strip()
        cur = db_conn.execute(
            "SELECT * FROM orders WHERE phone_number = ? ORDER BY created_at DESC",
            (phone,)
        )
        rows = cur.fetchall()
        orders = [dict(row) for row in rows]
        logger.info(f"Found {len(orders)} orders for {phone}")
        return orders
    except Exception as e:
        logger.exception(f"Error fetching orders: {e}")
        return []


def store_otp(phone, otp):
    """Store OTP for a phone number with expiration time."""
    try:
        db_conn = get_db_connection()
        phone = str(phone).strip()
        
        # Create OTP table if it doesn't exist
        db_conn.execute("""
            CREATE TABLE IF NOT EXISTS otps (
                phone_number TEXT PRIMARY KEY,
                otp_code TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            );
        """)
        db_conn.commit()
        
        # Calculate expiration time (10 minutes from now)
        import datetime
        expires_at = datetime.datetime.now() + datetime.timedelta(minutes=10)
        
        # Delete any existing OTP for this phone number
        db_conn.execute("DELETE FROM otps WHERE phone_number = ?", (phone,))
        
        # Insert new OTP
        db_conn.execute(
            "INSERT INTO otps (phone_number, otp_code, expires_at) VALUES (?, ?, ?)",
            (phone, otp, expires_at)
        )
        db_conn.commit()
        logger.info(f"OTP stored for {phone}")
        return True
        
    except Exception as e:
        logger.exception(f"Error storing OTP: {e}")
        return False


def verify_otp_code(phone, otp):
    """Verify OTP code for a phone number."""
    try:
        db_conn = get_db_connection()
        phone = str(phone).strip()
        otp = str(otp).strip()
        
        import datetime
        now = datetime.datetime.now()
        
        cur = db_conn.execute(
            "SELECT otp_code, expires_at FROM otps WHERE phone_number = ?",
            (phone,)
        )
        row = cur.fetchone()
        
        if not row:
            logger.warning(f"No OTP found for {phone}")
            return False
        
        stored_otp = row['otp_code']
        expires_at = datetime.datetime.fromisoformat(row['expires_at'])
        
        # Check if OTP has expired
        if now > expires_at:
            logger.warning(f"OTP expired for {phone}")
            db_conn.execute("DELETE FROM otps WHERE phone_number = ?", (phone,))
            db_conn.commit()
            return False
        
        # Check if OTP matches
        if stored_otp == otp:
            logger.info(f"OTP verified successfully for {phone}")
            # Delete used OTP
            db_conn.execute("DELETE FROM otps WHERE phone_number = ?", (phone,))
            db_conn.commit()
            return True
        else:
            logger.warning(f"Invalid OTP for {phone}")
            return False
        
    except Exception as e:
        logger.exception(f"Error verifying OTP: {e}")
        return False


def update_order_status(order_id, phone, new_status):
    """Update the status of an order (only if it belongs to the phone number)."""
    try:
        db_conn = get_db_connection()
        order_id = str(order_id).strip()  # UUID as string
        phone = str(phone).strip()
        new_status = str(new_status).strip()
        
        # Verify the order belongs to this phone number
        cur = db_conn.execute(
            "SELECT id FROM orders WHERE id = ? AND phone_number = ?",
            (order_id, phone)
        )
        row = cur.fetchone()
        
        if not row:
            logger.warning(f"Order {order_id} not found for {phone}")
            return False
        
        # Update the status
        db_conn.execute(
            "UPDATE orders SET order_status = ? WHERE id = ?",
            (new_status, order_id)
        )
        db_conn.commit()
        logger.info(f"Order {order_id} status updated to {new_status}")
        return True
        
    except Exception as e:
        logger.exception(f"Error updating order status: {e}")
        return False


def delete_order(order_id, phone):
    """Delete an order (only if it belongs to the phone number)."""
    try:
        db_conn = get_db_connection()
        order_id = str(order_id).strip()  # UUID as string
        phone = str(phone).strip()
        
        # Verify the order belongs to this phone number before deleting
        result = db_conn.execute(
            "DELETE FROM orders WHERE id = ? AND phone_number = ?",
            (order_id, phone)
        )
        db_conn.commit()
        
        if result.rowcount > 0:
            logger.info(f"Order {order_id} deleted for {phone}")
            return True
        else:
            logger.warning(f"Order {order_id} not found for {phone}")
            return False
        
    except Exception as e:
        logger.exception(f"Error deleting order: {e}")
        return False
