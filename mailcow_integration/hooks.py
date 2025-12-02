doc_events = {
    "User": {
        "after_insert": "mailcow_integration.user_hooks.create_mailcow_mailbox"
    }
}