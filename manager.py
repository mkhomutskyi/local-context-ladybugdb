"""Start the local document manager. Author: Maks Khomutskyi."""
import sys
from context_manager.launcher import main
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('Manager startup failed ('+type(exc).__name__+'). Check local prerequisites, free ports and the private role logs.',file=sys.stderr)
        sys.exit(1)
