from ._vendor import setup as _setup_vendor

_setup_vendor()

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
