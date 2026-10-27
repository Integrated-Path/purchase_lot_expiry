# -*- coding: utf-8 -*-
import json
import re
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


from .purchase_order import LOGISTICS_STAGES

# Mapping of Arabic keyboard layout (Windows/Linux Arabic 101/102) to English QWERTY
AR_TO_EN_KEYBOARD_MAP = {
    # Lowercase / unshifted
    'ذ': '`', 'ض': 'q', 'ص': 'w', 'ث': 'e', 'ق': 'r', 'ف': 't', 'غ': 'y', 'ع': 'u',
    'ه': 'i', 'خ': 'o', 'ح': 'p', 'ج': '[', 'د': ']', 'ش': 'a', 'س': 's', 'ي': 'd',
    'ب': 'f', 'ل': 'g', 'ا': 'h', 'ت': 'j', 'ن': 'k', 'م': 'l', 'ك': ';', 'ط': "'",
    'ئ': 'z', 'ء': 'x', 'ؤ': 'c', 'ر': 'v', 'لا': 'b', 'ى': 'n', 'ة': 'm', 'و': ',',
    'ز': '.', 'ظ': '/',
    # Shifted
    'َ': 'Q', 'ً': 'W', 'ُ': 'E', 'ٌ': 'R', 'لإ': 'T', 'إ': 'Y', '‘': 'U', '÷': 'I',
    '×': 'O', '؛': 'P', '<': '{', '>': '}', 'ِ': 'A', 'ٍ': 'S', ']': 'D', '[': 'F',
    'لأ': 'G', 'أ': 'H', 'ـ': 'J', '،': 'K', '/': 'L', ':': ':', '"': '"', 'ْ': 'X',
    '}': 'C', '{': 'V', 'لآ': 'B', 'آ': 'N', "'": 'M', ',': '<', '.': '>', '؟': '?',
    # Arabic Ligatures
    '\uFEF5': 'B', '\uFEF6': 'B', '\uFEF7': 'G', '\uFEF8': 'G',
    '\uFEF9': 'T', '\uFEFA': 'T', '\uFEFB': 'b', '\uFEFC': 'b',
    # Arabic-Indic and Persian digits
    '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4', '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
    '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4', '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
}


def normalize_arabic_scanner_input(raw_string):
    """ Translates keystrokes typed by barcode scanner when active keyboard is Arabic """
    if not raw_string:
        return raw_string
    chars = []
    i = 0
    n = len(raw_string)
    while i < n:
        if i + 1 < n and raw_string[i:i+2] in AR_TO_EN_KEYBOARD_MAP:
            chars.append(AR_TO_EN_KEYBOARD_MAP[raw_string[i:i+2]])
            i += 2
        elif raw_string[i] in AR_TO_EN_KEYBOARD_MAP:
            chars.append(AR_TO_EN_KEYBOARD_MAP[raw_string[i]])
            i += 1
        else:
            chars.append(raw_string[i])
            i += 1
    return "".join(chars)


def normalize_date_str(date_str):
    """ Normalize date strings into standard YYYY-MM-DD """
    if not date_str:
        return None
    d_clean = str(date_str).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d', '%y%m%d', '%Y%m%d'):
        try:
            return datetime.strptime(d_clean, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return d_clean


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
    purchase_logistics_stage = fields.Selection(
        related='purchase_id.logistics_stage',
        string='مرحلة أمر الشراء / PO Logistics Stage',
        store=True,
        readonly=True
    )
    purchase_type = fields.Selection(
        related='purchase_id.purchase_type',
        string='Purchase Type',
        readonly=True
    )
    bill_logistics_stage = fields.Selection(
        LOGISTICS_STAGES,
        string='مرحلة الشحنة (الفاتورة) / Bill Logistics Stage',
        compute='_compute_bill_logistics_stage',
        store=True,
        readonly=True
    )
    is_receipt_locked_for_clearance = fields.Boolean(
        string='Receipt Locked until Clearance',
        compute='_compute_receipt_locked_for_clearance',
        store=True,
        help='Locks receiving and validation until vendor bill reaches clearance stage.'
    )
    is_internal_transfer = fields.Boolean(
        string='Is Internal Transfer',
        compute='_compute_is_internal_transfer',
        store=True
    )

    @api.depends('picking_type_code', 'picking_type_id.code')
    def _compute_is_internal_transfer(self):
        for picking in self:
            code = picking.picking_type_code or (picking.picking_type_id and picking.picking_type_id.code)
            picking.is_internal_transfer = (code == 'internal')

    @api.depends(
        'purchase_id.purchase_type',
        'purchase_id.invoice_ids.logistics_stage',
        'purchase_id.invoice_ids.state'
    )
    def _compute_bill_logistics_stage(self):
        valid_keys = set(dict(LOGISTICS_STAGES).keys())
        for picking in self:
            stage = False
            if picking.purchase_id and picking.purchase_id.purchase_type != 'internal_po':
                active_bills = picking.purchase_id.invoice_ids.filtered(
                    lambda m: m.move_type == 'in_invoice' and m.state != 'cancel' and m.logistics_stage
                )
                if active_bills and active_bills[0].logistics_stage in valid_keys:
                    stage = active_bills[0].logistics_stage
            picking.bill_logistics_stage = stage

    @api.depends(
        'bill_logistics_stage',
        'purchase_id.logistics_stage',
        'purchase_id.purchase_type',
        'picking_type_code'
    )
    def _compute_receipt_locked_for_clearance(self):
        for picking in self:
            if (
                picking.picking_type_code == 'incoming'
                and picking.purchase_id
                and picking.purchase_id.purchase_type != 'internal_po'
            ):
                is_unlocked = (
                    picking.bill_logistics_stage in ('clearance', 'received') or
                    picking.purchase_id.logistics_stage in ('clearance', 'received')
                )
                picking.is_receipt_locked_for_clearance = not is_unlocked
            else:
                picking.is_receipt_locked_for_clearance = False

    def _get_clearance_stage_label(self):
        self.ensure_one()
        if self.purchase_id and self.purchase_id.logistics_stage:
            return dict(self.purchase_id._fields['logistics_stage'].selection).get(self.purchase_id.logistics_stage) or self.purchase_id.logistics_stage
        if self.bill_logistics_stage:
            return dict(self._fields['bill_logistics_stage'].selection).get(self.bill_logistics_stage) or self.bill_logistics_stage
        return _("لم تبدأ مرحلة التخليص بأمر الشراء")

    def button_validate(self):
        for picking in self:
            if (
                picking.picking_type_code == 'incoming'
                and picking.purchase_id
                and picking.purchase_id.purchase_type != 'internal_po'
                and picking.is_receipt_locked_for_clearance
            ):
                stage_label = picking._get_clearance_stage_label()
                raise UserError(_(
                    "⚠️ لا يمكن استلام هذه الشحنة حالياً في المخازن.\n\n"
                    "مرحلة الشحنة: [%s].\n"
                    "الشحنة للعرض والمتابعة فقط، والاستلام المخزني متاح فقط عندما يصل أمر الشراء إلى مرحلة 'بدء التخليص (Clearance)'."
                ) % stage_label)

        res = super(StockPicking, self).button_validate()

        for picking in self:
            if (
                picking.state == 'done'
                and picking.picking_type_code == 'incoming'
                and picking.purchase_id
                and picking.purchase_id.purchase_type != 'internal_po'
            ):
                po = picking.purchase_id
                incoming_picks = po.picking_ids.filtered(lambda x: x.picking_type_code == 'incoming')
                if all(p.state in ('done', 'cancel') for p in incoming_picks):
                    po.logistics_stage = 'received'
                    po.message_post(body=_(
                        "تم استلام الشحنة في المخازن بنجاح بواسطة الإذن: <b>%s</b>، واكتملت مرحلة <b>الاستلام المخزني (Received)</b> تلقائياً."
                    ) % picking.name)
            elif picking.purchase_id.purchase_type == 'internal_po':
                if picking.purchase_id and picking.location_dest_id.usage == 'supplier':
                    purchase = picking.purchase_id
                    
                    invoices_to_cancel = purchase.invoice_ids.filtered(lambda inv: inv.state != 'cancel')
                    if invoices_to_cancel:
                        invoices_to_cancel.button_cancel()

                    if purchase.state in ('purchase', 'done'):
                        purchase.button_unlock()
                    purchase.write({'state': 'draft'})
        return res

    def action_open_purchase_lot_qr_wizard(self):
        """ Open QR Label generation wizard pre-filled with lots from this transfer """
        self.ensure_one()
        if self.is_internal_transfer or self.picking_type_code == 'internal' or (self.purchase_id and self.purchase_id.purchase_type == 'internal_po'):
            raise UserError(_("QR label generation is not available for internal operations."))
        wizard_lines = []
        # First gather from stock.move.lines
        for ml in self.move_line_ids.filtered(lambda l: l.lot_id or l.lot_name):
            target_qty = ml.quantity if ml.quantity > 0 else ml.move_id.product_uom_qty
            copies = int(target_qty) if target_qty >= 1.0 else 1
            wizard_lines.append((0, 0, {
                'product_id': ml.product_id.id,
                'lot_id': ml.lot_id.id if ml.lot_id else False,
                'lot_name': ml.lot_id.name if ml.lot_id else ml.lot_name,
                'expiration_date': ml.lot_id.expiration_date if ml.lot_id else False,
                'quantity': 1.0,
                'copies': copies,
                'is_selected': True,
            }))

        # If move lines had no lots, check moves lot_ids
        if not wizard_lines:
            for move in self.move_ids.filtered(lambda m: m.lot_ids):
                nb = len(move.lot_ids)
                qty = move.product_uom_qty / nb if nb > 0 else 1.0
                copies = int(qty) if qty >= 1.0 else 1
                for lot in move.lot_ids:
                    wizard_lines.append((0, 0, {
                        'product_id': move.product_id.id,
                        'lot_id': lot.id,
                        'lot_name': lot.name,
                        'expiration_date': lot.expiration_date,
                        'quantity': 1.0,
                        'copies': copies,
                        'is_selected': True,
                    }))

        if not wizard_lines:
            raise UserError(_("No Lot/Serial numbers found on this transfer to generate labels."))

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
        if self.is_internal_transfer or self.picking_type_code == 'internal' or (self.purchase_id and self.purchase_id.purchase_type == 'internal_po'):
            parent_action = getattr(super(), 'action_open_lot_qr_wizard', None)
            if parent_action:
                return parent_action()
            raise UserError(_("QR label generation is not available for internal operations."))
        return self.action_open_purchase_lot_qr_wizard()

    def _ensure_picking_quantities_zero_for_scan(self):
        """ Ensure picking has Done quantities at 0 so scanning fills the transfer. """
        for picking in self:
            if picking.state not in ('done', 'cancel'):
                if (
                    picking.is_internal_transfer
                    or picking.picking_type_code == 'internal'
                    or (picking.purchase_id and picking.purchase_id.purchase_type == 'internal_po')
                ):
                    continue
                if (
                    picking.picking_type_code == 'incoming'
                    and picking.purchase_id
                    and picking.purchase_id.purchase_type != 'internal_po'
                ):
                    has_partial_scans = any(0 < ml.quantity < ml.move_id.product_uom_qty for ml in picking.move_line_ids)
                    if not has_partial_scans and all(ml.quantity == ml.move_id.product_uom_qty for ml in picking.move_line_ids if ml.move_id.product_uom_qty > 0):
                        picking.purchase_id._init_incoming_receipt_quantities()
                elif picking.picking_type_code == 'outgoing':
                    has_partial_scans = any(0 < ml.quantity < ml.move_id.product_uom_qty for ml in picking.move_line_ids)
                    if not has_partial_scans and all(ml.quantity == ml.move_id.product_uom_qty for ml in picking.move_line_ids if ml.move_id.product_uom_qty > 0):
                        for ml in picking.move_line_ids:
                            ml.quantity = 0.0
                            ml.picked = False
                        for move in picking.move_ids:
                            move.picked = False
                            move.invalidate_recordset(['quantity'])

    def _ensure_receipt_quantities_zero_for_scan(self):
        return self._ensure_picking_quantities_zero_for_scan()

    def action_open_picking_qr_scan_wizard(self):
        """ Open dedicated warehouse kiosk scanner wizard for any picking """
        self.ensure_one()
        if self.is_internal_transfer or self.picking_type_code == 'internal' or (self.purchase_id and self.purchase_id.purchase_type == 'internal_po'):
            raise UserError(_("Custom QR scanning is not available for internal operations."))
        if self.state in ('done', 'cancel'):
            raise UserError(_("This transfer is already in state '%s' and cannot be processed.") % self.state)
        if self.picking_type_code == 'incoming' and self.is_receipt_locked_for_clearance:
            stage_label = self._get_clearance_stage_label()
            raise UserError(_("⚠️ لا يمكن فتح نافذة مسح الاستلام حالياً.\nالشحنة في مرحلة: [%s].\nالاستلام متاح فقط بعد وصول فاتورة المورد إلى مرحلة 'بدء التخليص (Clearance)'.") % stage_label)

        self._ensure_picking_quantities_zero_for_scan()
        wizard = self.env['stock.picking.qr.scan.wizard'].create({
            'picking_id': self.id,
        })
        wizard._populate_lines()
        return {
            'name': _('Warehouse QR Inventory Scanner'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking.qr.scan.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_receipt_qr_scan_wizard(self):
        return self.action_open_picking_qr_scan_wizard()

    def action_open_qr_scan_wizard(self):
        self.ensure_one()
        if self.is_internal_transfer or self.picking_type_code == 'internal' or (self.purchase_id and self.purchase_id.purchase_type == 'internal_po'):
            parent_action = getattr(super(), 'action_open_qr_scan_wizard', None)
            if parent_action:
                return parent_action()
            raise UserError(_("Custom QR scanning is not available for internal operations."))
        return self.action_open_picking_qr_scan_wizard()

    def action_process_qr_scan(self):
        """ Process scan from inline picking form view input """
        self.ensure_one()
        if self.is_internal_transfer or self.picking_type_code == 'internal' or (self.purchase_id and self.purchase_id.purchase_type == 'internal_po'):
            raise UserError(_("Custom QR scanning is not available for internal operations."))
        if not self.qr_scan_input:
            return

        payload = self.qr_scan_input.strip()
        self.qr_scan_input = False
        res = self._process_picking_qr_payload(payload)
        return res

    def _parse_qr_payload(self, raw_string):
        """
        Parse QR payload supporting:
        1. JSON: {"barcode": "...", "lot": "...", "exp": "YYYY-MM-DD"}
        2. Delimited: PROD:code|LOT:lotname|EXP:YYYY-MM-DD
           or Positional Delimited: PROD|LOT
        3. GS1-128: (01)gtin(10)lot(17)YYMMDD
        4. Fallback: Plain lot name or product barcode
        Note: Every valid scan increments exactly 1.0 unit.
        Automatically converts Arabic keyboard layout keystrokes.
        """
        data = {
            'product_barcode': None,
            'product_code': None,
            'product_id': None,
            'lot_name': None,
            'expiration_date': None,
            'quantity': 1.0,
        }

        # Auto-convert Arabic keyboard layout
        clean_str = normalize_arabic_scanner_input(raw_string.strip())

        # 1. JSON
        if clean_str.startswith('{') and clean_str.endswith('}'):
            try:
                parsed = json.loads(clean_str)
                data['product_barcode'] = parsed.get('b') or parsed.get('barcode')
                data['product_code'] = parsed.get('c') or parsed.get('code')
                data['product_id'] = parsed.get('pid') or parsed.get('product_id')
                data['lot_name'] = parsed.get('l') or parsed.get('lot') or parsed.get('lot_name')
                exp = parsed.get('e') or parsed.get('exp') or parsed.get('expiration_date')
                data['expiration_date'] = normalize_date_str(exp)
                data['quantity'] = 1.0
                return data
            except Exception:
                pass

        # 2. Delimited string: PROD:...|LOT:...|EXP:... or Positional: CODE|LOT
        if '|' in clean_str or ':' in clean_str:
            parts = clean_str.split('|')
            has_keys = False
            for part in parts:
                if ':' in part:
                    k, v = part.split(':', 1)
                    k = k.strip().upper()
                    v = v.strip()
                    if k in ('PROD', 'PRODUCT', 'BC', 'BARCODE'):
                        data['product_barcode'] = v
                        has_keys = True
                    elif k in ('CODE', 'REF', 'DEFAULT_CODE', 'PART_NUMBER'):
                        data['product_code'] = v
                        has_keys = True
                    elif k in ('LOT', 'SERIAL', 'SN'):
                        data['lot_name'] = v
                        has_keys = True
                    elif k in ('EXP', 'EXPIRY', 'DATE'):
                        data['expiration_date'] = normalize_date_str(v)
                        has_keys = True
                    elif k in ('QTY', 'QUANTITY'):
                        has_keys = True  # Recognized, but quantity is strictly fixed to 1.0
            if has_keys:
                data['quantity'] = 1.0
                return data
            elif len(parts) >= 2:
                # Positional format: PROD_CODE|LOT_NAME
                data['product_code'] = parts[0].strip()
                data['lot_name'] = parts[1].strip()
                data['quantity'] = 1.0
                return data

        # 3. GS1-128 format with parentheses: (01)GTIN(10)LOT(17)YYMMDD
        gs1_match = re.search(r'\(01\)(\d{14})', clean_str)
        if gs1_match:
            data['product_barcode'] = gs1_match.group(1).lstrip('0')
            lot_match = re.search(r'\(10\)([^()]+)', clean_str)
            if lot_match:
                data['lot_name'] = lot_match.group(1)
            exp_match = re.search(r'\(17\)(\d{6})', clean_str)
            if exp_match:
                yymmdd = exp_match.group(1)
                data['expiration_date'] = normalize_date_str(yymmdd)
            data['quantity'] = 1.0
            return data

        # 4. Fallback: treat raw string as lot name
        data['lot_name'] = clean_str
        data['quantity'] = 1.0
        return data

    def _process_picking_qr_payload(self, raw_string):
        """ Resolves parsed QR payload and updates picking move lines by exactly +1 unit """
        self.ensure_one()
        if self.is_internal_transfer or self.picking_type_code == 'internal' or (self.purchase_id and self.purchase_id.purchase_type == 'internal_po'):
            raise UserError(_("Custom QR scanning is not available for internal operations."))
        if self.state in ('done', 'cancel'):
            raise UserError(_("Transfer '%s' is in state '%s' and cannot be modified.") % (self.name, self.state))
        if self.picking_type_code == 'incoming' and self.is_receipt_locked_for_clearance:
            stage_label = self._get_clearance_stage_label()
            raise UserError(_("⚠️ لا يمكن مسح واستلام المواد لهذه الشحنة حالياً.\nالشحنة في مرحلة: [%s].\nالاستلام متاح فقط بعد وصول فاتورة المورد إلى مرحلة 'بدء التخليص (Clearance)'.") % stage_label)

        clean_string = normalize_arabic_scanner_input(raw_string.strip())
        data = self._parse_qr_payload(clean_string)
        lot_name = data.get('lot_name')
        product_barcode = data.get('product_barcode')
        product_code = data.get('product_code')
        product_id = data.get('product_id')
        qty_to_add = 1.0  # Every single scan adds precisely 1 unit

        # Find matching stock move on this picking
        open_moves = self.move_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
        matched_move = None

        # 1. Match by product_id
        if product_id:
            matched_move = open_moves.filtered(lambda m: m.product_id.id == product_id)

        # 2. Match by candidate codes (barcode, default_code, part_number, unpadded codes)
        candidate_codes = [c for c in (product_barcode, product_code) if c]
        for c in list(candidate_codes):
            if c.lstrip('0') and c.lstrip('0') != c:
                candidate_codes.append(c.lstrip('0'))

        if not matched_move and candidate_codes:
            for code in candidate_codes:
                matched_move = open_moves.filtered(
                    lambda m: m.product_id.barcode == code or m.product_id.default_code == code or (hasattr(m.product_id, 'part_number') and m.product_id.part_number == code)
                )
                if matched_move:
                    break

        # 3. Match by default_code
        if not matched_move and product_code:
            matched_move = open_moves.filtered(
                lambda m: m.product_id.default_code == product_code or m.product_id.name == product_code
            )

        # 4. Match by existing lot in open moves
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
            msg = _("No matching move found on transfer %(transfer)s for scanned payload: %(payload)s") % {
                'transfer': self.name,
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

        # Find and verify stock.lot
        lot = False
        if product.tracking in ('lot', 'serial'):
            if not lot_name:
                msg = _("Product '%(product)s' requires a Lot/Serial number, but none was provided in the scan.") % {
                    'product': product.display_name,
                }
                self.qr_scan_status = msg
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Lot Required'),
                        'message': msg,
                        'type': 'warning',
                        'sticky': False,
                    }
                }

            clean_raw = clean_string
            existing_move_lots = (matched_move.lot_ids | matched_move.move_line_ids.lot_id).filtered(
                lambda l: l.name == lot_name or (lot_name.lstrip('0') and l.name == lot_name.lstrip('0')) or (getattr(l, 'qr_code_value', False) and l.qr_code_value in (clean_raw, raw_string))
            )
            if existing_move_lots:
                lot = existing_move_lots[0]
            else:
                domain = [
                    '|', '|', ('name', '=', lot_name), ('qr_code_value', '=', clean_raw), ('qr_code_value', '=', raw_string),
                    ('product_id', '=', product.id),
                ]
                if self.company_id:
                    domain.extend(['|', ('company_id', '=', False), ('company_id', '=', self.company_id.id)])
                lot = self.env['stock.lot'].search(domain, limit=1)
                if not lot and lot_name.lstrip('0') and lot_name.lstrip('0') != lot_name:
                    alt_domain = [('name', '=', lot_name.lstrip('0')), ('product_id', '=', product.id)]
                    if self.company_id:
                        alt_domain.extend(['|', ('company_id', '=', False), ('company_id', '=', self.company_id.id)])
                    lot = self.env['stock.lot'].search(alt_domain, limit=1)

            # Enforce lot must pre-exist: NO automatic lot creation upon scanning
            if not lot:
                msg = _("Lot/Serial number '%(lot)s' does not exist in inventory for '%(product)s'. Lots must be created and established before scanning.") % {
                    'lot': lot_name,
                    'product': product.display_name,
                }
                self.qr_scan_status = msg
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Unknown Lot Number'),
                        'message': msg,
                        'type': 'danger',
                        'sticky': False,
                    }
                }

        # Check over-scanning: Block if adding 1 unit exceeds demanded quantity
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        current_done = matched_move.quantity
        demand = matched_move.product_uom_qty
        if float_compare(current_done + qty_to_add, demand, precision_digits=precision) > 0:
            msg = _("Cannot scan: Required quantity (%(demand)s) for '%(product)s' is already fulfilled (Done: %(done)s). Over-scanning is strictly blocked.") % {
                'demand': demand,
                'product': product.display_name,
                'done': current_done,
            }
            self.qr_scan_status = msg
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Over-scan Blocked'),
                    'message': msg,
                    'type': 'danger',
                    'sticky': False,
                }
            }

        # Serial duplicate scan prevention
        if product.tracking == 'serial' and lot:
            existing_serial_ml = matched_move.move_line_ids.filtered(lambda ml: ml.lot_id == lot and ml.quantity > 0)
            if existing_serial_ml:
                msg = _("Serial number '%(lot)s' has already been scanned for '%(product)s'.") % {
                    'lot': lot.name,
                    'product': product.display_name,
                }
                self.qr_scan_status = msg
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Serial Already Scanned'),
                        'message': msg,
                        'type': 'danger',
                        'sticky': False,
                    }
                }

        # Update or create stock.move.line by adding precisely 1 unit
        move_line = False
        uom_id = (getattr(matched_move, 'product_uom', False) or getattr(matched_move, 'product_uom_id', False)).id
        if lot:
            if product.tracking == 'serial':
                empty_ml = matched_move.move_line_ids.filtered(lambda ml: not ml.lot_id and ml.quantity == 0)
                if empty_ml:
                    move_line = empty_ml[0]
                    move_line.write({'lot_id': lot.id, 'quantity': 1.0, 'picked': True})
                else:
                    move_line = self.env['stock.move.line'].create({
                        'move_id': matched_move.id,
                        'picking_id': self.id,
                        'product_id': product.id,
                        'product_uom_id': uom_id,
                        'location_id': matched_move.location_id.id,
                        'location_dest_id': matched_move.location_dest_id.id,
                        'lot_id': lot.id,
                        'quantity': 1.0,
                        'picked': True,
                    })
            else:
                existing_ml = matched_move.move_line_ids.filtered(lambda ml: ml.lot_id == lot)
                if existing_ml:
                    move_line = existing_ml[0]
                    move_line.quantity += 1.0
                    move_line.picked = True
                else:
                    empty_ml = matched_move.move_line_ids.filtered(lambda ml: not ml.lot_id and ml.quantity == 0)
                    if empty_ml:
                        move_line = empty_ml[0]
                        move_line.write({'lot_id': lot.id, 'quantity': 1.0, 'picked': True})
                    else:
                        move_line = self.env['stock.move.line'].create({
                            'move_id': matched_move.id,
                            'picking_id': self.id,
                            'product_id': product.id,
                            'product_uom_id': uom_id,
                            'location_id': matched_move.location_id.id,
                            'location_dest_id': matched_move.location_dest_id.id,
                            'lot_id': lot.id,
                            'quantity': 1.0,
                            'picked': True,
                        })
        else:
            # Non-tracked product scan
            if matched_move.move_line_ids:
                move_line = matched_move.move_line_ids[0]
                move_line.quantity += 1.0
                move_line.picked = True
            else:
                move_line = self.env['stock.move.line'].create({
                    'move_id': matched_move.id,
                    'picking_id': self.id,
                    'product_id': product.id,
                    'product_uom_id': uom_id,
                    'location_id': matched_move.location_id.id,
                    'location_dest_id': matched_move.location_dest_id.id,
                    'quantity': 1.0,
                    'picked': True,
                })

        # Register lot on move if needed
        if lot and lot not in matched_move.lot_ids:
            matched_move.lot_ids = [(4, lot.id)]

        matched_move.invalidate_recordset(['quantity'])
        status_msg = _("✓ Scanned %(product)s | Lot: %(lot)s | +1 Unit (Done: %(done)s / %(demand)s)") % {
            'product': product.display_name,
            'lot': lot.name if lot else _('N/A'),
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

    def _process_receipt_qr_payload(self, raw_string):
        return self._process_picking_qr_payload(raw_string)

    def _process_qr_payload(self, raw_string):
        self.ensure_one()
        if self.is_internal_transfer or self.picking_type_code == 'internal' or (self.purchase_id and self.purchase_id.purchase_type == 'internal_po'):
            parent_processor = getattr(super(), '_process_qr_payload', None)
            if parent_processor:
                return parent_processor(raw_string)
            raise UserError(_("Custom QR scanning is not available for internal operations."))
        return self._process_picking_qr_payload(raw_string)

    def action_open_picking_mobile_qr_wizard(self):
        """ Open dedicated mobile camera QR scanner for any transfer """
        self.ensure_one()
        if self.is_internal_transfer or self.picking_type_code == 'internal' or (self.purchase_id and self.purchase_id.purchase_type == 'internal_po'):
            raise UserError(_("Custom QR scanning is not available for internal operations."))
        if self.state in ('done', 'cancel'):
            raise UserError(_("Transfer '%s' is in state '%s' and cannot be processed.") % (self.name, self.state))
        if self.picking_type_code == 'incoming' and self.is_receipt_locked_for_clearance:
            stage_label = self._get_clearance_stage_label()
            raise UserError(_("⚠️ لا يمكن فتح كاميرا المسح حالياً.\nالشحنة في مرحلة: [%s].\nالاستلام متاح فقط بعد وصول فاتورة المورد إلى مرحلة 'بدء التخليص (Clearance)'.") % stage_label)
        self._ensure_picking_quantities_zero_for_scan()
        wizard = self.env['stock.picking.mobile.qr.wizard'].create({
            'picking_id': self.id,
        })
        return {
            'name': _('Mobile QR Scanner - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking.mobile.qr.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_receipt_mobile_qr_scan_wizard(self):
        return self.action_open_picking_mobile_qr_wizard()

    def action_open_mobile_qr_scan_wizard(self):
        self.ensure_one()
        if self.is_internal_transfer or self.picking_type_code == 'internal' or (self.purchase_id and self.purchase_id.purchase_type == 'internal_po'):
            parent_action = getattr(super(), 'action_open_mobile_qr_scan_wizard', None)
            if parent_action:
                return parent_action()
            raise UserError(_("Custom QR scanning is not available for internal operations."))
        return self.action_open_picking_mobile_qr_wizard()
