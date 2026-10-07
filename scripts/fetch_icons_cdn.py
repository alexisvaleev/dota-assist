"""Dev-обёртка: реализация в app/fetch_icons.py."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from fetch_icons import main  # noqa: E402

if __name__ == "__main__":
    main()
