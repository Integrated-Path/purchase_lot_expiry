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

    purchase_type = fields.Selection(
        related='order_id.purchase_type',
        string='Purchase Type',
        readonly=True
    )
    logistics_stage = fields.Selection(
        related='order_id.logistics_stage',
        string='Logistics Stage',
        readonly=True
    )
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

    @api.depends('lot_ids', 'product_qty', 'product_tracking', 'purchase_type', 'order_id.logistics_stage')
    def _compute_show_redistribute_button(self):
        for line in self:
            line.show_redistribute_button = (
                line.purchase_type != 'internal_po'
                and line.order_id.logistics_stage == 'expiry_check'
                and line.product_tracking in ('lot', 'serial')
                and len(line.lot_ids) >= 2
            )

    @api.depends('lot_ids', 'lot_ids.expiration_date', 'purchase_type')
    def _compute_expiration_date(self):
        for line in self:
            if line.purchase_type == 'internal_po':
                line.expiration_date = False
                continue
            dates = [lot.expiration_date for lot in line.lot_ids if lot.expiration_date]
            if dates:
                line.expiration_date = dates[0]
            elif not line.expiration_date:
                line.expiration_date = False

    @api.onchange('expiration_date')
    def _onchange_expiration_date(self):
        if self.purchase_type == 'internal_po':
            return
        if self.expiration_date and self.lot_ids:
            for lot in self.lot_ids:
                lot.expiration_date = self.expiration_date

    @api.depends('lot_ids', 'lot_ids.expiration_date', 'expiration_date', 'purchase_type')
    def _compute_lot_expiry_display(self):
        for line in self:
            if line.purchase_type == 'internal_po':
                line.lot_expiry_display = False
                continue
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

    @api.onchange('lot_ids', 'product_qty', 'purchase_type')
    def _onchange_lot_ids_sync_pol_lots(self):
        """ Automatically synchronize pol_lot_ids and distribute product_qty evenly if newly assigned. """
        for line in self:
            if line.purchase_type == 'internal_po':
                continue
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
        if self.purchase_type == 'internal_po':
            raise UserError(_("Lot redistribution is not available for internal purchase orders."))
        if self.order_id.logistics_stage != 'expiry_check':
            raise UserError(_("Lot quantities can only be redistributed during the 'Expiry Check' stage (تدقيق تواريخ التلف)."))
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
        if self.purchase_type == 'internal_po':
            raise UserError(_("QR label generation is not available for internal purchase orders."))
        if not self.lot_ids:
            raise UserError(_("No Lot/Serial numbers assigned to this purchase order line."))
        return self.order_id.action_open_lot_qr_wizard()

    def _sync_pol_lot_ids_default(self):
        """ Helper to sync pol_lot_ids synchronously if changed in backend code """
        for line in self:
            if line.purchase_type == 'internal_po':
                continue
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
            if line.purchase_type == 'internal_po':
                continue
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

    def _check_expiry_check_stage_for_lots(self, vals):
        """
        Ensure lots and expiration dates can only be inserted, added, or modified
        during the 'Expiry Check' stage (تدقيق تواريخ التلف) for external purchase orders.
        """
        if self.env.context.get('skip_expiry_check_stage_guard'):
            return

        lot_fields = {'lot_ids', 'pol_lot_ids', 'expiration_date'}
        if not (lot_fields & set(vals.keys())):
            return

        for line in self:
            order = line.order_id
            if not order or order.purchase_type == 'internal_po':
                continue

            if order.logistics_stage != 'expiry_check':
                is_changed = False
                if 'lot_ids' in vals:
                    raw_val = vals['lot_ids']
                    new_ids = set()
                    if isinstance(raw_val, (list, tuple)):
                        for cmd in raw_val:
                            if isinstance(cmd, (list, tuple)):
                                if cmd[0] == 6:  # (6, 0, [ids])
                                    new_ids = set(cmd[2])
                                elif cmd[0] == 4:  # (4, id)
                                    new_ids.add(cmd[1])
                                elif cmd[0] == 5:  # (5, 0, 0)
                                    new_ids = set()
                                elif cmd[0] == 3:  # (3, id)
                                    new_ids = set(line.lot_ids.ids) - {cmd[1]}
                            elif isinstance(cmd, int):
                                new_ids.add(cmd)
                    elif raw_val:
                        new_ids = set(raw_val.ids if hasattr(raw_val, 'ids') else [raw_val])

                    current_ids = set(line.lot_ids.ids)
                    if new_ids != current_ids:
                        is_changed = True

                if 'pol_lot_ids' in vals and not is_changed:
                    is_changed = True

                if 'expiration_date' in vals and not is_changed:
                    new_exp = vals['expiration_date']
                    cur_exp = fields.Datetime.to_string(line.expiration_date) if line.expiration_date else False
                    if str(new_exp or False) != str(cur_exp or False):
                        is_changed = True

                if is_changed:
                    stage_name = dict(order._fields['logistics_stage'].selection).get(order.logistics_stage, order.logistics_stage)
                    raise UserError(_(
                        "⚠️ لا يمكن إدخال أو تعديل أرقام التشغيلات (Lots) وتواريخ الصلاحية إلا في مرحلة 'تدقيق تواريخ التلف (Expiry Check)'.\n\n"
                        "المرحلة الحالية لأمر الشراء %(order)s هي: [%(stage)s].\n"
                        "يرجى الانتقال إلى مرحلة 'تدقيق تواريخ التلف (Expiry Check)' لإضافة أو تعديل أرقام التشغيلات.\n\n"
                        "Lots and expiration dates can only be inserted, added, or modified during the 'Expiry Check' stage (تدقيق تواريخ التلف).\n"
                        "Current stage of PO %(order)s is: [%(stage)s]."
                    ) % {
                        'order': order.name,
                        'stage': stage_name,
                    })

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('skip_expiry_check_stage_guard'):
            for vals in vals_list:
                lot_fields = {'lot_ids', 'pol_lot_ids', 'expiration_date'}
                if lot_fields & set(vals.keys()):
                    order_id = vals.get('order_id')
                    if order_id:
                        order = self.env['purchase.order'].browse(order_id)
                        if order.exists() and order.purchase_type != 'internal_po' and order.logistics_stage != 'expiry_check':
                            has_lots = False
                            if vals.get('lot_ids'):
                                raw_val = vals['lot_ids']
                                if isinstance(raw_val, (list, tuple)):
                                    for cmd in raw_val:
                                        if isinstance(cmd, (list, tuple)) and cmd[0] in (4, 6) and (cmd[2] if cmd[0] == 6 else [cmd[1]]):
                                            has_lots = True
                                            break
                                elif raw_val:
                                    has_lots = True
                            if vals.get('pol_lot_ids') or vals.get('expiration_date'):
                                has_lots = True
                            if has_lots:
                                stage_name = dict(order._fields['logistics_stage'].selection).get(order.logistics_stage, order.logistics_stage)
                                raise UserError(_(
                                    "⚠️ لا يمكن إدخال أو تعديل أرقام التشغيلات (Lots) وتواريخ الصلاحية إلا في مرحلة 'تدقيق تواريخ التلف (Expiry Check)'.\n\n"
                                    "المرحلة الحالية لأمر الشراء %(order)s هي: [%(stage)s].\n"
                                    "يرجى الانتقال إلى مرحلة 'تدقيق تواريخ التلف (Expiry Check)' لإضافة أو تعديل أرقام التشغيلات.\n\n"
                                    "Lots and expiration dates can only be inserted, added, or modified during the 'Expiry Check' stage (تدقيق تواريخ التلف).\n"
                                    "Current stage of PO %(order)s is: [%(stage)s]."
                                ) % {
                                    'order': order.name,
                                    'stage': stage_name,
                                })
        return super(PurchaseOrderLine, self).create(vals_list)

    def write(self, vals):
        external_lines = self.filtered(lambda line: line.purchase_type != 'internal_po')
        if external_lines:
            external_lines._check_expiry_check_stage_for_lots(vals)
            external_lines._check_modification_safety(vals)
        res = super(PurchaseOrderLine, self).write(vals)
        external_lines = self.filtered(lambda line: line.purchase_type != 'internal_po')
        sync_needed_fields = {'expiration_date', 'lot_ids', 'product_qty', 'pol_lot_ids'}
        if external_lines and (sync_needed_fields & set(vals.keys())):
            for line in external_lines:
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
            if line.order_id and line.order_id.purchase_type == 'internal_po':
                continue
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
            if line.purchase_type == 'internal_po':
                continue
            draft_bill_lines = line.invoice_lines.filtered(lambda l: l.move_id.state == 'draft')
            if draft_bill_lines:
                draft_bill_lines.write({'lot_ids': [(6, 0, line.lot_ids.ids)]})

    def _update_stock_move_lots(self):
        """ Update stock.move and stock.move.line for stock pickings linked to this line,
            ensuring Done quantity starts at 0.0 to await QR scan fulfillment. """
        for line in self:
            if line.purchase_type == 'internal_po':
                continue
            if not line.move_ids:
                continue
            for move in line.move_ids.filtered(lambda m: m.state not in ('done', 'cancel') and m.picking_id.picking_type_code == 'incoming'):
                move.picked = False
                uom = getattr(move, 'product_uom', False) or getattr(move, 'product_uom_id', False)
                if not line.lot_ids:
                    move.lot_ids = [(5, 0, 0)]
                    move.move_line_ids.unlink()
                    self.env['stock.move.line'].create({
                        'move_id': move.id,
                        'picking_id': move.picking_id.id if move.picking_id else False,
                        'product_id': move.product_id.id,
                        'product_uom_id': uom.id if uom else False,
                        'location_id': move.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                        'quantity': 0.0,
                        'picked': False,
                    })
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
                                'product_uom_id': uom.id if uom else False,
                                'location_id': move.location_id.id,
                                'location_dest_id': move.location_dest_id.id,
                                'lot_id': pol_lot.lot_id.id,
                                'quantity': 0.0,
                                'picked': False,
                            })
                        if move_lines_vals:
                            self.env['stock.move.line'].create(move_lines_vals)
                    else:
                        move_lines_vals = [{
                            'move_id': move.id,
                            'picking_id': move.picking_id.id if move.picking_id else False,
                            'product_id': move.product_id.id,
                            'product_uom_id': uom.id if uom else False,
                            'location_id': move.location_id.id,
                            'location_dest_id': move.location_dest_id.id,
                            'lot_id': lot.id,
                            'quantity': 0.0,
                            'picked': False,
                        } for lot in line.lot_ids]
                        if move_lines_vals:
                            self.env['stock.move.line'].create(move_lines_vals)
                move.invalidate_recordset(['quantity'])

    def _prepare_stock_moves(self, picking):
        return super(PurchaseOrderLine, self)._prepare_stock_moves(picking)

    def _create_stock_moves(self, picking):
        moves = super(PurchaseOrderLine, self)._create_stock_moves(picking)
        self._update_stock_move_lots()
        return moves

    def _prepare_account_move_line(self, move=False):
        if self.order_id and self.order_id.purchase_type == 'internal_po':
            return super(PurchaseOrderLine, self)._prepare_account_move_line(move=move)
        res = super(PurchaseOrderLine, self)._prepare_account_move_line(move=move)
        if self.lot_ids:
            res['lot_ids'] = [(6, 0, self.lot_ids.ids)]
        return res
