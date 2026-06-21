class MailInterceptor:
    def __init__(self, mail_service):
        self.mail_service = mail_service
        self.original_send_reply = mail_service.send_reply
        self.original_forward_parsed_email = mail_service.forward_parsed_email
        self.original_send_synthetic_email = mail_service.send_synthetic_email
        self.original_send_combined_email = mail_service.send_combined_email
        self.last_sent_email_data = None
        self._apply_mocks()

    def reset(self):
        self.last_sent_email_data = None

    def _apply_mocks(self):
        def intercepted_send_reply(to_email, subject, body, is_html=False, original_message_id=None):
            self.last_sent_email_data = {
                "recipient": to_email,
                "subject": subject,
                "body": body
            }
            return self.original_send_reply(to_email, subject, body, is_html, original_message_id)

        def intercepted_forward_parsed_email(parsed_email, to_email, prefix_text=None, prefix_html=None, dynamic_attachments=None):
            sources = []
            if dynamic_attachments:
                for filename, content, mimetype in dynamic_attachments:
                    if filename == "sources_ia.html" and content:
                        import re
                        # Extract filenames from the generated sources_html
                        html_str = content.decode("utf-8", errors="ignore")
                        matches = re.findall(r"<span class='source-title'>([^<]+)</span>|<a[^>]+class='source-title'[^>]*>([^<]+)</a>", html_str)
                        for m in matches:
                            source_name = m[0] if m[0] else m[1]
                            if source_name and source_name not in sources:
                                sources.append(source_name)

            self.last_sent_email_data = {
                "recipient": to_email,
                "subject": parsed_email.subject,
                "body": f"Forwarded email with prefix: {prefix_text} / {prefix_html}",
                "sources": sources
            }
            # Pour conserver les pièces jointes (le .msg/.eml et le html) tout en contournant 
            # l'anti-spam SMTP, on remplace temporairement l'adresse @gmail.com par une adresse locale.
            # L'usurpation de @gmail.com dans le Reply-To ou le corps est souvent la cause du rejet 5.7.1.
            original_sender = parsed_email.sender
            parsed_email.sender = "test-citoyen@dsiatlantic.com"
            
            result = self.original_forward_parsed_email(
                parsed_email, 
                to_email, 
                prefix_text=prefix_text, 
                prefix_html=prefix_html, 
                dynamic_attachments=dynamic_attachments
            )
            
            # Restauration
            parsed_email.sender = original_sender
            return result

        def intercepted_send_synthetic_email(to_email, subject, text_content, attachment_paths=None):
            self.last_sent_email_data = {
                "recipient": to_email,
                "subject": subject,
                "body": text_content
            }
            return self.original_send_synthetic_email(to_email, subject, text_content, attachment_paths)

        def intercepted_send_combined_email(service_email, client_email, subject, body_html, original_message_id=None):
            self.last_sent_email_data = {
                "recipient": service_email,
                "subject": subject,
                "body": body_html
            }
            return self.original_send_combined_email(service_email, client_email, subject, body_html, original_message_id)

        self.mail_service.send_reply = intercepted_send_reply
        self.mail_service.forward_parsed_email = intercepted_forward_parsed_email
        self.mail_service.send_synthetic_email = intercepted_send_synthetic_email
        self.mail_service.send_combined_email = intercepted_send_combined_email
