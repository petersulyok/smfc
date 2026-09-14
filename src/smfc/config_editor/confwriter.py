#
#   confwriter.py (C) 2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.config_editor.confwriter: change a configuration file without losing its comments.
#
import os
import re
import tempfile
from typing import Dict, List, Optional, Sequence, Tuple

from smfc.discover import format_device_list

# A section header line, e.g. "[CPU]" or "[CPU:1]".
SECTION_RE = re.compile(r"^\[([^\]]+)\]\s*$")

# A parameter line, e.g. "min_temp=30.0". A commented-out example does not count: it documents a
# parameter that has no value, and the editor must not treat it as one.
KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


class ConfWriter:
    """Read a configuration file, change parameters in it, and write it back with its comments intact.

    `ConfigParser` reads a file into a dictionary and writes a new file from that dictionary, so every
    comment is lost on the first save. The shipped `smfc.conf` is mostly comments, and so is a live one,
    so this writer edits the lines instead: it replaces the text after `=` on the line that holds the
    parameter and leaves every other byte of the file where it was.
    """

    path: str               # Path of the configuration file
    lines: List[str]        # Content of the file, one entry per line, newline included

    def __init__(self, path: str) -> None:
        """Read a configuration file.
        Args:
            path (str): path of the configuration file
        Raises:
            FileNotFoundError: the file does not exist
        """
        self.path = path
        with open(path, "rt", encoding="utf-8") as file:
            self.lines = file.readlines()

    @property
    def text(self) -> str:
        """Render the current content.
        Returns:
            str: the whole file as one string
        """
        return "".join(self.lines)

    def sections(self) -> List[str]:
        """List the section names of the file, in file order.
        Returns:
            List[str]: section names, instance numbers included (e.g. "CPU", "CPU:1")
        """
        return [m.group(1) for m in (SECTION_RE.match(line) for line in self.lines) if m]

    def has_section(self, section: str) -> bool:
        """Check whether the file holds a section.
        Args:
            section (str): section name
        Returns:
            bool: True if the section is in the file
        """
        return self._section_bounds(section) is not None

    def keys(self, section: str) -> List[str]:
        """List the parameters a section holds, in file order.
        Args:
            section (str): section name
        Returns:
            List[str]: parameter names, empty if the section is not in the file
        """
        bounds = self._section_bounds(section)
        if bounds is None:
            return []
        start, end = bounds
        result: List[str] = []
        index = start + 1
        while index < end:
            match = KEY_RE.match(self.lines[index])
            if match:
                result.append(match.group(1))
                index = self._value_end(index)
                continue
            index += 1
        return result

    def get(self, section: str, key: str) -> Optional[str]:
        """Read the current value of one parameter.
        Args:
            section (str): section name
            key (str): parameter name
        Returns:
            Optional[str]: the value as written, continuation lines included, or None if it is absent
        """
        found = self._find_key(section, key)
        if found is None:
            return None
        start, end = found
        first = KEY_RE.match(self.lines[start]).group(2)
        rest = [line.rstrip("\n") for line in self.lines[start + 1:end]]
        return "\n".join([first] + rest) if rest else first

    def set(self, section: str, key: str, value: str) -> None:
        """Write one parameter, replacing its value or adding the parameter to the section.
        Only the parameter line changes. The comment above it, the order of the other parameters and
        every other byte of the file stay where they are.
        Args:
            section (str): section name
            key (str): parameter name
            value (str): new value, which may carry continuation lines
        Raises:
            KeyError: the section is not in the file
        """
        bounds = self._section_bounds(section)
        if bounds is None:
            raise KeyError(f"[{section}] is not in {self.path}")
        found = self._find_key(section, key)
        # A value may carry continuation lines. It has to enter the list as one entry per line, or a
        # later lookup cannot see the key: the pattern that finds a parameter matches a single line.
        new_lines = f"{key}={value}\n".splitlines(keepends=True)
        if found is not None:
            start, end = found
            self.lines[start:end] = new_lines
            return
        point = self._insert_point(bounds)
        self.lines[point:point] = new_lines

    def set_device_list(self, section: str, key: str, devices: Sequence[str]) -> None:
        """Write a device list parameter in the form the parser needs.
        Args:
            section (str): section name
            key (str): parameter name (e.g. "hd_names")
            devices (Sequence[str]): device paths
        """
        self.set(section, key, format_device_list(devices))

    def add_section(self, section: str, values: Optional[Dict[str, str]] = None) -> None:
        """Append a section to the file.
        Only the parameters given are written. Every other parameter of that family then runs on its
        documented default, which is what the parser applies for a parameter that is absent.
        Args:
            section (str): section name
            values (Optional[Dict[str, str]]): parameters to write, in the order given
        Raises:
            KeyError: the section is already in the file
        """
        if self.has_section(section):
            raise KeyError(f"[{section}] is already in {self.path}")
        while self.lines and not self.lines[-1].strip():
            self.lines.pop()
        if self.lines:
            self.lines.append("\n")
        self.lines.append(f"[{section}]\n")
        for key, value in (values or {}).items():
            self.lines.extend(f"{key}={value}\n".splitlines(keepends=True))

    def remove_section(self, section: str) -> None:
        """Remove a section and every parameter in it.
        The comment block above the header goes with it, because it describes the section that is
        leaving. A blank line before that block is kept, so the file does not lose its spacing.
        Args:
            section (str): section name
        Raises:
            KeyError: the section is not in the file
        """
        bounds = self._section_bounds(section)
        if bounds is None:
            raise KeyError(f"[{section}] is not in {self.path}")
        start, end = bounds
        while start > 0 and self.lines[start - 1].lstrip().startswith("#"):
            start -= 1
        del self.lines[start:end]

    def save(self, path: Optional[str] = None) -> None:
        """Write the file back, through a temporary file in the same directory.
        A configuration file that is half written drives the fans of a live machine, so the new content
        is complete on disk before it takes the place of the old one. `os.replace()` is atomic on the
        same file system.
        Args:
            path (Optional[str]): path to write (default: the file that was read)
        """
        target = path or self.path
        directory = os.path.dirname(os.path.abspath(target))
        mode = os.stat(target).st_mode & 0o777 if os.path.exists(target) else 0o644
        handle, temp_path = tempfile.mkstemp(dir=directory, prefix=".smfc-", suffix=".conf")
        try:
            with os.fdopen(handle, "wt", encoding="utf-8") as file:
                file.write(self.text)
            os.chmod(temp_path, mode)
            os.replace(temp_path, target)
        except BaseException:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    # -- internals ---------------------------------------------------------------------------------

    def _section_bounds(self, section: str) -> Optional[Tuple[int, int]]:
        """Find the line range of a section.
        Args:
            section (str): section name
        Returns:
            Optional[Tuple[int, int]]: the header line index and the index after the last line of the
                section, or None if the section is not in the file
        """
        start: Optional[int] = None
        for index, line in enumerate(self.lines):
            match = SECTION_RE.match(line)
            if not match:
                continue
            if start is not None:
                return start, index
            if match.group(1) == section:
                start = index
        return (start, len(self.lines)) if start is not None else None

    def _value_end(self, start: int) -> int:
        """Find where the value of a parameter ends.
        A value may run over several lines: `configparser` reads a line that begins with whitespace as
        a continuation of the parameter above it. That is how a device list is written.
        Args:
            start (int): index of the parameter line
        Returns:
            int: index of the first line that is not part of the value
        """
        index = start + 1
        while index < len(self.lines):
            line = self.lines[index]
            if not line.strip() or not line[0].isspace():
                break
            index += 1
        return index

    def _find_key(self, section: str, key: str) -> Optional[Tuple[int, int]]:
        """Find the line range of one parameter inside one section.
        Args:
            section (str): section name
            key (str): parameter name
        Returns:
            Optional[Tuple[int, int]]: the first and the after-last line index of the parameter, or
                None if the section or the parameter is absent
        """
        bounds = self._section_bounds(section)
        if bounds is None:
            return None
        start, end = bounds
        index = start + 1
        while index < end:
            match = KEY_RE.match(self.lines[index])
            if match and match.group(1) == key:
                return index, self._value_end(index)
            index = self._value_end(index) if match else index + 1
        return None

    def _insert_point(self, bounds: Tuple[int, int]) -> int:
        """Find where a new parameter goes inside a section.
        It goes after the last parameter of the section, so the comment blocks of the parameters that
        are already there keep standing above their own parameter.
        Args:
            bounds (Tuple[int, int]): the line range of the section
        Returns:
            int: index the new parameter line is inserted at
        """
        start, end = bounds
        last = start + 1
        for index in range(start + 1, end):
            if KEY_RE.match(self.lines[index]) or self.lines[index].strip():
                last = index + 1
        return last


def is_writable(path: str) -> bool:
    """Check whether this process may write a configuration file.
    The editor tests this before it draws anything, so a user without the rights is told at once
    rather than after twenty fields are edited.
    Args:
        path (str): path of the configuration file
    Returns:
        bool: True if the file can be written, or created in an existing directory
    """
    if os.path.exists(path):
        return os.access(path, os.W_OK)
    return os.access(os.path.dirname(os.path.abspath(path)) or ".", os.W_OK)


# End.
