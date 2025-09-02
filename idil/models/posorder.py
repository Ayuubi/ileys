from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_is_zero, float_round
import logging
import time

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    def action_pos_order_paid(self):
        _logger.info("Starting action_pos_order_paid for order: %s", self.name)
        super(PosOrder, self).action_pos_order_paid()

        if self.state == 'paid':
            self.create_transaction_booking_lines()
            self.create_pos_order_log()
        return True

    def get_manual_transaction_source_id(self):
        trx_source = self.env['idil.transaction.source'].search([('name', '=', 'Point of Sale')], limit=1)
        if not trx_source:
            raise ValidationError(_('Transaction source "Point of Sale" not found.'))
        return trx_source.id

    def create_transaction_booking_lines(self):
        trx_source_id = self.get_manual_transaction_source_id()

        for order in self:
            try:
                # Start a database transaction
                self.env.cr.execute('SAVEPOINT start_transaction')

                # Step 1: Create the transaction booking
                payment_methods = self.determine_payment_methods(order)
                payment_method_id = next(iter(payment_methods), None)  # Get one payment method ID safely
                balance = order.amount_total - order.amount_paid

                transaction_booking = self.env['idil.transaction_booking'].with_context(skip_validations=True).create({
                    'transaction_number': order.id,
                    'order_number': order.name,
                    'trx_source_id': trx_source_id,
                    'payment_method': 'other',
                    'pos_payment_method': payment_method_id,
                    'payment_status': 'paid' if order.amount_total == order.amount_paid else 'partial_paid',
                    'trx_date': order.date_order,
                    'amount': round(order.amount_total, 2),
                    'amount_paid': round(order.amount_paid, 2),
                    'remaining_amount': balance
                })
                _logger.info("Transaction Booking ID: %s", transaction_booking.id)

                # Step 2: Create debit booking lines for each payment
                for payment in order.payment_ids:
                    payment_method_record = payment.payment_method_id.idil_payment_method_id
                    if not payment_method_record:
                        _logger.error("Payment method not found for ID %s", payment.payment_method_id.id)
                        raise ValidationError(_("Payment method not found for ID %s") % payment.payment_method_id.id)

                    payment_method_record.ensure_one()  # Ensure the record is a singleton
                    debit_line_vals = {
                        'transaction_booking_id': transaction_booking.id,
                        'description': payment_method_record.name,
                        'account_number': payment_method_record.account_number.id,
                        'transaction_type': 'dr',
                        # 'dr_amount': round((payment.amount * 0.05), 2),
                        'dr_amount': round(payment.amount - (payment.amount * 0.05), 2),

                        'cr_amount': 0.0,
                        'transaction_date': order.date_order
                    }
                    # ---------------------------------------------------------
                    self.env['idil.transaction_bookingline'].create(debit_line_vals)
                    _logger.info("Created debit booking line for payment method: %s", payment_method_record.name)

                # Step 3: Create credit booking lines for order lines
                for line in order.lines:
                    custom_product = self.env['my_product.product'].search(
                        [('id', '=', line.product_id.my_product_id.id)], limit=1)
                    if not custom_product:
                        _logger.error("Custom product not found for product %s", line.product_id.id)
                        raise ValidationError(_("Custom product not found for product %s") % line.product_id.id)

                    credit_line_vals = {
                        'transaction_booking_id': transaction_booking.id,
                        'description': line.product_id.name,
                        'account_number': custom_product.income_account_id.id,
                        'product_id': custom_product.id,
                        'transaction_type': 'cr',
                        'dr_amount': 0.0,
                        'cr_amount': round(line.price_subtotal, 2),
                        'transaction_date': order.date_order
                    }
                    self.env['idil.transaction_bookingline'].create(credit_line_vals)
                    _logger.info("Created credit booking line for product: %s", line.product_id.name)

                # Step 4: Handle tax booking lines
                total_tax_amount = sum(
                    line.price_subtotal * sum(tax.amount for tax in line.product_id.taxes_id) / 100 for line in
                    order.lines)

                if total_tax_amount > 0:
                    vat_account = self.get_vat_account()

                    tax_line_vals = {
                        'transaction_booking_id': transaction_booking.id,
                        'description': _('Tax Amount'),
                        'account_number': vat_account.id,
                        'transaction_type': 'cr',
                        'dr_amount': 0.0,
                        'cr_amount': round(total_tax_amount, 2),
                        'transaction_date': order.date_order
                    }
                    self.env['idil.transaction_bookingline'].create(tax_line_vals)
                    _logger.info("Created tax booking line for order: %s", order.name)

                    # Initialize a flag to track if VAT payment is already processed
                    vat_payment_processed = False

                    for payment in order.payment_ids:
                        payment_method_record = payment.payment_method_id.idil_payment_method_id
                        if not payment_method_record:
                            _logger.error("Payment method not found for ID %s", payment.payment_method_id.id)
                            raise ValidationError(
                                _("Payment method not found for ID %s") % payment.payment_method_id.id
                            )

                        # Process VAT payment only for the first loop iteration
                        if not vat_payment_processed:
                            debit_line_vals = {
                                'transaction_booking_id': transaction_booking.id,
                                'description': payment_method_record.name + _(' Tax Amount'),
                                'account_number': payment_method_record.account_number.id,
                                'transaction_type': 'dr',
                                'dr_amount': round(total_tax_amount, 2),
                                'cr_amount': 0.0,
                                'transaction_date': order.date_order
                            }
                            self.env['idil.transaction_bookingline'].create(debit_line_vals)

                            # Mark VAT payment as processed
                            vat_payment_processed = True
                # Commit the transaction if all operations are successful
                self.env.cr.execute('RELEASE SAVEPOINT start_transaction')

            except Exception as e:
                # Rollback the transaction if any exception occurs
                _logger.error("Error creating transaction booking lines for order %s: %s", order.name, str(e))
                self.env.cr.execute('ROLLBACK TO SAVEPOINT start_transaction')
                raise ValidationError(_("Error creating transaction booking lines: %s") % str(e))

    def determine_payment_methods(self, order):
        payment_methods = {}
        for payment in order.payment_ids:
            if payment.payment_method_id.id in payment_methods:
                payment_methods[payment.payment_method_id.id] += payment.amount
            else:
                payment_methods[payment.payment_method_id.id] = payment.amount
        return payment_methods

    def get_vat_account(self):
        # Search for the VAT account by name
        vat_account = self.env['idil.chart.account'].search([('name', '=', 'VAT')], limit=1)
        if not vat_account:
            raise ValidationError(_("VAT account not found. Please ensure that the VAT account exists in the system."))
        return vat_account

    def create_pos_order_log(self):
        """Create a log record for the POS order with order lines."""
        for order in self:
            log_vals = {
                'order_number': order.name,
                'order_date': order.date_order,
                'amount_total': order.amount_total,
                # Assuming the cashier is stored in 'user_id'; adjust if necessary
                'cashier_id': order.user_id.id or self.env.uid,
            }
            order_log = self.env['pos.order.log'].create(log_vals)
            _logger.info("Created POS Order Log for order: %s", order.name)

            for line in order.lines:
                line_vals = {
                    'order_log_id': order_log.id,
                    'product_id': line.product_id.id,
                    'product_name': line.product_id.name,
                    'quantity': line.qty,
                    'price_subtotal': line.price_subtotal,
                }
                self.env['pos.order.log.line'].create(line_vals)
                _logger.info("Created POS Order Log Line for product: %s", line.product_id.name)


class PosOrderLog(models.Model):
    _name = 'pos.order.log'
    _description = 'POS Order Log'

    order_number = fields.Char(string="Order Number", required=True)
    order_date = fields.Datetime(string="Order Date", required=True)
    amount_total = fields.Float(string="Total Amount", required=True)
    cashier_id = fields.Many2one('res.users', string="Cashier", required=True)
    log_line_ids = fields.One2many('pos.order.log.line', 'order_log_id', string="Order Lines")


class PosOrderLogLine(models.Model):
    _name = 'pos.order.log.line'
    _description = 'POS Order Log Line'

    order_log_id = fields.Many2one('pos.order.log', string="Order Log", required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string="Product", required=True)
    product_name = fields.Char(string="Product Name", required=True)
    quantity = fields.Float(string="Quantity", required=True)
    price_subtotal = fields.Float(string="Subtotal", required=True)
