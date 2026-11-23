"""Allow ``python -m snowgrid`` as an alias for ``python -m snowgrid.main``."""

import sys

from snowgrid.main import main

sys.exit(main())
