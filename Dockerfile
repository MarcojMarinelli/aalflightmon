# AAL Flightmonitor Docker image build file
# Use a base image with Python 3 and headless Chrome
FROM python:3.9-slim-buster AS base

# Install dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-dev \
    python3-pip \
    libsqlite3-dev \
    libjpeg-dev \
    libssl-dev \
    zlib1g-dev \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Create the data directory
RUN mkdir /data

# Copy stuff
COPY . /app

# Set the user and group for the container process
RUN groupadd -g 1000 aalmon
RUN useradd -m -u 1000 -g aalmon aalmon

# Set environment variables 
ENV TZ="Australia/Adelaide"
#ENV grid_url="http://192.168.1.20:4444/wd/hub"
ENV PATH=".:/app:$PATH"

# setup pyhton
COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Ensure the launch script owener and execute permissions
RUN chmod +x /app/AAL_FlightMon.sh
RUN chown 1000:1000 /app/AAL_FlightMon.sh
RUN chown 1000:1000 /app/AAL_FlightMon.py
RUN chown -R 1000:1000 /app /data


# Expose the port your application listens on (if applicable)
EXPOSE 8666

# Strart with NO DB file
RUN rm -f /app/Flight.db

# Entrypoint command (run the launch script)
CMD ["AAL_FlightMon.sh"]

# Run ass ALL Monitor user
USER aalmon
