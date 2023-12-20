# -*- coding: utf-8 -*-

from odoo import models, fields, api


class IrSequenceAtcud(models.Model):
    _name = "ir.sequence.atcud"

    sequence_id = fields.Many2one('ir.sequence', string="Sequência", readonly=True)
    codigo_validacao_serie = fields.Char(string="Código de Validação de Série",
                                         help="Código único para esta série a fornecer pela AT.", readonly=True)
    identificador_serie = fields.Char(string="Identificador da Série", readonly=True)
    inicio_numeracao = fields.Char(string="Início da Numeração", readonly=True)
    tipo_documento = fields.Char(string="Tipo de Documento", readonly=True)

    
    def open_wizard(self):
        for seqs in self:
            action = self.env.ref('opc_certification_ao.action_wizard_alert_atcud').read()[0]
            action['views'] = [(False, 'form')]
            action['context'] = {'default_hide': '1',
                                 'default_sequence_id': seqs.sequence_id.id,
                                 'default_codigo_validacao_serie': seqs.codigo_validacao_serie,
                                 'default_identificador_serie': seqs.identificador_serie,
                                 'default_inicio_numeracao': seqs.inicio_numeracao,
                                 'default_tipo_documento': seqs.tipo_documento,
                                 }
            return action