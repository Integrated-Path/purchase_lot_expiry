# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


class PurchaseLotRedistributeWizard(models.TransientModel):
    _name = 'purchase.lot.redistribute.wizard'
    _description = 'Redistribute Lot Quantities Wizard'

    purchase_line_id = fields.Many2one(
        'purchase.order.line',
        string='Purchase Order Line',
        required=True,
        ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product',
        related='purchase_line_id.product_id',
        string='Product',
        readonly=True
    )
    product_qty = fields.Float(
        related='purchase_line_id.product_qty',
        string='Total Order Quantity',
        readonly=True
    )
    product_uom_id = fields.Many2one(
        'uom.uom',
        related='purchase_line_id.product_uom_id',
        string='Unit of Measure',
        readonly=True
    )
    line_ids = fields.One2many(
        'purchase.lot.redistribute.wizard.line',
        'wizard_id',
        string='Lot Quantities'
    )
    total_allocated_qty = fields.Float(
        string='Total Allocated Quantity',
        compute='_compute_total_allocated_qty'
    )
    qty_mismatch = fields.Boolean(
        string='Quantity Mismatch',
        compute='_compute_total_allocated_qty'
    )

    @api.depends('line_ids.quantity', 'product_qty')
    def _compute_total_allocated_qty(self):
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for wizard in self:
            total = sum(wizard.line_ids.mapped('quantity'))
            wizard.total_allocated_qty = total
            wizard.qty_mismatch = float_compare(total, wizard.product_qty, precision_digits=precision) != 0

    def action_distribute_evenly(self):
        self.ensure_one()
        self._ensure_external_purchase()
        nb_lines = len(self.line_ids)
        if nb_lines > 0:
            even_qty = self.product_qty / nb_lines
            for line in self.line_ids:
                line.quantity = even_qty
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm(self):
        self.ensure_one()
        self._ensure_external_purchase()
        line = self.purchase_line_id

        # Safety Guard: Check if linked picking is done or bill is posted
        line._check_modification_safety({'pol_lot_ids': True, 'lot_ids': True})

        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        if float_compare(self.total_allocated_qty, self.product_qty, precision_digits=precision) != 0:
            raise UserError(
                _("Total allocated quantity (%(allocated)s) must equal total order quantity (%(order_qty)s).")
                % {'allocated': self.total_allocated_qty, 'order_qty': self.product_qty}
            )

        wizard_lots = self.line_ids.mapped('lot_id')
        wizard_lot_ids = set(wizard_lots.ids)

        # Update lot_ids on the purchase order line to reflect wizard selections
        line.lot_ids = [(6, 0, list(wizard_lot_ids))]

        pol_lot_env = self.env['purchase.order.line.lot']
        existing_pol_lots = {l.lot_id.id: l for l in line.pol_lot_ids}

        for w_line in self.line_ids:
            if w_line.expiration_date:
                w_line.lot_id.expiration_date = w_line.expiration_date

            if w_line.lot_id.id in existing_pol_lots:
                existing_pol_lots[w_line.lot_id.id].write({'quantity': w_line.quantity})
            else:
                pol_lot_env.create({
                    'purchase_line_id': line.id,
                    'lot_id': w_line.lot_id.id,
                    'quantity': w_line.quantity,
                })

        for lot_id, pol_lot in list(existing_pol_lots.items()):
            if lot_id not in wizard_lot_ids:
                pol_lot.unlink()

        line._update_stock_move_lots()
        line._update_draft_vendor_bills()
        return {'type': 'ir.actions.act_window_close'}

    def _ensure_external_purchase(self):
        for wizard in self:
            if wizard.purchase_line_id.purchase_type == 'internal_po':
                raise UserError(_("Lot redistribution is not available for internal purchase orders."))


class PurchaseLotRedistributeWizardLine(models.TransientModel):
    _name = 'purchase.lot.redistribute.wizard.line'
    _description = 'Redistribute Lot Quantities Wizard Line'

    wizard_id = fields.Many2one(
        'purchase.lot.redistribute.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lot / Serial Number',
        required=True
    )
    expiration_date = fields.Datetime(
        string='Expiry Date'
    )
    quantity = fields.Float(
        string='Quantity',
        digits='Product Unit of Measure',
        default=0.0
    )
