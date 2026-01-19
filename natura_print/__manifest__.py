{
    'name': 'Natura Label Printing',
    'version': '1.0',
    'category': 'Inventory/Label Printing',
    'summary': 'Manage Label Templates and printers and print labels',
    'description': "",
    'depends': ['base', 'product', 'stock'],
    'data': [
        'security/ir.model.access.csv', 
        'views/printers_list_views.xml', 
        'views/label_template_views.xml',
        'views/lot_label_wizard_views.xml',
        'views/product_label_wizard_views.xml',
        'views/product_template_views.xml',
        'views/quant_label_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/stock_lot_views.xml',
        'views/stock_quant_views.xml',
        'views/test_print_wizard_views.xml',
        'views/natura_print_menus.xml'
        ],
    'installable': True,
    'application': True,
    'auto_install': False
}
