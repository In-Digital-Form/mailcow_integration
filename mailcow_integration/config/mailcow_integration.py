from frappe import _


def get_data():
    return [
        {
            "label": _("Mailcow"),
            "items": [
                {
                    "type": "doctype",
                    "name": "Mailcow Settings",
                    "label": _("Mailcow Settings"),
                    "description": _("Configure Mailcow API and mailbox defaults"),
                }
            ],
        }
    ]
