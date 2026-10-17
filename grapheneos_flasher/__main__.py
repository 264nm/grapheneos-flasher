"""
Main module for direct package execution

Usage:
    python -m grapheneos_flasher <device> [--flash] [--release RELEASE]
"""

from grapheneos_flasher.cli import main

if __name__ == "__main__":
    main()
