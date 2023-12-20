# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, RedirectWarning, ValidationError
from datetime import datetime
from pytz import timezone
from . import hash_generation
from . import qr_code_generation

tz_pt = timezone('Europe/Lisbon')


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def _get_sequence_for_atcud(self):
        for payment in self:
            sequence_code = False
            if payment.payment_type == 'transfer':
                sequence_code = 'account.payment.transfer'
            else:
                if payment.partner_type == 'customer':
                    if payment.payment_type == 'inbound':
                        sequence_code = 'account.payment.customer.invoice'
                    if payment.payment_type == 'outbound':
                        sequence_code = 'account.payment.customer.refund'
                if payment.partner_type == 'supplier':
                    if payment.payment_type == 'inbound':
                        sequence_code = 'account.payment.supplier.refund'
                    if payment.payment_type == 'outbound':
                        sequence_code = 'account.payment.supplier.invoice'
            return self.env['ir.sequence'].sudo().search([('code', '=', sequence_code),
                                                          ('company_id', 'in', (payment.company_id.id, False))],
                                                         limit=1)

    def _compute_atcud(self):
        for payment in self:
            payment.atcud = ''
            needs_atcud = self.env['ir.config_parameter'].sudo().get_param('needs_atcud')
            if payment.hash and needs_atcud == 'True':
                wizard_atcud = self.env['alert.atcud']
                sequence_id = payment._get_sequence_for_atcud()
                codigo_validacao_serie = wizard_atcud._get_codigo_validacao_serie(sequence_id, payment.date)
                if codigo_validacao_serie:
                    n_sequencial_serie = payment.name.split('/')[1]
                    payment.atcud = _(codigo_validacao_serie) + '-' + n_sequencial_serie

    def _get_qr_code_generation(self):
        for payment in self:
            payment.qr_code_at = ''
            if payment.hash:
                nif_empresa = payment.company_id.vat
                nif_cliente = payment.partner_id.commercial_partner_id and payment.partner_id.commercial_partner_id.vat or \
                              payment.partner_id.vat
                pais_cliente = payment.partner_id.commercial_partner_id and payment.partner_id.commercial_partner_id.country_id and \
                               payment.partner_id.commercial_partner_id.country_id.code or (
                                           payment.partner_id.country_id and \
                                           payment.partner_id.country_id.code or 'PT')
                wizard_atcud = self.env['alert.atcud']
                tipo_documento = wizard_atcud.get_tipo_documento_from_sequence(self._get_sequence_for_atcud())
                doc_state = 'N'
                if payment.state == 'cancel':
                    doc_state = 'A'
                doc_date = payment.date
                numero = payment.name
                atcud = payment.atcud
                espaco_fiscal = '0'

                valor_base_isento = 0
                valor_base_red = 0
                valor_iva_red = 0
                valor_base_int = 0
                valor_iva_int = 0
                valor_base_normal = 0
                valor_iva_normal = 0
                valor_n_sujeito_iva = 0
                imposto_selo = 0
                retencao_na_fonte = 0

                total_impostos = 0.00
                total_com_impostos = 0.00

                quatro_caratecters_hash = _(payment.hash[0:1]) + _(payment.hash[10:11]) + _(payment.hash[20:21]) + \
                                          _(payment.hash[30:31])
                n_certificado = '1456'
                outras_infos = ''

                payment.qr_code_at = qr_code_generation.qr_code_at(nif_empresa, nif_cliente, pais_cliente,
                                                                   tipo_documento,
                                                                   doc_state, doc_date, numero, atcud, espaco_fiscal,
                                                                   round(valor_base_isento, 2),
                                                                   round(valor_base_red, 2),
                                                                   round(valor_iva_red, 2),
                                                                   round(valor_base_int, 2),
                                                                   round(valor_iva_int, 2),
                                                                   round(valor_base_normal, 2),
                                                                   round(valor_iva_normal, 2),
                                                                   round(valor_n_sujeito_iva, 2),
                                                                   round(imposto_selo, 2),
                                                                   round(total_impostos, 2),
                                                                   round(total_com_impostos, 2),
                                                                   round(retencao_na_fonte, 2),
                                                                   quatro_caratecters_hash,
                                                                   n_certificado, outras_infos)

    def _compute_qr_code_image(self):
        for payment in self:
            payment.qr_code_at_img = self.env['alert.atcud']._compute_qr_code_image(payment.qr_code_at)

    hash = fields.Char(string="Hash", size=256, readonly=True, help="Unique hash of the sale order.", copy=False)
    hash_control = fields.Char(string="Chave", size=40, copy=False)
    hash_date = fields.Datetime(string="Data em que o hash foi gerado", copy=False)
    atcud = fields.Char(compute='_compute_atcud', string='ATCUD')
    qr_code_at = fields.Char(compute='_get_qr_code_generation', string='QR Code AT')
    qr_code_at_img = fields.Binary("QR Code", compute='_compute_qr_code_image')

    def unlink(self):
        if any(rec.hash != False and rec.partner_type != 'supplier' for rec in self):
            raise UserError(_("Não pode apagar um pagamento que já tenha sido validado!"))

        if any(rec.state != 'draft' and rec.payment_type == 'inbound' for rec in self):
            raise UserError(_(u'Não pode eliminar pagamentos que não sejam rascunhos.'))
        return super(AccountPayment, self).unlink()

    def validar_hash(self):
        for payment in self:
            # verificar se é a primeira factura ou nota de credito
            ano = payment.date.year
            data_inicio = '01-01-' + _(ano)
            data_inicio = datetime.strptime(data_inicio, '%d-%m-%Y')
            data_fim = '31-12-' + _(ano)
            data_fim = datetime.strptime(data_fim, '%d-%m-%Y')
            numHash = self.env['account.payment'].search_count([
                ('partner_type', '=', payment.partner_type),
                ('id', '!=', payment.id),
                ('journal_id', '=', payment.journal_id.id),
                ('date', '<=', data_fim),
                ('date', '>=', data_inicio),
                ('state', '=', 'posted')
            ])
            # Se não for a primeira factura ou nota de encomenda vai buscar o hash anterior
            antigoHash = False
            if numHash > 0:
                antigoHash = self.env['account.payment'].search([
                    ('partner_type', '=', payment.partner_type),
                    ('id', '!=', payment.id),
                    ('journal_id', '=', payment.journal_id.id),
                    ('date', '<=', data_fim),
                    ('date', '>=', data_inicio),
                    ('state', '=', 'posted')
                ], order='id desc', limit=1).hash

                # antigoHash = self.env['account.payment'].search[
                #     ('partner_type', '=', payment.partner_type),
                #     ('id', '!=', payment.id),
                #     ('journal_id', '=', payment.journal_id.id),
                #     ('date', '<=', data_fim),
                #     ('date', '>=', data_inicio),
                #     ('state', '=', 'posted')
                # ], order = 'id desc', limit = 1).hash
                #
                # self.env.cr.execute("""
                #     SELECT ap.hash
                #     FROM account_payment ap, (
                #         SELECT max(id)
                #         FROM account_payment
                #         WHERE company_id= %s and journal_id=%s and hash != '' and id!=%s and partner_type=%s) mso
                #     WHERE ap.id = mso.max""",
                #                     (payment.company_id.id, payment.journal_id.id, payment.id, payment.partner_type))
                # antigoHash = self.env.cr.fetchone()[0]
                print(antigoHash)
            return numHash, antigoHash

    def create_hash(self):
        for payment in self:
            # Vai buscar a data da criação(datetime.now) todo datetime %Y-%m-%d %H-%M-%S
            self.env.cr.execute('SELECT write_date FROM account_payment WHERE id=%s', (payment.id,))
            datasistema = str(self.env.cr.fetchone()[0])[:19]
            datadocumento = payment.date
            numHash, antigoHash = payment.validar_hash()
            totalbruto = str(payment.amount)
            if (totalbruto.find('.') + 2) == len(totalbruto):
                totalbruto += "0"
            if not antigoHash:
                antigoHash = 'antigohash'
            number = payment.journal_id.saft_inv_type + ' ' + payment.name
            values = hash_generation.hash(self, payment.journal_id.manual, datadocumento,
                                          datasistema, number, numHash, antigoHash, totalbruto)
            payment.write(values)

    def action_post(self):
        for payment in self:
            if payment.payment_type == 'inbound':
                # ATCUD#
                needs_atcud = self.env['ir.config_parameter'].sudo().get_param('needs_atcud')
                if needs_atcud == 'True':
                    wizard_alert_atcud = self.env['alert.atcud']
                    sequence_id_atcud = payment._get_sequence_for_atcud()
                    codigo_validacao_serie = wizard_alert_atcud._get_codigo_validacao_serie(sequence_id_atcud,
                                                                                            payment.date)
                    if not codigo_validacao_serie:
                        if self.env.user.has_group('account.group_account_manager'):
                            action = self.env.ref('opc_certification.action_ir_sequence_atcud')
                            wizard_alert_atcud.treat_sequences()
                            msg = _(
                                'Falta definir o codigo de validação de sequência AT. '
                                '\nPor favor aceda a Faturação \ Configuração \ Configurar ATCUD ou clique no link abaixo.')
                            raise RedirectWarning(msg, action.id, _('Aceder ao menu de Configuração ATCUD'))
                        else:
                            raise UserError(_(
                                'Falta definir o codigo de validação de sequência AT. Para configurar, '
                                'deverá aceder ao menu Faturação -> Configuração -> Configurar ATCUD'))
                # FIM ATCUD#

            super(AccountPayment, payment).action_post()
            if payment.partner_id:
                payment.create_hash()