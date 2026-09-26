# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
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
            new_lots = line.lot_ids - existing_lots
            if new_lots or len(line.lot_ids) != len(line.pol_lot_ids):
                nb_lots = len(line.lot_ids)
                default_qty = line.product_qty / nb_lots if nb_lots > 0 else 0.0
                commands = [(5, 0, 0)]
                for lot in line.lot_ids:
                    commands.append((0, 0, {
                        'lot_id': lot.id,
                        'quantity': default_qty,
                    }))
                line.pol_lot_ids = commands

    def action_open_lot_redistribution_wizard(self):
        self.ensure_one()
        if len(self.lot_ids) < 2:
            raise UserError(_("Redistribution requires at least 2 assigned lots/serial numbers."))
        
        # Check safety guard before opening
        self._check_modification_safety({'pol_lot_ids': True})

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
            'name': _('Redistribute Lot Quantities'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.lot.redistribute.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_lot_qr_wizard(self):
        self.ensure_one()
        if not self.lot_ids:
            raise UserError(_("No Lot/Serial numbers assigned to this purchase order line."))
        return self.order_id.action_open_lot_qr_wizard()

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

    def _check_modification_safety(self, vals):
        """ Prevent modifying lots, quantities, or expiries if linked pickings are done or vendor bills posted """
        critical_fields = {'lot_ids', 'expiration_date', 'product_qty', 'pol_lot_ids'}
        if not (critical_fields & set(vals.keys())):
            return

        for line in self:
            if line.order_id.state in ('purchase', 'done'):
                # Check for done pickings
                done_pickings = line.move_ids.mapped('picking_id').filtered(lambda p: p.state == 'done')
                if done_pickings:
                    picking_names = ", ".join(done_pickings.mapped('name'))
                    raise UserError(
                        _("Cannot modify Lot/Serial numbers, quantities, or expiration dates on PO line for '%(product)s' "
                          "because linked receipt(s) (%(pickings)s) have already been processed and marked as Done. "
                          "Please process returns or scrap adjustments instead.")
                        % {'product': line.product_id.display_name, 'pickings': picking_names}
                    )
                
                # Check for posted vendor bills
                posted_bills = line.invoice_lines.mapped('move_id').filtered(lambda m: m.state == 'posted')
                if posted_bills:
                    bill_names = ", ".join(posted_bills.mapped('name'))
                    raise UserError(
                        _("Cannot modify Lot/Serial numbers, quantities, or expiration dates on PO line for '%(product)s' "
                          "because linked vendor bill(s) (%(bills)s) are already posted. "
                          "Please create a credit note or adjust the bill first.")
                        % {'product': line.product_id.display_name, 'bills': bill_names}
                    )

    def write(self, vals):
        self._check_modification_safety(vals)
        res = super(PurchaseOrderLine, self).write(vals)
        sync_needed_fields = {'expiration_date', 'lot_ids', 'product_qty', 'pol_lot_ids'}
        if sync_needed_fields & set(vals.keys()):
            for line in self:
                if line.expiration_date and line.lot_ids:
                    lots_to_update = line.lot_ids.filtered(
                        lambda l: not l.expiration_date or l.expiration_date != line.expiration_date
                    )
                    if lots_to_update:
                        lots_to_update.write({'expiration_date': line.expiration_date})
                line._sync_pol_lot_ids_default()
                line._update_stock_move_lots()
                line._update_draft_vendor_bills()
        return res

    def unlink(self):
        for line in self:
            if line.order_id.state in ('purchase', 'done'):
                done_pickings = line.move_ids.mapped('picking_id').filtered(lambda p: p.state == 'done')
                if done_pickings:
                    raise UserError(
                        _("Cannot delete PO line for '%(product)s' because linked receipt(s) have already been processed.")
                        % {'product': line.product_id.display_name}
                    )
        return super(PurchaseOrderLine, self).unlink()

    def _update_draft_vendor_bills(self):
        """ Propagate lot changes to linked draft vendor bill lines """
        for line in self:
            draft_bill_lines = line.invoice_lines.filtered(lambda l: l.move_id.state == 'draft')
            if draft_bill_lines:
                draft_bill_lines.write({'lot_ids': [(6, 0, line.lot_ids.ids)]})

    def _update_stock_move_lots(self):
        """ Update stock.move and stock.move.line for stock pickings linked to this line """
        for line in self:
            if not line.move_ids:
                continue
            for move in line.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                if not line.lot_ids:
                    move.lot_ids = [(5, 0, 0)]
                    move.move_line_ids.unlink()
                else:
                    move.lot_ids = [(6, 0, line.lot_ids.ids)]
                    move.move_line_ids.unlink()
                    if line.pol_lot_ids:
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
                    else:
                        nb_lots = len(line.lot_ids)
                        qty_per_lot = move.product_uom_qty / nb_lots if nb_lots > 0 else 0.0
                        move_lines_vals = [{
                            'move_id': move.id,
                            'picking_id': move.picking_id.id if move.picking_id else False,
                            'product_id': move.product_id.id,
                            'product_uom_id': move.product_uom.id,
                            'location_id': move.location_id.id,
                            'location_dest_id': move.location_dest_id.id,
                            'lot_id': lot.id,
                            'quantity': qty_per_lot,
                        } for lot in line.lot_ids]
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
