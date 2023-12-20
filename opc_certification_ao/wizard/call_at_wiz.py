# -*- coding: utf-8 -*-

from odoo import models, fields, api


# tabela models.Model pois pode ser necessário verificar o valor do campo 'resultado'
class CallAtWiz(models.Model):
    _name = "call.at.wiz"
    _description = "Wizard para pedir codigos AT para uma ou varias guias na vista de tree"

    data = fields.Datetime('Data de Carga', default=fields.Datetime.now())
    resultado = fields.Text('Resultado')

    
    def act_destroy(self):
        """ Fechar wizard
        """
        return {'type': 'ir.actions.act_window_close'}

    
    def call_at_multi(self):
        """ Pedir código AT para guias seleccionadas na vista de tree
            e preencher no campo Data de Carga o valor seleccionado no wizard
        """
        result_positivo = []
        result_negativo = []
        if 'active_ids' in self.env.context and self.env.context['active_ids'] != []:
            guias = self.env['stock.picking'].search(['|', ('at_code', '=', False),
                                                           ('at_status', '=', 'error'),
                                                           ('id', 'in', self.env.context['active_ids']),
                                                           ('state', '=', 'done')])
            for guia in guias:
                # definir a data de carga atual na guia (data_carga)
                guia.data_carga = self.data
                guia.callWebServiceGR()
                if guia.at_status == 'validated':
                    result_positivo.append(guia.name)
                else:
                    result_negativo.append(guia.name)

        self.resultado = "Com sucesso: " + " ".join(result_positivo) + "\nSem sucesso: " + " ".join(result_negativo)

        return {
            'name': 'Pedir Código AT',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'call.at.wiz',
            'type': 'ir.actions.act_window',
            'res_id': self.id,
            'target': 'new',
        }
