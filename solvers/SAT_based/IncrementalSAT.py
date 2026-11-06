"""Enhanced incremental_sat directly over the original repository .3pm format."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from salb3pm.compat import execute
if __name__ == "__main__":
    raise SystemExit(execute('incremental_sat',sys.argv[1:]))
