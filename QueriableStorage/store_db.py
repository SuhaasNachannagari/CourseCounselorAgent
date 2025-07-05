import json
import sqlite3
import os

# --- Configuration ---
JSON_FILE_PATH = 'all_cleanedgrades.json'
NEW_DB_FILE_PATH = 'grades_improved.db'

def create_new_database():
    """
    Creates a new SQLite database, handling invalid data and duplicates gracefully.
    """
    if not os.path.exists(JSON_FILE_PATH):
        print(f"Error: JSON file not found at '{JSON_FILE_PATH}'")
        return

    if os.path.exists(NEW_DB_FILE_PATH):
        os.remove(NEW_DB_FILE_PATH)

    try:
        conn = sqlite3.connect(NEW_DB_FILE_PATH)
        cursor = conn.cursor()
        print(f"Successfully created and connected to '{NEW_DB_FILE_PATH}'.")

        create_table_query = """
        CREATE TABLE grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT NOT NULL, subject_desc TEXT,
            course_number INTEGER NOT NULL, title TEXT NOT NULL, academic_period TEXT NOT NULL,
            instructor TEXT, a_plus_pct REAL, a_pct REAL, a_minus_pct REAL, b_plus_pct REAL,
            b_pct REAL, b_minus_pct REAL, c_plus_pct REAL, c_pct REAL, c_minus_pct REAL,
            d_plus_pct REAL, d_pct REAL, d_minus_pct REAL, f_pct REAL,
            withdrawn_failing_pct REAL, gpa_estimate_normalized REAL,
            UNIQUE(subject, course_number, academic_period, instructor)
        );
        """
        cursor.execute(create_table_query)

        with open(JSON_FILE_PATH, 'r') as f:
            data = json.load(f)
        print(f"Loaded {len(data)} records from '{JSON_FILE_PATH}'. Starting cleaning and insertion...")

        records_to_insert = []
        
        # --- THIS IS THE NEW DE-DUPLICATION LOGIC ---
        seen_records_fingerprints = set() # A set to track unique records
        
        skipped_invalid_count = 0
        skipped_duplicate_count = 0

        for record in data:
            course_num_raw = record.get("Course Number")
            
            # First, handle invalid course numbers
            try:
                if course_num_raw is None:
                    skipped_invalid_count += 1
                    continue
                course_num_int = int(course_num_raw)
            except (ValueError, TypeError):
                print(f"  [!] WARNING (Invalid Data): Skipping record with bad Course Number: '{course_num_raw}'")
                skipped_invalid_count += 1
                continue
            
            # Second, handle duplicate records
            subject = record.get("Subject")
            academic_period = record.get("Academic Period")
            instructor = record.get("Instructor")
            
            # Create a unique "fingerprint" for this record
            fingerprint = (subject, course_num_int, academic_period, instructor)
            
            if fingerprint in seen_records_fingerprints:
                # We've seen this exact class section before, skip it
                # print(f"  [!] WARNING (Duplicate): Skipping duplicate record: {fingerprint}")
                skipped_duplicate_count += 1
                continue
            else:
                # If it's new, add fingerprint to the set and process the record
                seen_records_fingerprints.add(fingerprint)

            record_tuple = (
                subject, record.get("Subject Desc"), course_num_int, record.get("Title"),
                academic_period, instructor, record.get("a_plus_pct"), record.get("a_pct"),
                record.get("a_minus_pct"), record.get("b_plus_pct"), record.get("b_pct"),
                record.get("b_minus_pct"), record.get("c_plus_pct"), record.get("c_pct"),
                record.get("c_minus_pct"), record.get("d_plus_pct"), record.get("d_pct"),
                record.get("d_minus_pct"), record.get("f_pct"), record.get("withdrawn_failing_pct"),
                record.get("gpa_estimate_normalized")
            )
            records_to_insert.append(record_tuple)
        
        if records_to_insert:
            insert_query = """
            INSERT INTO grades (
                subject, subject_desc, course_number, title, academic_period, instructor,
                a_plus_pct, a_pct, a_minus_pct, b_plus_pct, b_pct, b_minus_pct,
                c_plus_pct, c_pct, c_minus_pct, d_plus_pct, d_pct, d_minus_pct,
                f_pct, withdrawn_failing_pct, gpa_estimate_normalized
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """
            cursor.executemany(insert_query, records_to_insert)
            print(f"\nSUCCESS: Inserted {cursor.rowcount} unique and valid records.")
        
        if skipped_invalid_count > 0:
            print(f"INFO: Skipped a total of {skipped_invalid_count} records due to invalid data.")
        if skipped_duplicate_count > 0:
            print(f"INFO: Skipped a total of {skipped_duplicate_count} duplicate records.")

        conn.commit()
        conn.close()
        print("Database migration complete. Connection closed.")

    except Exception as e:
        print(f"\n--> SCRIPT FAILED: An unexpected error occurred: {e}")

if __name__ == '__main__':
    create_new_database()