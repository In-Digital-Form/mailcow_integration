import frappe
import requests

def test_minimal_headers():
    """
    Test with only the exact headers from working curl
    Can be called from bench console:
    exec(open('/Users/gue/Development/hellokitchen/erpnext/mailcow_integration/test_mailcow.py').read())
    test_minimal_headers()
    """
    try:
        settings = frappe.get_single("Mailcow Settings")
        
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
        
        result = {
            "status_code": r.status_code,
            "response": r.text[:300] if r.text else None,
            "headers_actually_sent": dict(prepared_request.headers),
            "success": r.status_code == 200
        }
        
        print("Test result:", result)
        return result
        
    except Exception as e:
        error = {"error": str(e)}
        print("Error:", error)
        return error

if __name__ == "__main__":
    test_minimal_headers()