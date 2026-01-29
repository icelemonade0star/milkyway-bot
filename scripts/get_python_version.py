import sys
import json

def get_python_version():
    version = sys.version_info
    return {
        "major": version.major,
        "minor": version.minor,
        "micro": version.micro,
        "full": f"{version.major}.{version.minor}.{version.micro}"
    }

if __name__ == "__main__":
    version_info = get_python_version()
    print(json.dumps(version_info))