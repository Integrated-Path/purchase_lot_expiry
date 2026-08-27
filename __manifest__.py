# -*- coding: utf-8 -*-
{
    'name': 'Purchase Lot & Serial Expiration Tracking',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Purchase',
    'summary': 'Add lot/serial numbers and expiration dates to Purchase Order lines with tag display across Pickings and Invoices',
    'description': """
Purchase Lot & Serial Expiration Tracking
=========================================
This module enables the selection and management of Lot/Serial Numbers and their corresponding
Expiration Dates directly within Purchase Order lines.

Key Features:
- Assign Lot/Serial Numbers and Expiration Dates on Purchase Order lines.
- Force 'Create and Edit...' dialog when creating new lots to ensure expiration dates are captured.
- Show lot & expiration fields only for products tracked by lot/serial.
- Redistribute quantities across multiple assigned lots via interactive wizard.
- Direct synchronization from Purchase Order lines to Stock Moves / Pickings and Account Move Lines (Vendor Bills).
""",
    'author': 'Antigravity',
    'website': 'https://www.odoo.com',
    'depends': [
        'purchase_stock',
        'account',
        'product_expiry',
    ],
    'data': [
        'security/purchase_lot_security.xml',
        'security/ir.model.access.csv',
        'wizard/purchase_lot_redistribute_wizard_views.xml',
        'views/purchase_order_views.xml',
        'views/stock_picking_views.xml',
        'views/account_move_views.xml',
        'views/stock_lot_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
