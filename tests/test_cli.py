import pytest

from mma import __version__
from mma.cli import main


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_help_lists_commands(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    for cmd in ("run", "transcript", "doctor", "validate", "skill"):
        assert cmd in out
