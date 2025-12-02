app_name = "mailcow_integration"
app_title = "Mailcow Integration"
app_publisher = "In Digital Form GmbH"
app_description = "Mailcow integration for ERPNext"
app_email = "guenther.eder@indigitalform.com"
app_license = "mit"

doc_events = {
    "User": {
        "after_insert": "mailcow_integration.user_hooks.create_mailcow_mailbox"
    }
}