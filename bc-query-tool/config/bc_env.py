r"""
Which Business Central environment the Query tool talks to.

config.json names Production, in environment_name and inside the base_api
URL. The run files in "launchers" choose the environment instead,
by setting BC_ENVIRONMENT_NAME (see _bc_environment.cmd there):

    Production\Run <tool>.bat           -> Production
    Sandbox\Run <tool> (Sandbox).bat    -> the sandbox, e.g. Sandbox_Test

load_config() returns config.json with that environment applied, so every
page and query.py build their URLs from one place. With BC_ENVIRONMENT_NAME
unset (QueryTool.bat double-clicked directly) config.json is used as it is.
"""

import json
import os

CONFIG_PATH = os.path.join("config", "config.json")
URL_KEYS = ("base_api", "general_journal_api", "batch_api")


def load_config(path: str = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    api = config["api"]
    wanted = os.environ.get("BC_ENVIRONMENT_NAME", "").strip()
    current = api.get("environment_name", "Production")
    if wanted and wanted != current:
        for key in URL_KEYS:
            if key in api:
                if f"/{current}/" not in api[key]:
                    raise RuntimeError(
                        f"config.json {key} does not contain /{current}/, so it cannot be "
                        f"switched to {wanted}. Check config.json.")
                api[key] = api[key].replace(f"/{current}/", f"/{wanted}/")
        api["environment_name"] = wanted
    return config


def environment(config: dict = None) -> str:
    config = config or load_config()
    return config["api"]["environment_name"]


def is_sandbox(config: dict = None) -> bool:
    return environment(config).lower() != "production"


def banner(st, config: dict = None) -> None:
    """One line at the top of a page saying which environment it is reading."""
    env = environment(config)
    if is_sandbox(config):
        st.success(f"Business Central environment: **{env}** (sandbox). Test data, "
                   "not Production.", icon=":material/science:")
    else:
        st.caption(f"Business Central environment: **{env}**")
