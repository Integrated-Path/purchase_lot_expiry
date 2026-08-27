# -*- coding: utf-8 -*-
from odoo import models, fields


class PurchaseLotSequence(models.Model):
    _name = 'purchase.lot.sequence'
    _description = 'Purchase Lot Generated Sequence Tracker'

    name = fields.Char(
        string='Generated Sequence',
        required=True,
        index=True
    )
    purchase_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        required=True,
        ondelete='cascade',
        index=True
    )
    purchase_line_id = fields.Many2one(
        'purchase.order.line',
        string='Purchase Order Line',
        ondelete='set null'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True
    )
    tracking_type = fields.Selection(
        [('lot', 'Lot'), ('serial', 'Serial')],
        string='Tracking Type',
        required=True
    )
    sequence_number = fields.Integer(
        string='Sequence Number',
        required=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )
