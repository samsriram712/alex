#!/usr/bin/env python3
"""
Cross-platform Lambda deployment package creator using uv.
Works on Windows, Mac, and Linux.
"""

import os
import sys
import shutil
import zipfile
from pathlib import Path

# ---- ONLY INCLUDE THE PACKAGES THE WORKER ACTUALLY USES ----
ALLOWED_PREFIXES = [
    "alex_database",
    "langfuse",
    "tenacity",
    "pydantic",
    "pydantic_core",
]

def should_include(name: str):
    return any(name.startswith(prefix) for prefix in ALLOWED_PREFIXES)

def create_deployment_package():
    """Create a Lambda deployment package with dependencies from uv."""
    
    # Paths
    current_dir = Path(__file__).parent
    build_dir = current_dir / 'build'
    package_dir = build_dir / 'package'
    zip_path = current_dir / 'lambda_function.zip'
    # venv_site_packages = current_dir / '.venv' / 'lib'
    # Look 1 level up for the workspace venv
    venv_site_packages = current_dir.parent / '.venv' / 'lib'
    
    # Clean up previous builds
    if build_dir.exists():
        shutil.rmtree(build_dir)
    if zip_path.exists():
        os.remove(zip_path)
    
    # Create build directory
    package_dir.mkdir(parents=True, exist_ok=True)
    
    # Find the site-packages directory (cross-platform)
    site_packages = None
    for path in venv_site_packages.rglob('site-packages'):
        site_packages = path
        break
    
    if not site_packages or not site_packages.exists():
        print("Error: Could not find site-packages. Make sure you've run 'uv init' and 'uv add' for dependencies.")
        sys.exit(1)
    
    print(f"Copying dependencies from {site_packages}...")
    # Copy all dependencies to package directory
    for item in site_packages.iterdir():
        if item.name.endswith('.dist-info') or item.name == '__pycache__':
            continue
        if should_include(item.name):
            dest = package_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
    
    # Copy alex-database workspace source files
    database_src = current_dir.parent / "database" / "src"
    if database_src.exists():
        print("Copying alex-database workspace package...")
        for file in database_src.iterdir():
            if file.suffix == ".py":  # Only Python files
                shutil.copy2(file, package_dir / file.name)
    else:
        print("WARNING: database/src directory not found!")


    # Copy Lambda function code
    print("Copying Lambda function code...")
    
    # Copy worker code
    if (current_dir / 'worker.py').exists():
        shutil.copy(current_dir / 'worker.py', package_dir)
    
    # Create ZIP file
    print("Creating deployment package...")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(package_dir):
            # Skip __pycache__ directories
            dirs[:] = [d for d in dirs if d != '_   _pycache__']
            for file in files:
                if file.endswith('.pyc'):
                    continue
                file_path = Path(root) / file
                arcname = file_path.relative_to(package_dir)
                zipf.write(file_path, arcname)
    
    # Clean up build directory
    shutil.rmtree(build_dir)
    
    # Get file size
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"\n✅ Deployment package created: {zip_path}")
    print(f"   Size: {size_mb:.2f} MB")
    
    if size_mb > 50:
        print("⚠️  Warning: Package exceeds 50MB. Consider using Lambda Layers.")
    
    return str(zip_path)


if __name__ == '__main__':
    create_deployment_package()