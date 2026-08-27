# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime


class PurchaseOrderLineLot(models.Model):
    _name = 'purchase.order.line.lot'
    _description = 'Purchase Order Line Lot Allocation'

    purchase_line_id = fields.Many2one(
        'purchase.order.line',
        string='Purchase Line',
        required=True,
        ondelete='cascade'
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lot/Serial Number',
        required=True,
        ondelete='cascade'
    )
    quantity = fields.Float(
        string='Quantity',
        digits='Product Unit of Measure',
        default=0.0
    )
    expiration_date = fields.Datetime(
        string='Expiration Date',
        related='lot_id.expiration_date',
        readonly=False
    )


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    product_tracking = fields.Selection(
        related='product_id.tracking',
        string='Product Tracking',
        readonly=True
    )
    lot_ids = fields.Many2many(
        'stock.lot',
        'purchase_order_line_stock_lot_rel',
        'purchase_line_id',
        'lot_id',
        string='Lots/Serial Numbers',
        domain="[('product_id', '=', product_id)]",
        copy=True,
        help="Lot/Serial numbers assigned to this purchase order line."
    )
    pol_lot_ids = fields.One2many(
        'purchase.order.line.lot',
        'purchase_line_id',
        string='Lot Quantity Allocation'
    )
    expiration_date = fields.Datetime(
        string='Expiry Date',
        compute='_compute_expiration_date',
        store=True,
        readonly=False,
        help="Expiration date assigned to the selected lot(s)."
    )
    lot_expiry_display = fields.Char(
        string='Expiry Dates',
        compute='_compute_lot_expiry_display',
        store=True,
        help="Formatted list of expiry dates for assigned lot(s)."
    )
    show_redistribute_button = fields.Boolean(
        string='Show Redistribute Button',
        compute='_compute_show_redistribute_button'
    )

    @api.depends('lot_ids', 'product_qty', 'product_tracking')
    def _compute_show_redistribute_button(self):
        for line in self:
            line.show_redistribute_button = (
                line.product_tracking in ('lot', 'serial') and len(line.lot_ids) >= 2
            )

    @api.depends('lot_ids', 'lot_ids.expiration_date')
    def _compute_expiration_date(self):
        for line in self:
            dates = [lot.expiration_date for lot in line.lot_ids if lot.expiration_date]
            if dates:
                line.expiration_date = dates[0]
            elif not line.expiration_date:
                line.expiration_date = False

    @api.onchange('expiration_date')
    def _onchange_expiration_date(self):
        if self.expiration_date and self.lot_ids:
            for lot in self.lot_ids:
                lot.expiration_date = self.expiration_date

    @api.depends('lot_ids', 'lot_ids.expiration_date', 'expiration_date')
    def _compute_lot_expiry_display(self):
        for line in self:
            expiries = []
            for lot in line.lot_ids:
                if lot.expiration_date:
                    exp_date = lot.expiration_date.date() if isinstance(lot.expiration_date, datetime) else lot.expiration_date
                    exp_str = fields.Date.to_string(exp_date)
                    if exp_str not in expiries:
                        expiries.append(exp_str)
            if not expiries and line.expiration_date:
                exp_date = line.expiration_date.date() if isinstance(line.expiration_date, datetime) else line.expiration_date
                exp_str = fields.Date.to_string(exp_date)
                expiries.append(exp_str)
            line.lot_expiry_display = ", ".join(sorted(expiries)) if expiries else ""

    @api.onchange('lot_ids', 'product_qty')
    def _onchange_lot_ids_sync_pol_lots(self):
        """ Automatically synchronize pol_lot_ids and distribute product_qty evenly if newly assigned. """
        for line in self:
            if not line.lot_ids:
                line.pol_lot_ids = [(5, 0, 0)]
                continue
            existing_lots = line.pol_lot_ids.mapped('lot_id')
            lines_to_remove = line.pol_lot_ids.filtered(lambda l: l.lot_id not in line.lot_ids)
            commands = [(2, l.id) for l in lines_to_remove if l.id]

            new_lots = line.lot_ids - existing_lots
            if new_lots or len(line.lot_ids) != len(line.pol_lot_ids):
                nb_lots = len(line.lot_ids)
                default_qty = line.product_qty / nb_lots if nb_lots > 0 else 0.0
                commands.append((5, 0, 0))
                for lot in line.lot_ids:
                    commands.append((0, 0, {
                        'lot_id': lot.id,
                        'quantity': default_qty,
                    }))
                line.pol_lot_ids = commands

    def action_open_lot_redistribution_wizard(self):
        self.ensure_one()
        if len(self.lot_ids) < 2:
            raise UserError("Redistribution requires at least 2 assigned lots/serial numbers.")
        
        self._sync_pol_lot_ids_default()

        wizard_lines = []
        for pol_lot in self.pol_lot_ids:
            wizard_lines.append((0, 0, {
                'lot_id': pol_lot.lot_id.id,
                'expiration_date': pol_lot.lot_id.expiration_date,
                'quantity': pol_lot.quantity,
            }))

        wizard = self.env['purchase.lot.redistribute.wizard'].create({
            'purchase_line_id': self.id,
            'line_ids': wizard_lines,
        })

        return {
            'name': 'Redistribute Lot Quantities',
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.lot.redistribute.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _sync_pol_lot_ids_default(self):
        """ Helper to sync pol_lot_ids synchronously if changed in backend code """
        for line in self:
            if not line.lot_ids:
                line.pol_lot_ids.unlink()
                continue
            existing_pol_lots = {l.lot_id.id: l for l in line.pol_lot_ids}
            current_lot_ids = set(line.lot_ids.ids)
            
            for lot_id, pol_lot in list(existing_pol_lots.items()):
                if lot_id not in current_lot_ids:
                    pol_lot.unlink()
            
            remaining_lots = line.lot_ids.filtered(lambda l: l.id not in existing_pol_lots)
            if remaining_lots:
                nb_lots = len(line.lot_ids)
                default_qty = line.product_qty / nb_lots if nb_lots > 0 else 0.0
                for lot in remaining_lots:
                    self.env['purchase.order.line.lot'].create({
                        'purchase_line_id': line.id,
                        'lot_id': lot.id,
                        'quantity': default_qty,
                    })

    def write(self, vals):
        res = super(PurchaseOrderLine, self).write(vals)
        if 'expiration_date' in vals or 'lot_ids' in vals:
            for line in self:
                if line.expiration_date and line.lot_ids:
                    lots_to_update = line.lot_ids.filtered(
                        lambda l: not l.expiration_date or l.expiration_date != line.expiration_date
                    )
                    if lots_to_update:
                        lots_to_update.write({'expiration_date': line.expiration_date})
                line._sync_pol_lot_ids_default()
                line._update_stock_move_lots()
        return res

    def _update_stock_move_lots(self):
        """ Update stock.move and stock.move.line for stock pickings linked to this line """
        for line in self:
            if not line.move_ids:
                continue
            for move in line.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                if line.lot_ids:
                    move.lot_ids = [(6, 0, line.lot_ids.ids)]
                    if line.pol_lot_ids:
                        move.move_line_ids.unlink()
                        move_lines_vals = []
                        for pol_lot in line.pol_lot_ids:
                            move_lines_vals.append({
                                'move_id': move.id,
                                'picking_id': move.picking_id.id if move.picking_id else False,
                                'product_id': move.product_id.id,
                                'product_uom_id': move.product_uom.id,
                                'location_id': move.location_id.id,
                                'location_dest_id': move.location_dest_id.id,
                                'lot_id': pol_lot.lot_id.id,
                                'quantity': pol_lot.quantity,
                            })
                        if move_lines_vals:
                            self.env['stock.move.line'].create(move_lines_vals)

    def _prepare_stock_moves(self, picking):
        res = super(PurchaseOrderLine, self)._prepare_stock_moves(picking)
        for vals in res:
            if self.lot_ids:
                vals['lot_ids'] = [(6, 0, self.lot_ids.ids)]
        return res

    def _create_stock_moves(self, picking):
        moves = super(PurchaseOrderLine, self)._create_stock_moves(picking)
        self._update_stock_move_lots()
        return moves

    def _prepare_account_move_line(self, move=False):
        res = super(PurchaseOrderLine, self)._prepare_account_move_line(move=move)
        if self.lot_ids:
            res['lot_ids'] = [(6, 0, self.lot_ids.ids)]
        return res


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def action_mass_create_lots(self):
        """
        Mass generate Lot and Serial numbers for Purchase Order Lines.
        Rules:
        - Only for lines where product tracking is 'lot' or 'serial'.
        - Option A: Skip lines that already have assigned lots (line.lot_ids is not empty).
        - Sequence Format:
            Lot: "PO00015-LN001-AUTO GENERATED"
            Serial: "PO00015-SN001-AUTO GENERATED"
        - Collision Bypass:
            Check stock.lot and purchase.lot.sequence for duplicates.
            If collision found, increment sequence number by 1 ("bypass by 1").
        - Store generated sequence in purchase.lot.sequence.
        - Store original sequence string on stock.lot.auto_generated_sequence.
        """
        for order in self:
            po_name = order.name or f"PO{order.id}"
            lines_to_process = order.order_line.filtered(
                lambda l: l.product_tracking in ('lot', 'serial') and not l.lot_ids
            )
            if not lines_to_process:
                continue

            for line in lines_to_process:
                tracking = line.product_tracking
                prefix = "LN" if tracking == "lot" else "SN"

                if tracking == "lot":
                    qty_to_generate = 1
                else:
                    qty_to_generate = int(line.product_qty) if line.product_qty > 0 else 1

                created_lots = self.env['stock.lot']
                for _ in range(qty_to_generate):
                    seq_num = 1
                    while True:
                        candidate_name = f"{po_name}-{prefix}{seq_num:03d}-AUTO GENERATED"

                        existing_lot = self.env['stock.lot'].search([
                            ('name', '=', candidate_name)
                        ], limit=1)
                        existing_seq = self.env['purchase.lot.sequence'].search([
                            ('name', '=', candidate_name)
                        ], limit=1)

                        if not existing_lot and not existing_seq:
                            break
                        seq_num += 1

                    self.env['purchase.lot.sequence'].create({
                        'name': candidate_name,
                        'purchase_id': order.id,
                        'purchase_line_id': line.id,
                        'product_id': line.product_id.id,
                        'tracking_type': tracking,
                        'sequence_number': seq_num,
                        'company_id': order.company_id.id,
                    })

                    lot = self.env['stock.lot'].create({
                        'name': candidate_name,
                        'product_id': line.product_id.id,
                        'company_id': order.company_id.id,
                        'expiration_date': line.expiration_date,
                        'auto_generated_sequence': candidate_name,
                    })
                    created_lots |= lot

                line.write({'lot_ids': [(6, 0, created_lots.ids)]})
                line._sync_pol_lot_ids_default()
                line._update_stock_move_lots()
        return True
