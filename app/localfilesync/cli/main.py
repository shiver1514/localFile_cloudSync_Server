"""Compatibility CLI entrypoint for `python -m localfilesync.cli.main`."""

from app.cli.main import app, main

__all__ = ["app", "main"]


if __name__ == "__main__":
    main()
