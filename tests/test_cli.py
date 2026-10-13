import pytest

from mma import __version__
from mma.cli import main


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_run_not_implemented(capsys):
    assert main(["run", "meeting.m4a"]) == 2
    assert "not implemented yet" in capsys.readouterr().err
