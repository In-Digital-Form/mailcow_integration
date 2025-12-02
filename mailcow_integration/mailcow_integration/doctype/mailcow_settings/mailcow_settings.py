# Copyright (c) 2024, In Digital Form GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class MailcowSettings(Document):
	def validate(self):
		"""Validate Mailcow settings"""
		if self.enabled:
			if not self.api_url:
				frappe.throw("API URL is required when Mailcow Integration is enabled")
			if not self.api_key:
				frappe.throw("API Key is required when Mailcow Integration is enabled")
			if not self.mail_domain:
				frappe.throw("Mail Domain is required when Mailcow Integration is enabled")
			
		# Always clean up API URL - remove trailing slashes
		if self.api_url:
			self.api_url = self.api_url.rstrip('/')
			
			# Validate URL format
			if not self.api_url.startswith(('http://', 'https://')):
				frappe.throw("API URL must start with http:// or https://")
				
		# Clean up mail domain - remove @ if present
		if self.mail_domain:
			self.mail_domain = self.mail_domain.lstrip('@').strip()
	
	def on_update(self):
		"""Clear cache when settings are updated"""
		frappe.cache().delete_key("mailcow_settings")