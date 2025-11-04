# Start from a clean, stable Debian-based Python image
FROM python:3.12-slim-bookworm

# Install required system dependencies for spaCy/blis compilation (The Fix)
# This bypasses the apt-get update failure and installs essential dev tools.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libblas-dev \
        liblapack-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Copy requirements file and install Python packages
# This ensures a clean installation of all your dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code (app.py, etc.)
COPY . .

# Expose the port Gunicorn runs on (Render uses 10000, but 8080 is standard)
EXPOSE 8080

# Define the command to run the application (Your Procfile command)
CMD ["gunicorn", "app:app"]
