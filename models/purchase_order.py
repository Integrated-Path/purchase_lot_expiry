# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

LOGISTICS_STAGES = [
    ('rfq', 'طلب سعر (RFQ)'),
    ('po', 'أمر شراء (PO)'),
    ('manufacturing', 'قيد التصنيع (Manufacturing)'),
    ('expiry_check', 'تدقيق تواريخ التلف (Expiry Check)'),
    ('pi', 'فاتورة شراء (PI)'),
    ('shipment_booking', 'حجز الشحنة (Shipment Booking)'),
    ('transport_port', 'نقل للميناء / المطار (Transport to Port/Airport)'),
    ('on_the_way', 'الشحنة في الطريق (Shipment on the way)'),
    ('clearance', 'التخليص (Clearance)'),
    ('received', 'الاستلام المخزني (Received by warehouse)'),
]


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # Logistics Pipeline Stage
    logistics_stage = fields.Selection(
        LOGISTICS_STAGES,
        string='مرحلة الشحنة / Logistics Stage',
        default='rfq',
        required=True,
        tracking=True,
        copy=False,
        help='Tracks the physical and documentary lifecycle of the purchase shipment.'
    )

    # Freight Type Selection (Sea / Air)
    freight_type = fields.Selection([
        ('sea', 'بحرية / Sea Freight'),
        ('air', 'جوية / Air Freight'),
    ], string='نوع الشحن / Freight Type', default='sea', tracking=True)

    # Destination Warehouse
    destination_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='المخزن المستلم / Destination Warehouse',
        compute='_compute_destination_warehouse_id',
        inverse='_inverse_destination_warehouse_id',
        store=True,
        readonly=False,
        tracking=True,
        help='Warehouse where materials will be received upon arrival and clearance.'
    )

    # Checklist Item 1: MOH Approval (موافقة وزارة الصحة)
    moh_approval = fields.Boolean(
        string='موافقة وزارة الصحة (MOH Approval)',
        tracking=True,
        copy=False
    )
    moh_attachment_ids = fields.Many2many(
        'ir.attachment',
        'po_moh_attachment_rel',
        'order_id',
        'attachment_id',
        string='مرفقات موافقة وزارة الصحة',
        copy=False
    )
    moh_ref = fields.Char(string='رقم مرجع وزارة الصحة', copy=False)
    moh_date = fields.Date(string='تاريخ موافقة وزارة الصحة', copy=False)

    # Checklist Item 2: MOT Approval (موافقة وزارة التجارة)
    mot_approval = fields.Boolean(
        string='موافقة وزارة التجارة (MOT Approval)',
        tracking=True,
        copy=False
    )
    mot_attachment_ids = fields.Many2many(
        'ir.attachment',
        'po_mot_attachment_rel',
        'order_id',
        'attachment_id',
        string='مرفقات موافقة وزارة التجارة',
        copy=False
    )
    mot_ref = fields.Char(string='رقم مرجع وزارة التجارة', copy=False)
    mot_date = fields.Date(string='تاريخ موافقة وزارة التجارة', copy=False)

    # Checklist Item 3: Attestation & Legalization (التصديق)
    attestation_approval = fields.Boolean(
        string='التصديق (Attestation / Legalization)',
        tracking=True,
        copy=False
    )
    attestation_attachment_ids = fields.Many2many(
        'ir.attachment',
        'po_attestation_attachment_rel',
        'order_id',
        'attachment_id',
        string='مرفقات التصديق',
        copy=False
    )
    attestation_ref = fields.Char(string='رقم مرجع التصديق', copy=False)
    attestation_date = fields.Date(string='تاريخ التصديق', copy=False)

    # Checklist Item 4: Customs Release (إخراج كمرك)
    customs_release_approval = fields.Boolean(
        string='إخراج كمرك (Customs Release)',
        tracking=True,
        copy=False
    )
    customs_attachment_ids = fields.Many2many(
        'ir.attachment',
        'po_customs_attachment_rel',
        'order_id',
        'attachment_id',
        string='مرفقات إخراج كمرك',
        copy=False
    )
    customs_ref = fields.Char(string='رقم البيان الجمركي', copy=False)
    customs_date = fields.Date(string='تاريخ الإخراج الجمركي', copy=False)

    @api.depends('picking_type_id')
    def _compute_destination_warehouse_id(self):
        for order in self:
            order.destination_warehouse_id = order.picking_type_id.warehouse_id

    def _inverse_destination_warehouse_id(self):
        for order in self:
            if order.destination_warehouse_id and order.destination_warehouse_id.in_type_id:
                order.picking_type_id = order.destination_warehouse_id.in_type_id

    # Pipeline Stage Transition Methods
    def button_confirm(self):
        res = super(PurchaseOrder, self).button_confirm()
        for order in self:
            if order.logistics_stage == 'rfq':
                order.logistics_stage = 'po'
        return res

    def button_approve(self, force=False):
        res = super(PurchaseOrder, self).button_approve(force=force)
        for order in self:
            if order.logistics_stage == 'rfq':
                order.logistics_stage = 'po'
        return res

    def button_draft(self):
        res = super(PurchaseOrder, self).button_draft()
        for order in self:
            order.logistics_stage = 'rfq'
        return res

    def action_stage_manufacturing(self):
        for order in self:
            order.logistics_stage = 'manufacturing'
            order.message_post(body=_('تم تحديث مرحلة الشحنة إلى: <b>قيد التصنيع (Manufacturing)</b>'))

    def action_stage_expiry_check(self):
        for order in self:
            order.logistics_stage = 'expiry_check'
            order.message_post(body=_('تم تحديث مرحلة الشحنة إلى: <b>تدقيق تواريخ التلف (Expiry Check)</b>'))

    def action_stage_pi(self):
        for order in self:
            order.logistics_stage = 'pi'
            order.message_post(body=_(
                'تم تحديث مرحلة الشحنة إلى: <b>فاتورة شراء (PI)</b>.<br/>'
                'تم إظهار إذن الاستلام في المخازن (عرض فقط، غير متاح للاستلام حتى مرحلة التخليص).'
            ))
            if not order.picking_ids:
                super(PurchaseOrder, order)._create_picking()

    def action_stage_shipment_booking(self):
        for order in self:
            order.logistics_stage = 'shipment_booking'
            order.message_post(body=_('تم تحديث مرحلة الشحنة إلى: <b>حجز الشحنة (Shipment Booking)</b>'))

    def action_stage_transport_port(self):
        for order in self:
            order.logistics_stage = 'transport_port'
            target_desc = _('الميناء البحري') if order.freight_type == 'sea' else _('المطار الجوي')
            order.message_post(body=_('تم تحديث مرحلة الشحنة إلى: <b>نقل البضاعة إلى %s</b>') % target_desc)

    def action_stage_on_the_way(self):
        for order in self:
            order.logistics_stage = 'on_the_way'
            order.message_post(body=_('تم تحديث مرحلة الشحنة إلى: <b>الشحنة في الطريق (Shipment on the way)</b>'))

    def action_stage_clearance(self):
        for order in self:
            order.logistics_stage = 'clearance'
            order.message_post(body=_(
                'تم تحديث مرحلة الشحنة إلى: <b>التخليص (Clearance)</b>.<br/>'
                '✅ أصبحت الشحنة الآن متاحة في المخازن للاستلام والمسح والاعتماد.'
            ))
            if not order.picking_ids:
                super(PurchaseOrder, order)._create_picking()

    def action_stage_received(self):
        for order in self:
            incoming = order.picking_ids.filtered(lambda p: p.picking_type_code == 'incoming' and p.state not in ('done', 'cancel'))
            if incoming:
                return order.action_view_picking()
            order.logistics_stage = 'received'
            order.message_post(body=_('تم تحديث مرحلة الشحنة إلى: <b>الاستلام المخزني (Received by warehouse)</b>'))

    def action_stage_previous(self):
        stage_sequence = [
            'rfq', 'po', 'manufacturing', 'expiry_check', 'pi',
            'shipment_booking', 'transport_port', 'on_the_way',
            'clearance', 'received'
        ]
        for order in self:
            if order.logistics_stage in stage_sequence:
                idx = stage_sequence.index(order.logistics_stage)
                if idx > 1:
                    prev_stage = stage_sequence[idx - 1]
                    order.logistics_stage = prev_stage
                    stage_name = dict(order._fields['logistics_stage'].selection).get(prev_stage)
                    order.message_post(body=_('تم التراجع إلى المرحلة السابقة: <b>%s</b>') % stage_name)

    def _create_picking(self):
        orders_to_create = self.filtered(lambda po: po.logistics_stage in (
            'pi', 'shipment_booking', 'transport_port', 'on_the_way', 'clearance', 'received'
        ))
        if orders_to_create:
            return super(PurchaseOrder, orders_to_create)._create_picking()
        return True

    def action_open_lot_qr_wizard(self):
        self.ensure_one()
        wizard_lines = []
        for line in self.order_line.filtered(lambda l: l.lot_ids):
            if line.pol_lot_ids:
                for pol_lot in line.pol_lot_ids:
                    wizard_lines.append((0, 0, {
                        'product_id': line.product_id.id,
                        'lot_id': pol_lot.lot_id.id,
                        'lot_name': pol_lot.lot_id.name,
                        'expiration_date': pol_lot.lot_id.expiration_date or pol_lot.expiration_date,
                        'quantity': pol_lot.quantity,
                        'copies': 1,
                        'is_selected': True,
                    }))
            else:
                nb = len(line.lot_ids)
                qty = line.product_qty / nb if nb > 0 else 1.0
                for lot in line.lot_ids:
                    wizard_lines.append((0, 0, {
                        'product_id': line.product_id.id,
                        'lot_id': lot.id,
                        'lot_name': lot.name,
                        'expiration_date': lot.expiration_date or line.expiration_date,
                        'quantity': qty,
                        'copies': 1,
                        'is_selected': True,
                    }))

        if not wizard_lines:
            raise UserError(_('No Lot/Serial numbers found on this purchase order to generate labels.'))

        wizard = self.env['purchase.lot.qr.wizard'].create({
            'purchase_id': self.id,
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
