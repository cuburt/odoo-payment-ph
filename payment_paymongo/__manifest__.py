# -*- coding: utf-8 -*-
{
    'name': "PayMongo Payment Acquirer",

    'summary': """
        PayMongo Acquirer: PayMongo Implementation""",

    'description': """
        PayMongo Payment Acquirer
    """,

    'author': "Cuburt R. Balanon",
    'website': "http://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/12.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Accounting',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['payment'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/payment_views.xml',
        'views/payment_paymongo_templates.xml',
        'data/payment_acquirer_data.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    # only loaded in demonstration mode
    'installable': True,
    'post_init_hook': 'create_missing_journal_for_acquirers',
    'uninstall_hook': 'uninstall_hook',
}