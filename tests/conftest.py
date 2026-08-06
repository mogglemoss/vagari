import sys
from pathlib import Path

# The editable-install .pth is unreliable here: iCloud marks .venv contents
# hidden under ~/Documents, and Python 3.11+ skips hidden .pth files.
sys.path.insert(0, str(Path(__file__).parent.parent))
