# -*- coding: utf-8 -*-
import polling
import json
import logging
import requests
import dateutil.parser
import pytz
import base64
from werkzeug import urls
from requests.exceptions import HTTPError

from odoo import api, fields, models, _
from odoo.addons.payment.models.payment_acquirer import ValidationError

paymaya_data = {}
_pending_url = '/payment/paymaya/pending/'
_success_url = '/payment/paymaya/success/'
_failed_url = '/payment/paymaya/failed/'
_cancel_url = '/payment/paymaya/cancel/'

_logger = logging.getLogger(__name__)

class AcquirerPaymaya(models.Model):
    _inherit = 'payment.acquirer'

    provider = fields.Selection(selection_add=[('paymaya','Paymaya')])
    paymaya_api_username = fields.Char('Rest API Username', groups='base.group_user')
    paymaya_api_password = fields.Char('Rest API Password', groups='base.group_user')
    paymaya_secret_key = fields.Char(required_if_provider='paymaya', groups='base.group_user')
    paymaya_publishable_key = fields.Char(required_if_provider='paymaya', groups='base.group_user')


    @api.model
    def paymaya_get_headers(self, key):
        auth = '%s:%s%s' %(key,self.paymaya_api_username,self.paymaya_api_password) \
            if self.paymaya_api_username and self.paymaya_api_password \
            else '%s:' %(key)
        encodedBytes = base64.b64encode(auth.encode('UTF-8'))
        encodedString = str(encodedBytes, 'UTF-8')
        print(encodedString)
        return {'Content-Type':'application/json', 'Authorization':'Basic %s'%(encodedString)}

    @api.model
    def _get_paymaya_urls(self, environment):
        """ Paymaya URLS """
        if environment == 'prod':
            return {'paymaya_form_url': 'https://pg.paymaya.com'}
        else:
            return {'paymaya_form_url': 'https://pg-sandbox.paymaya.com'}

    @api.multi
    def paymaya_compute_fees(self, amount, currency_id, country_id):

        if not self.fees_active:
            return 00.00
        country = self.env['res.country'].browse(country_id)
        if country and self.company_id.country_id.id == country.id:
            percentage = self.fees_dom_var
            fixed = self.fees_dom_fixed
        else:
            percentage = self.fees_int_var
            fixed = self.fees_int_fixed
        fees = (percentage / 100.0 * amount) + fixed / (1 - percentage / 100.0)
        return fees

    @api.multi
    def itemGenerator(self, reference):
        reference = self.split_reference(reference)
        if self.env['sale.order'].search([('name','=',reference)]):
            for order in self.env['sale.order'].search([('name','=',reference)]):
                for item in order.order_line:
                    yield { "name": item.product_id.name,
                            "quantity": item.product_uom_qty,
                            "code": item.product_id.code,
                            "description":item.product_id.type,
                            "amount": {
                                "value": item.price_unit,
                                "details": {
                                    "discount": 0,
                                    "serviceCharge": 0,
                                    "shippingFee": 0,
                                    "tax": item.tax_id.amount,
                                    "subtotal": item.price_subtotal
                                }
                            },
                            "totalAmount": {
                                "value": item.price_unit,
                                "details": {
                                    "discount": 0,
                                    "serviceCharge": 0,
                                    "shippingFee": 0,
                                    "tax": item.tax_id.amount,
                                    "subtotal": item.price_subtotal}
                            }
                         }
        elif self.env['account.invoice'].search([('number','=',reference)]):
            for invoice in self.env['account.invoice'].search([('number','=',reference)]):
                for item in invoice.invoice_line_ids:
                    yield { "name": item.product_id.name,
                            "quantity": item.quantity,
                            "code": item.product_id.code,
                            "description": item.name,
                            "amount": {
                                "value": item.price_unit,
                                "details": {
                                    "discount": item.discount,
                                    "serviceCharge": 0,
                                    "shippingFee": 0,
                                    "tax": item.price_tax,
                                    "subtotal": item.price_subtotal
                                }
                            },
                            "totalAmount": {
                                "value": item.price_unit,
                                "details": {
                                    "discount": item.discount,
                                    "serviceCharge": 0,
                                    "shippingFee": 0,
                                    "tax": item.price_tax,
                                    "subtotal": item.price_subtotal
                                }
                            }
                        }

    @api.multi
    def split_reference(self, reference):
        new_ref = ""
        for char in (list(reference)):
            if char == '-':
                break
            else:
                new_ref += char
        return new_ref

    @api.multi
    def paymaya_form_generate_values(self, values):
        self.ensure_one()
        base_url = self.get_base_url()
        paymaya_tx_values = dict(values)
        item_list = list(self.itemGenerator(values.get('reference')))
        paymaya_session_data = {
            "totalAmount": {
                "value": values['amount'],
                "currency": 'PHP', #values.get('currency').name
                "details": {
                    "discount": item_list[0].get('discount'),
                    "serviceCharge": 0,
                    "shippingFee": 0,
                    "tax": item_list[0].get('tax'),
                    "subtotal":values['amount']
                }
            },
            "buyer": {
                "firstName": values.get('partner_first_name'),
                "middleName": " ",
                "lastName": values.get('partner_last_name'),
                "birthday": " ",
                "customerSince": " ",
                "sex": " ",
                "contact": {
                    "phone": values.get('partner_phone'),
                    "email": values.get("partner_email")
                },
                "shippingAddress": {
                    "firstName": values.get('partner_first_name'),
                    "middleName": " ",
                    "lastName": values.get('partner_last_name'),
                    "phone": values.get('partner_phone'),
                    "email": "merchant@merchantsite.com",
                    "line1": " ",
                    "line2": values.get('partner_address'),
                    "city": values.get('partner_city'),
                    "state": (values.get('partner_state')).name,
                    "zipCode": values.get('partner_zip'),
                    "countryCode": (values.get('partner_country')).code,
                    "shippingType": "ST"
                },
                "billingAddress": {
                    "line1": " ",
                    "line2": values.get('billing_partner_address'),
                    "city": values.get('billing_partner_city'),
                    "state": (values.get('partner_state')).name,
                    "zipCode": values.get('billing_partner_zip'),
                    "countryCode": (values.get('partner_country')).code
                }
            },
            "items": [ item for item in item_list],
            "redirectUrl": {
                "success": urls.url_join(base_url, _pending_url)+'%s'%((values.get('reference')).replace('/','-')),
                "failure": urls.url_join(base_url, _pending_url)+'%s'%((values.get('reference')).replace('/','-')),
                "cancel": urls.url_join(base_url, _pending_url)+'%s'%((values.get('reference')).replace('/','-'))
            },
            #"reference"
            "requestReferenceNumber": values.get('reference'),
            "metadata": {
                "url_reference_number":(values.get('reference')).replace('/','-')
            }
        }
        paymaya_tx_values['checkout_id'] = self._create_paymaya_session(paymaya_session_data)
        self.paymaya_get_payment(paymaya_session_data)
        self.paymaya_data = paymaya_session_data
        paymaya_tx_values.update(paymaya_session_data)
        return paymaya_tx_values


    @api.multi
    def _paymaya_request(self, url, data, method, key):
        # self.ensure_one()
        paymaya_url = self._get_paymaya_urls(self.environment)['paymaya_form_url']
        url = urls.url_join(paymaya_url, url)
        resp = requests.request(method, url, data=json.dumps(data), headers=self.paymaya_get_headers(key))
        try:
            if not resp.ok and not (400 <= resp.status_code < 500 and resp.json().get('error', {}).get('code')):
                try:
                    resp.raise_for_status()
                except HTTPError:
                    _logger.error(resp.text)
                    paymaya_error = resp.json().get('error', {}).get('message', '')
                    print(paymaya_error)
                    error_msg = " " + (_("Paymaya gave us the following info about the problem: '%s'") % paymaya_error)
                    raise ValidationError(error_msg)
        except: pass
        return resp

    @api.multi
    def _customize_paymaya(self):
        self.ensure_one()
        data = {
            "logoUrl": "https://cdn3.iconfinder.com/data/icons/diagram_v2/PNG/96x96/diagram_v2-12.png",
            "iconUrl": "https://cdn3.iconfinder.com/data/icons/diagram_v2/PNG/96x96/diagram_v2-12.png",
            "appleTouchIconUrl": "https://cdn3.iconfinder.com/data/icons/diagram_v2/PNG/96x96/diagram_v2-12.png",
            "customTitle": "Custom Merchant",
            "colorScheme": "#89D0CE",
            "showMerchantName": True,
            "hideReceiptInput": False,
            "skipResultPage": False,
            "redirectTimer": 3
        }
        self._paymaya_request('/checkout/v1/customizations', data, 'POST', self.paymaya_secret_key).json()
        return True

    def _create_paymaya_session(self, data):
        self.ensure_one()
        resp = self._paymaya_request("checkout/v1/checkouts", data, 'POST', self.paymaya_publishable_key).json()
        if resp.get("checkoutId") and data.get("requestReferenceNumber"):
            tx = (
                self.env["payment.transaction"]
                    .sudo()
                    .search([("reference", "=", data["requestReferenceNumber"])])
            )
            tx.paymaya_checkout_id = resp["checkoutId"]
            tx.paymaya_redirect_url = resp["redirectUrl"]
        return resp["checkoutId"]

    @api.multi
    def paymaya_get_form_action_url(self):
        self._customize_paymaya()
        tx = self.env['payment.transaction'].search([('reference','=',self.paymaya_data['requestReferenceNumber'])])
        return tx.paymaya_redirect_url


    @api.multi
    def paymaya_get_payment(self, data):
        tx = self.env['payment.transaction'].sudo().search([('reference','=',data['requestReferenceNumber'])])
        checkout_details = self._paymaya_request('checkout/v1/checkouts/%s'%(str(tx.paymaya_checkout_id)),None,'GET', self.paymaya_secret_key).json()
        tx.paymaya_details = checkout_details
        tx.paymaya_url_reference = data['metadata']['url_reference_number']
        return checkout_details

    @api.multi
    def paymaya_capture_payment(self, data):
        body = {
            "captureAmount":{
                "amount": data.get('items', {}).get('totalAmount',{}).get('value'),
                "currency": "PHP"
            }
        }
        return self._paymaya_request('payments/v1/payments/'+data.get('id')+'/capture', body, 'POST', self.paymaya_secret_key).json()


class PaymayaTransaction(models.Model):
    _inherit = 'payment.transaction'

    paymaya_checkout_id = fields.Char('Paymaya Checkout ID', readonly=True)
    paymaya_redirect_url = fields.Char('Paymaya Checkout URL', readonly=True)
    paymaya_details = fields.Char('Session Details', readonly=True)
    paymaya_captured = fields.Char('Payment Details', readonly=True)
    paymaya_url_reference = fields.Char('URL Request Reference Number', readonly=True)

    @api.model
    def _paymaya_form_get_tx_from_data(self, data):
        reference = data.get('requestReferenceNumber')
        # if not reference:
        #     paymaya_error = data.get('error', {}).get('message', '')
        #     _logger.error('Paymaya: invalid reply received from paymaya API, looks like '
        #                   'the transaction failed. (error: %s)', paymaya_error or 'n/a')
        #     error_msg = _("We're sorry to report that the transaction has failed.")
        #     if paymaya_error:
        #         error_msg += " " + (_("Paymaya gave us the following info about the problem: '%s'") %
        #                             paymaya_error)
        #     error_msg += " " + _("Perhaps the problem can be solved by double-checking your "
        #                          "credit card details, or contacting your bank?")
        #     raise ValidationError(error_msg)

        tx = self.search([('reference', '=', reference)])
        if not tx:
            error_msg = (_('Paymaya: no order found for reference %s') % reference)
            _logger.error(error_msg)
            raise ValidationError(error_msg)
        elif len(tx) > 1:
            error_msg = (_('Paymaya: %s orders found for reference %s') % (len(tx), reference))
            _logger.error(error_msg)
            raise ValidationError(error_msg)
        return tx

    # @api.multi
    # def _paymaya_create_webhook(self):
    #     base_url = self.env['payment.acquirer'].search([('provider','=','paymaya')]).get_base_url()
    #     secret_key = self.env['payment.acquirer'].search([('provider','=','paymaya')]).paymaya_secret_key
    #     requests = [{"name":"PAYMENT_SUCCESS","callbackUrl": urls.url_join(base_url, _success_url)},
    #                 {"name":"PAYMENT_FAILED","callbackUrl": urls.url_join(base_url, _failed_url)},
    #                 {"name":"PAYMENT_EXPIRED","callbackUrl": urls.url_join(base_url, _cancel_url)},
    #                 {"name":"CHECKOUT_DROPOUT", "callbackUrl": urls.url_join(base_url, _success_url)},
    #                 {"name":"CHECKOUT_FAILURE", "callbackUrl": urls.url_join(base_url, _failed_url)}
    #                 ]
    #     for request in requests:
    #         response = self.env['payment.acquirer'].sudo()._paymaya_request("checkout/v1/webhooks",
    #                                                                           request, 'POST', secret_key)
    #         try:
    #             if response['code'] and response['code'] == 'PY0039':
    #                 pass
    #         except: pass
    #     return True

    @api.model
    def polling(self, checkout_id, reference, data):
        paymaya = self.env['payment.acquirer'].sudo().search([('provider','=','paymaya')])
        print(paymaya.paymaya_secret_key)
        try:
            polling.poll(lambda :
            paymaya._paymaya_request('checkout/v1/checkouts/%s'%(str(checkout_id)),None,'GET', paymaya.paymaya_secret_key).status_code==200,
            step=60, poll_forever=True,
            ignore_exceptions=(requests.exceptions.ConnectionError,))

            source_details = paymaya.paymaya_get_payment(data)
            return self._paymaya_form_validate(source_details)
        except Exception as e:
            print('ERROR:', str(e))
            return True

    @api.multi
    def _paymaya_form_validate(self, data):
        # self._paymaya_create_webhook()
        status = data.get('paymentStatus')
        former_tx_state = self.state
        res = {'acquirer_reference': data.get('transactionReferenceNumber')}

        if status in ['PENDING_TOKEN', 'PENDING_PAYMENT']:
            res.update(state_message=data.get('pending_reason', ''))
            self._set_transaction_pending()
            if self.state == 'pending' and self.state != former_tx_state:
                _logger.info('Received notification for Paymaya payment %s: set as pending' % (self.reference))
                self.write(res)
                return self.polling(self.paymaya_checkout_id, self.reference)
            return True

        elif status in ['CHECKOUT_FAILURE','PAYMENT_FAILED']:
            try:
                res.update(state_message=data.get('error', {}).get('message', ''))
            except: pass
            self._set_transaction_error()
            if self.state == 'error' and self.state != former_tx_state:
                _logger.info('Received notification for Paymaya checkout %s: set as failed' % (self.reference))
                return self.write(res)
            return True

        elif status in ['CHECKOUT_DROPOUT','PAYMENT_EXPIRED']:
            self._set_transaction_cancel()
            if self.state == 'cancel' and self.state != former_tx_state:
                _logger.info('Received notification for Paymaya checkout %s: set as cancelled' % (self.reference))
                return self.write(res)
            return True

        elif status in ['PAYMENT_SUCCESS']:
            print('capturing...')
            self.paymaya_captured = self.env['payment.acquirer'].sudo().search([('provider','=','paymaya')]).paymaya_capture_payment(self.paymaya_details)
            print('captured.')
            try:
                # dateutil and pytz don't recognize abbreviations PDT/PST
                tzinfos = {
                    'PST': -8 * 3600,
                    'PDT': -7 * 3600,
                }
                date = dateutil.parser.parse(data.get('paymentDetails', {}).get('paymentAt'), tzinfos=tzinfos).astimezone(pytz.utc)
            except:
                date = fields.Datetime.now()
            res.update(date=date)
            self._set_transaction_done()
            if self.state == 'done' and self.state != former_tx_state:
                print('done')
                _logger.info('Validated Paypal payment for tx %s: set as done' % (self.reference))
                return self.write(res)
            return True

        elif status in ['FOR_AUNTHENTICATION', 'AUTHENTICATING']:
            self._set_transaction_authorized()
            if self.state in ['draft','pending'] and self.state != former_tx_state:
                _logger.info('Received notification for Paymaya payment %s: set as pending' % (self.reference))
                return self.write(res)
            return True

        else:
            error = 'Received unrecognized status for Paymaya payment %s: %s, set as error' % (self.reference, status)
            res.update(state_message=error)
            self._set_transaction_cancel()
            if self.state == 'cancel' and self.state != former_tx_state:
                _logger.info(error)
                return self.write(res)
            return True