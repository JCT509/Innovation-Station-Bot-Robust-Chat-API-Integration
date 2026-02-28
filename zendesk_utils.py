# zendesk_utils.py

import requests
import os
from gcp_utils import access_secret

# Use environment variables for configuration, defaulting to hardcoded values if not set
ZENDESK_SUBDOMAIN = os.environ.get("ZENDESK_SUBDOMAIN", "blackbirdhealth")
ZENDESK_EMAIL = os.environ.get("ZENDESK_EMAIL", "jtheard@blackbirdhealth.com")
ZENDESK_PASSWORD_SECRET_ID = os.environ.get("ZENDESK_PASSWORD_SECRET_ID", "zendesk-password")

def _get_zendesk_auth():
    """Retrieves Zendesk credentials from Secret Manager and returns them.
    """
    password = access_secret(ZENDESK_PASSWORD_SECRET_ID)
    return (f"{ZENDESK_EMAIL}/token", password) # Using API token

def get_ticket(ticket_id):
    """Fetches a Zendesk ticket by ID.
    """
    url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/tickets/{ticket_id}.json"
    user_auth = _get_zendesk_auth()
    response = requests.get(url, auth=user_auth, timeout=20)
    response.raise_for_status()
    return response.json() # Returns a dictionary with ticket data

def create_ticket(subject, comment_body, requester_name, requester_email, custom_fields=None):
    """Creates a new Zendesk ticket.
    """
    url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/tickets.json"
    user_auth = _get_zendesk_auth()
    
    data = {
        "ticket": {
            "subject": subject,
            "comment": { "body": comment_body },
            "requester": { "name": requester_name, "email": requester_email }
        }
    }
    
    if custom_fields:
        data["ticket"]["custom_fields"] = custom_fields

    response = requests.post(url, json=data, auth=user_auth, timeout=20)
    response.raise_for_status()
    return response.json() # Returns a dictionary with the new ticket data

def add_note_to_ticket(ticket_id, note_body, public=False):
    """Adds a note (comment) to an existing Zendesk ticket.
    """
    url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/tickets/{ticket_id}.json"
    user_auth = _get_zendesk_auth()
    
    data = {
        "ticket": {
            "comment": { "body": note_body, "public": public }
        }
    }

    response = requests.put(url, json=data, auth=user_auth, timeout=20)
    response.raise_for_status()
    return response.json() # Returns a dictionary with the updated ticket data

def get_ticket_comments(ticket_id):
    """Fetches all comments for a Zendesk ticket by ID.
    """
    url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/tickets/{ticket_id}/comments.json"
    user_auth = _get_zendesk_auth()
    response = requests.get(url, auth=user_auth, timeout=20)
    response.raise_for_status()
    return response.json() # Returns a dictionary with comments data
