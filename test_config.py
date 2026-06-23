#!/usr/bin/env python3
import configparser
import traceback

try:
    parser = configparser.ConfigParser(inline_comment_prefixes=('#',))
    parser.read('config/config.ini')
    print("✓ Config parsed successfully")
    print(f"Sections: {parser.sections()}")
except Exception as e:
    print(f"✗ Config parsing failed: {e}")
    traceback.print_exc()

try:
    from settings import load_settings_from_ini
    settings = load_settings_from_ini('config/config.ini')
    print("✓ Settings loaded successfully")
except Exception as e:
    print(f"✗ Settings loading failed: {e}")
    traceback.print_exc()
