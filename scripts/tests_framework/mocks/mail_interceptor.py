class MailInterceptor:
    def __init__(self, mail_service):
        self.mail_service = mail_service
        self.original_send_reply = mail_service.send_reply
        self.original_forward_parsed_email = mail_service.forward_parsed_email
        self.original_send_synthetic_email = mail_service.send_synthetic_email
        self.original_send_combined_email = mail_service.send_combined_email
        self.original_send_generated_email = getattr(mail_service, 'send_generated_email', None)
        self.original_append_message_to_folder = getattr(mail_service, 'append_message_to_folder', None)
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
            pure_ai_text = None
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
                    elif filename == "reponse_ia.eml" and content:
                        import email
                        from email.policy import default
                        eml_msg = email.message_from_bytes(content, policy=default)
                        if eml_msg.is_multipart():
                            for part in eml_msg.walk():
                                if part.get_content_type() == 'text/plain':
                                    pure_ai_text = part.get_content()
                                    break
                        else:
                            pure_ai_text = eml_msg.get_content()
                        
                        if pure_ai_text:
                            import re
                            # Supprimer la citation de l'email d'origine pour ne garder que la réponse de l'IA
                            match = re.search(r"Le .*?, .*? a écrit :", pure_ai_text)
                            if match:
                                pure_ai_text = pure_ai_text[:match.start()].strip()

            if pure_ai_text:
                body_to_evaluate = pure_ai_text
            else:
                body_to_evaluate = f"Forwarded email with prefix: {prefix_text} / {prefix_html}"

            self.last_sent_email_data = {
                "recipient": to_email,
                "subject": parsed_email.subject,
                "body": body_to_evaluate,
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
            if self.original_send_combined_email:
                return self.original_send_combined_email(service_email, client_email, subject, body_html, original_message_id)
            return True

        def intercepted_send_generated_email(eml: "EmailMessage", dynamic_attachments: list = None) -> bool:
            self.last_sent_email_data = {
                "recipient": eml["To"],
                "subject": eml["Subject"],
                "body": str(eml)
            }
            if self.original_send_generated_email:
                return self.original_send_generated_email(eml=eml, dynamic_attachments=dynamic_attachments)
            return True

        def intercepted_append_message_to_folder(folder, msg, flags=()):
            return True

        self.mail_service.send_reply = intercepted_send_reply
        self.mail_service.forward_parsed_email = intercepted_forward_parsed_email
        self.mail_service.send_synthetic_email = intercepted_send_synthetic_email
        self.mail_service.send_combined_email = intercepted_send_combined_email
        self.mail_service.send_generated_email = intercepted_send_generated_email
        self.mail_service.append_message_to_folder = intercepted_append_message_to_folder
