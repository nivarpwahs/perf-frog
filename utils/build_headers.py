from utils.config_loader import load_cred_config
import base64

def build_common_headers():
    config = load_cred_config()
    headers = {}

    auth_token = config.get("auth_token")
    if auth_token:
        # For JFrog, we use Basic auth with the API token
        headers["Authorization"] = f"Basic {auth_token}"

    content_type = config.get("content_type", "application/json")
    if content_type:
        headers["Content-Type"] = content_type

    return headers