import sqlite3
import os

# --- Configuration ---
# Make sure this is the correct name of your database file.
DB_FILENAME = "grades_improved.db"

def inspect_database_schema(db_path):
    """
    Connects to an SQLite database and prints the schema for all tables.
    """
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at '{db_path}'")
        return

    print(f"--- Inspecting Schema for: {db_path} ---\n")
    
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get a list of all tables in the database
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        if not tables:
            print("No tables found in this database.")
            return

        print(f"Found {len(tables)} tables: {[table[0] for table in tables]}\n")

        # For each table, get its schema
        for table_name_tuple in tables:
            table_name = table_name_tuple[0]
            print(f"--- Schema for table: '{table_name}' ---")
            
            # Use PRAGMA to get table info
            cursor.execute(f"PRAGMA table_info('{table_name}');")
            columns = cursor.fetchall()
            
            # Print column details
            print(f"{'CID':<5} {'Name':<25} {'Type':<15} {'Not Null':<10} {'Default Value':<15} {'Primary Key':<10}")
            print("-" * 90)
            for col in columns:
                cid, name, col_type, not_null, dflt_value, pk = col
                print(f"{cid:<5} {name:<25} {col_type:<15} {str(bool(not_null)):<10} {str(dflt_value):<15} {str(bool(pk)):<10}")
            print("\n")

    except sqlite3.Error as e:
        print(f"An SQLite error occurred: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    inspect_database_schema(DB_FILENAME)