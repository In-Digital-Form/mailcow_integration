import frappe
import requests

def create_mailcow_mailbox(doc, method):
    """
    Called after a new ERPNext User is inserted.
    Creates a corresponding mailbox on Mailcow via API and
    auto-assigns it to the created User via an Email Account.
    """
    # Only create for certain users? Example: only System Users
    if doc.user_type != "System User":
        return

    # Basic config  you may store these in Site Config or a doctype
    enabled = frappe.db.get_single_value("Mailcow Settings", "enabled") or 0
    if not int(enabled):
        # Integration is globally disabled
        return

    mailcow_api_url = frappe.db.get_single_value("Mailcow Settings", "api_url")
    mailcow_api_key = frappe.db.get_single_value("Mailcow Settings", "api_key")
    mail_domain = frappe.db.get_single_value("Mailcow Settings", "mail_domain")
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
        # If no @, fallback  but you might want to abort instead
        local_part = doc.name
        domain = mail_domain

    display_name = doc.full_name or doc.first_name or local_part

    # Use one password consistently for Mailcow and the Email Account
    mailbox_password = doc.new_password or frappe.generate_hash()
    email_address = f"{local_part}@{domain}"

    payload = {
        "local_part": local_part,
        "domain": domain,
        "name": display_name,
        "quota": int(default_quota_mb) * 1024,  # Mailcow expects quota in MB or KiB depending on version/config
        "active": "1",
        "password": mailbox_password,  # You may want a separate mail password policy
        "password2": mailbox_password,
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
    except requests.RequestException:
        frappe.log_error(frappe.get_traceback(), "Mailcow mailbox creation failed")
        return

    # Create / link an Email Account in Frappe for this mailbox
    auto_create_email_account = (
        frappe.db.get_single_value("Mailcow Settings", "auto_create_email_account") or 0
    )

    if int(auto_create_email_account):
        try:
            # Reuse an existing Email Account if one already exists for this address
            existing_email_account_name = frappe.db.exists(
                "Email Account", {"email_id": email_address}
            )
            if existing_email_account_name:
                email_account = frappe.get_doc(
                    "Email Account", existing_email_account_name
                )
            else:
                # Try to link an existing Email Domain (named by domain_name)
                email_domain_name = None
                if domain:
                    if frappe.db.exists("Email Domain", domain):
                        email_domain_name = domain
                    else:
                        email_domain_name = frappe.db.get_value(
                            "Email Domain", {"domain_name": domain}, "name"
                        )

                email_account = frappe.get_doc(
                    {
                        "doctype": "Email Account",
                        "email_id": email_address,
                        "email_account_name": display_name or email_address,
                        "enable_incoming": 1,
                        "enable_outgoing": 1,
                        "default_incoming": 0,
                        "default_outgoing": 0,
                        "awaiting_password": 0,
                        "password": mailbox_password,
                    }
                )

                if email_domain_name:
                    email_account.domain = email_domain_name

                email_account.insert(ignore_permissions=True)

            # Attach this Email Account to the User (User.user_emails child table)
            user = frappe.get_doc("User", doc.name)
            already_linked = any(
                ue.email_account == email_account.name
                for ue in (user.user_emails or [])
            )
            if not already_linked:
                user.append("user_emails", {"email_account": email_account.name})
                user.save(ignore_permissions=True)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(), "Mailcow Email Account assignment failed"
            )

    # Optionally log success or store metadata on the User
    frappe.log_error(
        f"Mailbox created for {email_address}",
        "Mailcow Integration",
    )  # use log_error for quick debug, or a real log
