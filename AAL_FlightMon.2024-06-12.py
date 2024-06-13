#!/usr/bin/python3
################################################################################
#
#   A D E L A I D E    A I R P O R T S   -  F l i g h t  M o n i t o r 
#
#   Use : Use Selenium Grid to scrape AAL Flight info pages
#           1 - look for and report Flights that do not 'roll off' the page
#           2 - Generate JSON for consumption into LogicMonitor
#
#   Demo Script Only. Not to be used in a production enviornment
#
#   Marco Marinelli,  LogicMonitor,    marco.marinelli@logicmonitor.com
#   v Beta
##################################################################################
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from configparser import ConfigParser
from tabulate import tabulate
from datetime import datetime
from threading import Timer
import cgi
import json
import base64
from PIL import Image
import io
import time
import sqlite3
import os
import argparse
import json
import csv
import sys

class FlightDatabase:

    def __init__(self, config, mode):
        logger.info("FlightDatabase: init")
        self.config = config
        if self.config.get("global", "debug", fallback="False") == "True":
            self.debug = True
        else:
            self.debug = False
        self.mode = mode
        self.db_path = self.config.get("global", "DBFile", fallback="")
        self.conn = None
        self.cursor = None
        self.warn_after = self.config.get(mode, "warn_after", fallback=60)

        self.connect_to_db()


    def connect_to_db(self):
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
        except sqlite3.Error as e:
            logger.critical("Error connecting to database:", e)
            exit(1)
   

    def check_and_create_table(self):
        sql = f"""
           CREATE TABLE IF NOT EXISTS {self.mode} (
           flight_number TEXT NOT NULL,
           origin TEXT NOT NULL,
           destination TEXT NOT NULL,
           departure_time TEXT,
           arrival_time TEXT,
           gate TEXT,
           status TEXT,
           day_appear TEXT NOT NULL,
           date_status TIMESTAMP,
           date_Rolled TIMESTAMP,
           PRIMARY KEY (flight_number, day_appear)
           );
           """

        try:
            self.cursor.execute(sql)
        except sqlite3.OperationalError as e:
            if not "already exists" in str(e):  # Ignore "already exists" error
                logger.error(f"Error creating {self.mode} table:", e)
            return()
        else:
  	        logger.info(f"Table {self.mode} created (or already exists).")

	    # Commit changes to the database
        self.conn.commit()


    def updateDB(self,flight_data):
        #insert the flight_data into the arrivals table
        #Day of the year
        logger.info(f"updateDB: Inserting any new records into the {self.mode} table")
        today = datetime.today()
        DOY = today.strftime('%j')
        date_status = ""

        # Update mode table with any new AAL flight info
        for flight in flight_data:
            flight_number = flight["flight_number"]
            day_appear = DOY

            # Skip insertion if flight_number is null or an empty string
            if not flight_number:
                logger.info(f"updateDB: flight_data record seems empty, skip insertion. [{flight_number}]")
                continue

            # Check if the flight number + day_appear are already in the table
            self.cursor.execute(f" SELECT COUNT(*) FROM {self.mode} WHERE flight_number = ? AND day_appear = ?", (flight_number, day_appear))
            count = self.cursor.fetchone()[0]
            if not count == 0:
                logger.info(f"updateDB: flight_data record already exists in todays entries. [{flight_number}][{DOY}]")
                continue

            #Insert new Flight record into self.mode table
            logger.info(f"updateDB: NEW flight_data record being insetered into {self.mode} table. [{flight_number}][{DOY}]]")
            self.cursor.execute(f"INSERT OR IGNORE INTO {self.mode} (flight_number, origin, destination, departure_time, arrival_time, gate, status, day_appear) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ",
                    (flight_number, flight["origin"], flight["destination"], flight.get("departure_time"), flight.get("arrival_time"), flight.get("gate"),flight.get("status"), day_appear), )


            # AFTER First insert... check if new record has a Flights status, if so update entry with sttus &  timestamp into date_status
            if flight.get("status"):
                new_status=flight["status"]
                logger.info(f"updateDB: NEW flight_data record seems to have a 'status' , insert record with status and date_status. [{flight_number}][{DOY}][{new_status}]")
                date_status = int(time.time())
                self.cursor.execute(f" UPDATE {self.mode} SET status = ?, date_status = ? WHERE flight_number = ? AND day_appear = ?", (new_status,  int(time.time()), flight_number, day_appear),
                    )

        self.conn.commit()


    def flightStatusUpdate(self,flight_data):
        #Update the {mode} table with any Status changes
        today = datetime.today()
        DOY = today.strftime('%j')  # Day of the year
        logger.info(f"flightStatusUpdate: Updating Flight status into DB. Mode: {self.mode}")

        for flight in flight_data:
            flight_number = flight["flight_number"]
            day_appear = DOY
            time_appear=datetime.now()

            # Check if the flight exists and has a different status
            cursor = self.cursor  # Assuming cursor is available in the object's context
            cursor.execute(f" SELECT status FROM {self.mode} WHERE flight_number = ? AND day_appear = ?  ", (flight_number, day_appear),)
            fetched_data = cursor.fetchone()
            if fetched_data:  # Check if data is fetched
                existing_status = fetched_data[0]
                new_status=flight["status"]

                if existing_status != new_status:
                    # Update status and set date_status timestamp
                    cursor.execute( f" UPDATE {self.mode} SET status = ?, date_status = ?  WHERE flight_number = ? AND day_appear = ?  ", (new_status,  int(time.time()), flight_number, day_appear),)
                    logger.info(f"flightStatusUpdate: Flight {flight_number} Day [{day_appear}]. Status updated. Status; New[{new_status}] Old [{existing_status}] Time appear[{time_appear}]")
                    self.conn.commit()
                else:  # No change in status
                    logger.info(f"flightStatusUpdate: No Change in Status. Flight {flight_number} \tDay [{day_appear}]. Status; New[{new_status}] Old [{existing_status}]")
                          
            else:
                # Handle case where no data is found
                logger.info(f"flightStatusUpdate: Quesry returned NO data to update: Flight {flight_number} \tDay [{day_appear}]. ")
    
    def flagRolledEntries(self, flight_data):
        #Review arrivals table that no longer is represented in flight_data - assume the entry has been 'Rolled' off the Web sites displayed schedule
        today = datetime.today()
        DOY = today.strftime('%j')  # Day of the year
        logger.info(f"Updating Flight status into DB. mode {self.mode}")

      
        # Create a set of flight numbers from flight_data
        flight_numbers_set = {flight["flight_number"] for flight in flight_data}
    
        # Select all flight numbers from arrivals table for the current DOY
        self.cursor.execute(f"SELECT flight_number FROM {self.mode} WHERE day_appear = ?", (DOY,))
        existing_flight_numbers = {row[0] for row in self.cursor.fetchall()}

        # Find entries in DB but not in flight_data (rolled entries)
        rolled_entries = existing_flight_numbers - flight_numbers_set

        # Update date_rolled for rolled entries
        for flight_number in rolled_entries:
            self.cursor.execute(
                f"UPDATE {self.mode} SET date_rolled = ? WHERE flight_number = ? AND day_appear = ?",
                ( int(time.time()), flight_number, DOY),
            )
            logger.info(f"Flight {flight_number} (Day: {DOY}) marked as rolled.")
        self.conn.commit()

    def flightSummary(self):
        #Summarise the arrivals||departure table. Caluclate the time since a flights status was updated
        today = datetime.today()
        DOY = today.strftime('%j')  # Day of the year
        warn_after = self.warn_after
        mon_status = self.config.get(self.mode, "monStatus", fallback=20)
        logger.info(f"Summerising flight status. mode: {self.mode}")

        # Count total flights 
        self.cursor.execute(f"SELECT COUNT(*) FROM {self.mode} WHERE day_appear = ?", ( DOY,))
        total_flights = self.cursor.fetchone()[0]

        # Count scheduled flights 
        self.cursor.execute(f"SELECT COUNT(*) FROM {self.mode} WHERE status IN ('Delayed', 'Open','Final Call', '') AND day_appear = ? AND date_rolled IS NULL", ( DOY,))
        scheduled_flights = self.cursor.fetchone()[0]

        
        # Count landed flights 
        self.cursor.execute(f"SELECT COUNT(*) FROM {self.mode} WHERE status IN ('Landed','Early') AND day_appear = ? ", (DOY,))
        landed_flights = self.cursor.fetchone()[0]

        # Count departed flights 
        self.cursor.execute(f"SELECT COUNT(*) FROM {self.mode} WHERE status IN ('Departed') AND day_appear = ? ", (DOY,))
        departed_flights = self.cursor.fetchone()[0]

        # Get flight numbers that have a  status timestamp
        #self.cursor.execute( f"SELECT flight_number, date_status, date_rolled,  status FROM {self.mode} WHERE date_status IS NOT NULL AND day_appear = ? ", (DOY,))
        self.cursor.execute( f"SELECT flight_number, date_status, status FROM {self.mode} WHERE date_status IS NOT NULL AND day_appear = ? AND date_rolled IS NULL", (DOY,))
        flight_info_with_status = self.cursor.fetchall()

        # Count cancelled flights 
        self.cursor.execute(f"SELECT COUNT(*) FROM {self.mode} WHERE status = 'Cancelled' AND day_appear = ?", (DOY,))
        cancelled_flights = self.cursor.fetchone()[0]

        # Calculate time since status update for each flight
        current_time =  int(time.time())
        self.flights_flaged = []
        for flight_number, status_timestamp, status in flight_info_with_status:
            if status_timestamp is not None:  # Handle potential null values
                time_delta = current_time - status_timestamp
                minutes_since_update = int(time_delta / 60)
                logger.info(f"flightSummary: If update time without roll exceded then flag. [{minutes_since_update}] [{warn_after}]")
                if minutes_since_update > int(warn_after):
                    #Add to falgged flights - Only when Min Since Displayed exceeds the warning threshold
                    if status in mon_status:
                        # Only Flag for defined Status
                        logger.info(f"Flagged flight: {flight_number}.   Min {minutes_since_update}. warn_after {warn_after}. Status {status}")
                        #self.flights_flaged.append( {"flight_number": flight_number, "minutes_since_update": minutes_since_update, "status": status} )
                        self.flights_flaged.append( {"flight_number": flight_number, "minutes_since_update": minutes_since_update, "status": status} )

        # Prepare summary info formats
        if self.mode == "arrivals":
            self.table_data = [
                ["Landed ", landed_flights],
                ["Scheduled  ", scheduled_flights],
                ["Cancelled  ", cancelled_flights],
                ]
        
            # Prepare data for JSON output
            self.json_data = {
                "scheduled": scheduled_flights,
                "landed": landed_flights,
                "cancelled": cancelled_flights,
                "flights_web_display_errors": [],
                }
        else:
            self.table_data = [
                ["Departed ", departed_flights],
                ["Scheduled  ", scheduled_flights],
                ["Cancelled  ", cancelled_flights],
                ]
        
            # Prepare data for JSON output
            self.json_data = {
                "scheduled": scheduled_flights,
                "departed": departed_flights,
                "cancelled": cancelled_flights,
                "flights_web_display_errors": self.flights_flaged,
                }
            
        # Prepare data for flight info table (if flights_flagged has data)
        self.flight_info_data = []
        if self.flights_flaged:
            self.flight_info_data = [
                ["Flight Number", "Minutes Since Update"]
            ]  # Header row
            for flight in self.flights_flaged:
                truncflight = f"{flight['minutes_since_update']:.2f}"
                self.flight_info_data.append( [flight["flight_number"], truncflight]  )
                flight_info = {
                    "flight_number": flight["flight_number"],
                    "minutes_since_update": minutes_since_update,
                    "status": flight["status"],
                    }
                self.json_data["flights_web_display_errors"].append(flight_info)

 
            
    def printTable(self,format):
        # Print Flight table - several options CSV, HTML, Text
        logger.info(f"Flight data from DB: Table: {self.mode} Format:{format}")
        
         # set up
        today = datetime.today()
        DOY = today.strftime('%j') 
        self.cursor.execute(f"SELECT * FROM {self.mode} WHERE day_appear = ?", (DOY,))
        rows = self.cursor.fetchall()  # Fetch all rows as a list of tuples
        headers = [column_description[0] for column_description in self.cursor.description]
        
        #Test if json summary data available, if not generate it
        try:
            json_sum = self.json_data
        except:
            self.flightSummary()
            json_sum = self.json_data


        if not rows:
            logger.warning(f"printTable: No data found in the {self.mode} table.")
            return

        if format == "csv":
            filename = f"{today.strftime('%Y-%m-%d')}_{self.mode}.csv"
            with open(filename, 'w', newline='') as csvfile:
                csv_writer = csv.writer(csvfile)
                csv_writer.writerow(headers)
                csv_writer.writerows(rows)
            print(f"CSV file created: {filename}")
            return

        # For rows with a 'rolled' time, Calculate time since the last status update
        ##### This is where Emijan's problem can be tracked! ####
        updated_rows = []
        current_time =  int(time.time())
        for row in rows:
            date_status_ts = row[-2] if isinstance(row[-2], int) else None
            date_rolled_ts = row[-1] if isinstance(row[-1], int) else None

            #set up debug time stamp info
            if isinstance(date_status_ts,int):
                status_date_time = datetime.fromtimestamp(date_status_ts)
                status_formatted_date = status_date_time.strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(date_rolled_ts,int):
                rolled_date_time = datetime.fromtimestamp(date_rolled_ts)
                rolled_formatted_date = rolled_date_time.strftime("%Y-%m-%d %H:%M:%S")

            time_diff_mins = None
            if date_status_ts and date_rolled_ts:
               time_diff_mins = int((date_rolled_ts - date_status_ts) / 60)  # Convert to minutes
               logger.debug(f"printTable: Both date_stats and rolled_status exist. calc delta. Status [{date_status_ts}][{status_formatted_date}]. Rolled [{date_rolled_ts}][{rolled_formatted_date}] Delta[{time_diff_mins}]")
            elif date_status_ts:
               time_diff_mins = int((date_status_ts - current_time) / 60)  # Convert to minutes
               logger.debug(f"printTable: Only date_stats, No rolled_status exist. calc delta. Status [{date_status_ts}][{status_formatted_date}]. [{current_time}]. Delta[{time_diff_mins}]")
            updated_row = list(row)  # Create a copy to avoid modifying original
            updated_row.append(time_diff_mins)
            # Make output human readable, convert Unix time to H M S
            #for row_num in 8,9,10:
            for row_num in 8,9:
                if isinstance(updated_row[row_num], int):
                    time_string = datetime.fromtimestamp(updated_row[row_num])
                    HMS_string = time_string.strftime("%H:%M:%S")
                    updated_row[row_num] = HMS_string
                    logger.debug(f"printTable: Make Unix time readable. Row index [{row_num}][{time_string}]. HMS [{HMS_string}]")
            updated_rows.append(updated_row)

            headers.append("Time Delta (min)")


        if format == "html":
            # Generate HTML table
            sum_table_data = [(key.capitalize(), value) for key, value in json_sum.items() if key != 'flights_web_display_errors']
    
            html_table_style = " <style> table { border-collapse: collapse;  } th, td { border: 1px solid #ddd; padding: 8px; } tr:nth-child(even) {background-color: #f2f2f2;} </style>"

            #html_table_style = " <style> table { border-collapse: collapse; width: 100%; } th, td { border: 1px solid #ddd; padding: 8px; } tr:nth-child(even) {background-color: #f2f2f2;} </style>"
            html_table = tabulate(updated_rows, headers=headers, tablefmt="html")
            html_summary = tabulate(sum_table_data, headers=[self.mode, "Count"], tablefmt="html")
            html_content = f"""
            <h2>Flight Information ({self.mode}) - {today.strftime('%Y-%m-%d')}</h2>
            <p>Dump of AAL Flight Scraper Database. Table {self.mode}:</p>
            {html_table_style}
            {html_summary}
            <br>
            {html_table}
            """
            return html_content
        else:
            # Print the table using tabulate
            print(tabulate(updated_rows, headers=headers, tablefmt="grid"))
   


class FlightScraper:

    def __init__(self, config):
        self.config = config
        if self.config.get("global", "debug", fallback="False") == "True":
            self.debug = True
        else:
            self.debug = False
        self.verbose = True
        self.driver = None
        self.flight_data = []

        # Override grid_url with the environment variable if it exists
        grid_url = os.getenv('grid_url')
        if grid_url:
            self.grid_url = grid_url
            logger.info(f"FlightScraper init: Set Selenium Grid URL from ENV. grid_url [{grid_url}]")
        else:
            self.grid_url = self.config.get("global", "grid_url", fallback="ERROR GRID URL")
            logger.info(f"FlightScraper init: Set Selenium Grid URL from CFG File. grid_url [{grid_url}]")

        # Set up Chrome options
        self.options = Options()
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument('--disable-gpu')
        self.options.headless = False  # Set to False to use X11 forwarding
        #self.service=Service('/usr/bin/chromedriver') 
        self.conntect_to_database()

        logger.info(f"Class FlightScraper init mode: {self.mode}")
    
    def conntect_to_database(self):
        print("ERROR: This is a Base class and should not be directly instanuated")
        exit


    def open_browser(self):
        # Open a Browser session using Selenium Grid
        grid_url = self.grid_url
        chrome_options = self.options
        logger.info(f"open_browser: Open Browser session. mode: {self.mode} Grid URL: [{grid_url}]  URL [{self.url}]")
    
        # Create a new Chrome session
        try:
            self.driver = webdriver.Remote( command_executor=grid_url, options=chrome_options)
            logger.info(f"open_browser: Sucsessfully conneected to remote Selenium Grid [{grid_url}]")
        except:
            logger.critical(f"open_browser: ERROR attempting to establish Chrome via Selenium Grid[{self.grid_url}][{chrome_options}]")
            exit(1)

        #  Load a website
        try:
            self.driver.get(self.url)
        except:
            logger.error(f"open_browser: ERROR attempting to open Browser session to [{self.url}]")
            return
    
        # Print the title to the console
        logger.info(f"open_browser: Sucsessfully opened Browser session. Page title: [{self.driver.title}]")
    


    def wait_for_element(self, locator):
        WebDriverWait(self.driver, 10).until(EC.presence_of_element_located(locator))

    def scroll_down(self):
        #Scroll to the bottom of a Web page
        cnt = 0
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        while True:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)  # Wait for new content to load
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            cnt += 1
            if new_height == last_height:
                break
            last_height = new_height
        logger.info(f"scroll_down: Scrooled to end of page. Total scroll actions [{cnt}]")

    def close_browser(self):
        self.driver.quit()
        logger.info(f"close_broser: Closed Selenium Grid Browser session")

    def updateDB(self):
        #Insert newly fetched data into DB
        self.dataBase.updateDB(self.flight_data)

    def flightStatusUpdate(self):
        #Check newly fetched flight data for Flight status updates - and tag in DB
        self.dataBase.flightStatusUpdate(self.flight_data)


    def flagRolledEntries(self):
        # find flights that have "Rolled" off the AAL display and tag in DB
        self.dataBase.flagRolledEntries(self.flight_data)

    def printTable(self,format):
        return self.dataBase.printTable(format)

    def dumpFetch(self):
        if self.flight_data:
            for flight in self.flight_data:
                print(f"Flight Number: {flight['flight_number']}")
                print(f"Origin: {flight['origin']}")
                print(f"Destination: {flight['destination']}")
                print(f"Departure Time: {flight['departure_time']}")
                print(f"Arrival Time: {flight['arrival_time']}")
                print(f"Gate: {flight['gate']}")
                print(f"Status: {flight['status']}")
                print("-" * 20)
        else:
            print("No flight data found.")  

    def scrape_flight_info(self):
        try:
            self.wait_for_element((By.CLASS_NAME, 'SearchResultFlightListRow'))
        except TimeoutException:
            logger.info("Timeout waiting for flight data. No flight data available.")
            return
        
        search_results = self.driver.find_elements(By.CLASS_NAME, 'SearchResultFlightListRow')
        self.flight_data = []    # Ensure empty array to start
        cnt=0

        logger.info(f"Staring scraping.... {self.mode}")
        for result in search_results:
            flight_number = result.find_element(By.CSS_SELECTOR, '.flightNumberLogo .resultRow p').text
            origin = result.find_elements(By.CSS_SELECTOR, '.col-dest .resultRow p')[0].text
            destination = result.find_elements(By.CSS_SELECTOR, '.col-dest .resultRow p')[1].text
            departure_time = result.find_elements(By.CSS_SELECTOR, '.col-sched .resultRow p')[0].text
            arrival_time = result.find_elements(By.CSS_SELECTOR, '.col-sched .resultRow p')[1].text
            gate = result.find_elements(By.CSS_SELECTOR, '.col-xs-4.col-sm-3.col-lg-3 .resultRow p')[0].text
            status = result.find_elements(By.CSS_SELECTOR, '.col-xs-4.col-sm-3.col-lg-3 .resultRow p')[1].text

            flight_info = {
                "flight_number": flight_number,
                "origin": origin,
                "destination": destination,
                "departure_time": departure_time,
                "arrival_time": arrival_time,
                "gate": gate,
                "status": status
            }
            cnt += 1
            logger.info(f"Flight Info scrape [{cnt}]  {flight_info}")
            self.flight_data.append(flight_info)

    def scrapeNow(self):
        # Perfrom a scrape of AAL flight info and update Database
        # Read flight data into Dic self.flight_data
        # update the Database and prepare a summary of the updated data
        logger.info(f"Starting Scrape of : {self.mode}")
        self.open_browser()
        self.scroll_down()
        self.scrape_flight_info()
        self.close_browser()
        self.updateDB()

        #Store and process the Scrped info
        self.flightStatusUpdate()
        self.flagRolledEntries()
        self.flightSummary()

    def flightSummary(self):
        #Summerise the current flight data and prepare output structures
        self.dataBase.flightSummary()

    def printFlightSummary(self):
        #Print human readable summary
        self.dataBase.printFlightSummary()

    def JSONSummary(self):
        #Generate JSON summary
        myJSON = self.dataBase.json_data
        return myJSON
        

class ArrivalsFlightScraper(FlightScraper):
    # 
    def __init__(self,config):
        super().__init__(config)  

    def conntect_to_database(self):
        self.mode = 'arrivals'
        self.url = self.config.get(self.mode, "URL", fallback="Hello")
        self.dataBase = FlightDatabase(config,self.mode)
        self.dataBase.check_and_create_table()    
        self.warn_after = int(self.config.get("arrivals", "warn_after", fallback=20))
        # Override with the environment variable warn_after if it exists
        arrivals_timeout = os.getenv('arrivels_timeout')
        if arrivals_timeout:
            logger.info(f"connect_to_db : Setting arrivels_timeout fron ENV [{departures_timeout}]")
            self.warn_after=arrivals_timeout
        else:
            self.warn_after=int(self.config.get("arrivals", "warn_after", fallback=20))


class DepartureFlightScraper(FlightScraper):
    # 
    def __init__(self,config):
        super().__init__(config)  

    def conntect_to_database(self):
        self.mode = 'departures' 
        self.url = self.config.get(self.mode, "URL", fallback="Hello")
        self.dataBase = FlightDatabase(config,self.mode)
        self.dataBase.check_and_create_table()    
        self.warn_after = int(self.config.get("departures", "warn_after", fallback=20))
        # Override with the environment variable warn_after if it exists
        departures_timeout = os.getenv('departures_timeout')
        if departures_timeout:
            logger.info(f"connect_to_db : Setting depatures_timeout fron ENV [{departures_timeout}]")
            self.warn_after=departures_timeout
        else:
            self.warn_after=int(self.config.get("arrivals", "warn_after", fallback=20))
            logger.info(f"connect_to_db : Setting depatures_timeout from config file [{departures_timeout}]")



def initialize_objects(config):  # Function to initialize objects outside main flow
    global arrivals, departures
    arrivals = ArrivalsFlightScraper(config)
    departures = DepartureFlightScraper(config)

    departures.flightSummary()
    arrivals.flightSummary()
 

def aal_web(environ, start_response):
  # Mini Web service
  global arrivals, departures  # Access global variables
  departures.flightSummary()
  arrivals.flightSummary()
  data = {"arrivals": arrivals.JSONSummary(), "departures": departures.JSONSummary() }

  path = environ['PATH_INFO']
  query_string = environ['QUERY_STRING']

  # Some basic response to GET prompts
  if path == '/json':
        # Genrerate JSON status string
        status = '200 OK'
        headers = [('Content-type', 'application/json; charset=utf-8')]
        start_response(status, headers)
        # Convert dictionary to JSON string and return it as response
        return [json.dumps(data).encode('utf-8')]
  elif path == '/dump':
        # HTML content for departure information 'dump' of arrivals & departues' from DB
        status = '200 OK'
        headers = [('Content-type', 'text/html; charset=utf-8')]
        start_response(status, headers)

        # Generate HTML content
        html_content = "<html><head><title>Flight Information</title></head><body>"
        html_content += "<h1>Flight Information</h1>"
        html_content += arrivals.printTable("html")
        html_content += departures.printTable("html")
        html_content += "</body></html>"

        return [html_content.encode('utf-8')]
  else:
        # Loop through Flights summary  (might use a a Widget in LM)
        # Set headers
        headers = [('Content-Type', 'text/html')]
        start_response('200 OK', headers)

        # Resize images using Pillow (PIL)
        thumbnail_size = (50, 50)  # Adjust thumbnail size as needed
        with Image.open('plane_departure.png') as departure_icon_img:
            departure_icon_img.thumbnail(thumbnail_size)
            departure_icon_buffer = io.BytesIO()
            departure_icon_img.save(departure_icon_buffer, format="PNG")
            departure_icon = base64.b64encode(departure_icon_buffer.getvalue()).decode('utf-8')
        with Image.open('plane_arrival.png') as arrival_icon_img:
            arrival_icon_img.thumbnail(thumbnail_size)
            arrival_icon_buffer = io.BytesIO()
            arrival_icon_img.save(arrival_icon_buffer, format="PNG")
            arrival_icon = base64.b64encode(arrival_icon_buffer.getvalue()).decode('utf-8')

  # Build HTML content
  html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AAL Flight Status Summary</title>
  <style>
    body {{
      font-family: sans-serif;
      margin: 0;
      padding: 0;
      width: 400px;
      height: 300px;
      display: flex;  /* Arrange sections side-by-side */
    }}
    .section {{
      display: flex;
      flex-direction: column;
      align-items: center;
      margin: 10px;
      flex: 1;  /* Make sections equally sized */
    }}
    .icon {{
      width: 50px;
      height: 50px;
    }}
    .value {{
      font-size: 20px;
      margin-top: 5px;
    }}
  </style>
</head>
<body>
  <div class="section">
    <img class="icon" src="data:image/png;base64,{departure_icon}" alt="Departures">
    <div class="value">Departed: {data['departures']['departed']}</div>
    <div class="value">Scheduled: {data['departures']['scheduled']}</div>
    <div class="value">Cancelled: {data['departures']['cancelled']}</div>
  </div>
  <div class="section">
    <img class="icon" src="data:image/png;base64,{arrival_icon}" alt="Arrivals">
    <div class="value">Landed: {data['arrivals']['landed']}</div>
    <div class="value">Scheduled: {data['arrivals']['scheduled']}</div>
    <div class="value">Cancelled: {data['arrivals']['cancelled']}</div>
  </div>
  <script>
    setTimeout(function() {{
      window.location.reload(true);
    }}, 30000);  // Refresh every 30 seconds (30000 milliseconds)
  </script>
</body>
</body>
</html>
"""
  return [html.encode()]


def start_web_services():
        # Launch HTTP server
        # Override json file with the environment variable if it exists
        web_services_port = os.getenv('web_services_port')
        httpd=None
        if web_services_port:
            logger.info(f"start_web_services : web_services_port set from ENV [{web_services_port}]")
        else:
            web_services_port = config.get("global", "web_services_port", fallback="8666")
        from wsgiref.simple_server import make_server
        try:
            httpd = make_server('', int(web_services_port), aal_web)  
        except:
            logger.critical(f"ERROR: Failed to start web services. ", httpd)
            exit(1)
        print(f"AAL Flight Mon Serving on port {web_services_port}...")
        logger.info(f"AAL Flight Mon Serving on port {web_services_port}...")
        httpd.serve_forever()
        return


def save_json(json_out):

        # Override json file with the environment variable if it exists
        lm_file = os.getenv('lm_file')
        if lm_file:
            logger.info(f"save_json : lm_file set from ENV [{lm_file}]")
        else:
            lm_file = config.get("global", "lm_file", fallback="ERROR GRID URL")
            logger.info(f"save_json : lm_file set from cfg file [{lm_file}]")

        # Output results to a JSON file
        with open(lm_file, "w") as outfile:
            # Write the JSON data to the file using json.dump
            try:
                json.dump(json_out, outfile)
            except:
                logger.error(f"save_json: ERROE writing out JSON to lm_file,  lm_file [{lm_file}] JSON [{json}]")
                return

        logger.info(f"save_json: Sucsess writing out JSON to lm_file,  lm_file [{lm_file}] JSON [{json}]")
        return


import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", handlers=[logging.StreamHandler()])
logger = logging.getLogger(__name__)

if __name__ == "__main__":
  
  logger.info(f"Running : {sys.argv[0]} with arguments: {sys.argv[1:]}")
  parser = argparse.ArgumentParser(description="AAL Monitor Flight Sechedul for listings that do NOT roll  off")
  # Move Daemon function to outside script to run peridocily # parser.add_argument("-d", "--deamon", action="store_true", help="Run the script in deamon mode.")
  parser.add_argument("-p", "--print", action="store", type=str, nargs="?", const="tab", help="Print the AAL Flight status info. (optional argument for CSV or JSON output )")
  parser.add_argument("-s", "--scrape", action="store", type=str, nargs="?", const="now", help="scrape now")
  parser.add_argument("-w", "--www", action="store", type=str, nargs="?", help="Strart HTTP Service")
  args = parser.parse_args()
  
  # Set up Config object
  config = ConfigParser()
  config.read("AAL_FlightMon.cfg")
  loopTime = config.get("global", "run_every", fallback=300) 


  # Instaniuate Flight Scraper Objects
  arrivals = ArrivalsFlightScraper(config)
  departures = DepartureFlightScraper(config)

# Print mode - Just print the contents of the DB in human read format, no scraping
  if args.print == "csv":
      departures.printTable("csv")
      arrivals.printTable("csv")
      exit(0)
  elif args.print == "tab":
      departures.printTable("tab")
      arrivals.printTable("tab")
      exit(0)
  elif args.print == "html":
      print(departures.printTable("html"))
      print(arrivals.printTable("html"))
      exit(0)
  elif args.print == "json":
      departures.flightSummary()
      arrivals.flightSummary()
      LM_JSON = {"arrivals": arrivals.JSONSummary(), "departures": departures.JSONSummary() }
      logger.debug(f"{LM_JSON}")
      save_json(LM_JSON)
      print(LM_JSON)
      exit(0)

# Web services - To be run stand alone
  if args.www:
    # Launch HTTP server
    start_web_services()
    exit(0)


  if args.scrape:
      print("Scrape now...")
      departures.scrapeNow()
      arrivals.scrapeNow()
      exit(0)

