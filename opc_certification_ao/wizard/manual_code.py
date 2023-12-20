# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WizardManualCode(models.TransientModel):
    _name = "wizard.manual.code"
    _description = "Wizard para definir novo codigo AT manualmente na guia"

    name = fields.Char(string="Código AT", size=16, required=True, copy=False)
    at_status = fields.Selection([('insert', 'insert'), ('done', 'done')], string="Estado",
                                 default="insert", copy=False)

    
    def act_cancel(self):
        """ Fechar wizard
        """
        return {'type': 'ir.actions.act_window_close'}

    
    def act_getfile(self):
        """ Atualizar código AT na guia e colocar estado AT como 'sucesso'
        """
        if len(self.name) < 9:
            raise UserError(_('O código tem de ser composto por pelo menos 9 dígitos.'))

        if self.env.context.get('active_id'):
            picking = self.env['stock.picking'].browse(self.env.context.get('active_id'))
            if picking.at_status != 'success':
                self.env.cr.execute("""
                    UPDATE stock_picking
                    SET at_code=%s, at_status='success'
                    WHERE id=%s""", (self.name, self.env.context.get('active_id')))

        return {'type': 'ir.actions.act_window_close'}
