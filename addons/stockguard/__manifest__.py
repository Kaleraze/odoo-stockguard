{
    'name': 'StockGuard',
    'version': '17.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Lot control and multi-level approval workflow for restricted stock',
    'author': 'Your Name',
    'license': 'LGPL-3',
    'depends': ['mail', 'stock'],
    'data': [
        'security/stockguard_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/warehouse_approval_request_views.xml',
        'views/stock_lot_views.xml',
        'views/stockguard_menus.xml',
        'report/warehouse_approval_request_templates.xml',
        'report/warehouse_approval_request_report.xml',
    ],
    'demo': [
        'demo/stockguard_demo.xml',
    ],
    'installable': True,
    'application': True,
}
