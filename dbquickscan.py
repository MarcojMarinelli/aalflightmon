# Utility to sumerise DB file
#Reads AAL DB file and provides a summary of tables and data.
import sqlite3
from configparser import ConfigParser

def sumAALDB(filename):
  
  # Connect to the database
  conn = sqlite3.connect(filename)
  cursor = conn.cursor()
  
  # Get a list of all tables
  cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
  tables = [row[0] for row in cursor.fetchall()]
  
  # Print table summary
  print(f"Database: {filename}")
  print(f"Tables: ({len(tables)})")
  for table in tables:
    # Get a sample of data from each table (limit 5 rows)
    cursor.execute(f"SELECT * FROM {table} ")
    #cursor.execute(f"SELECT * FROM {table} LIMIT 5;")
    data = cursor.fetchall()
    
    # Print table name and sample data (if available)
    print(f"\t- {table}")
    if data:
      # Get column names
      column_names = [col[0] for col in cursor.description]
      # Print a sample row with column names
      print(f"\t\tSample Row: {', '.join(column_names)}")
      #print(f"\t\t\t{data[0]}")  # Print the first row as an example
      for row in data:
        print(f"\t\t\t{row}") 
    else:
      print(f"\t\t(No data available)")
  
  # Close the connection
  conn.close()

# Example usage

# Set up Config object
config = ConfigParser()
config.read("AAL_FlightMon.cfg")
database_file = config.get("global", "DBFile", fallback="")
sumAALDB(database_file)
