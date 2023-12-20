from odoo import api, models, fields

class ProviderMap(models.Model):
    _name = 'provider.map'

    fatura_id = fields.Many2one('account.move', string='Fatura')
    contador = fields.Integer(string='Nº Ordem', compute='_compute_contador')
    tipo_operacao = fields.Selection(string="Tipo de Operação", related='fatura_id.operation_type')
    numero_de_identifacao_fiscal = fields.Char(string="Número de Identificação Fiscal",
                                               related="fatura_id.partner_id.commercial_partner_id.vat")
    empresa = fields.Char(string="Nome / Firma", related="fatura_id.commercial_partner_id.name")
    tipo_documento = fields.Char(string="Tipo de Documento", compute="_compute_tipo_documento")
    data_documento = fields.Date(string="Data do Documento", related="fatura_id.invoice_date")
    referencia = fields.Char(string="Nº do Documento")
    valor_documento = fields.Monetary(string="Valor do Documento", related="fatura_id.amount_total")
    valor_tributavel = fields.Monetary(string="Valor Tributável")
    iva_suportado = fields.Monetary(string="IVA Suportado")
    percentagem_tax = fields.Float(string="IVA Dedutível - %", compute="_compute_tax")
    tipologia = fields.Char(string="Tipologia", compute="_compute_tipologia")
    iva_cativo_percentagem = fields.Float(string="IVA Cativo - %", default=0.00)
    iva_cativo_valor = fields.Float(string="IVA Cativo - Valor", default=0.00)
    linha_destino = fields.Char(string="Linha de Destino", compute="_compute_linha_destino")
    currency_id = fields.Many2one('res.currency', string='Currency', related='fatura_id.currency_id')

    def _compute_contador(self):
        counter = 0
        for invoice in self:
            invoice.contador = counter + 1
            counter+=1

    def _compute_tipo_documento(self):
        for invoice in self:
            invoice.tipo_documento = invoice.fatura_id.journal_id.saft_inv_type

    def _compute_tax(self):
        for invoice in self:
            invoice.percentagem_tax = (invoice.iva_suportado * 100)
            if invoice.iva_suportado > 0:
                invoice.percentagem_tax = invoice.percentagem_tax / invoice.fatura_id.amount_untaxed_signed
            invoice.percentagem_tax = abs(round(invoice.percentagem_tax, 2))

    def _compute_tipologia(self):
        for invoice in self:
            if invoice.tipo_operacao == 'meios_fixos_e_investimentos':
                invoice.tipologia = 'MFI'
            elif invoice.tipo_operacao == 'existencias_inventario':
                invoice.tipologia = 'INV'
            elif invoice.tipo_operacao == 'outros_bens_consumo':
                invoice.tipologia = 'OBC'
            elif invoice.tipo_operacao == 'servicos':
                invoice.tipologia = 'SERV'
            elif invoice.tipo_operacao == 'importacao':
                invoice.tipologia = 'IMPT'
            elif invoice.tipo_operacao == 'servicos_contratados_no_engenheiro':
                invoice.tipologia = 'SCE'
            else:
                invoice.tipologia = ''

    def _compute_linha_destino(self):
        for invoice in self:
            if invoice.tipo_operacao == 'meios_fixos_e_investimentos':
                invoice.linha_destino = 16
            elif invoice.tipo_operacao == 'existencias_inventario':
                invoice.linha_destino = 18
            elif invoice.tipo_operacao == 'outros_bens_consumo':
                invoice.linha_destino = 20
            elif invoice.tipo_operacao == 'servicos':
                invoice.linha_destino = 22
            elif invoice.tipo_operacao == 'importacao':
                invoice.linha_destino = 24
            elif invoice.tipo_operacao == 'servicos_contratados_no_engenheiro':
                invoice.linha_destino = 14
            else:
                invoice.linha_destino = ''

    