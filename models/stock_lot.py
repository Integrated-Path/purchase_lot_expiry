# -*- coding: utf-8 -*-
from odoo import models, fields


class StockLot(models.Model):
    _inherit = 'stock.lot'

    auto_generated_sequence = fields.Char(
        string='Auto-Generated Sequence',
        readonly=True,
        copy=False,
        help="Original auto-generated sequence reference for this lot number."
    )
