#!/bin/bash

# Ensure the script is run with sudo
if [ "$EUID" -ne 0 ]; then
  echo "Please run this script with sudo."
  exit 1
fi

echo "--- Starting Advanced Sender Setup ---"
set -e # Exit immediately if a command exits with a non-zero status.

export DEBIAN_FRONTEND=noninteractive

# --- 1. System Dependency Installation ---
echo "[1/5] Updating package lists and installing system dependencies..."
apt-get update -y
apt-get install -y software-properties-common curl git

# --- 2. Install Python 3.12 ---
echo "[2/5] Installing Python 3.12..."
if ! command -v python3.12 &> /dev/null; then
    add-apt-repository ppa:deadsnakes/ppa -y
    apt-get update -y
    apt-get install -y python3.12 python3.12-venv python3-pip
    echo "Python 3.12 installed successfully."
else
    echo "Python 3.12 is already installed."
fi

# --- 3. Install Node.js ---
echo "[3/5] Installing Node.js..."
if ! command -v node &> /dev/null; then
    # Using NodeSource repository for a stable Node.js installation
    curl -fsSL https://deb.nodesource.com/setup_lts.x -o nodesource_setup.sh
    bash nodesource_setup.sh
    apt-get install -y nodejs
    rm nodesource_setup.sh
    echo "Node.js installed successfully."
else
    echo "Node.js is already installed."
fi

# --- 4. Set up Project Environment ---
echo "[4/5] Setting up project environment..."

# Get the directory of the script to find the project root
PROJECT_ROOT="$(dirname "$(dirname "$(readlink -f "$0")")")"
cd "$PROJECT_ROOT"

# Create and own the virtual environment directory
echo "Creating Python virtual environment in '$PROJECT_ROOT/.venv'..."
python3.12 -m venv .venv

# Find the original user to give them ownership of the new files
ORIGINAL_USER=${SUDO_USER:-$(whoami)}
chown -R "$ORIGINAL_USER":"$ORIGINAL_USER" "$PROJECT_ROOT/.venv"

echo "Installing Python requirements..."
source .venv/bin/activate
pip install -r .sender/linux-requirements.txt

# Run installer.py to get pandoc
echo "Downloading pandoc..."
python installer.py
deactivate

echo "Installing Node.js dependencies..."
cd node_files
npm install
npm run test
cd ..

# --- 5. Finalize ---
echo "[5/5] Setup complete!"
echo ""
echo "To run the application, use the following commands:"
echo "cd '$PROJECT_ROOT'"
echo "source .venv/bin/activate"
echo "python main.py"
echo ""
