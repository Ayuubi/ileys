from odoo import api, models, fields
from odoo.tools import html2plaintext


class PosDailyReport(models.TransientModel):
    _name = 'pos.daily.sales.reports.wizard'
    _description = 'Point of Sale Daily Report'

    pos_session_id = fields.Many2one('pos.session', required=True, string="POS Session")
    recipient_email = fields.Char(string='Recipient Email', help="Enter the recipient's email address.")

    def generate_report1(self):
        """Generate POS Sales Report"""
        data = {
            'date_start': False,
            'date_stop': False,
            'config_ids': self.pos_session_id.config_id.ids,
            'session_ids': self.pos_session_id.ids,
        }
        return self.env.ref('point_of_sale.sale_details_report').report_action([], data=data)

    def generate_report(self):
        """Send POS Sales Report via email"""
        template = self.env.ref('point_of_sale.sale_details_report')
        rendered_pdf, _ = template._render_qweb_pdf([self.pos_session_id.id])
        rendered_html_text = html2plaintext(rendered_pdf.decode('utf-8'))

        mail_values = {
            'subject': 'POS Daily Sales Report',
            'body_html': rendered_html_text,
            'body': rendered_html_text,
            'email_to': self.recipient_email,
            'email_from': self.env.user.partner_id.email,
        }
        mail = self.env['mail.mail'].create(mail_values)
        mail.send()
