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

KNOWN_ISSUES_LINK = "https://docs.google.com/document/d/1-JFntF3DibIUYbn7W1X3AWPvzKegwJx-pAf9NT2ierI/edit?tab=t.0"

# In-memory session store (for demonstration purposes, not for production)
user_sessions = {}

def get_static_menu(user_display_name):
    # Static Menu Configuration using Cards v2 with improved interactive elements
    # Returning Action object with Navigation (Add-on v1 schema)
    return {
        "navigations": [
            {
                "pushCard": {
        "header": {
            "title": "Innovation Station AI Assistant",
            "subtitle": f"Welcome, {user_display_name}"
        },
                    "sections": [
                        {
                            "header": "Support Menu (Available 24/7)",
                            "widgets": [
                                {
                                    "textParagraph": {
                                        "text": "Choose an option below or type \"@bot help\" for assistance."
                                    }
                                },
                                {
                                    "buttonList": {
                                        "buttons": [
                                            {
                                                "text": "Existing Ticket",
                                                "onClick": {
                                                    "action": {
                                                        "function": "existing_ticket"
                                                    }
                                                }
                                            },
                                            {
                                                "text": "Known Issues",
                                                "onClick": {
                                                    "openLink": {
                                                        "url": KNOWN_ISSUES_LINK
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                },
                                {
                                    "buttonList": {
                                        "buttons": [
                                            {
                                                "text": "Error Code/Message",
                                                "onClick": {
                                                    "action": {
                                                        "function": "error_info"
                                                    }
                                                }
                                            },
                                            {
                                                "text": "Open New Ticket",
                                                "onClick": {
                                                    "action": {
                                                        "function": "new_ticket"
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                }
                            ]
                        }
                    ]
                }
            }
        ]
    }

@app.route("/", methods=["POST"])
def home():
    try:
        event = request.json
        print(f"Received event: {json.dumps(event, indent=2)}")

        # Handle ADDED_TO_SPACE events
        if event.get("type") == "ADDED_TO_SPACE":
            print(f"DEBUG: Bot added to space. Displaying static menu.")
            user_display_name = event.get("user", {}).get("displayName", "Innovation Station")
            return jsonify(get_static_menu(user_display_name))

        # Fallback for unrecognized/missing event types to ensure menu is shown
        if event.get("type") not in ["MESSAGE", "CARD_CLICKED", "ADDED_TO_SPACE"]:
            print(f"DEBUG: Unknown event type {event.get('type')}. Showing default menu.")
            # Attempt to get a display name if possible
            user_display_name = event.get("user", {}).get("displayName", "Innovation Station")
            # Ensure we always return a valid Card Response if possible
            return jsonify(get_static_menu(user_display_name))

        # Handle CARD_CLICKED events
        if event.get("type") == "CARD_CLICKED":
            user_email = event.get("user", {}).get("email")
            user_display_name = event.get("user", {}).get("displayName")
            # Support both Chat API (actionMethodName) and Add-on (function) fields
            action_name = event.get("action", {}).get("actionMethodName") or event.get("action", {}).get("function")
            print(f"DEBUG: Card clicked by {user_email}. Action: {action_name}")

            if action_name == "existing_ticket":
                user_sessions[user_email] = "awaiting_ticket_number"
                return jsonify({"text": "Please provide the existing ticket number."})
            elif action_name == "error_info":
                user_sessions[user_email] = "awaiting_error_info"
                return jsonify({"text": "Please provide the error code or message."})
            elif action_name == "new_ticket":
                user_sessions[user_email] = "awaiting_ticket_details"
                response_text = "Please provide the following information to create a new ticket:"
                response_text += "\nURL Link:"
                response_text += "\nPatient ID:"
                response_text += "\nProvider username:"
                response_text += "\nEncounter ID (if available):"
                response_text += "\nA screenshot of the issue occurring or steps to recreate the issue:"
                response_text += "\nApproximate timestamp of when the issue occurred:"
                return jsonify({"text": response_text})

        # Handle APP_HOME events for the App Home tab
        if event.get("type") == "APP_HOME":
            print(f"DEBUG: App Home event received. Displaying static menu.")
            user_display_name = event.get("user", {}).get("displayName", "Innovation Station")
            return jsonify(get_static_menu(user_display_name))

        # Handle MESSAGE events
        if event.get("type") == "MESSAGE":
            user_email = event.get("message", {}).get("sender", {}).get("email")
            raw_chat_message = event.get("message", {}).get("text", "").strip()
            user_display_name = event.get("message", {}).get("sender", {}).get("displayName")
            bot_mentioned_annotations = event.get("message", {}).get("annotations")

            print(f"DEBUG: Raw MESSAGE from {user_email}: '{raw_chat_message}' (Length: {len(raw_chat_message)}). Annotations: {bot_mentioned_annotations}")

            # --- Step 1: Clean the message by removing bot mentions ---
            chat_message = raw_chat_message
            if bot_mentioned_annotations:
                for annotation in bot_mentioned_annotations:
                    if annotation.get("type") == "USER_MENTION":
                        # We check if the mention corresponds to the bot's own ID or name if available
                        # For simplicity and robustness in spaces, we'll strip the annotated portion
                        mention_text = raw_chat_message[annotation["startIndex"] : annotation["endIndex"]]
                        chat_message = chat_message.replace(mention_text, "").strip()
            print(f"DEBUG: Mentions removed. Cleaned chat_message: '{chat_message}' (Length: {len(chat_message)})")

            # Now, `chat_message` is the cleaned message, ready for all subsequent parsing.

            # --- HIGH PRIORITY: Handle @help to reset session and show menu ---
            cleaned_for_help_check = chat_message.lower()
            print(f"DEBUG: Message for @help check (lowercase): '{cleaned_for_help_check}' (Length: {len(cleaned_for_help_check)})")
            print(f"DEBUG: Is cleaned_for_help_check == 'help'? {cleaned_for_help_check == 'help'}") # Added debug line

            if cleaned_for_help_check == "help":
                print(f"DEBUG: @help command detected for {user_email}.")
                
                if not user_email.endswith("@blackbirdhealth.com"):
                    print(f"DEBUG: Unauthorized user {user_email} attempting @help.")
                    return jsonify({"text": "Unauthorized access. This bot is only for Blackbird Health authenticated users."})

                if user_email in user_sessions:
                    print(f"DEBUG: Clearing session for {user_email} due to @help command.")
                    del user_sessions[user_email]
                
                print(f"DEBUG: Displaying static menu via @help command.")
                return jsonify(get_static_menu(user_display_name))
            # --- END HIGH PRIORITY @help handling ---

            # 2. Admin commands - higher priority than regular user input but lower than @help
            if is_admin(user_email) and chat_message.lower().startswith("@cline admin"):
                admin_command = chat_message.lower().replace("@cline admin", "").strip()
                if admin_command == "close bot":
                    response_text = "Admin command received: Closing the bot."
                elif admin_command == "restart bot":
                    response_text = "Admin command received: Restarting the bot."
                elif admin_command == "refresh bot":
                    response_text = "Admin command received: Refreshing bot (database updates)."
                else:
                    response_text = "Admin command not recognized. Available commands: 'close bot', 'restart bot', 'refresh bot'."
                
                return jsonify({"text": response_text})

            # 3. Handle existing ticket number input only if a session is active
            if user_email in user_sessions:
                current_state = user_sessions[user_email]

                if current_state == "awaiting_ticket_number":
                    ticket_id = chat_message.strip()
                    try:
                        ticket_info = get_ticket(ticket_id)
                        ticket_data = ticket_info["ticket"]
                        response_text = f"Ticket #{ticket_id} Information:"
                        response_text += f"\nSubject: {ticket_data['subject']}"
                        response_text += f"\nStatus: {ticket_data['status']}"
                        # Add more ticket details as needed
                    except requests.exceptions.HTTPError as e:
                        if e.response.status_code == 404:
                            response_text = f"Ticket #{ticket_id} not found."
                        else:
                            response_text = f"Error fetching ticket #{ticket_id}: {e}"
                    except Exception as e:
                        response_text = f"An unexpected error occurred: {e}"
                    finally:
                        del user_sessions[user_email] # Clear session state
                    return jsonify({"text": response_text})

                elif current_state == "awaiting_error_info":
                    error_info = chat_message.strip()
                    # Placeholder for searching for known error codes/messages
                    known_error_found = False # Simulate search result
                    if known_error_found:
                        response_text = f"Found known issue for '{error_info}'. Would you like to add this to a new ticket (Y/N)?"
                        user_sessions[user_email] = "awaiting_ticket_creation_after_error"
                    else:
                        response_text = f"No known issue found for '{error_info}'. Do you want to open a new ticket (Y/N)?"
                        user_sessions[user_email] = "awaiting_new_ticket_after_error"
                    return jsonify({"text": response_text})

                elif current_state == "awaiting_ticket_creation_after_error":
                    if chat_message.lower() == "y":
                        user_sessions[user_email] = "awaiting_ticket_details"
                        response_text = "Please provide the following information to create a new ticket:"
                        response_text += "\nURL Link:"
                        response_text += "\nPatient ID:"
                        response_text += "\nProvider username:"
                        response_text += "\nEncounter ID (if available):"
                        response_text += "\nA screenshot of the issue occurring or steps to recreate the issue:"
                        response_text += "\nApproximate timestamp of when the issue occurred:"
                    else:
                        response_text = "Understood. Returning to main menu."
                        del user_sessions[user_email]
                    return jsonify({"text": response_text})

                elif current_state == "awaiting_new_ticket_after_error":
                    if chat_message.lower() == "y":
                        user_sessions[user_email] = "awaiting_ticket_details"
                        response_text = "Please provide the following information to create a new ticket:"
                        response_text += "\nURL Link:"
                        response_text += "\nPatient ID:"
                        response_text += "\nProvider username:"
                        response_text += "\nEncounter ID (if available):"
                        response_text += "\nA screenshot of the issue occurring or steps to recreate the issue:"
                        response_text += "\nApproximate timestamp of when the issue occurred:"
                    else:
                        response_text = "Understood. Returning to main menu."
                        del user_sessions[user_email]
                    return jsonify({"text": response_text})

            elif current_state == "awaiting_ticket_details":
                # This is a simplified parsing. In a real app, you'd parse structured input or guide step-by-step.
                ticket_details = chat_message
                try:
                    # Extract details from chat_message (e.g., using regex or keyword spotting)
                    # For this example, we'll just put the whole message as comment_body
                    subject = f"New Ticket from {user_display_name}"
                    comment_body = f"User provided details: {ticket_details}"
                    # You'd extract URL, Patient ID, etc. here

                    new_ticket = create_ticket(subject, comment_body, user_display_name, user_email)
                    response_text = f"New ticket created successfully! Ticket ID: {new_ticket['ticket']['id']}"

                except requests.exceptions.HTTPError as e:
                    response_text = f"Error creating ticket: {e.response.text}"
                except Exception as e:
                    response_text = f"An unexpected error occurred during ticket creation: {e}"
                finally:
                    del user_sessions[user_email] # Clear session state
                return jsonify({"text": response_text})

            # 4. Handle initial menu selections if no session is active and not a help/admin command
            if "1." in chat_message or "1" == chat_message.strip(): # Existing ticket
                user_sessions[user_email] = "awaiting_ticket_number"
                response_text = "Please provide the existing ticket number."
                return jsonify({"text": response_text})
            
            elif "2." in chat_message or "2" == chat_message.strip(): # Known Issues
                response_text = f"Here is the link to Known Issues: {KNOWN_ISSUES_LINK}"
                return jsonify({"text": response_text})
            
            elif "3." in chat_message or "3" == chat_message.strip(): # Error code/message
                user_sessions[user_email] = "awaiting_error_info"
                response_text = "Please provide the error code or message."
                return jsonify({"text": response_text})

            elif "4." in chat_message or "4" == chat_message.strip(): # Open new ticket
                user_sessions[user_email] = "awaiting_ticket_details"
                response_text = "Please provide the following information to create a new ticket:"
                response_text += "\nURL Link:"
                response_text += "\nPatient ID:"
                response_text += "\nProvider username:"
                response_text += "\nEncounter ID (if available):"
                response_text += "\nA screenshot of the issue occurring or steps to recreate the issue:"
                response_text += "\nApproximate timestamp of when the issue occurred:"
                return jsonify({"text": response_text})

            # Default fallback: If no command matched and no session is active, show the Static Menu
            print(f"DEBUG: No command matched for '{chat_message}', showing static menu.")
            return jsonify(get_static_menu(user_display_name))


        print(f"DEBUG: Unhandled event type: {event.get('type', 'UNKNOWN')}. Returning default text response.")
        return jsonify({"text": "Received an unhandled event type. If you need help, please try typing '@bot help' for assistance."})

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
