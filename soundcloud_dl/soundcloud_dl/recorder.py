"""Record mode: run playwright codegen and scaffold a gate handler YAML."""

from __future__ import annotations

import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger("soundcloud_dl.recorder")

_HANDLERS_DIR = Path(__file__).parent / "gate_handlers"

# Patterns to extract from codegen output
_CLICK_PATTERN = re.compile(
    r'page\.(?:get_by_\w+\("([^"]+)"\)|locator\("([^"]+)"\)|click\("([^"]+)"\))'
)
_FILL_PATTERN = re.compile(
    r'page\.(?:get_by_\w+\("([^"]+)"\)|locator\("([^"]+)"\))\.fill\("([^"]*)"\)'
)


def _parse_codegen_output(code: str) -> list[dict]:
    """Best-effort parse of playwright codegen Python output into step dicts."""
    steps: list[dict] = []

    for raw_line in code.splitlines():
        line = raw_line.strip()

        fill_match = _FILL_PATTERN.search(line)
        if fill_match:
            selector = next(g for g in fill_match.groups()[:-1] if g)
            value = fill_match.group(3)
            steps.append(
                {
                    "id": f"fill_{len(steps)}",
                    "trigger": selector,
                    "action": "fill",
                    "value": value or "{{replace_me}}",
                    "optional": True,
                }
            )
            continue

        click_match = _CLICK_PATTERN.search(line)
        if click_match:
            selector = next(g for g in click_match.groups() if g)
            steps.append(
                {
                    "id": f"click_{len(steps)}",
                    "trigger": selector,
                    "action": "click",
                    "optional": True,
                }
            )

    return steps


def _write_yaml_scaffold(gate_name: str, steps: list[dict]) -> Path:
    """Write a starter YAML file for the gate. Returns the path written."""
    import yaml  # noqa: PLC0415 — deferred so recorder is importable without pyyaml

    out_path = _HANDLERS_DIR / f"{gate_name}.yaml"
    config = {
        "gate": gate_name,
        "url_pattern": f"{gate_name}.com",
        "steps": steps,
    }
    out_path.write_text(yaml.dump(config, sort_keys=False, allow_unicode=True))
    return out_path


def record(gate_name: str, url: str) -> None:
    """
    Launch playwright codegen for url, parse the output, and write a starter YAML
    to gate_handlers/<gate_name>.yaml.

    The generated YAML is a scaffold — review and annotate required/optional/depends_on
    and replace placeholder values with {{template_vars}} before using.
    """
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tmp:
        output_path = Path(tmp.name)

    logger.info("Starting playwright codegen for: %s", url)
    logger.info("Walk through the gate flow in the browser, then close it.")
    logger.info("Output will be written to: %s", output_path)

    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "playwright", "codegen", "--output", str(output_path), url],
        check=False,
    )

    if result.returncode != 0:
        logger.warning("playwright codegen exited with code %d", result.returncode)

    code = output_path.read_text() if output_path.exists() else ""
    output_path.unlink(missing_ok=True)

    steps = _parse_codegen_output(code)

    if not steps:
        logger.warning("No steps parsed from codegen output. Writing empty scaffold.")

    yaml_path = _write_yaml_scaffold(gate_name, steps)
    logger.info("Scaffold written to: %s", yaml_path)
    logger.info(
        "Next: annotate required/optional, add depends_on, replace values with {{template_vars}}."
    )
    logger.info("Then register the handler in gate_handlers/__init__.py if it's a new service.")
