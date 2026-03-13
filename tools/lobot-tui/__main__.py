"""Entry point: python3 -m lobot_tui"""

from .app import LobotApp


def main():
    app = LobotApp()
    app.run()


if __name__ == "__main__":
    main()
