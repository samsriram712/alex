import os, subprocess, shutil

def package_price_refresher():
    build_dir = "/tmp/alex_price_refresher_build"
    shutil.rmtree(build_dir, ignore_errors=True)
    os.makedirs(build_dir, exist_ok=True)

    # copy code
    subprocess.run(["cp", "-r", "../planner", build_dir], check=True)
    subprocess.run(["cp", "-r", "../database", build_dir], check=True)
    shutil.copy("lambda_handler.py", build_dir)


    # install deps
    subprocess.run([
    "docker", "run", "--rm", "--platform", "linux/amd64",
    "-v", f"{build_dir}:/build",
    "--entrypoint", "/bin/bash",
    "public.ecr.aws/lambda/python:3.12",
    "-c", "pip install boto3 requests --target /build"
    ], check=True)


    shutil.make_archive("price_refresher_lambda", "zip", build_dir)
    print("✅ Created price_refresher_lambda.zip")

if __name__ == "__main__":
    package_price_refresher()
