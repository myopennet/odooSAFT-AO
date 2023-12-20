# -*- coding: utf-8 -*-

from odoo import models, fields, api


class TipoProdutoSaft(models.Model):
    _name = "tipo.produto.saft"
    _description = "Tipos de produtos de acordo com as opçoes no ficheiro exportavel de stock para a AT"

    name = fields.Char(string="Nome")
    code = fields.Char(string="Código")

    _sql_constraints = [('code_unique', 'unique(code)', 'Código deve ser único!')]

    # definir produtos sem tipo de produto Saft como Mercadoria por defeito
    @api.model
    def create(self, vals):
        tipoproduto_saft = super(TipoProdutoSaft, self).create(vals)
        if 'code' in vals and vals['code'] == 'M':
            produtos = self.env['product.template'].search(['|', ('active', '=', True),
                                                            ('active', '=', False),
                                                            ('tipo_produto_id', '=', False),
                                                            ('type', '!=', 'service')])
            for produto in produtos:
                produto.tipo_produto_id = tipoproduto_saft.id

        return tipoproduto_saft
