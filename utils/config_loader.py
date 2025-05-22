import yaml
import os
from utils.log_helper import Logger

config_cache = None

def load_cred_config(config_path=None):
    global config_cache
    if config_cache is not None:
        return config_cache

    if config_path is None:
        # Use absolute path based on current working directory
        config_path = os.path.join(os.getcwd(), 'config', 'creds.yml')

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        config_cache = yaml.safe_load(f)
        return config_cache

def load_config(config_file):
    try:
        config_path = os.path.join(os.getcwd(), 'config', config_file)
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        Logger.log_message(f"Error loading config {config_file}: {str(e)}")
        return {}