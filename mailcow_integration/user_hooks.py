import frappe
import requests

def create_mailcow_mailbox(doc, method):
    """
    Called after a new ERPNext User is inserted.
    Creates a corresponding mailbox on Mailcow via API.
    """
    # Only create for certain users? Example: only System Users
    if doc.user_type != "System User":
        return

    # Basic config — you may store these in Site Config or a doctype
    mailcow_api_url = frappe.db.get_single_value("Mailcow Settings", "api_url")
    mailcow_api_key = frappe.db.get_single_value("Mailcow Settings", "api_key")
    mail_domain      = frappe.db.get_single_value("Mailcow Settings", "mail_domain")
    default_quota_mb = frappe.db.get_single_value("Mailcow Settings", "default_quota_mb") or 1024

    if not (mailcow_api_url and mailcow_api_key and mail_domain):
        frappe.log_error("Mailcow settings missing", "Mailcow Integration")
        return

    # Derive local_part from the user email
    # Assumes doc.email is like "user@yourdomain.com"
    if "@" in doc.email:
        local_part, domain_from_mail = doc.email.split("@", 1)
        # Optionally override domain
        domain = mail_domain or domain_from_mail
    else:
        # If no @, fallback – but you might want to abort instead
        local_part = doc.name
        domain = mail_domain

    display_name = doc.full_name or doc.first_name or local_part

    payload = {
        "local_part": local_part,
        "domain": domain,
        "name": display_name,
        "quota": int(default_quota_mb) * 1024,  # Mailcow expects quota in MB or KiB depending on version/config
        "active": "1",
        "password": doc.new_password or frappe.generate_hash(),  # You may want a separate mail password policy
        "password2": doc.new_password or frappe.generate_hash(),
        "force_pw_update": "0"
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-API-Key": mailcow_api_key
    }

    try:
        r = requests.post(
            f"{mailcow_api_url.rstrip('/')}/api/v1/add/mailbox",
            json=payload,
            headers=headers,
            timeout=10
        )
        r.raise_for_status()
    except requests.RequestException as e:
        frappe.log_error(frappe.get_traceback(), "Mailcow mailbox creation failed")
        return

    # Optionally log success or store metadata on the User
    frappe.log_error(f"Mailbox created for {doc.email}", "Mailcow Integration")  # use log_error for quick debug, or a real log