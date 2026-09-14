#
#   model.py (C) 2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.config_editor.model: the state of the editor, with no terminal code in it.
#
from dataclasses import dataclass, field as dataclass_field
from enum import Enum
from typing import Dict, List, Optional

from smfc.checks import CheckResult, Level, check_all, loaded_modules
from smfc.config import Config
from smfc.config_editor.confwriter import ConfWriter, is_writable
from smfc.config_editor.schema import SECTIONS, Field, Section, family_of, section_of, validate

# Name of the row that carries the findings belonging to no section.
OVERVIEW: str = "Overview"


class RowKind(str, Enum):
    """Kind of a row in the section list."""
    INSTANCE = "instance"       # a section the file holds, e.g. [CPU] or [CPU:1]
    ABSENT = "absent"           # a family the file does not hold; it reads as disabled
    SEPARATOR = "separator"     # the line above the Overview row
    OVERVIEW = "overview"       # the findings that belong to no section


class FieldState(str, Enum):
    """State of one parameter in the right pane."""
    NORMAL = "normal"           # editable
    INVALID = "invalid"         # the value in the file is not one the parser would accept
    INACTIVE = "inactive"       # a control_function= value overrides it
    UNKNOWN = "unknown"         # the file holds it and the schema does not; read-only, never deleted


@dataclass
class Row:
    """One row of the section list."""
    name: str                   # Section name as written in the file, or the family name if absent
    family: str                 # Family name (e.g. "CPU")
    kind: RowKind               # Kind of the row
    enabled: bool = False       # State of the enabled= parameter
    toggleable: bool = True     # False for [Ipmi], which is always active

    @property
    def selectable(self) -> bool:
        """Whether the cursor may stop on this row.
        Returns:
            bool: False for the separator line
        """
        return self.kind is not RowKind.SEPARATOR


@dataclass
class FieldView:
    """One parameter of the selected section, as the right pane shows it."""
    key: str                            # Parameter name
    value: str                          # Value as written in the file, or the default
    state: FieldState                   # Whether it is editable, overridden or unknown
    field: Optional[Field] = None       # Schema metadata, None for a parameter the schema does not know
    reason: str = ""                    # Why the parameter is inactive, empty otherwise


@dataclass
class EditorModel:
    """Everything the editor knows about one configuration file.

    `ConfWriter` is the source of truth: it is line-based, so it opens a file the parser rejects. That
    matters, because the shipped configuration file is such a file until the installer fills the disks
    in. `Config` is used only to validate, and its failure becomes a finding rather than a crash.
    """
    path: str                                                   # Path of the configuration file
    writer: ConfWriter                                          # Line-level access to the file
    read_only: bool                                             # True when the file cannot be written
    dirty: bool = False                                         # True when there are unsaved changes
    rows: List[Row] = dataclass_field(default_factory=list)     # The section list
    findings: Dict[str, List[CheckResult]] = dataclass_field(default_factory=dict)   # Findings per row
    checked: bool = False                                       # True once the checks have run

    @classmethod
    def load(cls, path: str) -> "EditorModel":
        """Read a configuration file into a model.
        Args:
            path (str): path of the configuration file
        Returns:
            EditorModel: the model
        Raises:
            FileNotFoundError: the file does not exist
        """
        model = cls(path=path, writer=ConfWriter(path), read_only=not is_writable(path))
        model.build_rows()
        return model

    def build_rows(self) -> None:
        """Build the section list from the schema, with the instances the file holds.

        The list always carries the same families, because a missing section and `enabled=0` mean the
        same thing to smfc. A family the file does not hold is one row, disabled. A family the file
        holds several times is one row per instance, because each instance is a complete controller.
        """
        in_file = self.writer.sections()
        rows: List[Row] = []
        for name, section in SECTIONS.items():
            instances = [s for s in in_file if family_of(s) == name]
            if not instances:
                rows.append(Row(name=name, family=name, kind=RowKind.ABSENT,
                                toggleable=section.toggleable))
                continue
            for instance in instances:
                rows.append(Row(name=instance, family=name, kind=RowKind.INSTANCE,
                                enabled=self._enabled(instance, section),
                                toggleable=section.toggleable))
        rows.append(Row(name="", family="", kind=RowKind.SEPARATOR))
        rows.append(Row(name=OVERVIEW, family="", kind=RowKind.OVERVIEW))
        self.rows = rows

    def fields_of(self, row: Row) -> List[FieldView]:
        """Build the parameter list of one row, as the right pane shows it.
        Args:
            row (Row): the selected row
        Returns:
            List[FieldView]: the parameters in schema order, then any parameter the schema does not know
        """
        section = section_of(row.family)
        if section is None or row.kind in (RowKind.SEPARATOR, RowKind.OVERVIEW):
            return []
        present = self.writer.keys(row.name) if row.kind is RowKind.INSTANCE else []
        has_curve = bool(self._raw(row, "control_function"))
        result: List[FieldView] = []
        for f in section.fields:
            raw = self._raw(row, f.key)
            value = raw if raw is not None else _default_text(f)
            state = FieldState.NORMAL
            reason = ""
            if has_curve and f.overridden_by_curve:
                state = FieldState.INACTIVE
                reason = "ignored: control_function is set"
            elif raw is not None:
                # Only a value the file actually holds can be wrong. A default never is.
                problem = validate(f, raw)
                if problem:
                    state = FieldState.INVALID
                    reason = problem
            result.append(FieldView(key=f.key, value=value, state=state, field=f, reason=reason))
        for key in present:
            if section.field(key) is None:
                result.append(FieldView(key=key, value=self._raw(row, key) or "",
                                        state=FieldState.UNKNOWN, reason="smfc does not know this key"))
        return result

    def value_of(self, row: Row, key: str) -> str:
        """Read the value of one parameter as the pane shows it.
        Args:
            row (Row): the selected row
            key (str): parameter name
        Returns:
            str: the value in the file, or the default when the parameter is absent
        """
        raw = self._raw(row, key)
        if raw is not None:
            return raw
        f = section_of(row.family).field(key) if section_of(row.family) else None
        return _default_text(f) if f else ""

    def set_value(self, row: Row, key: str, value: str) -> None:
        """Write one parameter. The section is created first when the family is not in the file yet.
        Args:
            row (Row): the selected row
            key (str): parameter name
            value (str): new value
        """
        self._ensure_section(row)
        self.writer.set(row.name, key, value)
        self.dirty = True
        if key == "enabled":
            row.enabled = value.strip() in ("1", "true", "yes", "on")

    def set_device_list(self, row: Row, key: str, devices: List[str]) -> None:
        """Write a device list in the form the parser needs.
        The first device sits on the key line, because a value that starts with a newline parses into
        an empty first element. `confwriter` holds that rule.
        Args:
            row (Row): the selected row
            key (str): parameter name
            devices (List[str]): device paths
        """
        self._ensure_section(row)
        self.writer.set_device_list(row.name, key, devices)
        self.dirty = True

    def toggle(self, row: Row) -> bool:
        """Switch a family on or off.
        Switching off writes `enabled=0` and keeps every value the user typed, so a family turned off
        for a week keeps its device list.
        Args:
            row (Row): the selected row
        Returns:
            bool: True if the row was switched, False when it carries no enabled= parameter
        """
        if not row.toggleable or row.kind in (RowKind.SEPARATOR, RowKind.OVERVIEW):
            return False
        self.set_value(row, "enabled", "0" if row.enabled else "1")
        return True

    def add_instance(self, family: str, values: Optional[Dict[str, str]] = None) -> str:
        """Add a numbered instance to a family.
        The suffix is only ordering and logging, so the next free number is used: `[CPU]` plus
        `[CPU:1]` is a valid pair and `[CPU:0]` need not exist.
        Args:
            family (str): family name (e.g. "CPU")
            values (Optional[Dict[str, str]]): parameters to write into the new section
        Returns:
            str: name of the new section
        Raises:
            KeyError: the family does not accept numbered instances
        """
        section = SECTIONS.get(family)
        if section is None or not section.repeatable:
            raise KeyError(f"[{family}] does not accept numbered instances")
        used = {s for s in self.writer.sections() if family_of(s) == family}
        number = 1
        while f"{family}:{number}" in used:
            number += 1
        name = f"{family}:{number}"
        self.writer.add_section(name, values or {"enabled": "0"})
        self.dirty = True
        self.build_rows()
        return name

    def remove_instance(self, row: Row) -> None:
        """Remove one instance of a family from the file.
        Args:
            row (Row): the selected row
        Raises:
            KeyError: the row is not a section of the file
        """
        if row.kind is not RowKind.INSTANCE:
            raise KeyError(f"[{row.name}] is not in the file")
        self.writer.remove_section(row.name)
        self.dirty = True
        self.build_rows()

    def free_zones(self, family: str, count: int = 8) -> List[int]:
        """List the IPMI zones no enabled instance of a family claims.
        Two enabled instances of one family may not share a zone, which the parser enforces. A disabled
        instance claims nothing.
        Args:
            family (str): family name
            count (int): how many zone numbers to consider
        Returns:
            List[int]: the zones that are free for a new instance of that family
        """
        claimed = set()
        for row in self.rows:
            if row.family != family or row.kind is not RowKind.INSTANCE or not row.enabled:
                continue
            for part in (self._raw(row, "ipmi_zone") or "").replace(",", " ").split():
                if part.isdigit():
                    claimed.add(int(part))
        return [zone for zone in range(count) if zone not in claimed]

    def run_checks(self, modules: Optional[str] = None) -> None:
        """Run the parse tier and the dependency checks, and group the findings by row.
        Args:
            modules (Optional[str]): content of /proc/modules, read from the system when omitted
        """
        findings: Dict[str, List[CheckResult]] = {}

        def add(result: CheckResult) -> None:
            findings.setdefault(result.section, []).append(result)

        try:
            config = Config(self.path)
        except (ValueError, FileNotFoundError) as error:
            add(_parse_finding(error))
            self.findings = findings
            self.checked = True
            return
        for result in check_all(config, modules if modules is not None else loaded_modules()):
            add(result)
        self.findings = findings
        self.checked = True

    def findings_of(self, row: Row) -> List[CheckResult]:
        """Read the findings that belong to one row.
        Args:
            row (Row): the row
        Returns:
            List[CheckResult]: its findings, empty if it has none
        """
        return self.findings.get(OVERVIEW if row.kind is RowKind.OVERVIEW else row.name, [])

    def worst_level(self, row: Row) -> Optional[Level]:
        """Read the most severe finding of one row.
        Args:
            row (Row): the row
        Returns:
            Optional[Level]: ERROR, WARN, INFO, or None when the row has no finding
        """
        levels = [f.level for f in self.findings_of(row)]
        for level in (Level.ERROR, Level.WARN, Level.INFO):
            if level in levels:
                return level
        return None

    def save(self) -> List[CheckResult]:
        """Write the file and report what the result is worth.
        Nothing blocks a save. A user who opens a file with errors must be able to save partial
        progress and come back later, so the errors are reported rather than enforced.
        Args:
            None
        Returns:
            List[CheckResult]: the findings of the saved file
        Raises:
            PermissionError: the file cannot be written
        """
        if self.read_only:
            raise PermissionError(f"{self.path} is not writable")
        self.writer.save()
        self.dirty = False
        self.run_checks()
        return [f for results in self.findings.values() for f in results]

    def has_errors(self) -> bool:
        """Whether the file would stop the daemon from starting.
        Returns:
            bool: True if any finding is an error
        """
        return any(f.level is Level.ERROR for results in self.findings.values() for f in results)

    # -- internals ---------------------------------------------------------------------------------

    def _enabled(self, section_name: str, section: Section) -> bool:
        """Read the enabled= parameter of one section.
        Args:
            section_name (str): section name as written in the file
            section (Section): schema metadata of its family
        Returns:
            bool: True when the section is enabled, and for a section that has no enabled= parameter
        """
        if not section.toggleable:
            return True
        value = self.writer.get(section_name, "enabled")
        return value.strip() in ("1", "true", "yes", "on") if value else False

    def _raw(self, row: Row, key: str) -> Optional[str]:
        """Read a parameter straight from the file.
        Args:
            row (Row): the selected row
            key (str): parameter name
        Returns:
            Optional[str]: the value as written, or None when the section or the parameter is absent
        """
        if row.kind is not RowKind.INSTANCE:
            return None
        return self.writer.get(row.name, key)

    def _ensure_section(self, row: Row) -> None:
        """Create the section of a row that is not in the file yet.
        Args:
            row (Row): the selected row
        """
        if row.kind is RowKind.ABSENT:
            self.writer.add_section(row.name)
            row.kind = RowKind.INSTANCE


def _default_text(f: Optional[Field]) -> str:
    """Render the default of a parameter the way the file would hold it.
    Args:
        f (Optional[Field]): schema metadata
    Returns:
        str: the default as text, empty for an unknown parameter
    """
    if f is None:
        return ""
    default = f.default
    if isinstance(default, bool):
        return "1" if default else "0"
    if isinstance(default, (list, tuple)):
        return ", ".join(str(item) for item in default)
    return str(default)


def _parse_finding(error: Exception) -> CheckResult:
    """Turn a parser failure into a finding of the section it names.
    `Config` raises with the section in brackets, e.g. "[HD] hd_names is not specified", so the finding
    can be placed on the right row. A message without a section goes to the Overview row.
    Args:
        error (Exception): the exception the parser raised
    Returns:
        CheckResult: an error finding
    """
    message = str(error)
    section = OVERVIEW
    if message.startswith("[") and "]" in message:
        section = message[1:message.index("]")]
    return CheckResult(Level.ERROR, section, message, "fix this parameter, then the next one is shown")


# End.
