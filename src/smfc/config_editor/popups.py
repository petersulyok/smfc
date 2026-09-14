#
#   popups.py (C) 2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.config_editor.popups: the windows that open over the panes, with no terminal code in them.
#
import curses
from dataclasses import dataclass, field as dataclass_field
from typing import Callable, List, Optional, Sequence, Tuple

from smfc.config_editor.panes import fit

# Keys every popup answers to. The letters of the device selector are on top of these.
KEY_ACCEPT: tuple = (curses.KEY_ENTER, 10, 13)
KEY_CANCEL: tuple = (27,)
KEY_BACKSPACE: tuple = (curses.KEY_BACKSPACE, 127, 8)


@dataclass
class Popup:
    """What every popup has: a title, a size, lines to draw, and an answer when it closes.

    A popup owns its state and its keys and knows nothing about the terminal, the same way the model
    and the panes do. `app.py` draws the lines it returns and forwards the keys it did not use.
    """
    title: str                                  # Shown in the top border
    width: int = 60                             # Width of the window
    done: bool = False                          # True once the popup wants to close
    accepted: bool = False                      # True when it closed on Enter rather than Esc
    error: str = ""                             # Why the value was refused, empty when it was not

    def lines(self) -> List[str]:
        """The body of the window.
        Returns:
            List[str]: one entry per line
        """
        raise NotImplementedError

    def keys(self) -> str:
        """The key list of this popup, shown on its last line.
        Returns:
            str: the keys
        """
        return "Enter OK   Esc cancel"

    def handle_key(self, key: int) -> None:
        """Act on one key press.
        Args:
            key (int): the key, as curses reports it
        """
        raise NotImplementedError

    def value(self):
        """The answer of the popup.
        Returns:
            Any: what the caller asked for, or None when it was cancelled
        """
        return None

    def cursor(self) -> int:
        """Index of the selected line of the body, for the highlight.
        Returns:
            int: the line, or -1 when nothing is selected
        """
        return -1

    def height(self) -> int:
        """Height of the window.
        Returns:
            int: rows, both borders and the key line included
        """
        return len(self.lines()) + 4

    def _cancel(self) -> None:
        """Close the popup without an answer."""
        self.done = True
        self.accepted = False


@dataclass
class TextPopup(Popup):
    """A wide input field for a value the right pane is too narrow to hold.

    A path can be 51 characters and a curve 27, while the value cell holds about 21. The popup also
    has room for the help text of the parameter and for the reason a value was refused.
    """
    text: str = ""                              # The value being typed
    summary: str = ""                           # One line about the parameter
    detail: str = ""                            # The range or the syntax
    validator: Optional[Callable[[str], str]] = None    # Returns why the value is wrong, or ""

    def lines(self) -> List[str]:
        """The body: the help, the input field, and the reason a value was refused.
        Returns:
            List[str]: one entry per line
        """
        body = [self.summary, self.detail, "", f"[{self.text}]"]
        if self.error:
            body.append(f"! {self.error}")
        return [fit(line, self.width - 4) for line in body]

    def handle_key(self, key: int) -> None:
        """Type into the field, accept it, or cancel.
        A value the parser would refuse does not close the popup: the reason is shown and the text
        stays, so the user can correct it. Esc always closes, so nobody is trapped.
        Args:
            key (int): the key, as curses reports it
        """
        if key in KEY_CANCEL:
            self._cancel()
        elif key in KEY_ACCEPT:
            self.error = self.validator(self.text.strip()) if self.validator else ""
            if not self.error:
                self.done = True
                self.accepted = True
        elif key in KEY_BACKSPACE:
            self.text = self.text[:-1]
            self.error = ""
        elif 32 <= key < 127:
            self.text += chr(key)
            self.error = ""

    def value(self) -> Optional[str]:
        """The text that was typed.
        Returns:
            Optional[str]: the value, or None when the popup was cancelled
        """
        return self.text.strip() if self.accepted else None


@dataclass
class ChoicePopup(Popup):
    """A list of the values one parameter accepts, with the label of each."""
    choices: Sequence[str] = ()                 # The values, as they are written into the file
    labels: Sequence[str] = ()                  # What each value means
    index: int = 0                              # The selected entry
    summary: str = ""                           # One line about the parameter

    def lines(self) -> List[str]:
        """The body: the help, then one line per choice.
        Returns:
            List[str]: one entry per line
        """
        body = [self.summary, ""]
        for choice, label in zip(self.choices, self.labels or self.choices):
            body.append(f"{choice}   {label}")
        return [fit(line, self.width - 4) for line in body]

    def cursor(self) -> int:
        """Index of the selected line of the body.
        Returns:
            int: the line the choice sits on
        """
        return self.index + 2

    def handle_key(self, key: int) -> None:
        """Move through the choices, accept one, or cancel.
        Args:
            key (int): the key, as curses reports it
        """
        if key in KEY_CANCEL:
            self._cancel()
        elif key in KEY_ACCEPT:
            self.done = True
            self.accepted = True
        elif key in (curses.KEY_UP, ord("k")):
            self.index = max(self.index - 1, 0)
        elif key in (curses.KEY_DOWN, ord("j")):
            self.index = min(self.index + 1, len(self.choices) - 1)

    def value(self) -> Optional[str]:
        """The chosen value.
        Returns:
            Optional[str]: the value, or None when the popup was cancelled
        """
        return str(self.choices[self.index]) if self.accepted else None


@dataclass
class DeviceEntry:
    """One line of the device selector."""
    path: str                   # What is written into the file
    label: str                  # Serial, size, kernel name and model, or "(missing)"
    ticked: bool = False        # True when the configuration lists it
    present: bool = True        # False when the machine does not have it


@dataclass
class DevicePopup(Popup):
    """The multi-select of the device lists.

    The serial leads every line, because a machine can hold eight disks of one model and the serial is
    the only part that tells them apart. An entry the configuration lists and the machine does not have
    is kept and marked, because that is what explains a warning about a missing disk.
    """
    entries: List[DeviceEntry] = dataclass_field(default_factory=list)
    index: int = 0                              # The selected entry
    note: str = ""                              # One line under the list

    def lines(self) -> List[str]:
        """The body: one line per device, then the note.
        Returns:
            List[str]: one entry per line
        """
        body = [f"[{'x' if e.ticked else ' '}] {e.label}" for e in self.entries]
        if not body:
            body = ["no device found"]
        if self.note:
            body += ["", self.note]
        return [fit(line, self.width - 4) for line in body]

    def keys(self) -> str:
        """The key list of the selector.
        Returns:
            str: the keys
        """
        return "Space toggle   a all   n none   p add by path   Enter OK   Esc cancel"

    def cursor(self) -> int:
        """Index of the selected line of the body.
        Returns:
            int: the line, or -1 when the list is empty
        """
        return self.index if self.entries else -1

    def handle_key(self, key: int) -> None:
        """Tick devices, accept the list, or cancel.
        Args:
            key (int): the key, as curses reports it
        """
        if key in KEY_CANCEL:
            self._cancel()
        elif key in KEY_ACCEPT:
            self.done = True
            self.accepted = True
        elif key in (curses.KEY_UP, ord("k")):
            self.index = max(self.index - 1, 0)
        elif key in (curses.KEY_DOWN, ord("j")):
            self.index = min(self.index + 1, max(len(self.entries) - 1, 0))
        elif key == ord(" ") and self.entries:
            self.entries[self.index].ticked = not self.entries[self.index].ticked
        elif key == ord("a"):
            for entry in self.entries:
                entry.ticked = True
        elif key == ord("n"):
            for entry in self.entries:
                entry.ticked = False

    def add_path(self, path: str) -> None:
        """Add a device the machine does not have, typed by hand.
        A user replacing a failed disk, or preparing a machine before the disks arrive, needs to name
        one that is not there yet. It is marked missing, like an entry that stopped resolving.
        Args:
            path (str): the /dev/disk/by-id/... path
        """
        if any(entry.path == path for entry in self.entries):
            return
        self.entries.append(DeviceEntry(path=path, label=f"(missing)  {path.split('/')[-1]}",
                                        ticked=True, present=False))
        self.index = len(self.entries) - 1

    def value(self) -> Optional[List[str]]:
        """The devices that are ticked.
        Returns:
            Optional[List[str]]: the paths, sorted as the file holds them, or None when cancelled
        """
        if not self.accepted:
            return None
        return sorted(entry.path for entry in self.entries if entry.ticked)


@dataclass
class ConfirmPopup(Popup):
    """A question with two answers, for something that cannot be undone."""
    question: str = ""              # What is being asked
    detail: str = ""                # What it will cost

    def lines(self) -> List[str]:
        """The body: the question and what it costs.
        Returns:
            List[str]: one entry per line
        """
        return [fit(line, self.width - 4) for line in (self.question, self.detail)]

    def keys(self) -> str:
        """The key list of the question.
        Returns:
            str: the keys
        """
        return "y yes   n no   Esc cancel"

    def handle_key(self, key: int) -> None:
        """Answer the question.
        Args:
            key (int): the key, as curses reports it
        """
        if key in (ord("y"), ord("Y")):
            self.done = True
            self.accepted = True
        elif key in (ord("n"), ord("N")) or key in KEY_CANCEL:
            self._cancel()

    def value(self) -> bool:
        """The answer.
        Returns:
            bool: True for yes
        """
        return self.accepted


@dataclass
class InstancePopup(Popup):
    """The dialog that adds one more fan curve to a family.

    Two enabled instances of one family may not share an IPMI zone, so the dialog offers the zones no
    enabled instance of that family claims.
    """
    families: Sequence[str] = ()                # Families that accept another instance
    zones: Sequence[int] = ()                   # Zones that are free for the chosen family
    index: int = 0                              # The selected family
    zone_index: int = 0                         # The selected zone
    on_family: Optional[Callable[[str], List[int]]] = None      # Free zones of a family

    def lines(self) -> List[str]:
        """The body: the families, then the zones of the one that is selected.
        Returns:
            List[str]: one entry per line
        """
        body = ["family:"]
        body += [f"  {name}" for name in self.families]
        body += ["", f"zone: {self.zones[self.zone_index] if self.zones else 'none free'}"]
        return [fit(line, self.width - 4) for line in body]

    def keys(self) -> str:
        """The key list of the dialog.
        Returns:
            str: the keys
        """
        return "up down family   left right zone   Enter add   Esc cancel"

    def cursor(self) -> int:
        """Index of the selected line of the body.
        Returns:
            int: the line the family sits on
        """
        return self.index + 1

    def handle_key(self, key: int) -> None:
        """Choose a family and a zone, add it, or cancel.
        Args:
            key (int): the key, as curses reports it
        """
        if key in KEY_CANCEL:
            self._cancel()
        elif key in KEY_ACCEPT:
            if self.zones:
                self.done = True
                self.accepted = True
            else:
                self.error = "every zone of this family is taken by an enabled instance"
        elif key in (curses.KEY_UP, ord("k")):
            self._select(max(self.index - 1, 0))
        elif key in (curses.KEY_DOWN, ord("j")):
            self._select(min(self.index + 1, len(self.families) - 1))
        elif key in (curses.KEY_LEFT, ord("h")):
            self.zone_index = max(self.zone_index - 1, 0)
        elif key in (curses.KEY_RIGHT, ord("l")):
            self.zone_index = min(self.zone_index + 1, max(len(self.zones) - 1, 0))

    def value(self) -> Optional[Tuple[str, int]]:
        """The family and the zone that were chosen.
        Returns:
            Optional[Tuple[str, int]]: the family name and the zone, or None when cancelled
        """
        if not self.accepted or not self.zones:
            return None
        return self.families[self.index], self.zones[self.zone_index]

    def _select(self, index: int) -> None:
        """Choose a family and read the zones it still has free.
        Args:
            index (int): index of the family
        """
        self.index = index
        self.zone_index = 0
        self.error = ""
        if self.on_family:
            self.zones = self.on_family(self.families[index])


# End.
