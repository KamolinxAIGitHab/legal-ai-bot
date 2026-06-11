import os
import sys

def verify_structure():
    required_dirs = [
        'bot/handlers',
        'bot/keyboards',
        'bot/middlewares',
        'bot/utils',
        'api',
        'core',
        'docs'
    ]

    missing = []
    for d in required_dirs:
        if not os.path.exists(d):
            missing.append(d)

    if missing:
        print(f"FAILED: Missing directories: {', '.join(missing)}")
        return False

    required_files = [
        'docs/TECHNICAL_DESIGN.md',
        'docs/database_schema.sql'
    ]

    for f in required_files:
        if not os.path.exists(f):
            missing.append(f)

    if missing:
        print(f"FAILED: Missing files: {', '.join(missing)}")
        return False

    print("SUCCESS: Project structure verified.")
    return True

if __name__ == "__main__":
    if verify_structure():
        sys.exit(0)
    else:
        sys.exit(1)
