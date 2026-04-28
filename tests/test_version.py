import re


def test_version_importable():
    from tg_monitor import __version__
    assert __version__ is not None


def test_version_is_semver():
    from tg_monitor import __version__
    assert re.match(r"^\d+\.\d+\.\d+", __version__), f"not semver: {__version__}"


def test_version_matches_pyproject():
    import tomllib
    import pathlib
    pyproject = pathlib.Path(__file__).parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    from tg_monitor import __version__
    assert __version__ == data["project"]["version"]
