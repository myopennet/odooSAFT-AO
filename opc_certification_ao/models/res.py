# -*- coding: utf-8 -*-
import os

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import json
import logging

import requests

_logger = logging.getLogger(__name__)


# tabela de parceiros - contactos
class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.depends('vat', 'company_id')
    def _compute_same_vat_partner_id_opc(self):
        for partner in self:
            # use _origin to deal with onchange()
            partner_id = partner._origin.id
            # active_test = False because if a partner has been deactivated you still want to raise the error,
            # so that you can reactivate it instead of creating a new one, which would loose its history.
            Partner = self.with_context(active_test=False).sudo()
            domain = [
                ('vat', '=', partner.vat),
                ('company_id', 'in', [False, partner.company_id.id]),
            ]
            if partner_id:
                domain += [('id', '!=', partner_id), '!', ('id', 'child_of', partner_id)]

            partner.same_vat_partner_id = bool(partner.vat) and not partner.parent_id and Partner.search(domain,
                                                                                                         limit=1)
            if partner.vat == '999999999':
                partner.same_vat_partner_id = False

    # metodo de computa o campo que diz se o nif esta em duplicado ou nao
    @api.depends('vat')
    def _compute_nif_duplicado(self):
        for partner in self:
            if partner.vat and partner.vat != '999999999' and not partner.company_id.validar_nif_duplicados:
                parceiros = self.search([('vat', '=', partner.vat)])
                if len(parceiros) > 1:
                    partner.nif_duplicado = True
                else:
                    partner.nif_duplicado = False
            else:
                partner.nif_duplicado = False

    same_vat_partner_id = fields.Many2one('res.partner', string='Partner with same Tax ID',
                                          compute='_compute_same_vat_partner_id_opc', store=False)
    cash_vat_scheme_indicator = fields.Boolean(string="Iva de Caixa",
                                               help="Assinale se houver adesão ao regime de iva de caixa.",
                                               default=False, copy=False)
    nif_duplicado = fields.Boolean(compute='_compute_nif_duplicado', string="Proibir NIF's Duplicados",
                                   help="Se levar visto, existe um outro parceiro com esse nif.",
                                   default=False, copy=False)
    vat = fields.Char(string="Nº Contribuinte", size=20,
                      help="Número de Identicação Fiscal",
                      default="999999999", copy=False, required=True)
    reg_com = fields.Char(string="N.Registo", size=32, help="Número do registo comercial", copy=False)
    conservatoria = fields.Char(string="Conservatória", size=64, help="Conservatória do registo comercial", copy=False)
    nif_representante = fields.Char(string="NIF do representante", size=20, copy=False)
    nif_toc = fields.Char(string="NIF do TOC", size=20, copy=False)
    fin_code = fields.Char(string="Código do serviço de finanças", size=4, copy=False)
    self_bill_sales = fields.Boolean(string="Auto Faturação para Vendas", copy=False,
                                     help="Assinale se existe acordo de auto-facturação para as vendas a este parceiro")
    self_bill_purch = fields.Boolean(string="Auto Faturação para Compras", copy=False,
                                     help="Assinale se existe acordo de auto-facturação para as compras ao parceiro")
    tipo_cambio = fields.Selection([
        ('Fixo', 'Fixo'),
        ('Variavel', 'Variável')], string='Tipo de Cambio', readonly=False, copy=False, default='Variavel',
        help='Se for fixo as diferenças cambiais são lançadas na conta do cliente, '
             'se for variável as diferenças são lançadas na conta 7861 ou 692.')

    @api.constrains('ref', 'company_id')
    def _check_ref(self):
        for partner in self:
            partner_code_count = self.sudo().search_count([('id', '!=', partner.id),
                                                            ('ref', '=', partner.ref),
                                                            '|', ('company_id', '=', partner.company_id.id),
                                                            ('company_id', '=', False)])
            if partner_code_count > 0:
                raise ValidationError(_("Partner ref must be unique, per company!"))


    @api.constrains('email')
    def _check_email(self):
        # Retirar carateres que nao sejam validos
        if not self.env.context.get('ignore_check', False) and self.email:
            self.with_context({'ignore_check': True}).email = self.email.encode('cp1252', 'ignore')

    @api.model
    def default_get(self, fields):
        """ Definir, por defeito, os valores dos campos:
            opt_out, notify_email, ref, is_company e company_type
        """
        defaults = super(ResPartner, self).default_get(fields)
        defaults.update({'ref': '/'})
        return defaults

    def copy(self, default=None, done_list=None, local=False):
        """ Herança do método copy da tabela res.partner
            ao duplicar um parceiro, preencher o campo vat com
            '999999999' e o campo ref com '/'
        """
        default = {} if default is None else default.copy()
        default.update({'vat': '999999999', 'ref': '/'})
        return super(ResPartner, self).copy(default)

    @api.onchange('tipo_cambio')
    def _onchange_tipo_cambio(self):
        if self.tipo_cambio == 'Fixo':
            self.tipo_cambio = 'Variavel'
            return {
                'warning': {'title': _('Atenção'),
                            'message': _('Esta funcionalidade ainda não está disponível!'), }
            }

    # validacoes ao apagar cliente
    
    def unlink(self):
        for partner in self:
            self.env.cr.execute("select id from stock_picking where partner_id=" + str(partner.id))
            picking_id = self.env.cr.fetchone()
            if picking_id and picking_id[0]:
                raise ValidationError(_('O parceiro entra em guias pelo que apenas o pode desactivar.'))
        return super(ResPartner, self).unlink()

    @api.model
    def _commercial_fields(self):
        remove_vat = super(ResPartner, self)._commercial_fields()
        remove_vat.remove('vat')
        return remove_vat

    
    def write(self, vals):
        Partner = self.env['res.partner']
        AccountMove = self.env['account.move']
        for partner in self:
            if 'vat' in vals and str(vals['vat']) != '999999999' and partner.company_id.validar_nif_duplicados:
                domain = [('vat', '=', str(vals['vat'])),
                          ('id', '!=', partner.id)]
                if 'company_id' in vals and vals['company_id'] is not False:
                    domain.append(('company_id', '=', str(vals['company_id'])))
                    if Partner.search_count(domain) > 0:
                        raise ValidationError(_("Ja existe um parceiro com esse NIF."))

            client_invoices = AccountMove.search_count([('state', '!=', 'draft'),
                                                        ('move_type', 'in', ['out_invoice', 'out_refund']),
                                                        ('partner_id', '=', partner.id)])
            if client_invoices > 0 and partner.vat != '999999999':
                if ('vat' in vals and vals['vat'] != partner.vat) or (
                        'ref' in vals and vals['ref'] != partner.ref):
                    raise ValidationError(_(
                        "Esse parceiro está incluido em documentos contabilisticos, "
                        "pelo que não pode alterar o seu código ou NIF."))

            if 'vat' in vals and str(vals['vat'])[:2] == 'PT':
                vals['vat'] = vals['vat'].replace('PT', '')

        result = super(ResPartner, self).write(vals)
        for partner in self:
            # verificar se esá a tentar tirar o visto cliente em parceiros que tem faturas
            if 'customer' in vals and not vals['customer']:
                faturas = AccountMove.search_count([
                    ('type', 'in', ['out_invoice', 'out_refund']),
                    ('partner_id', '=', partner.id)])
                if faturas > 0:
                    raise ValidationError(_('O parceiro tem de ser cliente porque possui faturas/notas de crédito.'))

            # contactos
            if partner.parent_id and partner.parent_id.id:
                if partner.customer != partner.parent_id.customer:
                    partner.customer = partner.parent_id.customer
                if partner.supplier != partner.parent_id.supplier:
                    partner.supplier = partner.parent_id.supplier
            # fim contactos
        return result

    @api.model
    def create(self, vals):
        """ Herança do método create da tabela res.partner
            se o parceiro tiver um parent, ou seja, um parceiro pai
            o valor do campo is_company é False
            se o parceiro tiver o campo ref preenchido com '/', preencher
            a sequência seguinte definida para os parceiros
        """
        if 'parent_id' in vals and vals['parent_id']:
            vals['is_company'] = False
        if vals.get('ref', '/') == '/' or vals.get('ref', '') == '':
            vals['ref'] = self.env['ir.sequence'].get('parceiros.ref.seq.itc') or '/'

        if 'vat' in vals:
            if str(vals['vat']) == '':
                vals['vat'] = '999999999'

            # contactos
            if 'parent_id' in vals and vals['parent_id']:
                self._cr.execute("select customer,supplier from res_partner where id=" + str(vals['parent_id']))
                parent_partner_id = self._cr.fetchone()
                if parent_partner_id[0] is True:
                    vals['customer'] = True
                else:
                    vals['customer'] = False
                if parent_partner_id[1] is True:
                    vals['supplier'] = True
                else:
                    vals['supplier'] = False
            # fim contactos

        partner = super(ResPartner, self).create(vals)

        self._cr.execute("""
            SELECT rc.validar_nif_duplicados
            FROM res_partner rp, res_company rc
            WHERE rp.company_id=rc.id and rp.id=%s""", (partner.id,))
        validar_nif_duplicados = self._cr.fetchone()
        if partner.vat != '999999999' and validar_nif_duplicados:
            if partner.company_id and partner.company_id.id:
                self._cr.execute("""
                    SELECT id
                    FROM res_partner
                    WHERE vat = %s AND company_id = %s AND id != %s """,
                                 (str(partner.vat), str(partner.company_id.id), str(partner.id)))
            else:
                self._cr.execute("""
                    SELECT id
                    FROM res_partner
                    WHERE vat = %s AND and id != %s """, (str(partner.vat), str(partner.id)))
            parent_partner_id = self._cr.fetchone()
            if parent_partner_id and parent_partner_id[0]:
                if validar_nif_duplicados[0] is not False:
                    raise ValidationError(_("Ja existe um cliente com esse NIF."))
        return partner

    def nif_process(self, type):
        message = ''
        if self.vat != '999999999' and self.vat:
            portugal = self.env['res.country'].search([('code', '=', 'PT'), ('name', '=', 'Portugal')])
            if portugal and (not self.country_id or self.country_id.id == portugal.id):
                self.vat = self.vat.replace("PT", "")
                keys = ['f8a4ca6f9d1d8f8a39a4cba0bb451c2c',
                        '0c3611cbf3ddb8b7ec2af1a4755b1d82',
                        'ad5e6acce3c6e16a7119da7101d7bde8',
                        'ff18d7e9b119f602dcbf9c15e72c701d',
                        '2ff1f934d20e7ffb23dc328c719d0000',
                        'cc0f1dff68c6641b18547700f4605030', ]
                contador = 0
                for key in keys:
                    payload = {'json': '1', 'q': self.vat, 'key': key}
                    r = requests.get("http://www.nif.pt/", params=payload)
                    res = r.text
                    download = json.loads(str(res).replace("'", "\""))
                    if 'message' in download and download['message'] and 'Limit per' in download['message']:
                        contador = contador + 1
                        if contador >= 6:
                            raise ValidationError('Limite de validaçẽs do NIF alcançado.')

                    if not ('message' in download and download['message'] and 'Limit per' in download['message']):
                        if 'is_nif' in download and (not download['is_nif'] or not download['nif_validation']):
                            return {
                                'warning': {'title': _('Atenção'),
                                            'message': _('O NIF é inválido!'), }}
                        name = ''
                        morada = ''
                        cp1 = ''
                        cp2 = ''
                        cidade = ''
                        email = ''
                        telefone = ''
                        website = ''
                        if download['result'] == 'success':
                            if 'title' in download['records'][self.vat] and download['records'][self.vat]['title']:
                                name = download['records'][self.vat]['title']

                            if 'address' in download['records'][self.vat] and download['records'][self.vat]['address']:
                                morada = download['records'][self.vat]['address']

                            if 'pc4' in download['records'][self.vat] and download['records'][self.vat]['pc4']:
                                cp1 = download['records'][self.vat]['pc4']

                            if 'pc3' in download['records'][self.vat] and download['records'][self.vat]['pc3']:
                                cp2 = '-' + download['records'][self.vat]['pc3']

                            if 'city' in download['records'][self.vat] and download['records'][self.vat]['city']:
                                cidade = download['records'][self.vat]['city']

                            if 'contacts' in download['records'][self.vat]:
                                if 'email' in download['records'][self.vat]['contacts'] and \
                                        download['records'][self.vat]['contacts']['email']:
                                    email = download['records'][self.vat]['contacts']['email']

                                if 'phone' in download['records'][self.vat]['contacts'] and \
                                        download['records'][self.vat]['contacts']['phone']:
                                    telefone = download['records'][self.vat]['contacts']['phone']

                                if 'website' in download['records'][self.vat]['contacts'] and \
                                        download['records'][self.vat]['contacts']['website']:
                                    website = download['records'][self.vat]['contacts']['website']

                        return {
                            'name': self.name or name,
                            'vat': self.vat,
                            'street': self.street or morada,
                            'country_id': portugal.id,
                            'city': self.city or cidade,
                            'zip': self.zip or str(cp1 + cp2),
                            'website': self.website or website,
                            'email': self.email or email,
                            'phone': self.phone or telefone,
                        }
        return {}

    
    def verificar_nif(self):
        values = self.nif_process('object')
        if values:
            self.write(values)

    @api.onchange('vat')
    def onchange_nif(self):
        message = ''
        if self.vat != '999999999' and self.vat:
            if not self.country_id or self.country_id.code == 'PT':
                value = {}
                try:
                    keys = ['f8a4ca6f9d1d8f8a39a4cba0bb451c2c',
                            '0c3611cbf3ddb8b7ec2af1a4755b1d82',
                            'ad5e6acce3c6e16a7119da7101d7bde8',
                            'ff18d7e9b119f602dcbf9c15e72c701d',
                            '2ff1f934d20e7ffb23dc328c719d0000',
                            'cc0f1dff68c6641b18547700f4605030', ]
                    contador = 0
                    for key in keys:
                        payload = {'json': '1', 'q': self.vat, 'key': key}
                        r = requests.get("http://www.nif.pt/", params=payload)
                        res = r.text
                        download = json.loads(str(res).replace("'", "\""))
                        if 'message' in download and download['message'] and 'Limit per' in download['message']:
                            contador = contador + 1
                            if contador >= 6:
                                return {
                                    'warning': {'title': _('Atenção'),
                                                'message': _('Limite de validaçẽs do NIF alcançado.'), }
                                }
                        if not ('message' in download and download['message'] and 'Limit per' in download['message']):
                            if 'is_nif' in download and (not download['is_nif'] or not download['nif_validation']):
                                return {
                                    'warning': {'title': _('Atenção'),
                                                'message': _('O NIF é inválido!'), }
                                }
                            name = ''
                            morada = ''
                            cp1 = ''
                            cp2 = ''
                            cidade = ''
                            email = ''
                            telefone = ''
                            website = ''
                            if download['result'] == 'success':
                                if 'title' in download['records'][self.vat] and download['records'][self.vat]['title']:
                                    name = download['records'][self.vat]['title']

                                if 'address' in download['records'][self.vat] and download['records'][self.vat][
                                    'address']:
                                    morada = download['records'][self.vat]['address']

                                if 'pc4' in download['records'][self.vat] and download['records'][self.vat]['pc4']:
                                    cp1 = download['records'][self.vat]['pc4']

                                if 'pc3' in download['records'][self.vat] and download['records'][self.vat]['pc3']:
                                    cp2 = '-' + download['records'][self.vat]['pc3']

                                if 'city' in download['records'][self.vat] and download['records'][self.vat]['city']:
                                    cidade = download['records'][self.vat]['city']

                                if 'contacts' in download['records'][self.vat]:
                                    if 'email' in download['records'][self.vat]['contacts'] and \
                                            download['records'][self.vat]['contacts']['email']:
                                        email = download['records'][self.vat]['contacts']['email']

                                    if 'phone' in download['records'][self.vat]['contacts'] and \
                                            download['records'][self.vat]['contacts']['phone']:
                                        telefone = download['records'][self.vat]['contacts']['phone']

                                    if 'website' in download['records'][self.vat]['contacts'] and \
                                            download['records'][self.vat]['contacts']['website']:
                                        website = download['records'][self.vat]['contacts']['website']

                            value = {
                                'name': self.name or name,
                                'vat': self.vat,
                                'street': self.street or morada,
                                'city': self.city or cidade,
                                'zip': self.zip or str(cp1 + cp2),
                                'website': self.website or website,
                                'email': self.email or email,
                                'phone': self.phone or telefone,
                            }
                            return {'value': value}
                except:
                    e = 1


# tabela da empresa da base de dados - configuracoes - utilizadores - empresas
class ResCompany(models.Model):
    _inherit = "res.company"

    def account_adjustments(self, code):
        account = self.env['account.account'].search([('code', '=like', code), ('tipo_conta', '=', 'GM')], limit=1)
        if not account:
            account = self.env['account.account'].search([('code', '=like', code)], limit=1)
        return account

    account_adjustments_purchase = fields.Many2one("account.account", string="Conta de acerto de casa decimal para "
                                                                             "compra",
                                                   default=lambda self: self.account_adjustments('611%'))
    account_adjustments_sale = fields.Many2one("account.account", string="Conta de acertos de casa decimal para venda",
                                               default=lambda self: self.account_adjustments('711%'))
    pais_certificacao = fields.Many2one('res.country', string="Pais Certificação", copy=False,
                                        help="Caso o campo esteja preechido na certificação este será consultado "
                                             "para verificar se as restrições se aplicam ou não.")
    validar_nif_duplicados = fields.Boolean(string="Proibir NIF's Duplicados",
                                            help="Se levar visto, o programa valida o nif tem de ser unico "
                                                 "por parceiro.", default=True, copy=False)
    validar_nif = fields.Boolean(string="Validar NIF",
                                 help="Se levar visto, o programa valida o nif dos parceiros sempre que os cria ou "
                                      "edita.", default=True, copy=False)
    cash_vat_scheme_indicator = fields.Boolean(string="Iva de Caixa",
                                               help="Assinale se houver adsão ao regime de iva de caixa.",
                                               default=False, copy=False)
    third_parties_billing_indicator = fields.Boolean(string="Faturação por Terceiros",
                                                     help="Assinale se respeitar a faturação emitida em nome e por conta de terceiros",
                                                     default=False, copy=False)
    open_journal = fields.Many2one('account.journal', string="Diário de Abertura", copy=False)
    conservatoria = fields.Char(related="partner_id.conservatoria", string='Conservatoria', size=64)
    reg_com = fields.Char(related="partner_id.reg_com", string='Reg. comercial', size=32)
    local_installation = fields.Boolean('Instalação Local', default=False)

    def write(self, vals):
        for company in self:
            if 'vat' in vals:
                if not company.company_registry:
                    vals['company_registry'] = vals['vat']
                if not company.conservatoria:
                    company.partner_id.conservatoria = vals['vat']
                if not company.reg_com:
                    company.partner_id.reg_com = '5.000'
        return super(ResCompany, self).write(vals)

    def copy(self, default=None):
        raise ValidationError(_("Não é possivel utilizar a opção duplicar nas empresas, por favor use o botão criar."))
