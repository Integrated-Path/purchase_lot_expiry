# -*- coding: utf-8 -*-
from odoo import models, fields, api


class StockLot(models.Model):
    _inherit = 'stock.lot'

    qr_code_value = fields.Char(
        string='QR Code Payload',
        compute='_compute_qr_code_value',
        store=True,
        index=True,
        help='Structured QR code payload used for scanning and label printing.'
    )
    product_part_number = fields.Char(
            related='product_id.part_number',
            string='Part Number',
            store=True,
            readonly=True
    )

    @api.depends('name', 'product_id', 'product_id.barcode', 'product_id.default_code', 'expiration_date')
    def _compute_qr_code_value(self):
        for lot in self:
            bc = ''
            if lot.product_id:
                bc = lot.product_id.barcode or lot.product_id.default_code or ''
            lot_name = lot.name or ''
            exp_str = ''
            if lot.expiration_date:
                exp_date = lot.expiration_date.date() if hasattr(lot.expiration_date, 'date') else lot.expiration_date
                exp_str = fields.Date.to_string(exp_date)
            lot.qr_code_value = f"PROD:{bc}|LOT:{lot_name}|EXP:{exp_str}|QTY:1.0"
