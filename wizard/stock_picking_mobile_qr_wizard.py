# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


class StockPickingMobileQrWizard(models.TransientModel):
    _name = 'stock.picking.mobile.qr.wizard'
    _description = 'Mobile Camera QR Scanner Wizard for Receipts'

    picking_id = fields.Many2one(
        'stock.picking',
        string='Stock Transfer',
        required=True,
        readonly=True,
        ondelete='cascade'
    )
    picking_name = fields.Char(related='picking_id.name', readonly=True)
    partner_id = fields.Many2one(related='picking_id.partner_id', readonly=True)
    picking_type_code = fields.Selection(related='picking_id.picking_type_code', readonly=True)

    last_scan_message = fields.Char(
        string='Last Scan Message',
        readonly=True,
        default='Ready to scan box labels.'
    )
    last_scan_status = fields.Selection([
        ('info', 'Info'),
        ('success', 'Success'),
        ('danger', 'Error'),
    ], default='info', readonly=True)

    scan_log = fields.Text(
        string='Scan Activity Log',
        readonly=True
    )

    total_demand = fields.Float(string='Total Demand', compute='_compute_progress')
    total_done = fields.Float(string='Total Done', compute='_compute_progress')
    is_all_fulfilled = fields.Boolean(string='Fully Received', compute='_compute_progress')

    line_ids = fields.One2many(
        'stock.picking.mobile.qr.wizard.line',
        'wizard_id',
        string='Receipt Lines',
        compute='_compute_lines',
        store=False
    )

    @api.depends('picking_id.move_ids.quantity', 'picking_id.move_ids.product_uom_qty')
    def _compute_progress(self):
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for wizard in self:
            moves = wizard.picking_id.move_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
            tot_demand = sum(m.product_uom_qty for m in moves)
            tot_done = sum(m.quantity for m in moves)
            wizard.total_demand = tot_demand
            wizard.total_done = tot_done
            wizard.is_all_fulfilled = bool(moves) and all(
                float_compare(m.quantity, m.product_uom_qty, precision_digits=precision) >= 0
                for m in moves
            )

    def _compute_lines(self):
        for wizard in self:
            lines = []
            for move in wizard.picking_id.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                lots_str = ", ".join(filter(None, move.move_line_ids.mapped('lot_id.name')))
                lines.append((0, 0, {
                    'wizard_id': wizard.id,
                    'product_id': move.product_id.id,
                    'demand_qty': move.product_uom_qty,
                    'done_qty': move.quantity,
                    'lot_names_display': lots_str,
                }))
            wizard.line_ids = lines

    def process_mobile_qr_scan(self, raw_payload):
        """
        Invoked asynchronously by the OWL camera widget upon every successful scan.
        Format: PRODUCT_REF|LOT_NUMBER|BOX_QTY
        """
        self.ensure_one()
        if not raw_payload:
            return {'success': False, 'message': _("Empty QR scan received.")}

        raw_str = raw_payload.strip()
        parts = [p.strip() for p in raw_str.split('|')]

        if len(parts) < 3:
            msg = _("Invalid QR format '%(code)s'. Expected: PRODUCT_REF|LOT_NUMBER|BOX_QTY") % {'code': raw_str}
            self._append_log(msg, 'danger')
            return {'success': False, 'message': msg}

        product_ref = parts[0]
        lot_number = parts[1]
        qty_str = parts[2]

        try:
            box_qty = float(qty_str)
            if box_qty <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            msg = _("Invalid box quantity '%(qty)s'. Must be a positive number.") % {'qty': qty_str}
            self._append_log(msg, 'danger')
            return {'success': False, 'message': msg}

        # 1. Search product.product by default_code or barcode
        product = self.env['product.product'].search([
            '|',
            ('default_code', '=', product_ref),
            ('barcode', '=', product_ref)
        ], limit=1)

        if not product:
            msg = _("Product reference '%(ref)s' not found in system.") % {'ref': product_ref}
            self._append_log(msg, 'danger')
            return {'success': False, 'message': msg}

        # 2. Search stock.lot matching lot_number and picking company. Create if missing (Receipt)
        company = self.picking_id.company_id or self.env.company
        lot = self.env['stock.lot'].search([
            ('name', '=', lot_number),
            ('product_id', '=', product.id),
            '|', ('company_id', '=', False), ('company_id', '=', company.id)
        ], limit=1)

        if not lot:
            lot = self.env['stock.lot'].create({
                'name': lot_number,
                'product_id': product.id,
                'company_id': company.id,
            })

        # 3. Find matching stock.move inside active picking
        open_moves = self.picking_id.move_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
        matched_move = open_moves.filtered(lambda m: m.product_id == product)

        if not matched_move:
            msg = _("Product '%(product)s' [%(code)s] is not part of receipt %(picking)s.") % {
                'product': product.display_name,
                'code': product_ref,
                'picking': self.picking_id.name,
            }
            self._append_log(msg, 'danger')
            return {'success': False, 'message': msg}

        matched_move = matched_move[0]

        # 4. Add scanned QTY to corresponding stock.move.line
        move_line = matched_move.move_line_ids.filtered(lambda ml: ml.lot_id == lot)
        if not move_line:
            empty_ml = matched_move.move_line_ids.filtered(lambda ml: not ml.lot_id and ml.quantity == 0)
            if empty_ml:
                move_line = empty_ml[0]
                move_line.write({
                    'lot_id': lot.id,
                    'quantity': box_qty,
                    'location_dest_id': matched_move.location_dest_id.id,
                })
            else:
                move_line = self.env['stock.move.line'].create({
                    'move_id': matched_move.id,
                    'picking_id': self.picking_id.id,
                    'product_id': product.id,
                    'product_uom_id': (matched_move.product_uom_id or getattr(matched_move, 'product_uom', False)).id,
                    'location_id': matched_move.location_id.id,
                    'location_dest_id': matched_move.location_dest_id.id,
                    'lot_id': lot.id,
                    'quantity': box_qty,
                })
        else:
            move_line = move_line[0]
            move_line.quantity += box_qty

        success_msg = _("✓ Added %(qty)s units of '%(product)s' (Lot: %(lot)s) [Done: %(done)s / %(demand)s]") % {
            'qty': box_qty,
            'product': product.display_name,
            'lot': lot.name,
            'done': matched_move.quantity,
            'demand': matched_move.product_uom_qty,
        }
        self._append_log(success_msg, 'success')

        return {
            'success': True,
            'message': success_msg,
            'product_name': product.display_name,
            'lot_name': lot.name,
            'added_qty': box_qty,
            'total_done': matched_move.quantity,
            'total_demand': matched_move.product_uom_qty,
        }

    def _append_log(self, message, status_type):
        now_str = fields.Datetime.now().strftime('%H:%M:%S')
        new_entry = f"[{now_str}] {message}"
        lines = (self.scan_log or "").splitlines()
        lines.insert(0, new_entry)
        self.write({
            'last_scan_message': message,
            'last_scan_status': status_type,
            'scan_log': "\n".join(lines[:25]),
        })

    def action_validate_transfer(self):
        """ Directly validate picking from mobile wizard """
        self.ensure_one()
        return self.picking_id.button_validate()


class StockPickingMobileQrWizardLine(models.TransientModel):
    _name = 'stock.picking.mobile.qr.wizard.line'
    _description = 'Mobile QR Wizard Line'

    wizard_id = fields.Many2one('stock.picking.mobile.qr.wizard', ondelete='cascade')
    product_id = fields.Many2one('product.product', readonly=True)
    lot_names_display = fields.Char(string='Lots', readonly=True)
    demand_qty = fields.Float(string='Demand', readonly=True)
    done_qty = fields.Float(string='Done', readonly=True)
    is_fulfilled = fields.Boolean(compute='_compute_fulfilled')

    @api.depends('demand_qty', 'done_qty')
    def _compute_fulfilled(self):
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for line in self:
            line.is_fulfilled = float_compare(line.done_qty, line.demand_qty, precision_digits=precision) >= 0
