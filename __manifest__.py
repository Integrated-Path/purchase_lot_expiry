# -*- coding: utf-8 -*-
{
    'name': 'Purchase Lot & Serial Expiration Tracking with QR Scanning & Printing',
    'version': '19.0.3.1.0',
    'category': 'Inventory/Purchase',
    'summary': 'Lot/Serial tracking, expiration sync across PO/Stock/Invoices, QR label printing (Thermal/Avery), and warehouse receipt scanning',
    'description': """
Purchase Lot & Serial Expiration Tracking & QR Warehouse Automation
===================================================================
This module enables end-to-end management of Lot/Serial Numbers and Expiration Dates:
- Assign Lot/Serial Numbers and Expiration Dates directly on Purchase Order lines.
- Force 'Create and Edit...' dialog when creating new lots to ensure expiration dates are captured.
- Redistribute quantities across multiple assigned lots via interactive wizard.
- Robust cascade synchronization and safety locking guards (protects completed receipts and posted vendor bills).
- Native QR Code label printing wizard with multiple layouts (Thermal rolls 50x30mm, 40x20mm, and Avery sheets).
- Warehouse receipt QR code scanner with multi-format parsing (JSON, Delimited, GS1-128, plain Lot) and one-click receipt validation.
""",
    'author': 'Abdulaziz',
    'depends': [
        'purchase_stock',
        'account',
        'product_expiry',
        'barcodes',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'report/purchase_lot_qr_report.xml',
        'report/purchase_lot_qr_report_templates.xml',
        'wizard/purchase_lot_redistribute_wizard_views.xml',
        'wizard/purchase_lot_qr_wizard_views.xml',
        'wizard/stock_picking_qr_scan_wizard_views.xml',
        'wizard/stock_picking_mobile_qr_wizard_views.xml',
        'views/purchase_order_views.xml',
        'views/stock_picking_views.xml',
        'views/account_move_views.xml',
        'views/stock_lot_views.xml',
        'views/account_journal_form_views.xml'
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
    'assets': {
        'web.assets_backend': [
            'purchase_lot_expiry/static/src/widgets/**/*',
        ],
    },
}
