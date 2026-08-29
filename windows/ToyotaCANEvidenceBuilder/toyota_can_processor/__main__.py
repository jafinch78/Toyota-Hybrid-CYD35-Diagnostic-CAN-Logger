from __future__ import annotations

import sys


if len(sys.argv) == 1:
    from .gui import main
    main()
else:
    from .cli import main
    raise SystemExit(main())
