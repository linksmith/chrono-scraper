#!/usr/bin/env python3
"""
Script to update all Docker Compose files to remove Firecrawl dependencies
and add robust extraction configuration.

This script systematically updates all compose files to:
1. Remove Firecrawl services (firecrawl-api, firecrawl-worker, firecrawl-playwright)
2. Remove Firecrawl environment variables
3. Add robust extraction environment variables
4. Update service dependencies
5. Preserve production-specific configurations
"""

import os
import re
import yaml
from pathlib import Path

# Configuration for robust extraction
ROBUST_EXTRACTION_ENV = {
    "USE_INTELLIGENT_EXTRACTION_ONLY": "true",
    "INTELLIGENT_EXTRACTION_CONCURRENCY": "15",
    "ROBUST_EXTRACTION_ENABLED": "true", 
    "EXTRACTION_TIMEOUT": "45",
    "EXTRACTION_CACHE_TTL": "3600"
}

# Firecrawl services to remove
FIRECRAWL_SERVICES = ["firecrawl-api", "firecrawl-worker", "firecrawl-playwright"]

# Firecrawl environment variables to remove (patterns)
FIRECRAWL_ENV_PATTERNS = [
    r"FIRECRAWL_.*",
    r".*FIRECRAWL.*"
]

def update_compose_file(file_path):
    """Update a single Docker Compose file"""
    print(f"Updating {file_path}...")
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        original_content = content
        
        # 1. Remove Firecrawl services sections
        for service in FIRECRAWL_SERVICES:
            # Match service definition and its entire block
            pattern = rf'\s*{service}:\s*\n((?:\s+.*\n)*?)(?=\n\s*[a-z_-]+:\s*\n|\n\s*networks:|\n\s*volumes:|\Z)'
            content = re.sub(pattern, '', content, flags=re.MULTILINE)
        
        # 2. Remove Firecrawl environment variables
        for pattern in FIRECRAWL_ENV_PATTERNS:
            env_pattern = rf'\s*-\s+{pattern}[^\n]*\n'
            content = re.sub(env_pattern, '', content, flags=re.MULTILINE | re.IGNORECASE)
        
        # 3. Remove Firecrawl dependencies from depends_on sections
        for service in FIRECRAWL_SERVICES:
            dep_pattern = rf'\s*-\s+{service}\s*\n'
            content = re.sub(dep_pattern, '', content, flags=re.MULTILINE)
        
        # 4. Add robust extraction environment variables to backend and celery services
        def add_robust_env(match):
            service_block = match.group(0)
            env_section = match.group(1) if match.group(1) else ""
            
            # Add robust extraction config if not already present
            if "USE_INTELLIGENT_EXTRACTION_ONLY" not in service_block:
                robust_env_lines = []
                robust_env_lines.append("      # Robust extraction configuration")
                for key, value in ROBUST_EXTRACTION_ENV.items():
                    robust_env_lines.append(f"      - {key}={value}")
                
                # Insert before the end of environment section
                if "environment:" in service_block:
                    # Find a good place to insert (before depends_on, networks, etc.)
                    insert_point = service_block.rfind('\n    depends_on:')
                    if insert_point == -1:
                        insert_point = service_block.rfind('\n    networks:')
                    if insert_point == -1:
                        insert_point = service_block.rfind('\n    restart:')
                    if insert_point == -1:
                        insert_point = len(service_block) - 1
                    
                    service_block = (service_block[:insert_point] + 
                                   '\n' + '\n'.join(robust_env_lines) + 
                                   service_block[insert_point:])
            
            return service_block
        
        # Apply to backend and celery services
        content = re.sub(r'(\s+backend:.*?(?=\n  [a-z_-]+:|\n\s*networks:|\n\s*volumes:|\Z))', 
                        add_robust_env, content, flags=re.MULTILINE | re.DOTALL)
        content = re.sub(r'(\s+celery_worker:.*?(?=\n  [a-z_-]+:|\n\s*networks:|\n\s*volumes:|\Z))', 
                        add_robust_env, content, flags=re.MULTILINE | re.DOTALL)
        
        # 5. Clean up any empty environment sections or duplicated newlines
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content, flags=re.MULTILINE)
        
        # Only write if content changed
        if content.strip() != original_content.strip():
            # Backup original
            backup_path = f"{file_path}.bak"
            with open(backup_path, 'w') as f:
                f.write(original_content)
            print(f"  Backed up original to {backup_path}")
            
            # Write updated content
            with open(file_path, 'w') as f:
                f.write(content)
            print(f"  Updated {file_path}")
        else:
            print(f"  No changes needed for {file_path}")
            
    except Exception as e:
        print(f"  Error updating {file_path}: {e}")

def main():
    """Main function to update all compose files"""
    project_root = Path(__file__).parent.parent
    
    # Find all docker-compose files
    compose_files = list(project_root.glob("docker-compose*.yml"))
    
    print(f"Found {len(compose_files)} Docker Compose files to update:")
    for f in compose_files:
        print(f"  {f}")
    
    print("\nStarting updates...")
    
    for file_path in compose_files:
        # Skip the main file since we already updated it manually
        if file_path.name == "docker-compose.yml":
            print(f"Skipping {file_path} (already updated)")
            continue
            
        update_compose_file(file_path)
    
    print("\nUpdate complete!")
    print("\nFiles updated:")
    for file_path in compose_files:
        if file_path.name != "docker-compose.yml":
            backup_exists = (Path(str(file_path) + ".bak")).exists()
            status = "✅ Updated" if backup_exists else "⏭️  Skipped"
            print(f"  {status}: {file_path.name}")

if __name__ == "__main__":
    main()