"""Dev-обёртка: реализация в app/fetch_data.py (нужна замороженному exe)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from fetch_data import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
