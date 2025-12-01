import os
import shutil
import zipfile
from pathlib import Path

# Allowed dependency prefixes — keep Lambda package small
ALLOWED_PREFIXES = [
    "boto3",
    "botocore",
    "jmespath",
    "s3transfer",
    "langfuse",
    "pydantic",      # ✅ REQUIRED
    "alex",          # ✅ alex_database
    "typing_extensions",
    "typing_inspection",
    "annotated_types",
]

def should_include(dep_name: str) -> bool:
    """Return True if the dependency should be included in the Lambda package."""
    return any(dep_name.startswith(prefix) for prefix in ALLOWED_PREFIXES)


def zip_directory(src: Path, zip_file: zipfile.ZipFile):
    """Zip a directory's contents."""
    for root, dirs, files in os.walk(src):
        for file in files:
            abs_path = Path(root) / file
            rel_path = abs_path.relative_to(src)
            zip_file.write(abs_path, rel_path)


def create_lambda_package():
    print("Starting Lambda packaging...")

    current_dir = Path(__file__).parent
    project_root = current_dir.parent

    build_dir = current_dir / "build"
    package_dir = build_dir / "package"
    zip_path = current_dir / "lambda_function.zip"

    # Clean previous build
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir()
    package_dir.mkdir()

    # -------------------------------
    # Copy dependencies from backend venv
    # -------------------------------
    venv_site_packages = project_root / ".venv" / "lib" / "python3.12" / "site-packages"

    if not venv_site_packages.exists():
        raise RuntimeError("ERROR: Could not find site-packages. Did you run `uv sync` at backend/?")

    print(f"Copying dependencies from {venv_site_packages} ...")

    for item in venv_site_packages.iterdir():
        name = item.name
        if name.endswith(".dist-info") or name == "__pycache__":
            continue

        if should_include(name):
            target = package_dir / name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)

    # -------------------------------
    # Copy common/ (JobTracker)
    # -------------------------------
    common_dir = project_root / "common"
    if common_dir.exists():
        print(f"Copying common/ from {common_dir} ...")
        shutil.copytree(common_dir, package_dir / "common", dirs_exist_ok=True)
    else:
        print("WARNING: common/ directory not found!")

    # -------------------------------
    # Copy database/src → src/
    # -------------------------------
    database_src = project_root / "database" / "src"
    if database_src.exists():
        print(f"Copying database/src from {database_src} ...")
        target_src = package_dir / "src"
        shutil.copytree(database_src, target_src, dirs_exist_ok=True)
    else:
        print("WARNING: database/src directory not found!")

    # -------------------------------
    # Copy worker.py
    # -------------------------------
    worker_file = current_dir / "worker.py"
    if worker_file.exists():
        print("Copying worker.py ...")
        shutil.copy2(worker_file, package_dir / "worker.py")
    else:
        raise RuntimeError("ERROR: worker.py not found in symbol_research directory.")

    # ----------------------------------------------------------
    # Copy database/src → package/database
    # ----------------------------------------------------------
    database_src = project_root / "database" / "src"
    database_dst = package_dir / "database/src"

    if database_src.exists():
        print(f"Copying database package from {database_src}")
        shutil.copytree(database_src, database_dst, dirs_exist_ok=True)
    else:
        print("WARNING: database/src not found – Database will not be packaged!")


    # -------------------------------
    # Create ZIP package
    # -------------------------------
    print("Creating deployment package...")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zip_directory(package_dir, zf)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"\n✅ Deployment package created: {zip_path}")
    print(f"   Size: {size_mb:.2f} MB")

    if size_mb > 50:
        print("⚠️  Warning: Package exceeds 50MB. Use S3 deployment.")

    print("Done.")


if __name__ == "__main__":
    create_lambda_package()
