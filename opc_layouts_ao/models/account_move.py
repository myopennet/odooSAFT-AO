# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class AccountMove(models.Model):
    _inherit = "account.move"


    @api.depends('partner_id', 'partner_shipping_id')
    def _get_view_transportation_data(self):
        # verificar se o partner_shipping_id é igual ao partner_id
        if self.partner_id and self.partner_shipping_id and self.partner_shipping_id != self.partner_id:
            self.view_transportation_data = True
        else:
            self.view_transportation_data = False

    loading_date = fields.Datetime('Date of Loading', readonly=True, states={'draft': [('readonly', False)]})
    unloading_date = fields.Datetime('Date of Unloading', readonly=True, states={'draft': [('readonly', False)]})
    vehicle_registration = fields.Char('Vehicle Registration', readonly=True, states={'draft': [('readonly', False)]})
    isprinted = fields.Boolean('Is Printed', copy=False)
    view_transportation_data = fields.Boolean('View Transportation Data', compute='_get_view_transportation_data')

    
    def _get_report_base_filename(self):
        self.ensure_one()
        return self.move_type == 'out_invoice' and self.state == 'draft' and _('Draft Invoice') or \
               self.move_type == 'out_invoice' and self.state in ('open', 'in_payment', 'paid', 'posted') and _('Invoice - %s') % (
                   self.internal_number) or \
               self.move_type == 'out_invoice' and self.state == 'cancel' and _('Cancelled Invoice - %s') % (
                   self.internal_number) or \
               self.move_type == 'out_refund' and self.state == 'draft' and _('Credit Note') or \
               self.move_type == 'out_refund' and _('Credit Note - %s') % (self.internal_number) or \
               self.move_type == 'out_refund' and self.state == 'cancel' and _('Cancelled Credit Note - %s') % (
                   self.internal_number) or \
               self.move_type == 'in_invoice' and self.state == 'draft' and _('Vendor Bill') or \
               self.move_type == 'in_invoice' and self.state in ('open', 'in_payment', 'paid', 'posted') and _('Vendor Bill - %s') % (
                   self.internal_number) or \
               self.move_type == 'in_invoice' and self.state == 'cancel' and _('Cancelled Vendor Bill - %s') % (
                   self.internal_number) or \
               self.move_type == 'in_refund' and self.state == 'draft' and _('Vendor Credit Note') or \
               self.move_type == 'in_refund' and _('Vendor Credit Note - %s') % (self.internal_number) or \
               self.move_type == 'in_refund' and self.state == 'cancel' and _('Cancelled Vendor Credit Note - %s') % (
                   self.internal_number)

