# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import io
import polling
import math
import json
import logging
import requests
import dateutil.parser
import pytz
import base64
from werkzeug import urls
from requests.exceptions import HTTPError
from odoo.addons.payment.models.payment_acquirer import ValidationError
import subprocess

_logger = logging.getLogger(__name__)
paymongo_data={}
_pending_url = '/payment/paymongo/pending/'
_notify_url = '/payment/paymongo/notify/'
_success_url = '/payment/paymongo/success/'
_failed_url = '/payment/paymongo/failed/'

class AcquirerPaymongo(models.Model):
    _inherit = 'payment.acquirer'

    provider = fields.Selection(selection_add=[('paymongo','Paymongo')])
    paymongo_secret_key = fields.Char(required_if_provider='paymongo', groups='base.group_user')
    paymongo_public_key = fields.Char(required_if_provider='paymongo', groups='base.group_user')

    @api.model
    def paymongo_get_headers(self):
        auth = '%s:%s' % (self.paymongo_secret_key, self.paymongo_public_key)
        encodedBytes = base64.b64encode(auth.encode('UTF-8'))
        encodedString = str(encodedBytes, 'UTF-8')
        return {'Content-Type': 'application/json', 'Authorization': 'Basic %s' % (encodedString)}

    @api.model
    def _get_paymongo_urls(self, environment):
        if environment == 'prod':
            return {'paymongo_form_url':'https://api.paymongo.com',
                    'paymongo_notify_url':urls.url_join(self.get_base_url(),_notify_url)}
        else:
            # subprocess.Popen('lt -h \'http://serverless.social\'-s \'odoo-test\' -p 8069', shell=True, bufsize=1,
            #                  stdin=subprocess.PIPE)
            return {'paymongo_form_url':'https://api.paymongo.com',
                    'paymongo_notify_url': 'https://odoo-test.serverless.social'}


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
    def paymongo_form_generate_values(self, values):
        self.ensure_one()
        base_url = self.get_base_url()
        paymongo_tx_values = dict(values)
        paymongo_source_data = {"data":
            {"attributes":{
            "type":"gcash",
            "amount":math.ceil((values.get('amount'))*100),
            "currency":"PHP",
            "redirect":{
                "success":urls.url_join(base_url, _pending_url)+'%s'%((values.get('reference')).replace('/','-')),
                "failed":urls.url_join(base_url, _pending_url)+'%s'%((values.get('reference')).replace('/','-'))
            },
            "billing":{
                "name":"%s %s"%(values.get('partner_first_name'),values.get('partner_last_name')),
                "phone":values.get('partner_phone'),
                "email":values.get('partner_email'),
                "address":{
                    "line1":" ",
                    "line2":values.get('partner_address'),
                    "state":(values.get('partner_state')).name,
                    "postal_code":values.get('partner_zip'),
                    "city":values.get('partner_city'),
                    "country":(values.get('partner_country')).code,
                }
            },
                                 }}}
        paymongo_tx_values['source_id'] = self._create_paymongo_source(paymongo_source_data, values.get('reference'))
        self.paymongo_get_source(values.get('reference'))
        self.paymongo_data = paymongo_source_data
        self.paymongo_data.update({"metadata":{"reference":values.get('reference')}})
        paymongo_tx_values.update(paymongo_source_data)
        return paymongo_tx_values

    @api.multi
    def _paymongo_request(self, url, data, method):
        # self.ensure_one()
        paymongo_url = self._get_paymongo_urls(self.environment)['paymongo_form_url']
        url = urls.url_join(paymongo_url, url)
        resp = requests.request(method, url, data=json.dumps(data), headers=self.paymongo_get_headers())
        try:
            if not resp.ok or resp.status_code >= 205:
                try:
                    resp.raise_for_status()
                except HTTPError:
                    _logger.error(resp.text)
                    paymongo_error = resp.json().get('errors')[0]
                    error_msg = " " + (_("Paymongo gave us the following info about the problem: '%s'") % paymongo_error)
                    raise ValidationError(error_msg)
        except: pass
        return resp

    def _create_paymongo_source(self, data, reference):
        self.ensure_one()
        resp = self._paymongo_request("/v1/sources", data, 'POST').json()
        if resp.get("data",{}).get('id'):
            tx = (
                self.env["payment.transaction"]
                    .sudo()
                    .search([("reference", "=", reference)])
            )
            tx.paymongo_source_id = resp.get('data',{}).get('id')
            tx.paymongo_redirect_url = resp.get('data',{}).get('attributes',{}).get('redirect',{}).get('checkout_url')
            # self._create_paymongo_webhook(reference)
        return resp.get('data', {}).get('id')

    @api.multi
    def paymongo_get_source(self, reference):
        tx = self.env['payment.transaction'].sudo().search([('reference', '=', reference)])
        source_details = self._paymongo_request('/v1/sources/%s' % (str(tx.paymongo_source_id)), None,
                                                 'GET').json()
        source_details.update({"metadata": {"reference": reference}})
        tx.paymongo_details = source_details
        tx.paymongo_url_reference = reference.replace('/','-')
        return source_details

    # @api.multi
    # def _create_paymongo_webhook(self, reference):
    #     request = {"data":{"attributes":{"events":["source.chargeable"],
    #                              "url": self._get_paymongo_urls(self.environment)['paymongo_notify_url']+_notify_url}}}
    #     response = self._paymongo_request("/v1/webhooks",request, 'POST')
    #     tx = self.env['payment.transaction'].sudo().search([('reference', '=', reference)])
    #     tx.paymongo_webhook_id = response.get('data',{}).get('id')
    #     return True
    #
    # @api.multi
    # def _enable_paymongo_webhook(self, id):
    #     try:
    #         self._paymongo_request("v1/webhooks/"+id+"/enable", None, 'POST')
    #     except: pass
    #     return True
    #
    # @api.multi
    # def _disable_paymongo_webhook(self, id):
    #     response = self._paymongo_request("v1/webhooks/" + id + "/disable", None, 'POST')
    #     return True

    @api.multi
    def _create_paymongo_payment(self,data, webhook_id):
        # self._disable_paymongo_webhook(webhook_id)
        request = {
            "data":{
                "attributes":{
                    "amount":data.get('data',{}).get('attributes',{}).get('amount'),
                    "currency":data.get('data',{}).get('attributes',{}).get('currency'),
                    "source":{
                        "id":data.get('data',{}).get('id'),
                        "type":data.get('data',{}).get('type')
                    }
                }
            }
        }
        return self._paymongo_request("/v1/payments", request, 'POST').json()

    @api.multi
    def paymongo_get_form_action_url(self):
        tx = self.env['payment.transaction'].sudo().search([('reference','=',self.paymongo_data['metadata']['reference'])])
        return tx.paymongo_redirect_url



class PaymongoTransaction(models.Model):
    _inherit = 'payment.transaction'

    paymongo_source_id = fields.Char('Paymongo Source ID', readonly=True)
    paymongo_webhook_id = fields.Char('Paymongo Webhook ID', readonly=True)
    paymongo_payment_id = fields.Char('Paymongo Payment ID', readonly=True)
    paymongo_redirect_url = fields.Char('Paymongo Redirect URL', readonly=True)
    paymongo_details = fields.Char('Source Details', readonly=True)
    paymongo_url_reference = fields.Char('URL Request Reference Number', readonly=True)

    @api.model
    def _paymongo_form_get_tx_from_data(self, data):
        reference = data['metadata']['reference']
        tx = self.search([('reference','=',reference)])
        if not tx:
            error_msg = (_('Paymongo: no order found for reference %s') % reference)
            _logger.error(error_msg)
            raise ValidationError(error_msg)
        elif len(tx) > 1:
            error_msg = (_('Paymongo: %s orders found for reference %s') % (len(tx), reference))
            _logger.error(error_msg)
            raise ValidationError(error_msg)
        return tx

    @api.model
    def polling(self, source_id, reference):
        try:
            polling.poll(lambda :
            self.env['payment.acquirer'].sudo().search([('provider','=','paymongo')])._paymongo_request('https://api.paymongo.com/v1/sources/'+source_id, None, 'GET').status_code==200,
            step=60, poll_forever=True,
            ignore_exceptions=(requests.exceptions.ConnectionError,))
            source_details = self.env['payment.acquirer'].sudo().search([('provider','=','paymongo')]).paymongo_get_source(reference)
            # process to paid state
            return self._paymongo_form_validate(source_details)
        except Exception as e:
            print('ERROR:',str(e))
            return True  # to pending state

    @api.multi
    def _paymongo_form_validate(self, data):
        status = data.get('data',{}).get('attributes',{}).get('status')
        former_tx_state = self.state
        res = {'acquirer_reference': data.get('data',{}).get('id')}

        if status in ['pending']:
            res.update(state_message='Pending authorization of payment.')
            self._set_transaction_pending()
            if self.state == 'pending' and self.state != former_tx_state:
                _logger.info('Received notification for Paymongo payment %s: set as pending' % (self.reference))
                print('to authorize')
                self.write(res)
                return self.polling(self.paymongo_source_id, self.reference)

            return True

        # elif status in ['failed']:
        #     try:
        #         res.update(state_message=data.get('error', {}).get('message', ''))
        #     except:
        #         pass
        #     self._set_transaction_error()
        #     if self.state in ['pending', 'authorized', 'draft'] and self.state != former_tx_state:
        #         _logger.info('Received notification for Paymaya checkout %s: set as failed' % (self.reference))
        #         return self.write(res)
        #     return True

        elif status in ['cancelled']:
            res.update(state_message='Payment source expired/cancelled.')
            self._set_transaction_cancel()
            if self.state == 'cancel' and self.state != former_tx_state:
                _logger.info('Received notification for Paymongo checkout %s: set as cancelled' % (self.reference))
                return self.write(res)
            return True

        elif status in ['chargeable']:
            # res.update(state_message='Payment is authorised.')
            # self._set_transaction_authorized()
            # if self.state == 'authorized' and self.state != former_tx_state:
            #     _logger.info('Validated Paymongo payment for tx %s: set as done' % (self.reference))
            #     return self.write(res)
            print('authorizing...')
            response = self.env['payment.acquirer'].sudo().search([('provider','=','paymongo')])._create_paymongo_payment(data, self.paymongo_webhook_id)
            print(response)
            print('authorized')
            self.paymongo_payment_id = response['data']['id']
            self.fees = response['data']['attributes']['fee']
            self.return_url = response['data']['attributes']['access_url']
            self.is_processed = True
            # self.env['payment.acquirer'].sudo().search([('provider','=','paymongo')])._disable_paymongo_webhook(self.paymongo_webhook_id)
            try:
                # dateutil and pytz don't recognize abbreviations PDT/PST
                tzinfos = {
                    'PST': -8 * 3600,
                    'PDT': -7 * 3600,
                }
                date = dateutil.parser.parse(data.get('paymentDetails', {}).get('paymentAt'),
                                             tzinfos=tzinfos).astimezone(pytz.utc)
            except:
                date = fields.Datetime.now()
            res.update(date=date)
            self._set_transaction_done()
            if self.state == 'done' and self.state != former_tx_state:
                print('done')
                _logger.info('Validated Paymongo payment for tx %s: set as done' % (self.reference))
                return self.write(res)
            return True

        else:
            error = 'Received unrecognized status for Paymongo payment %s: %s, set as error' % (self.reference, status)
            res.update(state_message=error)
            self._set_transaction_cancel()
            if self.state == 'cancel' and self.state != former_tx_state:
                _logger.info(error)
                return self.write(res)
            return True




