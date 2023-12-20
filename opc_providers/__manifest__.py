{
    'name': "Providers Map",
    'description': "With this module you can see a map of providers information",
    'author': "Opencloud",
    'website': "https://www.opencloud.pro",
    'category': 'Tools',
    'depends': [
        'account',
        'opc_certification_ao'
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/open_providers_map.xml',
        'views/provider_map.xml',
        'views/account_move.xml',
    ],
    'application': False,
    'license': 'OPL-1',
    'installable': True,
    'auto_install': False,
}