# -*- coding: utf-8 -*-
import logging
import ast
import requests
import werkzeug

from odoo import http
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.http import request
import web

_logger = logging.getLogger(__name__)

class PaymayaController(http.Controller):

    @http.route(['/payment/paymongo/pending/<string:ref>'], type='http', auth='public')
    def paymongo_pending(self,ref, **kwargs):
        tx = request.env['payment.transaction'].sudo().search([("paymongo_url_reference","=",ref)])
        request.env['payment.transaction'].sudo().form_feedback(ast.literal_eval(tx.paymongo_details), 'paymongo')
        return werkzeug.utils.redirect('/payment/process')

    # @http.route(['/payment/paymongo/notify'], type='http', auth='public', methods=['POST'])
    # def paymongo_notify(self, **kwargs):
    #     _request = kwargs
    #     _logger.info(kwargs)
    #     # tx = request.env['payment.transaction'].sudo().search([("paymongo_url_reference", "=", ref)])
    #     # details = ast.literal_eval(tx.paymongo_details)
    #     # print(details)
    #     # details['data']['attributes']['status'] = "chargeable"
    #     # print(details)
    #     request.env['payment.acquirer'].sudo().search([('provider','=','paymongo')]).request
    #     request.env['payment.transaction'].sudo().form_feedback(kwargs, 'paymongo')
    #     return werkzeug.utils.redirect('/payment/process')

    # @http.route('https://webhook.site/694017c2-0c14-4d14-b230-e54319fe4c6c', methods=['POST'])
    # def receive_webhook(self):
    #     print(request.form['data'])
    #     return



