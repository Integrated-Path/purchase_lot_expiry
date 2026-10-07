# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime


class StockMove(models.Model):
    _inherit = 'stock.move'

    purchase_type = fields.Selection(
        related='purchase_line_id.order_id.purchase_type',
        string='Purchase Type',
        readonly=True
    )
    product_tracking = fields.Selection(
        related='product_id.tracking',
        string='Product Tracking',
        readonly=True
    )
    lot_expiry_display = fields.Char(
        string='Expiry Dates',
        compute='_compute_lot_expiry_display',
        store=True,
        help="Formatted list of expiry dates for assigned lot(s) in this stock move."
    )

    @api.depends(
        'move_line_ids.expiration_date',
        'move_line_ids.lot_id',
        'move_line_ids.lot_id.expiration_date',
        'purchase_type'
    )
    def _compute_lot_expiry_display(self):
        for move in self:
            if move.purchase_type == 'internal_po':
                move.lot_expiry_display = False
                continue
            expiries = []
            lots = move.lot_ids | move.move_line_ids.lot_id
            for lot in lots:
                if lot.expiration_date:
                    exp_date = lot.expiration_date.date() if isinstance(lot.expiration_date, datetime) else lot.expiration_date
                    exp_str = fields.Date.to_string(exp_date)
                    if exp_str not in expiries:
                        expiries.append(exp_str)
            for ml in move.move_line_ids:
                if ml.expiration_date and not ml.lot_id:
                    exp_date = ml.expiration_date.date() if isinstance(ml.expiration_date, datetime) else ml.expiration_date
                    exp_str = fields.Date.to_string(exp_date)
                    if exp_str not in expiries:
                        expiries.append(exp_str)
            move.lot_expiry_display = ", ".join(sorted(set(expiries))) if expiries else ""

    def _set_lot_ids(self):
        """
        Odoo 19 bugfix: In stock.move._set_lot_ids(), line 676 calls
        self._prepare_move_line_vals() instead of move._prepare_move_line_vals(),
        causing 'ValueError: Expected singleton: stock.move(x, y)' when len(self) > 1.
        By delegating per single move, each invocation executes safely as a singleton.
        """
        for move in self:
            super(StockMove, move)._set_lot_ids()
