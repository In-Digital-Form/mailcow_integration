import frappe
import requests


def get_mailcow_settings():
    """Get Mailcow settings from the doctype"""
    settings = frappe.get_single("Mailcow Settings")
    return settings

def create_mailcow_mailbox(doc, method):
    """
    Called after a new ERPNext User is inserted.
    Creates a corresponding mailbox on Mailcow via API and
    auto-assigns it to the created User via an Email Account.
    """
    # Only create for certain users? Example: only System Users
    if doc.user_type != "System User":
        return

    # Basic config from Mailcow Settings doctype
    enabled = frappe.db.get_single_value("Mailcow Settings", "enabled") or 0
    if not int(enabled):
        # Integration is globally disabled
        return

    mailcow_api_url = frappe.db.get_single_value("Mailcow Settings", "api_url")
    mailcow_api_key = frappe.db.get_single_value("Mailcow Settings", "api_key")
    mail_domain = frappe.db.get_single_value("Mailcow Settings", "mail_domain")
    default_quota_mb = frappe.db.get_single_value("Mailcow Settings", "default_quota_mb") or 1024

    if not (mailcow_api_url and mailcow_api_key and mail_domain):
        frappe.log_error("Mailcow settings missing: API URL, API Key, or Mail Domain", "Mailcow Integration")
        return

    # Create email address based on user's name/email and configured domain
    if doc.email and "@" in doc.email:
        # If user already has an email, use the local part with our domain
        local_part = doc.email.split("@")[0]
    else:
        # Create local part from username (remove any existing domain)
        local_part = doc.name.split("@")[0] if "@" in doc.name else doc.name
    
    # Always use the configured mail domain
    domain = mail_domain
    email_address = f"{local_part}@{domain}"

    # Check if mailbox already exists to avoid duplicates
    existing_email_account = frappe.db.exists("Email Account", {"email_id": email_address})
    if existing_email_account:
        frappe.log_error(f"Email account {email_address} already exists, skipping mailbox creation", "Mailcow Integration")
        return

    display_name = doc.full_name or doc.first_name or local_part

    # Generate a secure password for the mailbox
    mailbox_password = frappe.generate_hash()[:12]  # Use first 12 chars for a reasonable password

    payload = {
        "local_part": local_part,
        "domain": domain,
        "name": display_name,
        "quota": int(default_quota_mb),  # Mailcow API expects quota in MB
        "active": "1",
        "password": mailbox_password,
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
        response_data = r.json()
        
        # Check if Mailcow API returned success
        if response_data and not response_data.get('success', True):
            error_msg = response_data.get('msg', 'Unknown error')
            frappe.log_error(f"Mailcow API error: {error_msg}", "Mailcow mailbox creation failed")
            return
            
    except requests.RequestException as e:
        frappe.log_error(f"Request failed: {str(e)}\n{frappe.get_traceback()}", "Mailcow mailbox creation failed")
        return
    except Exception as e:
        frappe.log_error(f"Unexpected error: {str(e)}\n{frappe.get_traceback()}", "Mailcow mailbox creation failed")
        return

    # Create Email Account in Frappe for this mailbox
    auto_create_email_account = (
        frappe.db.get_single_value("Mailcow Settings", "auto_create_email_account") or 0
    )

    if int(auto_create_email_account):
        try:
            # Create the Email Account
            email_account = frappe.get_doc(
                {
                    "doctype": "Email Account",
                    "email_id": email_address,
                    "email_account_name": f"{display_name} ({email_address})",
                    "enable_incoming": 1,
                    "enable_outgoing": 1,
                    "default_incoming": 0,
                    "default_outgoing": 0,
                    "awaiting_password": 0,
                    "password": mailbox_password,
                    # Add IMAP/SMTP settings for Mailcow
                    "use_imap": 1,
                    "use_smtp": 1,
                    "email_server": mailcow_api_url.replace('https://', '').replace('http://', '').rstrip('/'),
                    "smtp_server": mailcow_api_url.replace('https://', '').replace('http://', '').rstrip('/'),
                    "smtp_port": 587,
                    "use_tls": 1,
                    "imap_folder": "INBOX"
                }
            )

            email_account.insert(ignore_permissions=True)

            # Update the user's email field to the new email address
            doc.db_set("email", email_address, update_modified=False)
            
            # Attach this Email Account to the User via user_emails child table
            user = frappe.get_doc("User", doc.name)
            user.append("user_emails", {"email_account": email_account.name})
            user.save(ignore_permissions=True)
            
        except Exception as e:
            frappe.log_error(
                f"Email Account creation failed: {str(e)}\n{frappe.get_traceback()}", 
                "Mailcow Email Account assignment failed"
            )

    # Log success
    frappe.msgprint(f"Successfully created mailbox and email account for {email_address}")
    frappe.logger().info(f"Mailbox created for {email_address}")
    
    # Optionally store metadata on the User for future reference
    user_doc = frappe.get_doc("User", doc.name)
    user_doc.add_comment("Info", f"Mailcow mailbox created: {email_address}")


def test_mailcow_connection():
    """
    Test function to verify Mailcow API connection
    Can be called from bench console: 
    frappe.call("mailcow_integration.user_hooks.test_mailcow_connection")
    """
    try:
        settings = get_mailcow_settings()
        
        if not settings.enabled:
            return {"success": False, "message": "Mailcow Integration is disabled"}
        
        if not settings.api_url:
            return {"success": False, "message": "API URL missing"}
            
        if not settings.api_key:
            return {"success": False, "message": "API Key missing"}
        
        # Debug info
        debug_info = {
            "api_url": settings.api_url,
            "api_key_length": len(settings.api_key) if settings.api_key else 0,
            "api_key_preview": f"{settings.api_key[:8]}..." if settings.api_key and len(settings.api_key) > 8 else "Too short"
        }
        
        headers = {
            "Accept": "application/json",
            "X-API-Key": settings.api_key
        }
        
        # Test API connection by getting mailbox list
        test_url = f"{settings.api_url.rstrip('/')}/api/v1/get/mailbox/all"
        
        r = requests.get(
            test_url,
            headers=headers,
            timeout=10
        )
        
        if r.status_code == 200:
            return {
                "success": True, 
                "message": "Connection successful", 
                "debug": debug_info,
                "response_preview": str(r.json())[:200] + "..." if len(str(r.json())) > 200 else str(r.json())
            }
        else:
            return {
                "success": False, 
                "message": f"API returned status {r.status_code}: {r.text}",
                "debug": debug_info,
                "test_url": test_url,
                "headers_sent": {k: v for k, v in headers.items() if k != "X-API-Key"}
            }
            
    except Exception as e:
        return {"success": False, "message": f"Connection failed: {str(e)}"}


def debug_mailcow_settings():
    """
    Debug function to check current Mailcow settings
    Can be called from bench console:
    frappe.call("mailcow_integration.user_hooks.debug_mailcow_settings")
    """
    try:
        settings = get_mailcow_settings()
        
        return {
            "enabled": settings.enabled,
            "api_url": settings.api_url,
            "api_key_set": bool(settings.api_key),
            "api_key_length": len(settings.api_key) if settings.api_key else 0,
            "api_key_preview": f"{settings.api_key[:8]}..." if settings.api_key and len(settings.api_key) > 8 else settings.api_key,
            "mail_domain": settings.mail_domain,
            "default_quota_mb": settings.default_quota_mb,
            "auto_create_email_account": settings.auto_create_email_account
        }
    except Exception as e:
        return {"error": str(e)}


def test_basic_mailcow_api():
    """
    Test basic Mailcow API without authentication first
    Can be called from bench console:
    frappe.call("mailcow_integration.user_hooks.test_basic_mailcow_api")
    """
    try:
        settings = get_mailcow_settings()
        
        if not settings.api_url:
            return {"success": False, "message": "API URL missing"}
        
        # Test basic connectivity without authentication
        test_url = f"{settings.api_url.rstrip('/')}/api/v1/get/status/version"
        
        r = requests.get(test_url, timeout=10)
        
        return {
            "success": r.status_code < 400,
            "status_code": r.status_code,
            "response": r.text[:500],
            "url_tested": test_url
        }
        
    except Exception as e:
        return {"success": False, "message": f"Connection failed: {str(e)}"}


def generate_curl_command():
    """
    Generate a curl command for manual testing
    Can be called from bench console:
    frappe.call("mailcow_integration.user_hooks.generate_curl_command")
    """
    try:
        settings = get_mailcow_settings()
        
        if not (settings.api_url and settings.api_key):
            return {"error": "API URL or API Key missing"}
        
        curl_command = f"""curl -X GET "{settings.api_url.rstrip('/')}/api/v1/get/mailbox/all" \\
-H "Accept: application/json" \\
-H "X-API-Key: {settings.api_key}" \\
-v"""

        return {
            "curl_command": curl_command,
            "instructions": "Run this curl command in your terminal to test authentication manually"
        }
        
    except Exception as e:
        return {"error": str(e)}


def fix_api_url_trailing_slash():
    """
    Fix the API URL by removing trailing slash
    Can be called from bench console:
    frappe.call("mailcow_integration.user_hooks.fix_api_url_trailing_slash")
    """
    try:
        settings = frappe.get_single("Mailcow Settings")
        
        if settings.api_url:
            original_url = settings.api_url
            # Remove trailing slash
            cleaned_url = settings.api_url.rstrip('/')
            
            if original_url != cleaned_url:
                settings.api_url = cleaned_url
                settings.save()
                return {
                    "success": True,
                    "message": f"API URL updated from '{original_url}' to '{cleaned_url}'"
                }
            else:
                return {
                    "success": True,
                    "message": "API URL is already clean (no trailing slash)"
                }
        else:
            return {
                "success": False,
                "message": "No API URL set"
            }
            
    except Exception as e:
        return {"error": str(e)}
