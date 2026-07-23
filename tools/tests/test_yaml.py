import yaml
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

YAML_FILES = sorted([
    *REPO_ROOT.glob("*.yaml"),
    *REPO_ROOT.glob("*.yaml.bk"),
    *REPO_ROOT.glob("*.yml"),
])


@pytest.mark.parametrize("path", YAML_FILES, ids=lambda p: p.name)
def test_yaml_parses(path):
    list(yaml.safe_load_all(path.read_text()))
