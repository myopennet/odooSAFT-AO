# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import re


prefixo_journal_type = {'cash': 'CSH', 'bank': 'BNK', 'sale': 'VD', 'purchase': 'CP', 'general': 'DIV'}


class AccountJournal(models.Model):
    """ Adição de campos requeridos pelo saft:
    3.4.3.7  trasaction_type - para filtrar na contabilidade os tipos de transação conforme abaixo
    4.1.4.2/8  self_billing - servirá para preencher os campos 4.1.4.2 InvoiceStatus e 4.1.4.8 SelfBillingIndicator,
    nos casos de auto-facturação
    4.1.2.7    InvoiceType  classificar com um de FT, ND, NC  ou VD e AA alienação Acivos ou DA - devol activos
    """
    _inherit = "account.journal"

    sequence_id = fields.Many2one('ir.sequence', string='Entry Sequence',
                                  help="This field contains the information related to the numbering of the journal entries of this journal.",
                                  copy=False)
    refund_sequence_id = fields.Many2one('ir.sequence', string='Credit Note Entry Sequence',
                                         help="This field contains the information related to the numbering of the credit note entries of this journal.",
                                         copy=False)
    sequence_number_next = fields.Integer(string='Next Number',
                                          help='The next sequence number will be used for the next invoice.',
                                          compute='_compute_seq_number_next',
                                          inverse='_inverse_seq_number_next')
    refund_sequence_number_next = fields.Integer(string='Credit Notes Next Number',
                                                 help='The next sequence number will be used for the next credit note.',
                                                 compute='_compute_refund_seq_number_next',
                                                 inverse='_inverse_refund_seq_number_next')
    self_billing = fields.Boolean(string="Auto-Facturação",
                                  help="Assinale, se este diário se destina a registar Auto-facturação. As facturas "
                                       "emitidas em substituição dos fornecedores, ao abrigo de acordos de "
                                       "auto-facturação, são assinaladas como tal no SAFT",
                                  copy=False)
    transaction_type = fields.Selection([('N', 'Normal'),
                                         ('R', 'Regularizações'),
                                         ('A', 'Apur. Resultados'),
                                         ('J', 'Ajustamentos')],
                                        string="Tipo de Lançamento",
                                        help="Categorias para classificar os movimentos contabilísticos ao exportar "
                                             "o SAFT",
                                        default="N",
                                        copy=False)
    saft_inv_type = fields.Selection([('FT', 'Factura'),
                                      ('FR', 'Factura Recibo'),
                                      ('ND', 'Nota de débito'),
                                      ('VD', 'Venda a Dinheiro'),
                                      ('AA', 'Alienação de Activos'),
                                      ('DA', 'Devolução de Activos'),
                                      ('FS', 'Fatura Simplificada'),
                                      ('receipt', 'Recibo'),
                                      ('payment', 'Pagamento'),
                                      ('RC', 'Recibo Emitido'),
                                      ('AR', 'Aviso de Cobrança/Recibo'),
                                      ('RG', 'Outros Recibos Emitidos')],
                                     string="Tipo de Documento",
                                     help="Categorias para classificar os documentos comerciais, na exportação do SAFT",
                                     default="FT",
                                     copy=False)
    por_defeito = fields.Boolean(string="Diário por defeito", copy=False)
    manual = fields.Boolean(string="Faturação Manual", copy=False)
    integrado = fields.Boolean(string="Integrado", help="Documentos integrados de outra aplicação", copy=False)
    paga_me = fields.Boolean(string="Pagamento Automático",
                             help="Selecionar isto se quer que as faturas no Diário de VDs seja automaticamente pago",
                             default=False, copy=False)
    allow_date = fields.Boolean(string="Verificar Periodo", default=True, copy=False)
    refund_sequence = fields.Boolean(string='Dedicated Credit Note Sequence',
                                     help="Check this box if you don't want to share the same sequence for invoices and "
                                          "credit notes made from this journal", default=True)

    @api.model
    def create(self, vals):
        if 'sequence_id' not in vals or vals['sequence_id'] is False:
            values_sequence = {'name': _(vals['name']),
                               'prefix': _(vals['code']) + '/'}
            ir_sequence = self.env['ir.sequence'].create(values_sequence)
            vals['sequence_id'] = ir_sequence.id
        if 'refund_sequence_id' not in vals or vals['refund_sequence_id'] is False:
            values_sequence_refund = {'name': vals['name'],
                                      'prefix': 'R' + vals['code'] + '/'}
            refund_ir_sequence = self.env['ir.sequence'].create(values_sequence_refund)
            vals['refund_sequence_id'] = refund_ir_sequence.id
        return super(AccountJournal, self).create(vals)

    # do not depend on 'sequence_id.date_range_ids', because
    # sequence_id._get_current_sequence() may invalidate it!
    @api.depends('sequence_id.use_date_range', 'sequence_id.number_next_actual')
    def _compute_seq_number_next(self):
        '''Compute 'sequence_number_next' according to the current sequence in use,
        an ir.sequence or an ir.sequence.date_range.
        '''
        for journal in self:
            if journal.sequence_id:
                sequence = journal.sequence_id._get_current_sequence()
                journal.sequence_number_next = sequence.number_next_actual
            else:
                journal.sequence_number_next = 1

    def _inverse_seq_number_next(self):
        '''Inverse 'sequence_number_next' to edit the current sequence next number.
        '''
        for journal in self:
            if journal.sequence_id and journal.sequence_number_next:
                sequence = journal.sequence_id._get_current_sequence()
                sequence.sudo().number_next = journal.sequence_number_next

    # do not depend on 'refund_sequence_id.date_range_ids', because
    # refund_sequence_id._get_current_sequence() may invalidate it!
    @api.depends('refund_sequence_id.use_date_range', 'refund_sequence_id.number_next_actual')
    def _compute_refund_seq_number_next(self):
        '''Compute 'sequence_number_next' according to the current sequence in use,
        an ir.sequence or an ir.sequence.date_range.
        '''
        for journal in self:
            if journal.refund_sequence_id and journal.refund_sequence:
                sequence = journal.refund_sequence_id._get_current_sequence()
                journal.refund_sequence_number_next = sequence.number_next_actual
            else:
                journal.refund_sequence_number_next = 1

    def _inverse_refund_seq_number_next(self):
        '''Inverse 'refund_sequence_number_next' to edit the current sequence next number.
        '''
        for journal in self:
            if journal.refund_sequence_id and journal.refund_sequence and journal.refund_sequence_number_next:
                sequence = journal.refund_sequence_id._get_current_sequence()
                sequence.sudo().number_next = journal.refund_sequence_number_next

    # codigo do diario tem de ser alfanomérico
    @api.constrains('code')
    def _check_code(self):
        # Retirar carateres que nao sejam alfanumericos
        for journal in self:
            if not journal.code.isalnum():
                journal.code = re.sub('[^A-Za-z0-9]', '', journal.code)

            # Verificar codigos repetidos
            if len(self.search([('code', '=', journal.code), ('company_id', '=', self.env.user.company_id.id),
                                ('id', '!=', journal.id)])) > 0:
                # Se vier do metodo duplicar gera o codigo, caso contrario da um erro
                if self.env.context.get('defcopy'):
                    ctx = self.env.context.copy()
                    del ctx['defcopy']
                    journal.code = journal.with_context(ctx).generate_code()
                else:
                    raise ValidationError('Este código já existe noutro diário')
        return True

    # Se o diario for de vendas ou compras tem de ter sequencia de retorno
    @api.constrains('type')
    def _check_type(self):
        # Retirar carateres que nao sejam alfanumericos
        for journal in self:
            if journal.type in ['sale', 'purchase'] and not journal.refund_sequence_id:
                raise ValidationError('O diário tem de ter sequência de reembolso')
        return True

    @api.onchange('code')
    def _onchange_code(self):
        # Retirar carateres que nao sejam alfanumericos
        for journal in self:
            if journal.code:
                journal.code = re.sub('[^A-Za-z0-9]', '', journal.code)

    
    def copy(self, default=None):
        ctx = self.env.context.copy()
        ctx['defcopy'] = True
        return super(AccountJournal, self.with_context(ctx)).copy(default)

    
    def generate_code(self):
        for journal in self:
            if self.search([('code', '=', journal.code), ('company_id', '=', self.env.user.company_id.id)]):
                for num in range(1, 100):
                    # journal_code has a maximal size of 5, hence we can enforce the boundary num < 100
                    journal_code = prefixo_journal_type[journal.type] + str(num)
                    if not self.env['account.journal'].search(
                            [('code', '=', journal_code), ('company_id', '=', self.env.user.company_id.id)], limit=1):
                        return journal_code
        return journal.code

    
    def write(self, vals):
        # verificar manual e integrado
        for journal in self:
            if 'manual' in vals or 'integrado' in vals:
                total = self.env['account.payment'].search_count([('journal_id', '=', journal.id)])
                total += self.env['account.move'].search_count([('journal_id', '=', journal.id)])

                if 'manual' in vals and total > 0:
                    raise ValidationError(_('Não pode definir o diário como manual, '
                                            'pois este já entra em faturas ou recibos.'))

                if 'integrado' in vals and total > 0:
                    raise ValidationError(_('Não pode definir o diário como integrado, '
                                            'pois este já entra em faturas ou recibos.'))

        return super(AccountJournal, self).write(vals)
