# -*- coding: utf-8 -*-

from odoo import models, fields


class AccountConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"
    _description = 'Esta classe e criada com o objetivo de criar 2 novos campos nas configuracoes da contabilidade' \
                   'estes dois campos servem para as contas de acerto de casos decimais, ' \
                   'tanto de compras como de vendas, serem configuraveis.'

    account_adjustments_purchase = fields.Many2one("account.account", related='company_id.account_adjustments_purchase',
                                                   string="Conta de acerto de casa decimal para compra")
    account_adjustments_sale = fields.Many2one("account.account", string="Conta de acertos de casa decimal para venda",
                                               related='company_id.account_adjustments_sale')


