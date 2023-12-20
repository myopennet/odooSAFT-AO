# -*- coding: utf-8 -*-
{
    'name': "Angola - Opencloud Layouts",
    'summary': """Opencloud Certification""",
    'description': """
        Módulo para os layouts certificados:
        - Faturas
        - Guias
        - Orçamentos
        - Proforma
        - Recibos
    """,
    'author': "Opencloud",
    'website': "http://www.opencloud.pro",
    'category': 'Certificacao',
    'version': '15.0.0',
    'depends': ['base', 'account', 'sale', 'web', 'stock', 'opc_certification_ao'],
    'data': [
        'security/security.xml',
        'views/account_move_view.xml',
        'views/res_company_view.xml',
        'report/report_account_invoice.xml',
        'report/report_sale_order.xml',
        'report/report_stock_picking.xml',
        'report/report_account_payment.xml',
        'report/report_external_layouts.xml',
    ],
}
