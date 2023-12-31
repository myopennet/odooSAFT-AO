# -*- coding: utf-8 -*-
{
    'name': "Angola - Opencloud Certification - Opennet",
    'summary': """Opencloud Certification""",
    'description': """
        Módulo para a Certificação.
        Angola - Saft
        Geração de Hash
    """,
    'author': "Opencloud",
    'website': "http://www.opencloud.pro",
    'category': 'Certificacao',
    'version': '15.0.1.1',
    'depends': ['account', 'sale', 'stock', 'sale_stock', 'l10n_pt', 'web',
                'base_vat', 'delivery', 'product', 'base'],
    # always loaded
    'data': [
         'security/ir.model.access.csv',
         'security/account_security.xml',
         'data/account_data.xml',
         'data/account_tax_data.xml',
         'data/tipos_produtos_saft.xml',
         'data/data_GT.xml',
         'data/res_lang.xml',
         'data/taxonomias_data.xml',
         'data/ir_sequence_type.xml',
         'data/sequence.xml',
         'data/journal_data.xml',
         'views/account_journal_view.xml',
         'views/account_move_view.xml',
         'views/account_view.xml',
         'views/ir_sequence_view.xml',
         'views/taxonomia_view.xml',
         'views/tipo_produto_saft.xml',
         'views/account_config_settings.xml',
         'views/product_view.xml',
         'views/res_view.xml',
         'views/stock_view.xml',
         'views/pedidos_at_historico_view.xml',
         'views/utilizador_financas_view.xml',
         'views/hist_saft_view.xml',
         'views/account_resequence_wizard_view.xml',
         'wizard/recall_at_view.xml',
         'wizard/alterar_guia_view.xml',
         'wizard/manual_code_view.xml',
         'wizard/import_saft_view.xml',
         'wizard/exportar_stock_view.xml',
         'wizard/call_at_wiz_view.xml',
         'wizard/wizard_l10n_pt_saft.xml',
         'wizard/cancelar_fatura_view.xml',
         'wizard/alert_atcud_view.xml',
         'views/ir_sequence_atcud.xml',
         'views/sale_order.xml',
         'views/menus.xml',
         'wizard/cancelar_sale_order_view.xml',
    ],
}
