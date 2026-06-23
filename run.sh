#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
VENV_PATH="$SCRIPT_DIR/.venv"

# Check if the virtual environment exists
if [ ! -f "$VENV_PATH/bin/activate" ]; then
    echo "Virtual environment not found."
    echo "Please run the 'linux_install.sh' or 'mac_install.sh' script first."
    exit 1
fi

echo "Activating virtual environment..."
source "$VENV_PATH/bin/activate"

echo "Starting the Advanced Sender ultra menu..."
python "$SCRIPT_DIR/menu.py" "$@"

echo
echo "Menu has been closed."