from odoo import api, fields, models
from odoo.exceptions import UserError


class CustomModel(models.Model):
    _name = 'idil.custom.model'  # Replace with your model name
    _description = 'Custom Model for Sending Email'

    recipient_email = fields.Char(string="Recipient Email", required=True)
    email_subject = fields.Char(string="Subject", required=True)
    email_body = fields.Html(string="Email Body")

    # def _compute_email_body(self):
    #     for record in self:
    #         # Fetch trial balance data
    #         trial_balance_records = self.env['idil.trial.balance'].search([])
    #
    #         # Construct HTML content for the email body
    #         email_content = "<h3>Trial Balance Report</h3>"
    #         email_content += "<table border='1' style='width:100%; border-collapse: collapse;'>"
    #         email_content += """
    #             <tr>
    #                 <th>Account Number</th>
    #                 <th>Account Type</th>
    #                 <th>Dr Balance</th>
    #                 <th>Cr Balance</th>
    #                 <th>Currency</th>
    #             </tr>
    #         """
    #         for trial_balance in trial_balance_records:
    #             email_content += f"""
    #                 <tr>
    #                     <td>{trial_balance.account_number.name or 'N/A'}</td>
    #                     <td>{trial_balance.header_name or 'N/A'}</td>
    #                     <td>{trial_balance.dr_balance}</td>
    #                     <td>{trial_balance.cr_balance}</td>
    #                     <td>{trial_balance.currency_id.name or 'N/A'}</td>
    #                 </tr>
    #             """
    #         email_content += "</table>"
    #
    #         # Set the generated HTML to email_body
    #         record.email_body = email_content
    #
    # def send_custom_email(self):
    #     for record in self:
    #         if not record.recipient_email:
    #             raise UserError("Please provide a recipient email address.")
    #         if not record.email_subject:
    #             raise UserError("Please provide an email subject.")
    #
    #         mail_values = {
    #             'subject': record.email_subject,
    #             'body_html': record.email_body,
    #             'email_to': record.recipient_email,
    #             'email_from': self.env.user.email or 'noreply@example.com',
    #         }
    #         mail = self.env['mail.mail'].create(mail_values)
    #         mail.send()
    def generate_trial_balance_report(self):
        """Generates the trial balance HTML to be used in the email body."""
        # Fetch trial balance data
        trial_balance_records = self.env['idil.trial.balance'].search([])

        # Construct HTML content for the email body
        email_content = "<h3>Trial Balance Report</h3>"
        email_content += "<table border='1' style='width:100%; border-collapse: collapse;'>"
        email_content += """
            <tr>
                <th>Account Number</th>
                <th>Account Type</th>
                <th>Dr Balance</th>
                <th>Cr Balance</th>
                <th>Currency</th>
            </tr>
        """
        for trial_balance in trial_balance_records:
            email_content += f"""
                <tr>
                    <td>{trial_balance.account_number.name or 'N/A'}</td>
                    <td>{trial_balance.header_name or 'N/A'}</td>
                    <td>{trial_balance.dr_balance}</td>
                    <td>{trial_balance.cr_balance}</td>
                    <td>{trial_balance.currency_id.name or 'N/A'}</td>
                </tr>
            """
        email_content += "</table>"
        return email_content

    def send_custom_email(self):
        for record in self:
            if not record.recipient_email:
                raise UserError("Please provide a recipient email address.")
            if not record.email_subject:
                raise UserError("Please provide an email subject.")

            # Generate the HTML content for the email body before sending
            email_body_content = record.generate_trial_balance_report()

            mail_values = {
                'subject': record.email_subject,
                'body_html': email_body_content,
                'email_to': record.recipient_email,
                'email_from': self.env.user.email or 'noreply@example.com',
            }
            mail = self.env['mail.mail'].create(mail_values)
            mail.send()
