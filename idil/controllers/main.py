from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class SaveOrderBillButtonController(http.Controller):
    @http.route('/pos/save_order', type='json', auth='user', methods=['POST'])
    def save_order_api(self, **kwargs):
        """
        API endpoint to save an order.
        """
        _logger.info("Received API request: %s", kwargs)
        try:
            order_data = kwargs.get('order')
            if not order_data:
                return {"status": "error", "message": "No order data provided"}

            result = request.env['save.order.bill.button'].sudo().save_order(order_data)
            return result
        except Exception as e:
            _logger.exception("Error saving order: %s", e)
            return {"status": "error", "message": str(e)}
