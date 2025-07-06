import sqlite3
import os
from types import SimpleNamespace

# --- CONFIGURATION ---
DB_FILE = "grades_improved.db"

def query_gpa(args):
    """Constructs and executes a query to get the average GPA."""
    # This check is now more for internal validation, as the main loop ensures this.
    if not any([args.subject, args.number, args.instructor]):
        print("\nError: You must provide at least a subject, course number, or instructor for a GPA query.")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    query = "SELECT AVG(gpa_estimate_normalized) FROM grades WHERE 1=1"
    params = []
    
    # Build query based on provided arguments
    if args.subject:
        query += " AND subject = ?"
        params.append(args.subject.upper())
    if args.number:
        query += " AND course_number = ?"
        params.append(args.number)
    if args.instructor:
        query += " AND instructor LIKE ?"
        params.append(f'%{args.instructor}%')
    if args.year:
        query += " AND academic_period LIKE ?"
        params.append(f'%{args.year}%')
    if args.semester:
        query += " AND academic_period LIKE ?"
        params.append(f'{args.semester.capitalize()}%')
    
    # Execute the query
    cursor.execute(query, tuple(params))
    result = cursor.fetchone()[0]
    conn.close()

    # Print the results
    print("-" * 20)
    if result is not None:
        print(f"Query successful. Average GPA: {result:.2f}")
    else:
        print("No data found for the specified criteria.")
    print("-" * 20)


def query_title(args):
    """Constructs and executes a query to get a course title."""
    if not (args.subject and args.number):
        print("\nError: You must provide both a subject and number to get a course title.")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    query = "SELECT DISTINCT title FROM grades WHERE subject = ? AND course_number = ?"
    params = (args.subject.upper(), args.number)
    
    cursor.execute(query, params)
    result = cursor.fetchone()
    conn.close()
    
    print("-" * 20)
    if result:
        print(f"Query successful. Course Title: {result[0]}")
    else:
        print("No title found for that course.")
    print("-" * 20)


def get_user_input():
    """Gathers and validates all necessary inputs from the user."""
    print("\n--- New Query ---")
    print("Enter query details. Press Enter to skip any optional field.")

    subject = input("Enter subject (e.g., CS): ").strip()
    
    number_str = input("Enter course number (e.g., 18000): ").strip()
    number = None
    if number_str:
        try:
            number = int(number_str)
        except ValueError:
            print("Invalid input for course number. It will be ignored.")

    instructor = input("Enter instructor's last name: ").strip()

    year_str = input("Enter year (e.g., 2023): ").strip()
    year = None
    if year_str:
        try:
            year = int(year_str)
        except ValueError:
            print("Invalid input for year. It will be ignored.")
            
    semester = input("Enter semester (Fall, Spring, Summer): ").strip()
    if semester.capitalize() not in ['Fall', 'Spring', 'Summer', '']:
        print("Invalid semester. It will be ignored.")
        semester = ''

    # Create a namespace object that mimics the 'args' object from argparse
    args = SimpleNamespace(
        subject=subject or None,
        number=number or None,
        instructor=instructor or None,
        year=year or None,
        semester=semester or None
    )
    return args


def main():
    """Main function to run the interactive query loop."""
    if not os.path.exists(DB_FILE):
        print(f"Error: Database file '{DB_FILE}' not found in the current directory.")
        return

    while True:
        print("\n==============================================")
        print(" Purdue Grades Database Interactive Query")
        print("==============================================")
        
        query_type = input("What do you want to query? ('gpa', 'title', or 'exit' to quit): ").lower().strip()

        if query_type == 'exit':
            print("Exiting. Goodbye!")
            break
        elif query_type == 'gpa':
            args = get_user_input()
            query_gpa(args)
        elif query_type == 'title':
            args = get_user_input()
            query_title(args)
        else:
            print("\nInvalid choice. Please enter 'gpa', 'title', or 'exit'.")

if __name__ == "__main__":
    main()