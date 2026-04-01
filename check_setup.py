"""
STEP 1 — Run this first to check your environment
Save as: check_setup.py
Run with: python check_setup.py
"""

import sys
import subprocess

print("=" * 50)
print("  Quotex Signal Bot — Environment Check")
print("=" * 50)

# Python version
v = sys.version_info
print(f"\n[1] Python version: {v.major}.{v.minor}.{v.micro}", end="")
if v.major == 3 and v.minor >= 8:
    print("  ✓ OK")
else:
    print("  ✗ Need Python 3.8+")
    print("     Download: https://www.python.org/downloads/")

# Check packages
packages = {
    "quotexapi": "quotexapi",
    "flask":     "flask",
    "flask_cors":"flask-cors",
    "numpy":     "numpy",
    "pandas":    "pandas",
}

print("\n[2] Required packages:")
missing = []
for imp, pkg in packages.items():
    try:
        __import__(imp)
        print(f"     {pkg:15} ✓ installed")
    except ImportError:
        print(f"     {pkg:15} ✗ MISSING")
        missing.append(pkg)

if missing:
    print(f"\n  → Install missing packages:")
    print(f"    pip install {' '.join(missing)}")
    print(f"\n  → Or install everything at once:")
    print(f"    pip install quotexapi flask flask-cors numpy pandas")
else:
    print("\n  → All packages installed ✓")

print("\n[3] Network check: testing internet connection...", end="")
try:
    import urllib.request
    urllib.request.urlopen("https://quotex.io", timeout=5)
    print(" ✓ Can reach quotex.io")
except:
    print(" ✗ Cannot reach quotex.io — check internet connection")

print("\n" + "=" * 50)
if not missing:
    print("  All checks passed! Run server.py next.")
else:
    print("  Fix the issues above then re-run this script.")
print("=" * 50 + "\n")
