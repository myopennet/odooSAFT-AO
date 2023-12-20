# -*- coding: utf-8 -*-

from odoo import models, fields, api


class WizardCancelarSaleOrder(models.TransientModel):
    _name = "wizard.cancelar.sale"
    _description = "Wizard de cancelamento da SO"

    descricao_cancel = fields.Char(string="Motivo do Cancelamento", size=64, copy=False)

    
    def act_fechar(self):
        return {'type': 'ir.actions.act_window_close'}

    
    def act_cancel(self):
        sale = self.env['sale.order'].browse(self.env.context.get('active_ids'))
        for reason in sale:
            reason.descricao_cancel = self.descricao_cancel
            reason.action_cancel()
