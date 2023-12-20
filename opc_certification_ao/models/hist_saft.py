# -*- coding: utf-8 -*-

from odoo import models, fields


# tabela de historico de exportacoes de saft - contabilidade - relatorios - saft - historico
class HistSaft(models.Model):
    _name = "hist.saft"
    _description = 'Histórico de SAFT'
    _order = 'data_criacao desc'

    data_criacao = fields.Datetime(string="Data de Criação", readonly=True)
    data_inicio = fields.Date(string="Data de Inicio", readonly=True)
    data_fim = fields.Date(string="Data de Fim", readonly=True)
    user = fields.Many2one('res.users', string="Utilizador", readonly=True, default=lambda self: self.env.uid)
    tipo = fields.Selection([('import', 'Importação'),
                                       ('export', 'Exportação')], string="Tipo", readonly=True)
    state = fields.Selection([('nao_validado', 'Não validado'), ('validado', 'Validado'),
                                        ('submetido', 'Submetido')], string="Estado", readonly=True,
                             default="nao_validado")
    empresa = fields.Many2one('res.company', string="Companhia", readonly=True,
                              default=lambda self: self.env['res.company']._company_default_get('hist.saft'))
    nif = fields.Char(string="NIF", size=64, readonly=True)
    num_faturas = fields.Integer(string="Nº de Faturas", readonly=True)
    valor_credito = fields.Char(string="Valor a Crédito", size=64, readonly=True)
    valor_debito = fields.Char(string="Valor a Débito", size=64, readonly=True)

    # validar registo no historico de saft
    def do_valida(self):
        self.write({'state': 'validado'})

    # submeter registo no historico de saft
    def do_submete(self):
        self.write({'state': 'submetido'})

    # desvalidar registo no historico de saft
    def do_nao_valida(self):
        self.write({'state': 'nao_validado'})
