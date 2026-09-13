"""Where the tunables come from: the environment, and the `.env` it falls back to."""
import os

from amonhen import settings


def test_the_env_file_is_read_without_overriding_what_is_already_there(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# a comment\n"
        "\n"
        "AMONHEN_TEST_FROM_FILE=from-file\n"
        "AMONHEN_TEST_QUOTED='quoted value'\n"
        "AMONHEN_TEST_ALREADY_SET=from-file\n"
        "a line that is not a setting\n"
        "AMONHEN_TEST_EMPTY=\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AMONHEN_TEST_ALREADY_SET", "from-shell")
    monkeypatch.delenv("AMONHEN_TEST_FROM_FILE", raising=False)
    monkeypatch.delenv("AMONHEN_TEST_QUOTED", raising=False)
    monkeypatch.delenv("AMONHEN_TEST_EMPTY", raising=False)

    settings._load_env_file(env_file)

    # The shell wins, like compose does with an exported variable.
    assert os.environ["AMONHEN_TEST_ALREADY_SET"] == "from-shell"
    assert os.environ["AMONHEN_TEST_FROM_FILE"] == "from-file"
    assert os.environ["AMONHEN_TEST_QUOTED"] == "quoted value"
    assert os.environ["AMONHEN_TEST_EMPTY"] == ""


def test_a_missing_env_file_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.delenv("AMONHEN_TEST_ABSENT", raising=False)

    settings._load_env_file(tmp_path / "nothing-here")

    assert "AMONHEN_TEST_ABSENT" not in os.environ
