import sqlite3

def execute_sql_query(db_path, query):
    """
    Execute a SQL query against a SQLite database and return the results.
    
    Args:
        db_path (str): Path to the SQLite database file
        query (str): SQL query to execute
    
    Returns:
        list: Query results as a list of rows
        None: If there's an error executing the query
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        conn.close()
        return results
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return None

if __name__ == "__main__":
    db_path = "nba.sqlite"
    
    # Get list of tables
    tables_query = "SELECT name FROM sqlite_master WHERE type='table';"
    tables = execute_sql_query(db_path, tables_query)
    print("Tables in database:", tables)
    
    # Sample query to read from a specific table
    sample_query = "SELECT * FROM player LIMIT 5;"
    players = execute_sql_query(db_path, sample_query)
    if players:
        print("\nFirst 5 players:", players)