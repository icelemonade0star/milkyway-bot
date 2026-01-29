import pkg_resources
from pathlib import Path

def generate_requirements():
    # 현재 환경의 모든 패키지 가져오기
    installed_packages = [
        f"{dist.key}=={dist.version}"
        for dist in pkg_resources.working_set
    ]

    # FastAPI 필수 패키지 추가
    required_packages = [
        "fastapi",
        "uvicorn[standard]",
        "python-dotenv",
        "sqlalchemy",
        "alembic",
        "pytest",
        "httpx"
    ]

    # requirements.txt 생성
    output_path = Path("requirements.txt")
    with output_path.open("w") as f:
        for package in required_packages:
            if any(p.startswith(package) for p in installed_packages):
                matching_pkg = next(p for p in installed_packages if p.startswith(package))
                f.write(f"{matching_pkg}\n")
            else:
                f.write(f"{package}\n")

if __name__ == "__main__":
    generate_requirements()
    print("requirements.txt has been generated successfully!")