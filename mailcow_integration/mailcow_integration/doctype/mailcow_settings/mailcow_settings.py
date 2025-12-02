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
			
			# Ensure API URL ends with /
			if not self.api_url.endswith('/'):
				self.api_url += '/'
	
	def on_update(self):
		"""Clear cache when settings are updated"""
		frappe.cache().delete_key("mailcow_settings")