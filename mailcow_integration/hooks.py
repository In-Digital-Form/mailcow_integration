doc_events = {
    "User": {
        "after_insert": "mailcow_integration.mailcow_api.user_hooks.create_mailcow_mailbox"
    }
}