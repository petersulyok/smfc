#!/usr/bin/env python3
#
#   test_config_editor.py (C) 2026, Peter Sulyok
#   Unit test for the smfc.config_editor model, panes, app and cmd modules.
#
import curses
import os
import shutil
from pathlib import Path
import pytest
from smfc.checks import Level
from smfc.config_editor import panes
from smfc.config_editor.app import EditorApp, PANE_FIELDS, PANE_SECTIONS
from smfc.config_editor.cmd import EXIT_CONFIG_ERROR, main
from smfc.config_editor.model import EditorModel, FieldState, RowKind
from smfc.config_editor.schema import SECTIONS


# Repository paths used by the tests.
REPO_ROOT: Path = Path(__file__).resolve().parent.parent
SHIPPED_CONF: Path = REPO_ROOT / "config" / "smfc.conf"

# A module list with nothing smfc needs in it, so the checks report what they should.
NO_MODULES: str = "usbcore 1 - Live 0x0\n"

# A small configuration with two sections.
SMALL: str = "[Ipmi]\ncommand=/usr/bin/ipmitool\n\n[CPU]\nenabled=1\nipmi_zone=0\nmin_temp=30.0\n"


def _model(tmp_path: Path, body: str = SMALL) -> EditorModel:
    """Build a model from a configuration file written for the test.
    Args:
        tmp_path (Path): pytest temporary directory
        body (str): content of the configuration file
    Returns:
        EditorModel: the model
    """
    path = tmp_path / "smfc.conf"
    path.write_text(body, encoding="utf-8")
    return EditorModel.load(str(path))


def _shipped(tmp_path: Path) -> EditorModel:
    """Build a model from a copy of the shipped configuration file.
    Args:
        tmp_path (Path): pytest temporary directory
    Returns:
        EditorModel: the model
    """
    path = tmp_path / "smfc.conf"
    shutil.copy(SHIPPED_CONF, path)
    return EditorModel.load(str(path))


def _row(model: EditorModel, name: str):
    """Find one row of the section list by name.
    Args:
        model (EditorModel): the editor state
        name (str): section or family name
    Returns:
        Row: the row
    """
    return [r for r in model.rows if r.name == name][0]


class TestEditorModel:
    """Unit test class for the smfc.config_editor.model module."""

    def test_the_section_list_holds_every_family_of_the_schema(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.build_rows(). It contains the following steps:
        - load a file that holds two sections out of nine
        - ASSERT: every family of the schema has a row, because a missing section reads as disabled
        - ASSERT: the families that are not in the file are marked absent
        - ASSERT: the list ends with a separator and the Overview row
        """
        model = _model(tmp_path)
        names = [r.name for r in model.rows if r.kind is not RowKind.SEPARATOR]
        assert set(SECTIONS) <= set(names)
        assert _row(model, "PCI").kind is RowKind.ABSENT
        assert _row(model, "CPU").kind is RowKind.INSTANCE
        assert model.rows[-1].kind is RowKind.OVERVIEW
        assert model.rows[-2].kind is RowKind.SEPARATOR

    def test_every_instance_of_a_family_is_its_own_row(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.build_rows(). It contains the following steps:
        - load a file that holds [CPU] and [CPU:1]
        - ASSERT: both are rows of their own, because each instance is a complete fan controller
        - ASSERT: there is no parent row above them
        """
        model = _model(tmp_path, "[Ipmi]\n[CPU]\nenabled=1\n[CPU:1]\nenabled=1\nipmi_zone=1\n")
        cpu_rows = [r.name for r in model.rows if r.family == "CPU"]
        assert cpu_rows == ["CPU", "CPU:1"]

    def test_the_ipmi_row_is_always_active(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.build_rows(). It contains the following steps:
        - load a file and look at the [Ipmi] row
        - ASSERT: it is not toggleable, because the section has no enabled= parameter
        - ASSERT: it still counts as enabled, so its checks run
        """
        model = _model(tmp_path)
        row = _row(model, "Ipmi")
        assert row.toggleable is False
        assert row.enabled is True

    def test_the_editor_opens_a_file_the_parser_rejects(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.run_checks(). It contains the following steps:
        - load the shipped configuration file, which the parser rejects because [HD] is enabled with
          an empty hd_names=
        - run the checks
        - ASSERT: the model still built every row, so the file can be edited
        - ASSERT: the parse failure became an error finding
        - ASSERT: the finding sits on the [HD] row, taken from the section the message names
        """
        model = _shipped(tmp_path)
        model.run_checks(modules=NO_MODULES)
        assert len(model.rows) > 5
        assert model.has_errors() is True
        findings = model.findings_of(_row(model, "HD"))
        assert findings and findings[0].level is Level.ERROR
        assert "hd_names" in findings[0].message

    def test_a_curve_makes_four_parameters_inactive(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.fields_of(). It contains the following steps:
        - load a file whose [CPU] carries a control_function= value
        - ASSERT: min_temp, max_temp, min_level and max_level are inactive, because the curve wins
        - ASSERT: every other parameter stays editable
        - ASSERT: the inactive ones carry the reason, for the help pane
        """
        model = _model(tmp_path, "[Ipmi]\n[CPU]\nenabled=1\ncontrol_function=40-35, 70-100\n")
        views = {v.key: v for v in model.fields_of(_row(model, "CPU"))}
        for key in ("min_temp", "max_temp", "min_level", "max_level"):
            assert views[key].state is FieldState.INACTIVE
            assert "control_function" in views[key].reason
        assert views["sensitivity"].state is FieldState.NORMAL

    def test_a_parameter_smfc_does_not_know_is_kept(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.fields_of(). It contains the following steps:
        - load a file that holds a parameter the schema does not define
        - ASSERT: the parameter is shown, so the user can see what is in their file
        - ASSERT: it is marked unknown, which the editor draws read-only and never deletes
        """
        model = _model(tmp_path, "[Ipmi]\n[CPU]\nenabled=1\nmystery_key=42\n")
        views = {v.key: v for v in model.fields_of(_row(model, "CPU"))}
        assert views["mystery_key"].state is FieldState.UNKNOWN
        assert views["mystery_key"].value == "42"

    def test_a_parameter_that_is_absent_shows_its_default(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.fields_of(). It contains the following steps:
        - load a file whose [CPU] names only two parameters
        - ASSERT: every other parameter is shown with the default the parser would apply
        """
        model = _model(tmp_path)
        views = {v.key: v for v in model.fields_of(_row(model, "CPU"))}
        assert views["steps"].value == "6"
        assert views["max_temp"].value == "60.0"

    def test_toggling_a_family_keeps_its_values(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.toggle(). It contains the following steps:
        - switch [CPU] off, then read the file back
        - ASSERT: enabled=0 was written
        - ASSERT: min_temp still carries the value the user typed, because nothing was deleted
        """
        model = _model(tmp_path)
        model.toggle(_row(model, "CPU"))
        model.writer.save()
        assert model.writer.get("CPU", "enabled") == "0"
        assert model.writer.get("CPU", "min_temp") == "30.0"

    def test_the_ipmi_row_cannot_be_toggled(self, tmp_path: Path) -> None:
        """Negative unit test for EditorModel.toggle(). It contains the following steps:
        - try to switch the [Ipmi] row off
        - ASSERT: the call reports that nothing was switched
        """
        model = _model(tmp_path)
        assert model.toggle(_row(model, "Ipmi")) is False

    def test_writing_to_an_absent_family_creates_its_section(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.set_value(). It contains the following steps:
        - switch on a family the file does not hold
        - ASSERT: the section is created and holds only what was written
        - ASSERT: the row becomes an instance of the file
        """
        model = _model(tmp_path)
        row = _row(model, "PCI")
        model.set_value(row, "enabled", "1")
        assert row.kind is RowKind.INSTANCE
        assert model.writer.keys("PCI") == ["enabled"]
        assert model.dirty is True

    def test_adding_an_instance_takes_the_next_free_number(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.add_instance(). It contains the following steps:
        - add two instances to a family that already holds the base section
        - ASSERT: they are numbered :1 and :2, because the suffix is only ordering
        - ASSERT: the base section is untouched
        """
        model = _model(tmp_path)
        assert model.add_instance("CPU") == "CPU:1"
        assert model.add_instance("CPU") == "CPU:2"
        assert model.writer.get("CPU", "min_temp") == "30.0"

    def test_a_family_that_takes_no_instance(self, tmp_path: Path) -> None:
        """Negative unit test for EditorModel.add_instance(). It contains the following steps:
        - add an instance to [Ipmi], which is not repeatable
        - ASSERT: it raises KeyError
        """
        model = _model(tmp_path)
        with pytest.raises(KeyError):
            model.add_instance("Ipmi")

    def test_removing_an_instance(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.remove_instance(). It contains the following steps:
        - add an instance and remove it again
        - ASSERT: only the base section is left
        - ASSERT: removing a family that is not in the file raises
        """
        model = _model(tmp_path)
        model.add_instance("CPU")
        model.remove_instance(_row(model, "CPU:1"))
        assert [r.name for r in model.rows if r.family == "CPU"] == ["CPU"]
        with pytest.raises(KeyError):
            model.remove_instance(_row(model, "PCI"))

    def test_free_zones_skips_the_zones_an_enabled_instance_claims(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.free_zones(). It contains the following steps:
        - load a file whose enabled [CPU] drives zones 0 and 1, and whose disabled [CPU:1] names zone 2
        - ASSERT: zones 0 and 1 are not offered, because an enabled instance holds them
        - ASSERT: zone 2 is offered, because a disabled instance claims nothing
        """
        model = _model(tmp_path, "[Ipmi]\n[CPU]\nenabled=1\nipmi_zone=0,1\n"
                                 "[CPU:1]\nenabled=0\nipmi_zone=2\n")
        assert model.free_zones("CPU", count=4) == [2, 3]

    def test_saving_a_read_only_file_is_refused(self, tmp_path: Path) -> None:
        """Negative unit test for EditorModel.save(). It contains the following steps:
        - take the write rights away from the configuration file
        - ASSERT: the model reports it as read-only
        - ASSERT: saving raises PermissionError rather than losing the change quietly
        """
        path = tmp_path / "smfc.conf"
        path.write_text(SMALL, encoding="utf-8")
        os.chmod(path, 0o400)
        model = EditorModel.load(str(path))
        if os.geteuid() == 0:
            pytest.skip("root may write a read-only file")
        assert model.read_only is True
        with pytest.raises(PermissionError):
            model.save()

    def test_saving_reports_the_findings_and_clears_the_dirty_flag(self, tmp_path: Path) -> None:
        """Positive unit test for EditorModel.save(). It contains the following steps:
        - change a value of the shipped configuration file and save it
        - ASSERT: the save is not blocked, although the file has an error in it
        - ASSERT: the unsaved-changes flag is cleared
        - ASSERT: the findings of the saved file are returned
        """
        model = _shipped(tmp_path)
        model.set_value(_row(model, "CPU"), "min_temp", "40.0")
        assert model.dirty is True
        findings = model.save()
        assert model.dirty is False
        assert any(f.level is Level.ERROR for f in findings)


class TestPanes:
    """Unit test class for the smfc.config_editor.panes module."""

    @pytest.mark.parametrize(
        "width, height, two_pane",
        [
            pytest.param(80, 24, True, id="a-standard-terminal"),
            pytest.param(64, 14, True, id="exactly-the-minimum"),
            pytest.param(63, 14, False, id="one-column-too-narrow"),
            pytest.param(64, 13, False, id="one-row-too-short"),
            pytest.param(200, 60, True, id="a-very-large-terminal"),
        ],
    )
    def test_the_two_pane_layout_has_a_floor(self, width: int, height: int, two_pane: bool) -> None:
        """Positive unit test for layout_for(). It contains the following steps:
        - compute the layout for terminals around the minimum size
        - ASSERT: two panes are used at 64 columns and 14 rows and above
        - ASSERT: below either figure the editor falls back to one pane instead of refusing to start
        """
        assert panes.layout_for(width, height).two_pane is two_pane

    def test_the_frame_stops_growing(self) -> None:
        """Positive unit test for layout_for(). It contains the following steps:
        - compute the layout for a very wide terminal
        - ASSERT: the frame stops at 100 columns, because wrapped help text stops being readable
        - ASSERT: every extra row goes to the panes, while the help pane keeps its height
        """
        layout = panes.layout_for(200, 60)
        assert layout.width == panes.MAX_WIDTH
        assert layout.help_rows == panes.HELP_ROWS
        assert layout.pane_rows == 60 - panes.HELP_ROWS - panes.FIXED_ROWS

    def test_a_long_line_is_cut_in_the_middle(self) -> None:
        """Positive unit test for fit(). It contains the following steps:
        - cut a device name that is longer than the pane
        - ASSERT: the head and the tail survive, because the serial number is at the end
        - ASSERT: the result is exactly as wide as the pane
        """
        name = "ata-WDC_WD120EFAX-68UNTN0_3A19R759"
        cut = panes.fit(name, 20)
        assert len(cut) == 20
        assert cut.startswith("ata-WDC")
        assert cut.endswith("R759")

    def test_a_disabled_section_gets_no_check_glyph(self, tmp_path: Path) -> None:
        """Positive unit test for check_glyph(). It contains the following steps:
        - run the checks on a file whose [NVME] is disabled
        - ASSERT: the disabled row shows no check glyph, rather than a green one
        - ASSERT: a row that has not been checked yet shows the not-checked glyph
        """
        model = _model(tmp_path)
        assert panes.check_glyph(model, _row(model, "CPU")) == panes.GLYPH_UNCHECKED
        model.run_checks(modules=NO_MODULES)
        assert panes.check_glyph(model, _row(model, "NVME")) == " "

    def test_an_error_shows_on_its_row(self, tmp_path: Path) -> None:
        """Positive unit test for check_glyph(). It contains the following steps:
        - run the checks on the shipped file, whose [HD] cannot be parsed
        - ASSERT: the [HD] row carries the error glyph
        """
        model = _shipped(tmp_path)
        model.run_checks(modules=NO_MODULES)
        assert panes.check_glyph(model, _row(model, "HD")) == panes.GLYPH_ERROR

    def test_the_help_pane_always_has_the_same_height(self, tmp_path: Path) -> None:
        """Positive unit test for render_help(). It contains the following steps:
        - render the help of a parameter, of a section row, and of a row with a finding
        - ASSERT: each one is exactly as tall as the layout says
        - ASSERT: a parameter's help names the parameter and its summary
        """
        model = _shipped(tmp_path)
        model.run_checks(modules=NO_MODULES)
        layout = panes.layout_for(80, 24)
        row = _row(model, "CPU")
        views = model.fields_of(row)
        assert len(panes.render_help(model, row, views[6], layout)) == layout.help_rows
        assert len(panes.render_help(model, row, None, layout)) == layout.help_rows
        assert views[6].key in panes.render_help(model, row, views[6], layout)[0]

    def test_the_help_pane_shows_the_finding_of_the_row(self, tmp_path: Path) -> None:
        """Positive unit test for render_help(). It contains the following steps:
        - render the help of the [HD] row of the shipped file, after the checks
        - ASSERT: the last line carries the finding, which is what the user has to act on
        """
        model = _shipped(tmp_path)
        model.run_checks(modules=NO_MODULES)
        row = _row(model, "HD")
        lines = panes.render_help(model, row, None, panes.layout_for(80, 24))
        assert "hd_names" in lines[-1]

    def test_the_key_line_follows_the_context(self, tmp_path: Path) -> None:
        """Positive unit test for render_keys(). It contains the following steps:
        - render the key line while editing and while not editing
        - ASSERT: editing offers only accept and cancel
        - ASSERT: a read-only file does not offer a save key
        """
        model = _model(tmp_path)
        assert "Esc cancel" in panes.render_keys(model, True)
        assert "F2 save" in panes.render_keys(model, False)
        model.read_only = True
        assert "read-only" in panes.render_keys(model, False)

    def test_a_device_list_is_shown_as_a_count(self, tmp_path: Path) -> None:
        """Positive unit test for render_fields(). It contains the following steps:
        - render a section whose hd_names= holds three devices
        - ASSERT: the value cell shows the number of devices, not the first path
        """
        model = _model(tmp_path, "[Ipmi]\n[HD]\nenabled=1\nhd_names=/dev/a\n\t/dev/b\n\t/dev/c\n")
        views = model.fields_of(_row(model, "HD"))
        lines = panes.render_fields(views, 0, 0, panes.layout_for(80, 24))
        assert any("3 devices..." in line for line in lines)


class TestEditorApp:
    """Unit test class for the key dispatch of the smfc.config_editor.app module."""

    def test_tab_moves_between_the_panes(self, tmp_path: Path) -> None:
        """Positive unit test for EditorApp.handle_key(). It contains the following steps:
        - press Tab twice
        - ASSERT: the cursor moves to the parameter list and back
        """
        app = EditorApp(_model(tmp_path))
        assert app.pane is PANE_SECTIONS
        app.handle_key(ord("\t"))
        assert app.pane is PANE_FIELDS
        app.handle_key(ord("\t"))
        assert app.pane is PANE_SECTIONS

    def test_the_cursor_skips_the_separator(self, tmp_path: Path) -> None:
        """Positive unit test for EditorApp.move_row(). It contains the following steps:
        - move the cursor down to the end of the section list
        - ASSERT: it never stops on the separator line
        - ASSERT: it stops at the Overview row and does not run past the end
        """
        app = EditorApp(_model(tmp_path))
        for _ in range(len(app.model.rows) + 5):
            app.handle_key(curses.KEY_DOWN)
        assert app.row.kind is RowKind.OVERVIEW
        for _ in range(len(app.model.rows) + 5):
            app.handle_key(curses.KEY_UP)
        assert app.row_index == 0

    def test_typing_a_value_writes_it(self, tmp_path: Path) -> None:
        """Positive unit test for the editing keys. It contains the following steps:
        - move to the [CPU] row and into the parameter list, and open min_temp for editing
        - type a new value and press Enter
        - ASSERT: the value is written into the file
        - ASSERT: the unsaved-changes flag is set
        """
        app = EditorApp(_model(tmp_path))
        app.row_index = [i for i, r in enumerate(app.model.rows) if r.name == "CPU"][0]
        app.pane = PANE_FIELDS
        app.field_index = [i for i, v in enumerate(app.views()) if v.key == "min_temp"][0]
        app.handle_key(curses.KEY_ENTER)
        assert app.editing == "30.0"
        for _ in range(4):
            app.handle_key(curses.KEY_BACKSPACE)
        for char in "42.5":
            app.handle_key(ord(char))
        app.handle_key(10)
        assert app.editing is None
        assert app.model.writer.get("CPU", "min_temp") == "42.5"
        assert app.model.dirty is True

    def test_escape_drops_the_typed_value(self, tmp_path: Path) -> None:
        """Negative unit test for the editing keys. It contains the following steps:
        - open a parameter for editing, type into it, and press Esc
        - ASSERT: the file still holds the old value
        - ASSERT: the file is not marked as changed
        """
        app = EditorApp(_model(tmp_path))
        app.row_index = [i for i, r in enumerate(app.model.rows) if r.name == "CPU"][0]
        app.pane = PANE_FIELDS
        app.field_index = [i for i, v in enumerate(app.views()) if v.key == "min_temp"][0]
        app.handle_key(curses.KEY_ENTER)
        app.handle_key(ord("9"))
        app.handle_key(27)
        assert app.model.writer.get("CPU", "min_temp") == "30.0"
        assert app.model.dirty is False

    def test_space_toggles_a_family(self, tmp_path: Path) -> None:
        """Positive unit test for EditorApp.toggle(). It contains the following steps:
        - put the cursor on the [CPU] row and press Space
        - ASSERT: the family is switched off
        - ASSERT: the message says what happened
        """
        app = EditorApp(_model(tmp_path))
        app.row_index = [i for i, r in enumerate(app.model.rows) if r.name == "CPU"][0]
        app.handle_key(ord(" "))
        assert app.model.writer.get("CPU", "enabled") == "0"
        assert "disabled" in app.message

    def test_a_read_only_file_refuses_every_change(self, tmp_path: Path) -> None:
        """Negative unit test for EditorApp. It contains the following steps:
        - mark the model read-only, then press Space and try to edit a parameter
        - ASSERT: nothing is changed
        - ASSERT: both messages name the way to fix it
        """
        app = EditorApp(_model(tmp_path))
        app.model.read_only = True
        app.handle_key(ord(" "))
        assert "sudo smfc-config" in app.message
        app.pane = PANE_FIELDS
        app.start_edit()
        assert app.editing is None
        assert "sudo smfc-config" in app.message

    def test_a_popup_parameter_says_where_it_is_edited(self, tmp_path: Path) -> None:
        """Negative unit test for EditorApp.start_edit(). It contains the following steps:
        - try to edit a path in place, which belongs in a popup
        - ASSERT: the edit does not open, and the message says so
        """
        app = EditorApp(_model(tmp_path))
        app.row_index = [i for i, r in enumerate(app.model.rows) if r.name == "Ipmi"][0]
        app.pane = PANE_FIELDS
        app.field_index = [i for i, v in enumerate(app.views()) if v.key == "command"][0]
        app.start_edit()
        assert app.editing is None
        assert "popup" in app.message

    def test_escape_does_not_quit_the_editor(self, tmp_path: Path) -> None:
        """Negative unit test for EditorApp.handle_key(). It contains the following steps:
        - move the cursor into the parameter list and press Esc
        - ASSERT: the editor is still running, because Esc is the first byte of every function key
          sequence and a terminal that delivers them byte by byte would otherwise close it on F2
        - ASSERT: the cursor returns to the section list instead
        """
        app = EditorApp(_model(tmp_path))
        app.pane = PANE_FIELDS
        app.handle_key(27)
        assert app.running is True
        assert app.pane is PANE_SECTIONS

    def test_f5_runs_the_checks_and_f10_quits(self, tmp_path: Path) -> None:
        """Positive unit test for EditorApp.handle_key(). It contains the following steps:
        - press F5, then F10
        - ASSERT: the checks have run
        - ASSERT: the loop is asked to stop
        """
        app = EditorApp(_model(tmp_path))
        assert app.model.checked is False
        app.handle_key(curses.KEY_F5)
        assert app.model.checked is True
        app.handle_key(curses.KEY_F10)
        assert app.running is False

    def test_saving_an_invalid_file_is_allowed_and_says_so(self, tmp_path: Path) -> None:
        """Positive unit test for EditorApp.save(). It contains the following steps:
        - open the shipped configuration file, which the parser rejects, and press F2
        - ASSERT: the file is written, because nothing blocks a save
        - ASSERT: the message says smfc will not start and that the running service is untouched
        """
        app = EditorApp(_shipped(tmp_path))
        app.handle_key(curses.KEY_F2)
        assert app.model.dirty is False
        assert "will not start" in app.message
        assert "running service" in app.message


class TestCommand:
    """Unit test class for the smfc.config_editor.cmd module."""

    def test_a_missing_file_names_the_template_of_the_installed_release(self, tmp_path: Path,
                                                                       capsys) -> None:
        """Negative unit test for main(). It contains the following steps:
        - run smfc-config against a path that does not exist, with no backup beside it
        - ASSERT: it exits with the configuration error code of the service
        - ASSERT: it names the tagged URL of the template, so the version always matches the daemon
        """
        assert main(["-c", str(tmp_path / "nosuch.conf")]) == EXIT_CONFIG_ERROR
        err = capsys.readouterr().err
        assert "does not exist" in err
        assert "refs/tags/v" in err

    def test_a_missing_file_offers_the_local_backup_first(self, tmp_path: Path, capsys) -> None:
        """Negative unit test for main(). It contains the following steps:
        - put a backup beside a configuration file that does not exist
        - run smfc-config against it
        - ASSERT: the backup is named, and the copy command is printed
        - ASSERT: the download is not offered, because a local file is the better answer
        """
        target = tmp_path / "smfc.conf"
        (tmp_path / "smfc.conf.20260914_120000").write_text(SMALL, encoding="utf-8")
        assert main(["-c", str(target)]) == EXIT_CONFIG_ERROR
        err = capsys.readouterr().err
        assert "smfc.conf.20260914_120000" in err
        assert "refs/tags/v" not in err


# End.
