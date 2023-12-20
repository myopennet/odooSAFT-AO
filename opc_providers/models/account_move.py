from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'
    
    operation_type = fields.Selection([('meios_fixos_e_investimentos', 'Meios Fixos e Investimentos'),('existencias_inventario', 'Existências/Inventário'),('outros_bens_consumo', 'Outros Bens de Consumo'),('servicos', 'Serviços'),('importacao', 'Importação'),('servicos_contratados_no_engenheiro', 'Serviços Contratados no Engenheiro')], string="Tipo de Operação")