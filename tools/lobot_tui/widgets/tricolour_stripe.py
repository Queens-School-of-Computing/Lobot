"""TricolourStripe: thin Queen's gold+red dividing stripe."""

from rich.text import Text
from textual.widget import Widget

_GOLD = "#fabd0f"
_RED = "#af0000"
_CHROME = "#002452"


class TricolourStripe(Widget):
    """One row, 50% gold / 50% red, using a half-block character for thinness."""

    DEFAULT_CSS = """
    TricolourStripe {
        height: 1;
        width: 1fr;
    }
    """

    def __init__(self, char: str = "▄", **kwargs) -> None:
        super().__init__(**kwargs)
        self._char = char

    def render(self) -> Text:
        w = self.size.width
        half = w // 2
        t = Text(no_wrap=True)
        t.append(self._char * half,       style=f"{_GOLD} on {_CHROME}")
        t.append(self._char * (w - half), style=f"{_RED} on {_CHROME}")
        return t
