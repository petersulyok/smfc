#
#   lineedit.py (C) 2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.config_editor.lineedit: the one-line text editor of smfc-config.
#
import curses
from dataclasses import dataclass
from typing import Tuple

# The keys that edit a line, named once so the two places that type a value behave the same.
KEY_BACKSPACE: tuple = (curses.KEY_BACKSPACE, 127, 8)
KEY_DELETE: tuple = (curses.KEY_DC,)
KEY_HOME: tuple = (curses.KEY_HOME, 1)
KEY_END: tuple = (curses.KEY_END, 5)
KEY_INSERT: tuple = (curses.KEY_IC,)


@dataclass
class LineEdit:
    """One line of text being typed, with a caret and an insert flag.

    A value is typed in two places: the value cell of the parameter pane and the input field of a
    popup. Both use this, so the keys mean the same thing in both.
    """
    text: str = ""          # The value being typed
    caret: int = 0          # Where the next character lands, 0..len(text)
    insert: bool = True     # True to push the text along, False to type over it

    @classmethod
    def of(cls, text: str) -> "LineEdit":
        """Open a value for editing, with the caret at its end.
        Args:
            text (str): the value the file holds
        Returns:
            LineEdit: the editor state
        """
        return cls(text=text, caret=len(text))

    def handle_key(self, key: int) -> bool:
        """Act on one key press.
        Args:
            key (int): the key, as curses reports it
        Returns:
            bool: True when the key was used, False when the caller should handle it
        """
        if key == curses.KEY_LEFT:
            self.caret = max(0, self.caret - 1)
        elif key == curses.KEY_RIGHT:
            self.caret = min(len(self.text), self.caret + 1)
        elif key in KEY_HOME:
            self.caret = 0
        elif key in KEY_END:
            self.caret = len(self.text)
        elif key in KEY_INSERT:
            self.insert = not self.insert
        elif key in KEY_BACKSPACE:
            if self.caret > 0:
                self.text = self.text[:self.caret - 1] + self.text[self.caret:]
                self.caret -= 1
        elif key in KEY_DELETE:
            self.text = self.text[:self.caret] + self.text[self.caret + 1:]
        elif 32 <= key < 127:
            # Overwrite replaces the character under the caret, except at the end of the line, where
            # there is nothing to replace and both modes append.
            tail = self.text[self.caret:] if self.insert else self.text[self.caret + 1:]
            self.text = self.text[:self.caret] + chr(key) + tail
            self.caret += 1
        else:
            return False
        return True

    def view(self, width: int) -> Tuple[str, int]:
        """The part of the line that fits the field, and where the caret sits in it.
        A value can be longer than its field, so the window follows the caret rather than the start
        of the text: the user always sees what is being typed.
        Args:
            width (int): columns the field has
        Returns:
            Tuple[str, int]: the text to draw, padded to the width, and the caret column in it
        """
        if width <= 0:
            return "", 0
        # One column is kept for the caret sitting after the last character.
        start = max(0, self.caret - width + 1)
        return self.text[start:start + width].ljust(width), self.caret - start
