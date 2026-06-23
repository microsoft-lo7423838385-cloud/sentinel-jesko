import os
import zipfile
import shutil
from io import BytesIO
import requests

# This is a known compatible version of GTK3 for WeasyPrint on Windows 64-bit
# Updated to 2021-04-29 release which has a valid ZIP asset
GTK_URL = "https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases/download/2021-04-29/gtk3-runtime-3.24.29-2021-04-29-ts-win64.zip"
RELEASES_URL = "https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases"

def install_gtk():
    print("--- Sentinel Jesko: GTK3 Local Installer ---")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    gtk_dir = os.path.join(base_dir, 'gtk')
    
    # Clean up existing bad installation if present
    if os.path.exists(gtk_dir):
        print(f"Removing existing/broken 'gtk' folder at: {gtk_dir}")
        try:
            shutil.rmtree(gtk_dir)
        except Exception as e:
            print(f"Error removing folder: {e}. Please delete the 'gtk' folder manually and try again.")
            return
    
    # 1. Try to find existing system installation (The EXE the user likely downloaded)
    system_gtk_paths = [
        os.environ.get('ProgramFiles', r'C:\Program Files') + r'\GTK3-Runtime',
        os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)') + r'\GTK3-Runtime',
        r'C:\GTK3-Runtime'
    ]
    for sys_path in system_gtk_paths:
        bin_path = os.path.join(sys_path, 'bin')
        if os.path.exists(os.path.join(bin_path, 'libpango-1.0-0.dll')):
            print(f"\n[INFO] Found system GTK3 installation at: {sys_path}")
            print("Copying to local folder for portability...")
            try:
                shutil.copytree(sys_path, gtk_dir)
                print(f"\n[SUCCESS] GTK3 copied locally from {sys_path}")
                print("PDF generation will now work.")
                return
            except Exception as e:
                print(f"Failed to copy system GTK: {e}")

    os.makedirs(gtk_dir, exist_ok=True)
    
    print(f"Downloading compatible GTK3 Runtime from: {GTK_URL}")
    print("This may take a minute...")
    try:
        # --- "World-Class" Fix: Add User-Agent headers to prevent GitHub 404/403 errors ---
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(GTK_URL, stream=True, headers=headers)
        response.raise_for_status()
        
        print("Download complete. Extracting files...")
        with zipfile.ZipFile(BytesIO(response.content)) as z:
            z.extractall(gtk_dir)
            
        print(f"\n[SUCCESS] GTK3 installed to: {gtk_dir}")
        print("You can now run 'main.py' again. PDF generation will work correctly.")
        
    except Exception as e:
        print(f"\n[ERROR] Installation failed: {e}")
        print(f"\n--- Manual Resolution ---")
        print("We could not download GTK3, and we could not find it installed on your system.")
        print("\nStep 1: PLEASE INSTALL THE EXE YOU DOWNLOADED.")
        print("   (It's likely named 'gtk3-runtime-3.24.31-2022-01-04-ts-win64.exe')")
        print("   Default options are fine.")
        print("\nStep 2: Tell us where you installed it.")
        
        custom_path = input("Enter the installation path (e.g., C:\\Program Files\\GTK3-Runtime): ").strip().strip('"').strip("'")
        if custom_path and os.path.exists(os.path.join(custom_path, 'bin', 'libpango-1.0-0.dll')):
            print(f"Found GTK3 at {custom_path}. Copying...")
            try:
                shutil.copytree(custom_path, gtk_dir)
                print(f"\n[SUCCESS] GTK3 copied locally.")
                print("PDF generation will now work.")
            except Exception as copy_err:
                print(f"Error copying: {copy_err}")
        else:
            print("Invalid path or GTK3 not found there. Please check the path and try again.")

if __name__ == "__main__":
    install_gtk()