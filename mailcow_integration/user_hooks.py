import frappe
import requests
from frappe.utils.password import get_decrypted_password


def get_mailcow_settings():
    """Get Mailcow settings from the doctype with decrypted API key"""
    settings = frappe.get_single("Mailcow Settings")
    # Get the decrypted API key
    settings.api_key = get_decrypted_password("Mailcow Settings", "Mailcow Settings", "api_key")
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
    mailcow_api_key = get_decrypted_password("Mailcow Settings", "Mailcow Settings", "api_key")
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

    # Use curl subprocess since that's what works reliably
    curl_result = create_mailbox_via_curl(local_part, domain, display_name, default_quota_mb, mailbox_password)
    
    if not curl_result["success"]:
        frappe.log_error(f"Mailcow mailbox creation failed: {curl_result.get('error', 'Unknown error')}", "Mailcow Integration")
        return
    
    # Check API response
    response_data = curl_result.get("response", {})
    if isinstance(response_data, str):
        try:
            import json
            response_data = json.loads(response_data)
        except:
            pass
    
    if isinstance(response_data, dict) and not response_data.get('success', True):
        error_msg = response_data.get('msg', 'Unknown error')
        frappe.log_error(f"Mailcow API error: {error_msg}", "Mailcow mailbox creation failed")
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


def test_exact_curl_replication():
    """
    Test with exactly the same headers as your working curl command
    Can be called from bench console:
    frappe.call("mailcow_integration.user_hooks.test_exact_curl_replication")
    """
    try:
        settings = get_mailcow_settings()
        
        if not (settings.api_url and settings.api_key):
            return {"error": "Settings missing"}
        
        test_url = f"{settings.api_url.rstrip('/')}/api/v1/get/mailbox/all"
        
        # Test 1: Exact minimal headers like your working curl
        headers_minimal = {
            "Content-Type": "application/json",
            "X-API-Key": settings.api_key
        }
        
        # Create a session and disable auto-headers
        session = requests.Session()
        
        # Remove default headers that requests adds
        session.headers.clear()
        
        try:
            r1 = session.get(test_url, headers=headers_minimal, timeout=10)
            result1 = {
                "status": r1.status_code,
                "response": r1.text[:200] if r1.text else None,
                "headers_sent": dict(session.prepare_request(requests.Request('GET', test_url, headers=headers_minimal)).headers)
            }
        except Exception as e:
            result1 = {"error": str(e)}
        
        # Test 2: Try with exactly your curl headers order
        headers_curl_order = {}
        headers_curl_order["Content-Type"] = "application/json"
        headers_curl_order["X-API-Key"] = settings.api_key
        
        try:
            r2 = requests.get(test_url, headers=headers_curl_order, timeout=10)
            result2 = {
                "status": r2.status_code,
                "response": r2.text[:200] if r2.text else None
            }
        except Exception as e:
            result2 = {"error": str(e)}
            
        # Test 3: Try with requests.Session and custom adapter
        try:
            from requests.adapters import HTTPAdapter
            session3 = requests.Session()
            session3.mount('https://', HTTPAdapter())
            
            r3 = session3.get(test_url, headers=headers_minimal, timeout=10)
            result3 = {
                "status": r3.status_code,
                "response": r3.text[:200] if r3.text else None
            }
        except Exception as e:
            result3 = {"error": str(e)}
        
        return {
            "test_1_minimal_headers_clean_session": result1,
            "test_2_curl_header_order": result2,
            "test_3_custom_adapter": result3,
            "working_curl_command": f'curl --header "Content-Type: application/json" --header "X-API-Key: {settings.api_key}" {test_url}'
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
        
        curl_command = f"""curl --header "Content-Type: application/json" --header "X-API-Key: {settings.api_key}" "{settings.api_url.rstrip('/')}/api/v1/get/mailbox/all\""""

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


def debug_request_details():
    """
    Debug the exact request being sent vs working curl
    Can be called from bench console:
    frappe.call("mailcow_integration.user_hooks.debug_request_details")
    """
    try:
        import urllib3
        
        # Enable detailed logging
        urllib3.disable_warnings()
        
        settings = get_mailcow_settings()
        
        if not (settings.api_url and settings.api_key):
            return {"error": "Settings missing"}
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-API-Key": settings.api_key
        }
        
        test_url = f"{settings.api_url.rstrip('/')}/api/v1/get/mailbox/all"
        
        # Create session for detailed debugging
        session = requests.Session()
        
        # Prepare the request
        req = requests.Request('GET', test_url, headers=headers)
        prepared = session.prepare_request(req)
        
        # Send and capture details
        response = session.send(prepared, timeout=10)
        
        return {
            "request_details": {
                "method": prepared.method,
                "url": prepared.url,
                "headers": dict(prepared.headers),
                "body": prepared.body
            },
            "response_details": {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "text": response.text[:500] if response.text else None
            },
            "api_key_info": {
                "length": len(settings.api_key),
                "first_4": settings.api_key[:4] if settings.api_key else None,
                "last_4": settings.api_key[-4:] if settings.api_key else None
            }
        }
        
    except Exception as e:
        return {"error": str(e), "traceback": frappe.get_traceback()}


def test_different_approaches():
    """
    Test different ways to make the request
    Can be called from bench console:
    frappe.call("mailcow_integration.user_hooks.test_different_approaches")
    """
    try:
        settings = get_mailcow_settings()
        test_url = f"{settings.api_url.rstrip('/')}/api/v1/get/mailbox/all"
        results = {}
        
        # Approach 1: Original way
        try:
            headers1 = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-API-Key": settings.api_key
            }
            r1 = requests.get(test_url, headers=headers1, timeout=10)
            results["approach_1_original"] = {
                "status": r1.status_code,
                "response": r1.text[:200]
            }
        except Exception as e:
            results["approach_1_original"] = {"error": str(e)}
        
        # Approach 2: Minimal headers (like your curl)
        try:
            headers2 = {
                "Content-Type": "application/json",
                "X-API-Key": settings.api_key
            }
            r2 = requests.get(test_url, headers=headers2, timeout=10)
            results["approach_2_minimal"] = {
                "status": r2.status_code,
                "response": r2.text[:200]
            }
        except Exception as e:
            results["approach_2_minimal"] = {"error": str(e)}
            
        # Approach 3: Even more minimal (just API key)
        try:
            headers3 = {
                "X-API-Key": settings.api_key
            }
            r3 = requests.get(test_url, headers=headers3, timeout=10)
            results["approach_3_api_key_only"] = {
                "status": r3.status_code,
                "response": r3.text[:200]
            }
        except Exception as e:
            results["approach_3_api_key_only"] = {"error": str(e)}
            
        # Approach 4: Using requests with verify=False (in case SSL issue)
        try:
            headers4 = {
                "Content-Type": "application/json",
                "X-API-Key": settings.api_key
            }
            r4 = requests.get(test_url, headers=headers4, timeout=10, verify=False)
            results["approach_4_no_ssl_verify"] = {
                "status": r4.status_code,
                "response": r4.text[:200]
            }
        except Exception as e:
            results["approach_4_no_ssl_verify"] = {"error": str(e)}
            
        return results
        
    except Exception as e:
        return {"error": str(e)}


def test_with_curl_user_agent():
    """
    Test connection with curl User-Agent to fix the blocking issue
    Can be called from bench console:
    frappe.call("mailcow_integration.user_hooks.test_with_curl_user_agent")
    """
    try:
        settings = get_mailcow_settings()
        
        if not (settings.api_url and settings.api_key):
            return {"error": "Settings missing"}
        
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": settings.api_key,
            "User-Agent": "curl/7.68.0"  # Mimic curl to avoid blocking
        }
        
        test_url = f"{settings.api_url.rstrip('/')}/api/v1/get/mailbox/all"
        
        r = requests.get(test_url, headers=headers, timeout=10)
        
        if r.status_code == 200:
            return {
                "success": True,
                "message": "✅ SUCCESS! Fixed User-Agent blocking issue",
                "status_code": r.status_code,
                "response_preview": str(r.json())[:300] + "..." if len(str(r.json())) > 300 else str(r.json())
            }
        else:
            return {
                "success": False,
                "message": f"Still failing with status {r.status_code}",
                "response": r.text[:200]
            }
            
    except Exception as e:
        return {"error": str(e)}


def test_minimal_headers():
    """
    Test with only the exact headers from working curl
    Can be called from bench console:
    frappe.call("mailcow_integration.user_hooks.test_minimal_headers")
    """
    try:
        settings = get_mailcow_settings()
        
        if not (settings.api_url and settings.api_key):
            return {"error": "Settings missing"}
        
        test_url = f"{settings.api_url.rstrip('/')}/api/v1/get/mailbox/all"
        
        # Try to prevent requests from adding extra headers
        session = requests.Session()
        
        # Explicitly override problematic auto-headers
        headers_override = {
            "Content-Type": "application/json", 
            "X-API-Key": settings.api_key,
            "Accept": "*/*",  # Simpler accept header like curl
            "Accept-Encoding": "",  # Disable compression
            "Connection": "close",  # Disable keep-alive
            "User-Agent": ""  # Empty user agent
        }
        
        r = session.get(test_url, headers=headers_override, timeout=10)
        
        # Get the actual headers that were sent
        prepared_request = session.prepare_request(requests.Request('GET', test_url, headers=headers_override))
        
        return {
            "status_code": r.status_code,
            "response": r.text[:300] if r.text else None,
            "headers_actually_sent": dict(prepared_request.headers),
            "success": r.status_code == 200
        }
        
    except Exception as e:
        return {"error": str(e)}


def test_mailcow_connection():
    """
    Test Mailcow connection using subprocess curl (the method that works)
    Can be called from bench console:
    frappe.call("mailcow_integration.user_hooks.test_mailcow_connection")
    """
    try:
        import subprocess
        settings = get_mailcow_settings()
        
        if not settings.enabled:
            return {"success": False, "message": "Mailcow Integration is disabled"}
        
        if not (settings.api_url and settings.api_key):
            return {"success": False, "message": "API URL or API Key missing"}
        
        # Use subprocess curl since that's what actually works
        result = subprocess.run([
            'curl', '-s',
            '--header', 'Content-Type: application/json',
            '--header', f'X-API-Key: {settings.api_key}',
            f'{settings.api_url.rstrip("/")}/api/v1/get/mailbox/all'
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            try:
                import json
                response_data = json.loads(result.stdout)
                return {
                    "success": True,
                    "message": "✅ Connection successful!",
                    "mailbox_count": len(response_data) if isinstance(response_data, list) else "Unknown",
                    "response_preview": str(response_data)[:300] + "..." if len(str(response_data)) > 300 else str(response_data)
                }
            except json.JSONDecodeError:
                if "authentication failed" in result.stdout:
                    return {
                        "success": False, 
                        "message": "❌ Authentication failed - check API key",
                        "response": result.stdout
                    }
                else:
                    return {
                        "success": True,
                        "message": "✅ Connection successful!",
                        "response": result.stdout[:300]
                    }
        else:
            return {
                "success": False,
                "message": f"❌ Curl command failed (exit code: {result.returncode})",
                "error": result.stderr,
                "response": result.stdout
            }
            
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "❌ Request timed out"}
    except Exception as e:
        return {"success": False, "message": f"❌ Error: {str(e)}"}


def create_mailbox_via_curl(local_part, domain, display_name, quota_mb, password):
    """
    Create mailbox using curl subprocess (the reliable method)
    """
    try:
        import subprocess
        import json
        
        settings = get_mailcow_settings()
        
        payload = {
            "local_part": local_part,
            "domain": domain,
            "name": display_name,
            "quota": int(quota_mb),
            "active": "1",
            "password": password,
            "password2": password,
            "force_pw_update": "0"
        }
        
        # Use curl for the POST request
        result = subprocess.run([
            'curl', '-s', '-X', 'POST',
            '--header', 'Content-Type: application/json',
            '--header', f'X-API-Key: {settings.api_key}',
            '--data', json.dumps(payload),
            f'{settings.api_url.rstrip("/")}/api/v1/add/mailbox'
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            try:
                response_data = json.loads(result.stdout)
                return {"success": True, "response": response_data}
            except json.JSONDecodeError:
                if "authentication failed" in result.stdout:
                    return {"success": False, "error": "Authentication failed", "response": result.stdout}
                else:
                    return {"success": True, "response": result.stdout}
        else:
            return {"success": False, "error": f"Curl failed (exit code: {result.returncode})", "stderr": result.stderr}
            
    except Exception as e:
        return {"success": False, "error": str(e)}
