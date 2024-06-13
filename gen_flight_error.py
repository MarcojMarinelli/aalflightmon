#!/usr/bin/python3
# AAL Flight Monitor untility script
# Utility to insert an Error condition into the Database
# Note: Error condition will not exist after next  scrape run is  executed (as the data will be flagged as 'rolled' because it is  not on the AAL Website)
# Note: run "AAL-FlightMon.py -p json"  after insrting error, this will generate json structure with error details  (good gor testing into LM)
import sqlite3
import random
import string
import time
#import psycopg2
#from psycopg2 import sql
from datetime import datetime, timedelta
from configparser import ConfigParser

def insertError(filename,table, errorRow):
  
    # Connect to the database
    conn = sqlite3.connect(filename)
    cursor = conn.cursor()
  
    # Insert statement
    try:

        cursor.execute(f"INSERT INTO {table} (flight_number, origin, destination, departure_time, arrival_time, gate, status, day_appear, date_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ",
                 (errorRow[0], errorRow[1],errorRow[2], errorRow[3], errorRow[4], errorRow[5],errorRow[6],errorRow[7], errorRow[8] ))

        conn.commit()
    except:
        print(f"ERROR:  Inserting in DB File [{filename}]  Table [{table}] INSERT QUERY: [{errorRow[0]}]")
        exit(1)
    print(f"Succsess:  Inserting in DB File [{filename}]  Table [{table}] INSERT QUERY: [{errorRow[0]}]")

    # Close the DB
    cursor.close()
    conn.close()


def genDummyData():
    # Data to insert
    today = datetime.today()
    DOY = today.strftime('%j')

    # Generate a random 6-character flight number beginning with 'X'
    flight_number = 'X' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

    # ERROR condition - Current time minus 120 minutes
    date_calc = datetime.now() - timedelta(minutes=120)
    date_status = int(time.mktime(date_calc.timetuple()))

    dummyData = (
        flight_number,         # flight_number
        'OriginPlace',         # origin
        'DestinationPlace',    # destination
        '2024-06-08 12:00:00', # dummy departure_time 
        '2024-06-08 14:00:00', # dummy arrival_time
        '666',              # gate
        'Landed',              # status
        DOY,          
        date_status            # date_status
    )
    #print(f"Dummy Error data: [{dummyData}]")
    return dummyData


# Set up Config object
config = ConfigParser()
config.read("AAL_FlightMon.cfg")
database_file = config.get("global", "DBFile", fallback="")
table="arrivals"

errorEntry=genDummyData()
insertError(database_file, table, errorEntry)
print(f"Inserted Error row into database. Table [{table}] . Data [{errorEntry}]")


