"""Entry point: python3 -m lobot_tui"""

import sys

from .app import LobotApp


def main():
    app = LobotApp()
    app.run()
    # Clear terminal after exit (works on both alternate-screen and inline modes)
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
