# -*- coding: utf-8 -*-
import logging
import ast
import requests
import werkzeug

from odoo import http
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)

class PaymayaController(http.Controller):

    @http.route(['/payment/paymaya/pending/<string:ref>'], type='http', auth='public')
    def paymaya_success(self,ref, **kwargs):
        tx = request.env['payment.transaction'].sudo().search([("paymaya_url_reference","=",ref)])
        request.env['payment.transaction'].sudo().form_feedback(ast.literal_eval(tx.paymaya_details), 'paymaya')
        return werkzeug.utils.redirect('/payment/process')

    # @http.route(['/payment/paymaya/failed/<string:ref>'], type='http', auth='public')
    # def paymaya_success(self, ref, **kwargs):
    #     tx = request.env['payment.transaction'].sudo().search([("paymaya_url_reference", "=", ref)])
    #     request.env['payment.transaction'].sudo().form_feedback(ast.literal_eval(tx.paymaya_details), 'paymaya')
    #     return werkzeug.utils.redirect('/payment/paymaya/failed')
    #
    # @http.route(['/payment/paymaya/cancel/<string:ref>'], type='http', auth='public')
    # def paymaya_success(self, ref, **kwargs):
    #     tx = request.env['payment.transaction'].sudo().search([("paymaya_url_reference", "=", ref)])
    #     request.env['payment.transaction'].sudo().form_feedback(ast.literal_eval(tx.paymaya_details), 'paymaya')
    #     return werkzeug.utils.redirect('/payment/paymaya/cancel')
    #
    # @http.route(['/payment/paymaya/success'], type='http', auth='public')
    # def paymaya_webhook(self, **kwargs):
    #     print('WEBHOOK PAYLOAD' , dict(kwargs))
    #     request.env['payment.transaction'].sudo().form_feedback(dict(kwargs), 'paymaya')
    #     return werkzeug.utils.redirect('/payment/process')
    #
    # @http.route(['/payment/paymaya/failed'], type='http', auth='public')
    # def paymaya_webhook(self, **kwargs):
    #     request.env['payment.transaction'].sudo().form_feedback(dict(kwargs), 'paymaya')
    #     return werkzeug.utils.redirect('/payment/process')
    #
    # @http.route(['/payment/paymaya/cancel'], type='http', auth='public')
    # def paymaya_webhook(self, **kwargs):
    #     request.env['payment.transaction'].sudo().form_feedback(dict(kwargs), 'paymaya')
    #     return werkzeug.utils.redirect('/payment/process')