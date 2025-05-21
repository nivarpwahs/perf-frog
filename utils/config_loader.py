import yaml
import os

_config_cache = None

def load_cred_config(config_path=None):
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    if config_path is None:
        # Use absolute path based on current working directory
        config_path = os.path.join(os.getcwd(), 'config', 'creds.yml')

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        _config_cache = yaml.safe_load(f)
        return _config_cache