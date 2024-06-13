#!/bin/bash
# Wrapper shell script for AAL_FlightMon;py
# Run scraping of AAL Flight Web page every 5 min, store flight info for the purpose of determine if/when flight infomation hangs around longer than expected

# Start AAL_FlighMon Web service. Launch AAL_FlightMon.py with -www option in the background
# Check if web_services environment variable is set to True
if [[ "${web_services}" == "True" ]]; then
  # Start AAL_FlightMon Web service. Launch AAL_FlightMon.py with -www option in the background
  python3 AAL_FlightMon.py -www &
  WWW_PID=$!
  echo "ENV web_services is True. Launched AAL_FlightMon.py -www with PID $WWW_PID"
else
  echo "web_services environment variable not set to True. Skipping web service launch."
fi

sleep 2

# Function to check if a process is running
is_running() {
  ps -p $1 > /dev/null 2>&1
}

# Define default scrape loop time (moved after checking environment variable)
loop_time=300

# Check for scrape_loop_time environment variable
if [[ -n "${scrape_loop_time}" ]]; then
  # Check if scrape_loop_time is an integer greater than 120
  if [[ "$scrape_loop_time" =~ ^[0-9]+$ ]]; then
    if [[ $scrape_loop_time -gt 120 ]]; then
      # Valid integer and greater than 120, use it as loop time
      loop_time=$scrape_loop_time
      echo "Using scrape_loop_time from environment: $loop_time seconds"
    else
      echo "scrape_loop_time set but less than or equal to 120, using default (300 seconds)"
    fi
  else
    echo "scrape_loop_time is not a valid integer, using default (300 seconds)"
  fi
fi

# Infinite loop
while true; do
  # Check if the process with the saved PID is still running
  if ! is_running $WWW_PID; then
    echo "AAL_FlightMon.py -www is not running. Relaunching..."
    # Relaunch the process in the background and save the new PID
    if [[ "${web_services}" == "True" ]]; then
      python3 AAL_FlightMon.py -www &
      WWW_PID=$!
      echo "Relaunched AAL_FlightMon.py -www with PID $WWW_PID"
    else
      echo "web_services environment variable not set to True. Skipping relaunch."
    fi
  else
    echo "AAL_FlightMon.py -www is still running with PID $WWW_PID"
  fi

  # Run AAL_FlightMon.py with -s option
  python3 AAL_FlightMon.py -s

  # Sleep for the defined scrape loop time
  echo "Sleeping for $loop_time  seconds...."
  sleep $loop_time

done

