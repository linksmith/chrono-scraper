#!/usr/bin/env python3
"""
Quick progress checker for the complete historical fetch.
"""

import os
import json
from pathlib import Path
from collections import defaultdict

def check_progress():
    """Check current progress of the historical fetch"""
    
    stoerwoud_dir = Path("/app/stoerwoud")
    
    if not stoerwoud_dir.exists():
        print("❌ Stoerwoud directory not found")
        return
    
    # Count HTML files
    html_files = list(stoerwoud_dir.glob("*.html"))
    
    if not html_files:
        print("⚠️ No HTML files found yet")
        return
    
    print(f"📁 Found {len(html_files)} HTML files")
    
    # Group by year
    files_by_year = defaultdict(list)
    
    for f in html_files:
        # Extract timestamp from filename (last part before .html)
        parts = f.stem.split('_')
        if parts:
            timestamp = parts[-1]
            if len(timestamp) >= 4:
                year = timestamp[:4]
                files_by_year[year].append(f.name)
    
    # Show year distribution
    print("\n📅 Files by year:")
    for year in sorted(files_by_year.keys()):
        print(f"   {year}: {len(files_by_year[year])} files")
    
    # Show sample recent files
    print(f"\n📄 Sample files:")
    for f in html_files[:10]:
        size = f.stat().st_size
        print(f"   {f.name} ({size:,} bytes)")
    
    # Check for log file
    log_file = Path("/app/fetch_stoerwoud_complete.log")
    if log_file.exists():
        print(f"\n📊 Log file size: {log_file.stat().st_size:,} bytes")

if __name__ == "__main__":
    check_progress()