# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    product_tracking = fields.Selection(
        related='product_id.tracking',
        string='Product Tracking',
        readonly=True
    )
    lot_ids = fields.Many2many(
        'stock.lot',
        'account_move_line_stock_lot_rel',
        'account_move_line_id',
        'stock_lot_id',
        string='Lots/Serial Numbers',
        domain="[('product_id', '=', product_id)]",
        compute='_compute_lot_ids',
        store=True,
        readonly=False,
        copy=True,
        help="Lot/Serial numbers associated with this bill/invoice line."
    )
    lot_expiry_display = fields.Char(
        string='Expiry Dates',
        compute='_compute_lot_expiry_display',
        store=True,
        help="Formatted list of expiry dates for assigned lot(s)."
    )

    @api.depends('purchase_line_id', 'purchase_line_id.lot_ids')
    def _compute_lot_ids(self):
        if hasattr(super(), '_compute_lot_ids'):
            super()._compute_lot_ids()
        for line in self:
            if not line.lot_ids and line.purchase_line_id and line.purchase_line_id.lot_ids:
                line.lot_ids = [(6, 0, line.purchase_line_id.lot_ids.ids)]

    @api.depends('lot_ids', 'lot_ids.expiration_date')
    def _compute_lot_expiry_display(self):
        for line in self:
            expiries = []
            for lot in line.lot_ids:
                if lot.expiration_date:
                    exp_date = lot.expiration_date.date() if isinstance(lot.expiration_date, datetime) else lot.expiration_date
                    exp_str = fields.Date.to_string(exp_date)
                    if exp_str not in expiries:
                        expiries.append(exp_str)
            line.lot_expiry_display = ", ".join(sorted(set(expiries))) if expiries else ""
