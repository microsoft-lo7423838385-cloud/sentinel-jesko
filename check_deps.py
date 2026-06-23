import sys
import os
try:
    from importlib.metadata import distributions, version, PackageNotFoundError
except ImportError:
    print("ERROR: 'importlib.metadata' not found. This script requires Python 3.8+.")
    sys.exit(1)
import re

def check_dependencies():
    """
    Checks if all packages listed in requirements.txt are installed in the current environment.
    Exits with a non-zero status code if any dependencies are missing.
    """
    try:
        requirements_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
        with open(requirements_path, 'r', encoding='utf-8') as f:
            requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        missing = []
        for req_str in requirements:
            # Basic parsing for package name from requirement string (e.g., "package_name>=1.0")
            # This is a simplification and might not handle all complex cases, but works for this project.
            match = re.match(r"([a-zA-Z0-9\-_]+)", req_str)
            if not match:
                continue
            package_name = match.group(1)

            try:
                # Check if the package is installed by trying to get its version
                version(package_name)
            except PackageNotFoundError:
                missing.append(req_str)

        if missing:
            print(f"\nERROR: The following required packages are missing: {', '.join(missing)}")
            sys.exit(1)
            
    except Exception as e:
        print(f"\nAn error occurred during dependency check: {e}")
        sys.exit(1)

if __name__ == "__main__":
    check_dependencies()