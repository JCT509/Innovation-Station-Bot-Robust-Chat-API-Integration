# app.py

from flask import Flask, request, jsonify
import os
import json
from datetime import datetime
import requests # Import requests
import traceback
import sys

from gcp_utils import PROJECT_ID
from zendesk_utils import get_ticket, create_ticket, add_note_to_ticket # Import Zendesk utilities

app = Flask(__name__)

# Admin users (replace with actual admin emails)
ADMIN_USERS = ["jtheard@blackbirdhealth.com"]

def is_admin(user_email):
    return user_email in ADMIN_USERS

def handle_slash_command(command, user_email, user_display_name):
    if command == "/help":
        return jsonify({"text": get_static_menu(user_display_name)})
    elif command.startswith("/ticket"):
        parts = command.split()
        if len(parts) > 1:
            ticket_id = parts[1]
            return create_ticket_dialog(ticket_id=ticket_id)
        else:
            return get_existing_ticket_dialog()
    elif command == "/knownissues":
        response_text = f"Here is the link to Known Issues: {KNOWN_ISSUES_LINK}"
        return jsonify({"text": response_text})
    elif command == "/errorinfo":
        return get_error_info_dialog()
    elif command == "/newticket":
        return create_ticket_dialog()
    else:
        return jsonify({"text": "Command not recognized. Type `/help` for options."})


def handle_dialog_submission(event):
    form_inputs = event.get("dialogEvent", {}).get("formInputs", {})
    action_method_name = event.get("actionMethodName")

    if action_method_name == "submit_ticket_dialog":
        url_link = form_inputs.get("url_link", "").get("stringValue", "")
        patient_id = form_inputs.get("patient_id", "").get("stringValue", "")
        provider_username = form_inputs.get("provider_username", "").get("stringValue", "")
        encounter_id = form_inputs.get("encounter_id", "").get("stringValue", "")
        issue_description = form_inputs.get("issue_description", "").get("stringValue", "")
        timestamp = form_inputs.get("timestamp", "").get("stringValue", "")
        
        ticket_id_hidden = form_inputs.get("ticket_id_hidden", "").get("stringValue", "")
        error_info_hidden = form_inputs.get("error_info_hidden", "").get("stringValue", "")

        user_display_name = event.get("user", {}).get("displayName")
        user_email = event.get("user", {}).get("email")

        if ticket_id_hidden:
            comment_body = f"Note added by {user_display_name} via bot:\nURL: {url_link}\nPatient ID: {patient_id}\nProvider: {provider_username}\nEncounter ID: {encounter_id}\nIssue: {issue_description}\nTimestamp: {timestamp}"
            try:
                add_note_to_ticket(ticket_id_hidden, comment_body)
                return jsonify({"text": f"Note successfully added to Ticket #{ticket_id_hidden}."})
            except Exception as e:
                return jsonify({"text": f"Error adding note to Ticket #{ticket_id_hidden}: {e}"})
        else:
            subject = "New Ticket from Innovation Station Bot"
            if error_info_hidden:
                subject = f"New Ticket: {error_info_hidden}"
            
            comment_body = f"Issue reported by {user_display_name} via bot:\nURL: {url_link}\nPatient ID: {patient_id}\nProvider: {provider_username}\nEncounter ID: {encounter_id}\nIssue: {issue_description}\nTimestamp: {timestamp}"
            
            try:
                new_ticket = create_ticket(subject, comment_body, user_display_name, user_email)
                return jsonify({"text": f"New ticket created successfully! Ticket ID: {new_ticket["ticket"]["id"]}"})
            except Exception as e:
                return jsonify({"text": f"An unexpected error occurred during ticket creation: {e}"})

    elif action_method_name == "submit_existing_ticket_dialog":
        ticket_id = form_inputs.get("ticket_id", "").get("stringValue", "")
        if ticket_id:
            return create_ticket_dialog(ticket_id=ticket_id)
        else:
            return jsonify({"text": "Ticket number not provided. Please try again with `/ticket <ticket_id>`."})

    elif action_method_name == "submit_error_info_dialog":
        error_code_message = form_inputs.get("error_code_message", "").get("stringValue", "")
        if error_code_message:
            return create_ticket_dialog(error_info=error_code_message)
        else:
            return jsonify({"text": "Error code or message not provided. Please try again with `/errorinfo`."})
    
    return jsonify({"text": "Dialog submission not recognized."})


KNOWN_ISSUES_LINK = "https://docs.google.com/document/d/1-JFntF3DibIUYbn7W1X3AWPvzKegwJx-pAf9NT2ierI/edit?tab=t.0"

# In-memory session store (for demonstration purposes, not for production)
user_sessions = {}

def get_static_menu(user_display_name):
    menu_text = f"Welcome, {user_display_name}! I am the Innovation Station AI Assistant. Here\"s how I can help:\n\n"
    menu_text += "*   Type `/ticket <ticket_id>` to view an existing ticket.\n"
    menu_text += "*   Type `/knownissues` to see a link to known issues.\n"
    menu_text += "*   Type `/errorinfo` to provide an error code or message.\n"
    menu_text += "*   Type `/newticket` to open a new ticket.\n\n"
    menu_text += "You can also type `@bot help` at any time to see this menu again."
    return menu_text

@app.route("/", methods=["POST"])
def home():
    try:
        event = request.json
        print(f"Received event: {json.dumps(event, indent=2)}")

        if event.get("type") == "ADDED_TO_SPACE":
            print(f"DEBUG: Bot added to space. Displaying static menu.")
            user_display_name = event.get("user", {}).get("displayName", "Innovation Station")
            return jsonify({"text": get_static_menu(user_display_name)})

        if event.get("type") == "SUBMIT_DIALOG":
            print(f"DEBUG: Dialog submission received: {json.dumps(event, indent=2)}")
            return handle_dialog_submission(event)

        if event.get("type") not in ["MESSAGE", "ADDED_TO_SPACE", "SUBMIT_DIALOG"]:
            print(f"DEBUG: Unknown event type {event.get("type")}. Showing default menu.")
            user_display_name = event.get("user", {}).get("displayName", "Innovation Station")
            return jsonify({"text": get_static_menu(user_display_name)})

        if event.get("type") == "MESSAGE":
            user_email = event.get("message", {}).get("sender", {}).get("email")
            raw_chat_message = event.get("message", {}).get("text", "").strip()
            user_display_name = event.get("message", {}).get("sender", {}).get("displayName")
            bot_mentioned_annotations = event.get("message", {}).get("annotations")

            print(f"DEBUG: Raw MESSAGE from {user_email}: ")

            chat_message = raw_chat_message
            if bot_mentioned_annotations:
                for annotation in bot_mentioned_annotations:
                    if annotation.get("type") == "USER_MENTION":
                        mention_text = raw_chat_message[annotation["startIndex"] : annotation["endIndex"]]
                        chat_message = chat_message.replace(mention_text, "").strip()
            print(f"DEBUG: Mentions removed. Cleaned chat_message: ")

            cleaned_for_help_check = chat_message.lower()

            if chat_message.startswith("/"):
                return handle_slash_command(chat_message, user_email, user_display_name)

            if cleaned_for_help_check == "help":
                print(f"DEBUG: @bot help command detected for {user_email}. Redirecting to /help command.")
                return handle_slash_command("/help", user_email, user_display_name)

            if is_admin(user_email) and chat_message.lower().startswith("@cline admin"):
                admin_command = chat_message.lower().replace("@cline admin", "").strip()
                if admin_command == "close bot":
                    response_text = "Admin command received: Closing the bot."
                elif admin_command == "restart bot":
                    response_text = "Admin command received: Restarting the bot."
                elif admin_command == "refresh bot":
                    response_text = "Admin command received: Refreshing bot (database updates)."
                else:
                    response_text = "Admin command not recognized. Available commands: \"close bot\", \"restart bot\", \"refresh bot\"."
                return jsonify({"text": response_text})

            print(f"DEBUG: Message not handled by slash commands or admin commands. Showing static menu.")
            return jsonify({"text": get_static_menu(user_display_name)})

        print(f"DEBUG: Unhandled event type: {event.get("type", "UNKNOWN")}. Returning default text response.")
        return jsonify({"text": "Received an unhandled event type. If you need help, please try typing \"@bot help\" for assistance."})

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({
            "header": {
                "title": "Error",
                "subtitle": "An internal error occurred",
                "imageUrl": "https://www.gstatic.com/images/branding/product/1x/avatar_square_grey_512dp.png"
            },
            "sections": [{
                "widgets": [{
                    "textParagraph": {
                        "text": f"Error: {str(e)}"
                    }
                }]
            }]
        })

if __name__ == "__main__":
    app.run(port=5000, debug=True)
