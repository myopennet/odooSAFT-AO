# -*- coding: utf-8 -*-

from odoo import models, fields


# tabela historico de comunicacoes de guias a at
class PedidosAtHistorico(models.Model):
    _name = "pedidos.at.historico"
    _description = 'Histórico dos pedidos AT'
    _order = 'id desc'

    name = fields.Char(string="Cód. Documento", size=64, copy=False)
    at_code = fields.Char(string="Cód. AT", size=256, copy=False)
    codigo_erro = fields.Char(string="Cód. erro", size=64, copy=False)
    msg_erro = fields.Char(string="Mensagem do erro", size=512, copy=False)
    doc_state = fields.Char(string="Estado do documento", size=8, copy=False)
    user_id = fields.Many2one('res.users', string="Utilizador", required=True, copy=False)
    pedido = fields.Text(string="Pedido", copy=False)


# tabela que grava o utilizador e as suas credenciais de acesso para ser feita a comunicacao de guias a at
class UtilizadorFinancas(models.Model):
    _name = "utilizador.financas"
    _description = 'Utilizador das finanças'

    name = fields.Char(string="Permissão", size=64, required=True, default="WDT", copy=False)
    user = fields.Char(string="Utilizador", size=64, required=True, copy=False)
    passe = fields.Char(string="Senha", size=64, required=True, copy=False)
    company_id = fields.Many2one('res.company',
                                 string="Empresa",
                                 required=True,
                                 default=lambda self: self.env.user.company_id,
                                 copy=False)
    por_defeito = fields.Boolean(string="Preenchimento automático",
                                 help="Assinalar (visto) caso seja para o sistema preencher automaticamente "
                                      "a data de carga, matricula,etc.",
                                 default=False, copy=False)
    por_defeito_matricula = fields.Char(string="Matricula", size=16,
                                        help="Matricula a usar quando é para preencher por defeito a mesma, "
                                             "pode deixar em branco.",
                                        copy=False)
    por_defeito_minutos = fields.Integer(string="Minutos adicionais",
                                         help="Tempo em minutos a adicionar à hora em que a guia é validada para o "
                                              "campo hora de carga.",
                                         copy=False)
