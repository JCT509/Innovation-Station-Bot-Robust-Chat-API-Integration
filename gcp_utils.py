# gcp_utils.py

from google.cloud import secretmanager
import os

PROJECT_ID = "care-cockpit-dev"
PROJECT_NUMBER = "1042296906285"

def get_secret_manager_client():
    """Initializes and returns a Secret Manager client.
    Assumes GOOGLE_APPLICATION_CREDENTIALS environment variable is set
    or running in a GCP environment with default credentials.
    """
    return secretmanager.SecretManagerServiceClient()

def access_secret(secret_id, version_id="latest"):
    """Access the payload for the given secret and version.
    """
    client = get_secret_manager_client()
    # Use PROJECT_ID instead of PROJECT_NUMBER for better portability
    name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")
