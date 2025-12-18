#!/usr/bin/env python3
"""
Manual verification script for archive source fix.
This script verifies that the enum values match between frontend and backend.
"""

import json
import sys
from pathlib import Path

def verify_enum_consistency():
    """Verify that TypeScript and Python enum values match."""
    
    print("🔍 Verifying Archive Source Enum Consistency")
    print("=" * 50)
    
    # Expected enum values that should match between frontend and backend
    expected_values = {
        'wayback': 'Wayback Machine',
        'commoncrawl': 'Common Crawl', 
        'hybrid': 'Hybrid Mode'
    }
    
    # Check Python enum (from models)
    try:
        sys.path.append('backend')
        from app.models.project import ArchiveSource
        
        python_values = {source.value: source.name for source in ArchiveSource}
        print(f"✅ Python enum values: {python_values}")
        
        # Verify all expected values are present
        for expected_value in expected_values.keys():
            if expected_value not in python_values:
                print(f"❌ Missing Python enum value: {expected_value}")
                return False
            else:
                print(f"✅ Python has: {expected_value}")
                
    except ImportError as e:
        print(f"❌ Could not import Python enum: {e}")
        return False
    
    # Check TypeScript types (from archive.ts)
    try:
        archive_ts_path = Path('frontend/src/lib/types/archive.ts')
        if archive_ts_path.exists():
            content = archive_ts_path.read_text()
            print(f"✅ Found TypeScript archive types file")
            
            # Check for type definition
            if "export type ArchiveSource = 'wayback' | 'commoncrawl' | 'hybrid';" in content:
                print("✅ TypeScript enum values match expected format")
                
                # Check for getArchiveSourceName function
                for expected_value, expected_name in expected_values.items():
                    if f"case '{expected_value}': return '{expected_name}'" in content:
                        print(f"✅ TypeScript has correct mapping: {expected_value} -> {expected_name}")
                    else:
                        print(f"❌ TypeScript missing mapping: {expected_value} -> {expected_name}")
                        return False
            else:
                print("❌ TypeScript enum definition not found or incorrect")
                return False
        else:
            print("❌ TypeScript archive types file not found")
            return False
            
    except Exception as e:
        print(f"❌ Error checking TypeScript file: {e}")
        return False
    
    print("\n🎉 All enum values are consistent between frontend and backend!")
    return True

def verify_archive_source_options():
    """Verify that the ARCHIVE_SOURCE_OPTIONS array is correct."""
    
    print("\n🔍 Verifying Archive Source Options")
    print("=" * 40)
    
    try:
        archive_ts_path = Path('frontend/src/lib/types/archive.ts')
        content = archive_ts_path.read_text()
        
        # Check for correct archive source options
        expected_options = [
            "value: 'wayback' as ArchiveSource",
            "title: 'Wayback Machine (Internet Archive)'",
            "value: 'commoncrawl' as ArchiveSource", 
            "title: 'Common Crawl'",
            "value: 'hybrid' as ArchiveSource",
            "title: 'Hybrid (Recommended)'"
        ]
        
        for option in expected_options:
            if option in content:
                print(f"✅ Found: {option}")
            else:
                print(f"❌ Missing: {option}")
                return False
                
        print("✅ All archive source options are correctly defined")
        return True
        
    except Exception as e:
        print(f"❌ Error verifying options: {e}")
        return False

def verify_badge_component():
    """Verify that the ArchiveSourceBadge component has correct mappings."""
    
    print("\n🔍 Verifying ArchiveSourceBadge Component")
    print("=" * 45)
    
    try:
        badge_path = Path('frontend/src/lib/components/project/ArchiveSourceBadge.svelte')
        if badge_path.exists():
            content = badge_path.read_text()
            
            # Check for correct mappings in archiveSourceConfig
            expected_mappings = [
                "wayback: {",
                "label: 'Wayback Machine'",
                "commoncrawl: {",
                "label: 'Common Crawl'",
                "hybrid: {", 
                "label: 'Hybrid Mode'"
            ]
            
            for mapping in expected_mappings:
                if mapping in content:
                    print(f"✅ Found: {mapping}")
                else:
                    print(f"❌ Missing: {mapping}")
                    return False
                    
            print("✅ ArchiveSourceBadge component has correct mappings")
            return True
        else:
            print("❌ ArchiveSourceBadge component not found")
            return False
            
    except Exception as e:
        print(f"❌ Error checking badge component: {e}")
        return False

def main():
    """Run all verification checks."""
    
    print("🚀 Archive Source Fix Verification")
    print("=" * 60)
    print()
    
    all_passed = True
    
    # Run all verification checks
    checks = [
        verify_enum_consistency,
        verify_archive_source_options,
        verify_badge_component
    ]
    
    for check in checks:
        if not check():
            all_passed = False
        print()
    
    if all_passed:
        print("🎉 SUCCESS: All archive source fix verifications passed!")
        print("✅ The enum mismatch has been resolved")
        print("✅ Frontend and backend are consistent")
        print("✅ Components have correct mappings")
        return 0
    else:
        print("❌ FAILURE: Some verifications failed")
        print("Please check the issues above and fix them")
        return 1

if __name__ == "__main__":
    sys.exit(main())