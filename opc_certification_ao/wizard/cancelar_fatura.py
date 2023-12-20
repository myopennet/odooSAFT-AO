# -*- coding: utf-8 -*-

from odoo import models, fields
from odoo.exceptions import ValidationError


class WizardCancelarFatura(models.Model):
    _name = "wizard.cancelar.fatura"
    _description = "Wizard de cancelamento da fatura"

    descricao_cancel = fields.Char(string="Motivo do Cancelamento", size=64, copy=False, required=True)

    
    def act_fechar(self):
        return {'type': 'ir.actions.act_window_close'}

    
    def act_cancel(self):
        fatura = self.env['account.move'].browse(self.env.context.get('active_id'))
        fatura.reason_cancel = self.descricao_cancel
        if not self.descricao_cancel:
            raise ValidationError(_('O campo motivo de cancelamento é obrigatório'))
        fatura.button_cancel()
