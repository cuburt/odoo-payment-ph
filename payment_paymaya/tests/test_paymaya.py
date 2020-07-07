import unittest
import odoo
from odoo import fields
from odoo.addons.payment.tests.common import PaymentAcquirerCommon
from odoo.tools import mute_logger

class PaymayaCommon(PaymentAcquirerCommon):

    def setUp(self):
        super(PaymayaCommon, self).setUp()
        self.paymaya = self.env.ref('paymant.payment_acquirer_paymaya')
        self.paymaya.write({
            'paymaya_secret_key': 'sk-X8qolYjy62kIzEbr0QRK1h4b4KDVHaNcwMYk39jInSl',
            'paymaya_publishable_key': 'pk-Z0OSzLvIcOI2UIvDhdTGVVfRSSeiGStnceqwUE7n0Ah'
        })