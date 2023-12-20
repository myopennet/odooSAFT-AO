# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


# impostos na fatura - contabilidade - configuracao - contabilidade - impostos
class AccountTax(models.Model):
    _inherit = "account.tax"

    # Colocar o campo obrigatório
    description = fields.Char(string='Label on Invoices', required=True)
    # Campos necessário para o saft
    autoliquidacao = fields.Boolean(string="Auto-Liquidação")
    country_region = fields.Selection([('PT', 'Continente'), ('PT-AC', 'Açores'), ('PT-MA', 'Madeira')],
                                      string="Espaço Fiscal", required=True, default='PT', copy=False)
    saft_tax_type = fields.Selection([('IVA', 'IVA'), ('IS', 'Imp do Selo')], string="Imposto", required=True,
                                     default='IVA', copy=False)
    saft_tax_code = fields.Selection([('RED', 'Reduzida'), ('NOR', 'Normal'), ('INT', 'Intermédia'), ('ISE', 'Isenta'),
                                      ('OUT', 'Outra')], string="Nível de Taxa",
                                     required=True, default='NOR', copy=False)
    expiration_date = fields.Date(string="Data Expiração", copy=False)
    exemption_reason = fields.Char(string="Motivo da isenção", size=60,
                                   help="No caso de IVA isento, indique qual a norma do codigo do IVA que autribui a "
                                        "isenção",
                                   default="M01: Artigo 16.º n.º 6 do CIVA", copy=False)
    
    def configure_account_tax_group_and_saft_code(self):
        for tax in self:
            if str(tax.amount)[:2] == '23':
                tax.saft_tax_code = 'NOR'
                tax.tax_group_id = self.env['ir.model.data'].check_object_reference('l10n_pt', 'tax_group_iva_23')[1]
            elif str(tax.amount)[:2] == '13':
                tax.saft_tax_code = 'INT'
                tax.tax_group_id = self.env['ir.model.data'].check_object_reference('l10n_pt', 'tax_group_iva_13')[1]
            elif str(tax.amount)[:1] == '6':
                tax.saft_tax_code = 'RED'
                tax.tax_group_id = self.env['ir.model.data'].check_object_reference('l10n_pt', 'tax_group_iva_6')[1]
            elif str(tax.amount)[:1] == '0':
                tax.saft_tax_code = 'ISE'
                tax.tax_group_id = self.env['ir.model.data'].check_object_reference('l10n_pt', 'tax_group_iva_0')[1]
            elif str(tax.amount)[:1] == '2':
                tax.saft_tax_code = 'RED'
                tax.tax_group_id = self.env['ir.model.data'].check_object_reference('opc_certification_ao', 'tax_group_iva_2')[1]
            else:
                tax.saft_tax_code = 'OUT'
                tax.tax_group_id = self.env['ir.model.data'].check_object_reference('opc_certification_ao', 'tax_group_retencao')[1]

    # validacoes ao alterar o imposto
    def _validar_imposto_utilizado(self, aviso):
        for tax in self:
            taxes_count = self.env['account.move.line'].sudo().search_count([('tax_ids', 'in', [tax.id]),
                                                                             ('company_id', '=', tax.company_id.id)])
            if taxes_count:
                raise ValidationError(aviso)


    def _validar_imposto(self, vals):
        for tax in self:
            tax_name = tax.name
            if 'name' in vals:
                tax_name = vals['name']
            type_tax_use = tax.type_tax_use
            if 'type_tax_use' in vals:
                type_tax_use = vals['type_tax_use']
            tax_count = self.sudo().search_count([('name', '=', tax_name),
                                                  ('type_tax_use', '=', type_tax_use),
                                                  ('company_id', '=', tax.company_id.id),
                                                  ('id', '!=', tax.id)])
            if tax_count > 0:
                raise ValidationError(
                    _("Não pode ter dois impostos na mesma empresa com o mesmo nome e tipo de uso."))

            # impostos isentos tem de ter descritivo
            amount = tax.amount
            if 'amount' in vals:
                amount = vals['amount']
            exemption_reason = tax.exemption_reason
            if 'exemption_reason' in vals:
                exemption_reason = vals['exemption_reason']
            if amount == 0 and not exemption_reason:
                raise ValidationError(_("Não pode ter impostos isentos sem preencher o campo (Motivo da isenção) "
                                        "na aba (Dados SAFT)."))

            if 'amount' in vals:
                tax._validar_imposto_utilizado(_("Esse imposto está incluído em documentos contabilisticos, pelo que "
                                                 "não pode alterar o seu montante ou se ele esta ou nao incluido no "
                                                 "preco. Para proceder a estas alterações por favor crie um novo "
                                                 "imposto."))

    def write(self, vals):
        vals['include_base_amount'] = False
        self._validar_imposto(vals)
        return super(AccountTax, self).write(vals)

    # validacoes ao criar impostos
    @api.model
    def create(self, vals):
        # niveis de imposto
        if 'description' in vals and vals['description']:
            if vals['description'].lower().find('isento') != -1:
                vals['saft_tax_code'] = 'ISE'
            elif vals['description'].lower().find('normal') != -1:
                vals['saft_tax_code'] = 'NOR'
            elif vals['description'].lower().find('reduzida') != -1:
                vals['saft_tax_code'] = 'RED'
            elif vals['description'].lower().find('intermedia') != -1:
                vals['saft_tax_code'] = 'INT'

        vals['include_base_amount'] = False
        resultado = super(AccountTax, self).create(vals)
        resultado._validar_imposto(vals)
        resultado.configure_account_tax_group_and_saft_code()
        return resultado

    # validacoes ao apagar impostos
    def unlink(self):
        for tax in self:
            tax._validar_imposto_utilizado(_("Esse imposto está incluído em documentos contabilisticos, pelo que não "
                                             "pode eliminá-lo."))
        return super(AccountTax, self).unlink()
