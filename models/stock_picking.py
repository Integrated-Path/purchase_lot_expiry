# -*- coding: utf-8 -*-
import json
import re
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    qr_scan_input = fields.Char(
        string='Scan QR / Barcode',
        help='Scan a Lot/Product QR code here to immediately match and fulfill receiving.'
    )
    qr_scan_status = fields.Char(
        string='Last Scan Status',
        readonly=True,
        copy=False
    )

    def action_open_purchase_lot_qr_wizard(self):
        """ Open QR Label generation wizard pre-filled with lots from this purchase receipt """
        self.ensure_one()
        wizard_lines = []
        # First gather from stock.move.lines
        for ml in self.move_line_ids.filtered(lambda l: l.lot_id or l.lot_name):
            wizard_lines.append((0, 0, {
                'product_id': ml.product_id.id,
                'lot_id': ml.lot_id.id if ml.lot_id else False,
                'lot_name': ml.lot_id.name if ml.lot_id else ml.lot_name,
                'expiration_date': ml.lot_id.expiration_date if ml.lot_id else False,
                'quantity': ml.quantity if ml.quantity > 0 else ml.move_id.product_uom_qty,
                'copies': 1,
                'is_selected': True,
            }))

        # If move lines had no lots, check moves lot_ids
        if not wizard_lines:
            for move in self.move_ids.filtered(lambda m: m.lot_ids):
                nb = len(move.lot_ids)
                qty = move.product_uom_qty / nb if nb > 0 else 1.0
                for lot in move.lot_ids:
                    wizard_lines.append((0, 0, {
                        'product_id': move.product_id.id,
                        'lot_id': lot.id,
                        'lot_name': lot.name,
                        'expiration_date': lot.expiration_date,
                        'quantity': qty,
                        'copies': 1,
                        'is_selected': True,
                    }))

        if not wizard_lines:
            raise UserError(_("No Lot/Serial numbers found on this receipt to generate labels."))

        wizard = self.env['purchase.lot.qr.wizard'].create({
            'picking_id': self.id,
            'line_ids': wizard_lines,
        })
        return {
            'name': _('Print Lot/Serial QR Labels'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.lot.qr.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_lot_qr_wizard(self):
        self.ensure_one()
        if self.picking_type_code == 'incoming' or not hasattr(super(), 'action_open_lot_qr_wizard'):
            return self.action_open_purchase_lot_qr_wizard()
        return super().action_open_lot_qr_wizard()

    def action_open_receipt_qr_scan_wizard(self):
        """ Open dedicated warehouse receipt kiosk scanner wizard """
        self.ensure_one()
        if self.state in ('done', 'cancel'):
            raise UserError(_("This transfer is already in state '%s' and cannot be processed.") % self.state)

        wizard = self.env['stock.picking.qr.scan.wizard'].create({
            'picking_id': self.id,
        })
        wizard._populate_lines()
        return {
            'name': _('Warehouse QR Receiving Scanner'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking.qr.scan.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_qr_scan_wizard(self):
        self.ensure_one()
        if self.picking_type_code == 'incoming' or not hasattr(super(), 'action_open_qr_scan_wizard'):
            return self.action_open_receipt_qr_scan_wizard()
        return super().action_open_qr_scan_wizard()

    def action_process_qr_scan(self):
        """ Process scan from inline picking form view input """
        self.ensure_one()
        if not self.qr_scan_input:
            return

        payload = self.qr_scan_input.strip()
        self.qr_scan_input = False
        res = self._process_qr_payload(payload)
        return res

    def _parse_qr_payload(self, raw_string):
        """
        Parse QR payload supporting:
        1. JSON: {"barcode": "...", "lot": "...", "exp": "YYYY-MM-DD", "qty": 1.0}
        2. Delimited: PROD:code|LOT:lotname|EXP:YYYY-MM-DD|QTY:1.0
        3. GS1-128: (01)gtin(10)lot(17)YYMMDD or 01...10...17...
        4. Fallback: Plain lot name or product barcode
        """
        data = {
            'product_barcode': None,
            'product_code': None,
            'product_id': None,
            'lot_name': None,
            'expiration_date': None,
            'quantity': 1.0,
        }

        # 1. JSON
        if raw_string.startswith('{') and raw_string.endswith('}'):
            try:
                parsed = json.loads(raw_string)
                data['product_barcode'] = parsed.get('b') or parsed.get('barcode')
                data['product_code'] = parsed.get('c') or parsed.get('code')
                data['product_id'] = parsed.get('pid') or parsed.get('product_id')
                data['lot_name'] = parsed.get('l') or parsed.get('lot') or parsed.get('lot_name')
                data['expiration_date'] = parsed.get('e') or parsed.get('exp') or parsed.get('expiration_date')
                if 'q' in parsed or 'qty' in parsed or 'quantity' in parsed:
                    data['quantity'] = float(parsed.get('q') or parsed.get('qty') or parsed.get('quantity') or 1.0)
                return data
            except Exception:
                pass

        # 2. Delimited string: PROD:...|LOT:...|EXP:...|QTY:...
        if '|' in raw_string or ':' in raw_string:
            parts = raw_string.split('|')
            has_keys = False
            for part in parts:
                if ':' in part:
                    k, v = part.split(':', 1)
                    k = k.strip().upper()
                    v = v.strip()
                    if k in ('PROD', 'PRODUCT', 'BC', 'BARCODE'):
                        data['product_barcode'] = v
                        has_keys = True
                    elif k in ('LOT', 'SERIAL', 'SN'):
                        data['lot_name'] = v
                        has_keys = True
                    elif k in ('EXP', 'EXPIRY', 'DATE'):
                        data['expiration_date'] = v
                        has_keys = True
                    elif k in ('QTY', 'QUANTITY'):
                        try:
                            data['quantity'] = float(v)
                        except ValueError:
                            data['quantity'] = 1.0
                        has_keys = True
            if has_keys:
                return data

        # 3. GS1-128 format with parentheses: (01)GTIN(10)LOT(17)YYMMDD
        gs1_match = re.search(r'\(01\)(\d{14})', raw_string)
        if gs1_match:
            data['product_barcode'] = gs1_match.group(1).lstrip('0')
            lot_match = re.search(r'\(10\)([^()]+)', raw_string)
            if lot_match:
                data['lot_name'] = lot_match.group(1)
            exp_match = re.search(r'\(17\)(\d{6})', raw_string)
            if exp_match:
                yymmdd = exp_match.group(1)
                try:
                    data['expiration_date'] = datetime.strptime(yymmdd, '%y%m%d').strftime('%Y-%m-%d')
                except ValueError:
                    pass
            return data

        # 4. Fallback: treat raw string as lot name
        data['lot_name'] = raw_string
        return data

    def _process_receipt_qr_payload(self, raw_string):
        """ Resolves parsed QR payload and updates picking move lines """
        self.ensure_one()
        if self.state in ('done', 'cancel'):
            raise UserError(_("Receipt '%s' is in state '%s' and cannot be modified.") % (self.name, self.state))

        data = self._parse_qr_payload(raw_string)
        lot_name = data.get('lot_name')
        product_barcode = data.get('product_barcode')
        product_code = data.get('product_code')
        product_id = data.get('product_id')
        exp_date_str = data.get('expiration_date')
        qty_to_add = data.get('quantity') or 1.0

        # Find matching stock move on this picking
        open_moves = self.move_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
        matched_move = None

        # 1. Match by product_id
        if product_id:
            matched_move = open_moves.filtered(lambda m: m.product_id.id == product_id)

        # 2. Match by barcode
        if not matched_move and product_barcode:
            matched_move = open_moves.filtered(lambda m: m.product_id.barcode == product_barcode)

        # 3. Match by default_code
        if not matched_move and product_code:
            matched_move = open_moves.filtered(lambda m: m.product_id.default_code == product_code)

        # 4. Match by existing lot
        if not matched_move and lot_name:
            existing_lots = self.env['stock.lot'].search([
                ('name', '=', lot_name),
                ('product_id', 'in', open_moves.mapped('product_id').ids)
            ])
            if existing_lots:
                matched_move = open_moves.filtered(lambda m: m.product_id == existing_lots[0].product_id)

        # If only 1 move in picking and lot_name is provided, match that single move
        if not matched_move and len(open_moves) == 1:
            matched_move = open_moves[0]

        if not matched_move:
            msg = _("No matching move found on receipt %(receipt)s for scanned payload: %(payload)s") % {
                'receipt': self.name,
                'payload': raw_string,
            }
            self.qr_scan_status = msg
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Scan Mismatch'),
                    'message': msg,
                    'type': 'warning',
                    'sticky': False,
                }
            }

        matched_move = matched_move[0]
        product = matched_move.product_id

        # Find or match stock.lot
        lot = False
        if lot_name:
            # First check if the move already has this lot assigned
            existing_move_lots = (matched_move.lot_ids | matched_move.move_line_ids.lot_id).filtered(
                lambda l: l.name == lot_name
            )
            if existing_move_lots:
                lot = existing_move_lots[0]
            else:
                domain = [
                    ('name', '=', lot_name),
                    ('product_id', '=', product.id),
                ]
                if self.company_id:
                    domain.extend(['|', ('company_id', '=', False), ('company_id', '=', self.company_id.id)])
                lot = self.env['stock.lot'].search(domain, limit=1)

            if not lot:
                lot_vals = {
                    'name': lot_name,
                    'product_id': product.id,
                }
                if self.company_id:
                    lot_vals['company_id'] = self.company_id.id
                if exp_date_str:
                    try:
                        lot_vals['expiration_date'] = fields.Datetime.to_datetime(exp_date_str)
                    except Exception:
                        pass
                lot = self.env['stock.lot'].create(lot_vals)
            elif exp_date_str and not lot.expiration_date:
                try:
                    lot.expiration_date = fields.Datetime.to_datetime(exp_date_str)
                except Exception:
                    pass

        # Update or create stock.move.line
        move_line = False
        if lot:
            move_line = matched_move.move_line_ids.filtered(lambda ml: ml.lot_id == lot)
            if not move_line:
                # Check for an empty lot move line to claim
                empty_ml = matched_move.move_line_ids.filtered(lambda ml: not ml.lot_id and ml.quantity == 0)
                if empty_ml:
                    move_line = empty_ml[0]
                    move_line.write({'lot_id': lot.id, 'quantity': qty_to_add})
                else:
                    move_line = self.env['stock.move.line'].create({
                        'move_id': matched_move.id,
                        'picking_id': self.id,
                        'product_id': product.id,
                        'product_uom_id': matched_move.product_uom.id,
                        'location_id': matched_move.location_id.id,
                        'location_dest_id': matched_move.location_dest_id.id,
                        'lot_id': lot.id,
                        'quantity': qty_to_add,
                    })
            else:
                move_line = move_line[0]
                if move_line.quantity == 0:
                    move_line.quantity = qty_to_add
                elif qty_to_add > 1.0 and move_line.quantity == qty_to_add:
                    pass
                else:
                    move_line.quantity += qty_to_add
        else:
            # Non-lot product scan or unassigned lot
            if matched_move.move_line_ids:
                move_line = matched_move.move_line_ids[0]
                move_line.quantity += qty_to_add
            else:
                move_line = self.env['stock.move.line'].create({
                    'move_id': matched_move.id,
                    'picking_id': self.id,
                    'product_id': product.id,
                    'product_uom_id': matched_move.product_uom.id,
                    'location_id': matched_move.location_id.id,
                    'location_dest_id': matched_move.location_dest_id.id,
                    'quantity': qty_to_add,
                })

        # Update move lot_ids if needed
        if lot and lot not in matched_move.lot_ids:
            matched_move.lot_ids = [(4, lot.id)]

        status_msg = _("✓ Scanned %(product)s | Lot: %(lot)s | Qty: +%(qty)s (Done: %(done)s / %(demand)s)") % {
            'product': product.display_name,
            'lot': lot.name if lot else _('N/A'),
            'qty': qty_to_add,
            'done': matched_move.quantity,
            'demand': matched_move.product_uom_qty,
        }
        self.qr_scan_status = status_msg

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Scan Successful'),
                'message': status_msg,
                'type': 'success',
                'sticky': False,
            }
        }

    def _process_qr_payload(self, raw_string):
        self.ensure_one()
        if self.picking_type_code == 'incoming' or not hasattr(super(), '_process_qr_payload'):
            return self._process_receipt_qr_payload(raw_string)
        return super()._process_qr_payload(raw_string)
