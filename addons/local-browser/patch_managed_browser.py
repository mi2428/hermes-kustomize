"""Honor managed browser selection in the pinned Hermes release."""

from pathlib import Path

import tools.browser_tool_cloud as browser_cloud

path = Path(browser_cloud.__file__).resolve()
source = path.read_text(encoding="utf-8")
old = 'from hermes_cli.config import read_raw_config\n        browser_cfg = read_raw_config().get("browser", {})'
new = 'from hermes_cli.config import load_config_readonly\n        browser_cfg = load_config_readonly().get("browser", {})'
if source.count(old) != 1:
    raise SystemExit("Unsupported Hermes browser resolver; review the pinned version")
path.write_text(source.replace(old, new), encoding="utf-8")
