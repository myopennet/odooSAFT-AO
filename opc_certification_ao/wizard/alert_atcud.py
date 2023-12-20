from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime
import qrcode
import base64
from io import BytesIO


class AlertAtcud(models.TransientModel):
    _name = "alert.atcud"
    _description = "Wizard de adicao de atcud"

    def _compute_qr_code_image(self, qr_code_data):
        qr = qrcode.QRCode(
            version=10,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=2,
            border=2,
        )
        qr.add_data(qr_code_data)
        qr.make(fit=True)
        img = qr.make_image()
        temp = BytesIO()
        img.save(temp, format="PNG")
        qr_image = base64.b64encode(temp.getvalue())
        return qr_image

    
    def get_tipo_documento_from_sequence(self, sequence_id):

        #VENNDAS
        if sequence_id.code == 'sale.order.or':
            type = 'OR'
        elif sequence_id.code == 'pro.forma':
            type = 'PP'
        elif sequence_id.code == 'cosignation':
            type = 'FC'
        elif sequence_id.code == 'nota.encomenda':
            type = 'NE'

        #FATURAS
        account_journal = self.env['account.journal']
        for journal in account_journal.search([('sequence_id', '=', sequence_id.id) ]):
            type = journal.saft_inv_type
        for journal in account_journal.search([('refund_sequence_id', '=', sequence_id.id)]):
            type = 'NC'

        #RECIBOS
        if sequence_id.code in ('account.payment.transfer', 'account.payment.customer.invoice',
                         'account.payment.customer.refund', 'account.payment.supplier.refund',
                         'account.payment.supplier.invoice'):
            type = 'RG'

        #GUIAS
        stock_picking_type = self.env['stock.picking.type']
        for picking_types in stock_picking_type.search(['|', ('sequence_id_validate', '=', sequence_id.id),
                                                        ('sequence_id_gd_validate', '=', sequence_id.id)]):
            if picking_types.code == 'incoming':
                type = 'GD'
            if picking_types.code == 'outgoing':
                type = 'GR'
            if picking_types.code == 'internal':
                type = 'GT'

        if sequence_id.code == 'stock.picking.out.validate':
            type = 'GR'
        if sequence_id.code == 'stock.picking.internal.validate':
            type = 'GT'
        if sequence_id.code == 'stock.picking.gd.validate':
            type = 'GD'

        return type

    
    def get_identificador_serie(self, sequence_id, date):
        if sequence_id and sequence_id.id:
            ano = ''
            if '%(year)s' in sequence_id.prefix:
                ano = str(datetime.now())[:4]
            elif '%(range_year)s' in sequence_id.prefix and date:
                ano = str(date)[:4]
            try:
                identificador = sequence_id.prefix.split(' ')[1].replace('/', '')
            except:
                identificador = sequence_id.prefix.split('%')[0].replace('/', '')
            if not identificador:
                identificador = self.get_tipo_documento_from_sequence(sequence_id)
            return identificador.replace('%(year)s', '').replace('%(range_year)s', '') + ano

    
    def _get_sequences_that_need_atcud(self):
        list_of_sequences = []
        ir_sequence = self.env['ir.sequence']
        account_journal = self.env['account.journal']
        stock_picking_type = self.env['stock.picking.type']

        #vendas e recibos
        list_of_codes = ('sale.order.or', 'pro.forma', 'cosignation', 'nota.encomenda',
                         'account.payment.transfer', 'account.payment.customer.invoice',
                         'account.payment.customer.refund', 'account.payment.supplier.refund',
                         'account.payment.supplier.invoice')
        for seqs in ir_sequence.search([('code', 'in', list_of_codes)]):
            if seqs not in list_of_sequences:
                list_of_sequences.append(seqs)

        #faturacao
        for journal_id in account_journal.search([('type', '=', 'sale')]):
            if journal_id.sequence_id.id and journal_id.sequence_id not in list_of_sequences:
                list_of_sequences.append(journal_id.sequence_id)
            if journal_id.refund_sequence_id.id and journal_id.refund_sequence_id not in list_of_sequences:
                list_of_sequences.append(journal_id.refund_sequence_id)

        #guias
        for picking_types in stock_picking_type.search([]):
            if picking_types.sequence_id_validate.id and picking_types.sequence_id_validate not in list_of_sequences:
                list_of_sequences.append(picking_types.sequence_id_validate)
            if picking_types.sequence_id_gd_validate.id and picking_types.sequence_id_gd_validate not in list_of_sequences:
                list_of_sequences.append(picking_types.sequence_id_gd_validate)


        for seqs_validate in ir_sequence.search([('code', 'ilike', 'validate')]):
            if seqs_validate not in list_of_sequences:
                list_of_sequences.append(seqs_validate)

        for data in list_of_sequences:
            if 'fornecedor' in data.name:
                list_of_sequences.remove(data)
        return list_of_sequences

    
    def treat_sequences(self):
        list_of_atcud_sequences = self.env['ir.sequence.atcud']
        list_of_atcud_sequences.sudo().search([]).unlink()
        for ses in self._get_sequences_that_need_atcud():
            date_range = self._get_date_range(ses.id, False, False)
            if date_range:
                inicio_numeracao = date_range.number_next_actual
            else:
                inicio_numeracao = ses.number_next_actual

            list_of_atcud_sequences.sudo().create({
                'sequence_id': ses.id,
                'codigo_validacao_serie': self._get_codigo_validacao_serie(ses, str(datetime.now())[:10]),
                'identificador_serie': self.get_identificador_serie(ses, False),
                'inicio_numeracao': inicio_numeracao,
                'tipo_documento': self.get_tipo_documento_from_sequence(ses),
            })
    
    def open_sequences(self):
        self.treat_sequences()
        return self.env.ref('opc_certification_ao.action_ir_sequence_atcud').read()[0]

    
    def call_wizard_alert_atcud(self, sequence_id, type_doc, hide):
        action = self.env.ref('opc_certification_ao.action_wizard_alert_atcud').read()[0]
        action['context'] = {'default_sequence_id': sequence_id.id, 'default_tipo_documento': type_doc, 'default_hide': hide}
        return action

    
    def _get_date_range(self, sequence_id, date_start, date_end):
        date_range = self.env["ir.sequence.date_range"].sudo().search(
            [("sequence_id", "=", sequence_id),
             ("date_from", "<=", date_start),
             ("date_to", ">=", date_end)], limit=1)
        return date_range

    
    def add_new_code(self):
        for wizard in self:
            if not wizard.sequence_id:
                raise ValidationError(_('O campo sequência está por preencher.'))
            if wizard.codigo_validacao_serie and wizard.sequence_id.number_next_actual > 1 \
                    and wizard.sequence_id.codigo_validacao_serie:
                raise ValidationError(_('Esta sequência já tem código de validação para documentos anteriores'))
            if not wizard.codigo_validacao_serie:
                raise ValidationError(_('O campo Código de Validação de Série está por preencher. \n'
                                        'Deverá efectuar o pedido à AT deste código e preencher o mesmo antes de proceder. '))
            if not wizard.sequence_id.use_date_range and not wizard.data_prevista_fim and not wizard.data_prevista_fim:
                wizard.sequence_id.codigo_validacao_serie = wizard.codigo_validacao_serie
            else:
                date_range = self._get_date_range(wizard.sequence_id.id,
                                     wizard.data_prevista_inicio,
                                     wizard.data_prevista_fim)
                if date_range:
                    if wizard.codigo_validacao_serie and date_range.number_next_actual > 1 \
                            and date_range.codigo_validacao_serie:
                        raise ValidationError(_('Esta sequência deste período '
                                                'já tem código de validação para documentos anteriores'))
                    date_range.codigo_validacao_serie = wizard.codigo_validacao_serie
                    wizard.sequence_id.use_date_range = True
                else:
                    if not wizard.inicio_numeracao_new:
                        raise ValidationError(_('O campo próximo número é obrigatório.'))
                    if not wizard.data_prevista_inicio or not wizard.data_prevista_fim:
                        raise ValidationError(_('Os campos datas são obrigatórios.'))
                    self.env["ir.sequence.date_range"].sudo().create({
                        'sequence_id': wizard.sequence_id.id,
                        'date_from': wizard.data_prevista_inicio,
                        'date_to': wizard.data_prevista_fim,
                        'number_next_actual': int(wizard.inicio_numeracao_new),
                        'codigo_validacao_serie': str(wizard.codigo_validacao_serie),
                    })

            self.treat_sequences()
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }

    
    def _get_codigo_validacao_serie(self, sequence_id, date_start):
        if sequence_id:
            sequence_id_search = self.env['ir.sequence'].sudo().search([('id', '=', sequence_id.id)])
            if sequence_id_search.use_date_range:
                return self._get_date_range(sequence_id.id, date_start, date_start).codigo_validacao_serie
            else:
                return sequence_id_search.codigo_validacao_serie
        else:
            return False

    
    def change_prefix_year(self):
        for wizard in self:
            prefixo = wizard.sequence_id.prefix
            if '%(year)s' in prefixo:
                ano = str(datetime.now())[:4]
                prefixo = prefixo.replace('%(year)s', ano)
                proximo_numero = 1
                if wizard.sequence_id.number_next_actual > 1:
                    self.env.cr.execute("update ir_sequence set prefix ='"+str(prefixo)+"' where id="+str(wizard.sequence_id.id))
                else:
                    wizard.sequence_id.prefix = prefixo

                self.treat_sequences()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }

    @api.depends('sequence_id', 'data_prevista_inicio', 'data_prevista_fim')
    def _get_dados(self):
        for wizard in self:
            if wizard.sequence_id:
                wizard.show_error, wizard.error_message = False, ''
                if not wizard.sequence_id.use_date_range and '%' in wizard.sequence_id.prefix:
                    wizard.show_error = True
                    wizard.error_message = _('Erro na sequência. \nO campo prefixo não pode incluir'
                                            ' percentagens, a menos que defina sequências diferentes por período.\n\n'
                                             'Clique no botão em baixo "Alterar Prefixo" para fixar o ano corrente '
                                             'no prefixo em vez da variável com percentagem.')
                wizard.identificador_serie = self.get_identificador_serie(wizard.sequence_id, wizard.data_prevista_inicio)
                date_range = self._get_date_range(wizard.sequence_id.id,
                                                               wizard.data_prevista_inicio,
                                                               wizard.data_prevista_fim)
                if date_range:
                    wizard.inicio_numeracao = date_range.number_next_actual
                    wizard.codigo_validacao_serie = date_range.codigo_validacao_serie
                else:
                    wizard.inicio_numeracao = wizard.sequence_id.number_next_actual
                    wizard.codigo_validacao_serie = wizard.sequence_id.codigo_validacao_serie
                if wizard.data_prevista_inicio and wizard.data_prevista_fim and not date_range:
                    wizard.inicio_numeracao_boolean = True
                else:
                    wizard.inicio_numeracao_boolean = False

    @api.onchange('sequence_id', 'data_prevista_inicio', 'data_prevista_fim')
    def _onchange_codigo_validacao(self):
        for wizard in self:
            date_range = self._get_date_range(wizard.sequence_id.id,
                                              wizard.data_prevista_inicio,
                                              wizard.data_prevista_fim)
            if date_range:
                wizard.codigo_validacao_serie = date_range.codigo_validacao_serie
            else:
                date_range = self._get_date_range(wizard.sequence_id.id,
                                                  str(datetime.now())[:10],
                                                  str(datetime.now())[:10])
                if date_range:
                    wizard.codigo_validacao_serie = date_range.codigo_validacao_serie
                else:
                    wizard.codigo_validacao_serie = wizard.sequence_id.codigo_validacao_serie

    sequence_id = fields.Many2one('ir.sequence', string="Sequência", readonly=True)
    codigo_validacao_serie = fields.Char(string="Código de Validação de Série",
                                         help="Código único para esta série a fornecer pela AT.")
    identificador_serie = fields.Char(string="Identificador da Série", compute=_get_dados)
    inicio_numeracao = fields.Char(string="Início da Numeração", compute=_get_dados)
    inicio_numeracao_new = fields.Char(string="Início da Numeração")
    data_prevista_inicio = fields.Date(string="Data Prevista de Início", help="Deixe vazio para definir novo código sem datas")
    data_prevista_fim= fields.Date(string="Data Prevista de Fim")
    tipo_documento = fields.Char(string="Tipo de Documento", readonly=True)
    inicio_numeracao_boolean = fields.Boolean(string="Check if Inicio de Numeracao", compute=_get_dados)
    show_error = fields.Boolean(string="Show Error", compute=_get_dados)
    error_message = fields.Text(string="Error Message", compute=_get_dados)
    hide = fields.Selection([('0', '0'),('1', '1'),('2', '2')], default='0')

    
    def act_fechar(self):
        return {'type': 'ir.actions.act_window_close'}

    
    def act_cancel(self):
        self.env['account.move'].check_advance()
        fatura = self.env['account.move'].browse(self.env.context.get('active_id'))
        fatura.reason_cancel = self.descricao_cancel
        fatura.action_invoice_cancel()
