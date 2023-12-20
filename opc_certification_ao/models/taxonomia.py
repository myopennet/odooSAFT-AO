# -*- coding: utf-8 -*-
import datetime
from odoo import models, fields, api


class TaxonomiaTipoEmpresa(models.Model):
    _name = "taxonomia.tipo.empresa"
    _description = """Tabela taxonomias - relacao entre impostos e contas financeiras
                      Menu Contabilidade - Configuraçao - Taxonomias"""

    name = fields.Char(string="Classificação Plano de Contas", required=True)
    code = fields.Char(string="Código", required=True)


class TaxonomiaPeriodo(models.Model):
    _name = "taxonomia.periodo"
    _description = "Tabela de relacao entre taxonomias e os periodos e empresas"

    name = fields.Many2one('taxonomia.tipo.empresa', 'Classificação Plano de Contas')
    company_id = fields.Many2one('res.company', 'Empresa')
    start_date = fields.Date("Inicio")
    end_date = fields.Date("Fim")
    taxonomias = fields.One2many('taxonomia.periodo.linhas', 'periodo_id', 'Taxonomias')

    @api.model
    def create(self, vals):
        if 'company_id' not in vals or not vals['company_id']:
            empresa = self.env['res.company'].search([])
            if len(empresa) > 0:
                vals['company_id'] = empresa[0].id

        if 'start_date' not in vals or not vals['start_date']:
            vals['start_date'] = datetime.datetime.strptime(str(datetime.datetime.now())[:4] + "-01-01", '%Y-%m-%d')

        if 'end_date' not in vals or not vals['end_date']:
            vals['end_date'] = datetime.datetime.strptime(str(datetime.datetime.now())[:4] + "-12-31", '%Y-%m-%d')

        return super(TaxonomiaPeriodo, self).create(vals)


class TaxonomiaPeriodoLinhas(models.Model):
    _name = "taxonomia.periodo.linhas"
    _description = "tabela de linhas de relacao entre taxonomias e periodos"

    name = fields.Many2one('taxonomia', sring='Taxonomia')
    contas = fields.Many2many('account.account', 'taxonomia_account_rel',
                              'taxonomia_periodo_linhas_id', 'account_id', string='Contas')
    periodo_id = fields.Many2one('taxonomia.periodo', string="Periodo")

    # metodo que preenche automaticameente as contas nas linhas ao preencher a taxonomia
    @api.onchange('name')
    def _onchange_name(self):
        if self.name:
            lista_contas = []
            contasstr = self.name.contas.split('|')
            for conta_str in contasstr:
                contas = self.env['account.account'].search([('code', '=like',  conta_str.replace(" ", "") + '%')])
                for conta in contas:
                    lista_contas.append(conta.id)
            self.contas = [(6, 0, lista_contas)]

    # metodo que adiciona taxonomias automaticamente caso o campo esteje vazio
    @api.model
    def create(self, vals):
        taxonomia_line_id = super(TaxonomiaPeriodoLinhas, self).create(vals)

        if 'contas' not in vals or vals['contas'] == []:
            if taxonomia_line_id.name:
                lista_contas = []
                contasstr = taxonomia_line_id.name.contas.split('|')
                for contastr in contasstr:
                    contas = self.env['account.account'].search([('code', '=like', contastr.replace(" ", "") + '%')])
                    for conta in contas:
                        lista_contas.append(conta.id)
                taxonomia_line_id.contas = [(6, 0, lista_contas)]

        return taxonomia_line_id


class Taxonomia(models.Model):
    _name = "taxonomia"
    _description = "Tabela de taxonomias"

    name = fields.Char('Taxonomia')
    contas = fields.Char('Contas')
    deprecated = fields.Boolean("Obsoleto")

    # actualizar a taxonomia no imposto
    @api.model
    def create(self, vals):
        taxonomia_id = super(Taxonomia, self).create(vals)

        if 'contas' in vals and vals['contas']:
            contas = vals['contas'].replace(' ', '').split('|')
            for conta in contas:
                account_account_id = self.env['account.account'].search([('code', 'like', conta)])
                for account_id in account_account_id:
                    if str(account_id.code[:len(conta)]) == str(conta):
                        self.env.cr.execute("UPDATE account_account "
                                            "SET taxonomia_id=%s "
                                            "WHERE id=%s", (taxonomia_id.id, account_id.id))
        return taxonomia_id
