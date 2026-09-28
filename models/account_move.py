# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from markupsafe import Markup

BILL_LOGISTICS_STAGES = [
    ('shipment_booking', 'حجز الشحنة (Shipment Booking)'),
    ('transport_port', 'نقل للميناء / المطار (Transport)'),
    ('on_the_way', 'الشحنة في الطريق (On the way)'),
    ('clearance', 'بدء التخليص (Clearance)'),
    ('received', 'الاستلام المخزني (Received)'),
]


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Stored reference to linked Purchase Order
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='أمر الشراء / Purchase Order',
        compute='_compute_purchase_order_id',
        store=True,
        readonly=False,
        copy=False,
        help="Linked Purchase Order for logistics and clearance tracking."
    )

    # Secondary statusbar for Vendor Bill logistics pipeline
    logistics_stage = fields.Selection(
        BILL_LOGISTICS_STAGES,
        string='مرحلة الشحنة / Logistics Stage',
        default=False,
        tracking=True,
        copy=False,
        help='Tracks the post-PI physical and customs lifecycle on the vendor bill.'
    )

    freight_type = fields.Selection(
        related='purchase_order_id.freight_type',
        string='نوع الشحن / Freight Type',
        readonly=True
    )

    destination_warehouse_id = fields.Many2one(
        related='purchase_order_id.destination_warehouse_id',
        string='المخزن المستلم / Destination Warehouse',
        readonly=True
    )

    # Checklist Item 1: MOH Approval (موافقة وزارة الصحة)
    moh_approval = fields.Boolean(
        string='موافقة وزارة الصحة (MOH Approval)',
        tracking=True,
        copy=False
    )
    moh_attachment_ids = fields.Many2many(
        'ir.attachment',
        'bill_moh_attachment_rel',
        'move_id',
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
        'bill_mot_attachment_rel',
        'move_id',
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
        'bill_attestation_attachment_rel',
        'move_id',
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
        'bill_customs_attachment_rel',
        'move_id',
        'attachment_id',
        string='مرفقات إخراج كمرك',
        copy=False
    )
    customs_ref = fields.Char(string='رقم البيان الجمركي', copy=False)
    customs_date = fields.Date(string='تاريخ الإخراج الجمركي', copy=False)

    @api.depends('invoice_line_ids.purchase_order_id', 'line_ids.purchase_line_id.order_id')
    def _compute_purchase_order_id(self):
        for move in self:
            if not move.purchase_order_id:
                pos = move.invoice_line_ids.purchase_order_id | move.line_ids.purchase_line_id.order_id
                move.purchase_order_id = pos[:1] if pos else False

    def action_stage_shipment_booking(self):
        for move in self:
            move.logistics_stage = 'shipment_booking'
            move.message_post(body=Markup(_('تم تحديث مرحلة الشحنة إلى: <b>حجز الشحنة (Shipment Booking)</b>')))

    def action_stage_transport_port(self):
        for move in self:
            move.logistics_stage = 'transport_port'
            target_desc = _('الميناء البحري') if move.freight_type == 'sea' else _('المطار الجوي')
            move.message_post(body=Markup(_('تم تحديث مرحلة الشحنة إلى: <b>نقل البضاعة إلى %s (Transport)</b>')) % target_desc)

    def action_stage_on_the_way(self):
        for move in self:
            move.logistics_stage = 'on_the_way'
            move.message_post(body=Markup(_('تم تحديث مرحلة الشحنة إلى: <b>الشحنة في الطريق (Shipment on the way)</b>')))

    def action_stage_clearance(self):
        for move in self:
            move.logistics_stage = 'clearance'
            move.message_post(body=Markup(_(
                'تم تحديث مرحلة الشحنة إلى: <b>بدء التخليص (Clearance)</b>.<br/>'
                '✅ أصبحت الشحنة الآن متاحة في المخازن للاستلام والمسح والاعتماد.'
            )))
            # If linked PO has pickings, unlock for clearance and initialize quantities
            if move.purchase_order_id:
                if not move.purchase_order_id.picking_ids:
                    super(models.Model, move.purchase_order_id)._create_picking()
                move.purchase_order_id._init_incoming_receipt_quantities()
                incoming = move.purchase_order_id.picking_ids.filtered(
                    lambda p: p.picking_type_code == 'incoming' and p.state not in ('done', 'cancel')
                )
                if incoming:
                    incoming._compute_receipt_locked_for_clearance()

    def action_stage_received(self):
        for move in self:
            if move.purchase_order_id:
                incoming = move.purchase_order_id.picking_ids.filtered(
                    lambda p: p.picking_type_code == 'incoming' and p.state not in ('done', 'cancel')
                )
                if incoming:
                    return move.purchase_order_id.action_view_picking()
            move.logistics_stage = 'received'
            move.message_post(body=Markup(_('تم تحديث مرحلة الشحنة إلى: <b>الاستلام المخزني (Received by warehouse)</b>')))

    def action_stage_previous(self):
        stage_sequence = ['shipment_booking', 'transport_port', 'on_the_way', 'clearance']
        for move in self:
            if move.logistics_stage in stage_sequence:
                idx = stage_sequence.index(move.logistics_stage)
                if idx > 0:
                    prev_stage = stage_sequence[idx - 1]
                    move.logistics_stage = prev_stage
                    stage_name = dict(move._fields['logistics_stage'].selection).get(prev_stage)
                    move.message_post(body=Markup(_('تم التراجع إلى المرحلة السابقة: <b>%s</b>')) % stage_name)
                    if move.purchase_order_id:
                        incoming = move.purchase_order_id.picking_ids.filtered(
                            lambda p: p.picking_type_code == 'incoming' and p.state not in ('done', 'cancel')
                        )
                        if incoming:
                            incoming._compute_receipt_locked_for_clearance()
