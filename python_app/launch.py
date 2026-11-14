"""PyInstaller-friendly launcher for the Prism Python application."""

from python_app.desktop import main

if __name__ == "__main__":
    raise SystemExit(main())
