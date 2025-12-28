# Mailcow Integration for ERPNext

Integrate your ERPNext instance with a Mailcow email server to automatically manage mailboxes for your system users.

## Features

*   **Automatic Mailbox Creation**: When a new System User is created in ERPNext, a corresponding mailbox is automatically created in your Mailcow instance.
*   **Auto-configure Email Account**: Automatically creates a "Email Account" record in ERPNext with the correct IMAP/SMTP settings and assigns it to the user, so they can start emailing immediately.
*   **User Deletion Handling**: Optionally disable the Mailcow mailbox when an ERPNext user is deleted/disabled, ensuring better security and license management.
*   **Customizable Quota**: Set a default mailbox quota (in MB) for new users.

## Installation

1.  Get the app:
    ```bash
    bench get-app https://github.com/yourusername/mailcow_integration
    ```

2.  Install it on your site:
    ```bash
    bench --site [your.site.name] install-app mailcow_integration
    ```

## Configuration

Navigate to **Mailcow Settings** in ERPNext to configure the integration.

1.  **Enable Mailcow Integration**: Check this to activate the hooks.
2.  **Mailcow API URL**: The full URL to your Mailcow server (e.g., `https://mail.yourdomain.com`).
3.  **Mailcow API Key**: Your Read-Write API key from the Mailcow admin interface.
4.  **Mail Domain**: The domain to be used for new email addresses (e.g., `yourcompany.com`).
    *   *Note: If a user is created as `john`, their email will be `john@yourcompany.com`.*
5.  **Default Quota (MB)**: The storage quota assigned to new mailboxes (default: 1024 MB).
6.  **Auto-create Email Account for User**: If enabled, ERPNext will automatically configure the "Email Account" for the user.
7.  **Disable Mailbox on User Deletion**: If enabled, deleting a user in ERPNext will set the corresponding Mailcow mailbox to "inactive" instead of deleting it.

## Usage

### Creating a User
1.  Create a new User in ERPNext.
2.  Ensure `User Type` is set to "System User".
3.  Upon saving, the app will:
    *   Check if the user exists in Mailcow.
    *   Create the mailbox if it doesn't exist.
    *   Generate a secure random password.
    *   Create an `Email Account` in ERPNext linked to this user.
    *   Update the user's `Email` field to the new Mailcow address.

### Deleting a User
1.  When you delete a System User in ERPNext:
    *   The app checks the "Disable Mailbox on User Deletion" setting.
    *   If enabled, it connects to Mailcow and sets the mailbox status to inactive (allowing you to preserve data or re-enable it later).

## Troubleshooting

*   Check the **Error Log** list in ERPNext for any integration errors (search for "Mailcow").
*   Ensure your Mailcow API key has correct permissions (Read-Write).
*   Verify your ERPNext server can reach your Mailcow server (check firewalls/DNS).

## License

[MIT](./LICENSE)
