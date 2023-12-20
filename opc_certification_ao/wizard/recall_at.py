# -*- coding: utf-8 -*-

from odoo import models, api


class WizardRecallAt(models.TransientModel):
    _name = "wizard.recall.at"
    _description = "Wizard para pedir novos codigos AT nas guias"

    
    def act_cancel(self):
        """ Fechar wizard
        """
        return {'type': 'ir.actions.act_window_close'}

    
    def act_recall(self):
        """ Voltar a efetuar o pedido de código AT em guia com estado AT 'erro'
        """
        if self.env.context.get('active_ids'):
            pickings = self.env['stock.picking'].browse(self.env.context.get('active_ids'))
            for picking in pickings:
                if picking.at_status == 'error':
                    picking.callWebServiceGR(False)
        return {'type': 'ir.actions.act_window_close'}
