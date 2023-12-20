# -*- coding: utf-8 -*-
import base64
import datetime
import logging
from decimal import Decimal
import dateutil.relativedelta
import calendar
from lxml import etree as et

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import re

_logger = logging.getLogger(__name__)

# VALORES FIXO do cabecalho relativos ao OpenERP
productCompanyTaxID = '999999999'
productID = 'OpenSoft/OPENNET - TELECOMUNICAÇOES E INFORMATICA, LDA'
productVersion = 'Opencloud - 15.0'
headerComment = 'Software criado por Odoo e adaptado por Opencloud - Angola'
softCertNr = '380'

tipos_saft = [('C', 'Contabilidade'),  # ctb na v.1
              ('F', 'Facturação'),  # fact na v.1
              ('I', 'Integrado - Contabilidade e Facturação')]


def date_format(data, tipo='DateType'):
    date = datetime.datetime.strptime(str(data)[:19], '%Y-%m-%d %H:%M:%S')
    if tipo == 'DateType':
        return date.strftime('%Y-%m-%d')
    else:
        return date.strftime('%Y-%m-%dT%H:%M:%S')


class WizardSaft(models.Model):
    _name = "wizard.l10n_pt.saft"
    _description = "Wizard exportador ficheiro Saft-T. Menu: Contabilidade - Relatorios - Saft - Exportar Ficheiro Saft"

    @api.model
    def _default_company(self):
        # Devolve a empresa do utilizador, ou a primeira encontrada
        if self.env.user.company_id:
            return self.env.user.company_id.id
        return self.env['res.company'].search([('parent_id', '=', False)], limit=1)

    @api.model
    def get_date_inicio(self):
        today = datetime.date.today()
        first_day = datetime.date(day=1, month=today.month, year=today.year)
        last_month = first_day - datetime.timedelta(days=1)
        return last_month

    @api.model
    def get_date_fim(self):
        today = datetime.date.today()
        first_day = datetime.date(day=1, month=today.month, year=today.year)
        last_month = str(first_day - datetime.timedelta(days=1))
        return last_month

    name = fields.Char(string="Filename", size=254, readonly=True, default="saftpt.xml", copy=False)
    info = fields.Text(string="Informação", copy=False)
    comp = fields.Many2one('res.company', string="Companhia", required=True, default=_default_company, copy=False)
    tipo = fields.Selection(tipos_saft, string="Tipo ficheiro", required=True, default='F', copy=False)
    filedata = fields.Binary(string="File", readonly=True, copy=False)
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], string="Estado", default='choose', copy=False)
    versao = fields.Selection([('1.03_01', '1.03_01'), ('1.04_01', '1.04_01')], string="Versão", required=True,
                              default="1.04_01", copy=False)
    date_inicio = fields.Date('Data de Início', default=get_date_inicio, copy=False)
    date_fim = fields.Date('Data do Fim', default=get_date_fim, copy=False)

    @api.model
    def saft_aviso(self):
        warning_day = self.env['ir.config_parameter'].search([('key', '=', 'dia.limite.de.envio.de.saft')]).value
        # verificar se o dia do aviso é hoje
        if warning_day == str(datetime.datetime.now().day):

            first_day_last_month = datetime.datetime.now() - dateutil.relativedelta.relativedelta(months=1)
            last_day_last_month = calendar.monthrange(first_day_last_month.year, first_day_last_month.month)[1]
            # formar a data do primeiro dia do mes anterior
            first_day_last_month = str(first_day_last_month)[0:8] + "01"
            # formar a data do utlimo dia do mes anterior
            last_day_last_month = str(first_day_last_month)[0:8] + str(last_day_last_month)
            # verificar se já exportou o saft para o mês anterior
            check_history = self.env['hist.saft'].search([('data_inicio', '=', first_day_last_month),
                                                          ('data_fim', '=', last_day_last_month)])
            if not check_history:
                # se ainda não exportou, verificar se o mês anterior tem faturas
                check_invoices = self.env['account.move'].search([('date', '>=', first_day_last_month),
                                                                     ('date', '<=', last_day_last_month)])
                if check_invoices:
                    # managers de contabilidade
                    for user in self.env['res.users'].sudo().search([]):
                        if user.has_group('account.group_account_manager'):
                            # enviar e-mail para os manager de contabilidade
                            notification_template = self.env['ir.model.data'].sudo().check_object_reference (
                                'opc_certification_ao', 'saft_aviso25')

                            notification_template = notification_template and self.env['mail.template'].browse(
                                notification_template[1])

                            notification_template.email_to = user.partner_id.email

                            notification_template.send_mail(False)

    @api.onchange('versao')
    def _onchange_versao(self):
        self.info = ""

    
    def get_address(self, parent_tag, partner):
        dict_type = {'CompanyAddress': False, 'BillingAddress': 'invoice'}
        address = self.env['res.partner'].search(
            [('parent_id', '=', partner.id),
             ('type', '=', dict_type[parent_tag]),
             '|',
             ('active', '=', True),
             ('active', '=', False)
             ], limit=1)
        if not address:
            address = partner

        # obtem os campos (para o id acima) de addressStruture
        # print address
        # TODO: criar aqui o XML do endereco
        """Funcao para gerar campo Address -   Elementos e ordem:
            BuildingNumber
            StreetName
          * AddressDetail
          * City
          * PostalCode
          * Country    """
        street = address.street and address.street[:60] or 'Desconhecido'
        city = address.city or 'Desconhecido'
        postal_code = address.zip and address.zip.replace(" ", "")[:8] or '0000-000'
        country_code = address.country_id and address.country_id.code or 'AO'
        if country_code == "UK":
            country_code = "GB"
        elif country_code == "R.":
            country_code = "RU"

        xml_address = et.Element(parent_tag)
        for el, txt in zip(('AddressDetail', 'City', 'Country'),
                           (street, city, country_code)):
            if txt is None:
                if el == 'Country':
                    txt = 'AO'
                    country_code = 'AO'
            i = et.SubElement(xml_address, el)
            i.text = txt
            i.tail = '\n'

        xml_contacts = et.Element('PhoneFaxMail')

        phone = address.phone and address.phone[:20] or '000000000'
        fax = '000000000'

        email = address.email or ' '
        if email:
            if email.find(';') != -1:
                email = email.split(';')
                email = email[0]
            if email.find(',') != -1:
                email = email.split(',')
                email = email[0]
            if email.find('@') == -1:
                email = None
            if email is not None and email is not False:
                email = email[:60]
        for el, txt in zip(('Telephone', 'Fax', 'Email'), (phone, fax, email)):
            if txt is None:
                continue
            et.SubElement(xml_contacts, el).text = txt
        return xml_address, xml_contacts

    
    def act_getfile(self):
        import datetime

        date_start_str = '2017-07-01'
        date_time_obj = datetime.datetime.strptime(date_start_str, '%Y-%m-%d').date()

        if self.versao != '1.04_01' and (self.date_inicio >= date_time_obj or self.date_fim >= date_time_obj):
            raise ValidationError(_('Apenas pode exportar a versão 1.04_01 para datas iguais ou superiores a '
                                    '2017-07-01.'))

        # cria o historico
        self.env['hist.saft'].create({
            'nif': self.comp.partner_id.vat or '',
            'tipo': 'export',
            'data_inicio': self.date_inicio,
            'data_fim': self.date_fim,
            'data_criacao': datetime.datetime.now(),
        })
        # fim de gravar no historico

        _logger.info("saft :", ' A exportar o ficheiro xml SAFT ****')

        # Namespaces declaration
        xmlns = "urn:OECD:StandardAuditFile-Tax:AO_01_01"
        attrib = {'xmlns': xmlns}

        root = et.Element("AuditFile", attrib=attrib)
        header = et.SubElement(root, 'Header', xmlns=xmlns)
        header.tail = '\n'

        # master
        master = self._get_masters()
        root.append(master)

        for element in (header, master):
            element.tail = '\n'

        # entries : exclui na facturação
        if self.tipo in ('C', 'I'):
            entries = self._get_entries()
            root.append(entries)
            for element in entries:
                element.tail = '\n'

        et.SubElement(header, 'AuditFileVersion').text = "1.01_01"

        partner_company = self.comp.partner_id

        if not partner_company.vat:
            raise ValidationError(_('O parceiro associado à empresa não tem NIF definido.'))

        vat = re.sub("[^0-9]", "", partner_company.vat)

        if partner_company.conservatoria != False and partner_company.reg_com != False:
            #  <CompanyID>Numero da Certidao Permanente</CompanyID> "
            for element, texto in zip(('CompanyID', 'TaxRegistrationNumber', 'TaxAccountingBasis', 'CompanyName'),
                                      (str(partner_company.conservatoria) + ' ' + str(partner_company.reg_com), vat,
                                       self.tipo, partner_company.name[:60])):
                if partner_company.reg_com:
                    et.SubElement(header, element).text = texto.replace(partner_company.reg_com,'').strip()
                elif partner_company.conservatoria:
                        et.SubElement(header, element).text = texto.replace(partner_company.conservatoria, '').strip()
                else:
                    et.SubElement(header, element).text = texto

        else:
            raise ValidationError(_('Preencha os campos N.Registo e Conservatória no contacto da empresa antes de '
                                    'exportar o Saft'))

        comp_address, phone_fax_mail = self.get_address('CompanyAddress', self.comp.partner_id)

        header.append(comp_address)

        # gera o header propriamente
        tags = (('FiscalYear', str(self.date_inicio)[:4]),
                ('StartDate', str(self.date_inicio)),
                ('EndDate', str(self.date_fim)),
                ('CurrencyCode', 'AOA'),
                ('DateCreated', '%s' % str(datetime.date.today())),
                ('TaxEntity', 'Global'),
                ('ProductCompanyTaxID', productCompanyTaxID),
                ('SoftwareValidationNumber', softCertNr),
                ('ProductID', productID),
                ('ProductVersion', productVersion),
                ('HeaderComment', headerComment),
                )
        for tag, valor in tags:
            if valor is None:
                continue
            et.SubElement(header, tag).text = valor
        for element in phone_fax_mail.getchildren():
            header.append(element)
        del phone_fax_mail
        if partner_company.website:
            et.SubElement(header, 'Website').text = partner_company.website
        for element in header.getchildren():
            element.tail = '\n'

        nome_file_2 = self.comp and self.comp.name
        nome_file_3 = str(self.date_inicio) or ''
        nome_file_4 = ''
        if nome_file_3 != '':
            nome_file_3 = 'de' + nome_file_3
            nome_file_4 = str(self.date_fim) or ''
        if nome_file_4 != '':
            nome_file_4 = 'ate' + nome_file_4

        nome_file = 'Saft-T-AGT-' + nome_file_2 + '-' + nome_file_3 + nome_file_4 + '.xml'

        # Os pagamento só vão para o saft se o mesmo for de Contabilidade ou se a empresa for de iva de caixa
        if self.tipo != 'C':
            docs = self._write_source_documents(self.date_inicio, self.date_fim, self.versao, self.comp.id)
            if docs is not None:
                root.append(docs)

        xml_txt = et.tostring(root, encoding="windows-1252")
        out = base64.encodestring(xml_txt)

        self.write({'state': 'get', 'filedata': out, 'name': nome_file})

        return {
            'name': 'Exportar Ficheiro SAFT',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'wizard.l10n_pt.saft',
            'type': 'ir.actions.act_window',
            'res_id': self.id,
            'target': 'new',
        }

    
    def _get_masters(self):
        _logger.info("saft :", ' A exportar MasterFiles')
        xmlns = "urn:OECD:StandardAuditFile-Tax:AO_01_01"
        master = et.Element('MasterFiles', xmlns=xmlns)
        master.tail = '\n'
        # 2.1 GeneralLedger
        # obtem lista de contas com movimentos, com saldos 99de abertura
        # precisa obter contas-mãe para cada cta de movimento
        if self.tipo in ('C', 'I'):
            self.env.cr.execute("""
                SELECT DISTINCT ac.id, ac.code, ac.name, COALESCE(debito, 0.0), COALESCE(credito, 0)
                FROM account_move_line ml
                    INNER JOIN account_account  ac  ON  ac.id = ml.account_id
                    LEFT JOIN
                        (SELECT account_id, SUM(debit) AS debito, SUM(credit) AS credito
                        FROM account_move_line
                        WHERE journal_id =
                            (SELECT open_journal
                            FROM res_company
                            WHERE id = %s)
                            GROUP BY account_id)
                        abertura ON ml.account_id = abertura.account_id
            """, (self.comp.id,))
            acc_dict = {}
            for ac_id, code, name, debit, credit in self.env.cr.fetchall():
                acc_dict[code] = {'name': name, 'debit': debit, 'credit': credit}

            _logger.info("saft :", ' A exportar Plano de Contas (GeneralLedger)')

            if self.versao != '1.03_01':
                gl = et.SubElement(master, 'GeneralLedgerAccounts')
                # get tipo de Empresa
                taxonomia = self.env['taxonomia.periodo'].search([('company_id', '=', self.comp.id),
                                                                  ('start_date', '<=', self.date_inicio),
                                                                  ('end_date', '>=', self.date_fim)], limit=1)
                if taxonomia and taxonomia.name:
                    et.SubElement(gl, 'TaxonomyReference').text = taxonomia.name.code
                else:
                    raise ValidationError(_('Não existem taxonomias definidas para a empresa.'))

            for code in sorted(acc_dict):
                if self.versao == '1.03_01':
                    gl = et.SubElement(master, 'GeneralLedger')
                    elemento = gl
                else:
                    # este gl ven do If anterior ao For
                    glacc = et.SubElement(gl, 'Account')
                    glacc.tail = '\n'
                    elemento = glacc
                et.SubElement(elemento, 'AccountID').text = code
                et.SubElement(elemento, 'AccountDescription').text = (acc_dict[code]['name'])[:60]
                et.SubElement(elemento, 'OpeningDebitBalance').text = str(round(float(acc_dict[code]['debit']),2))
                et.SubElement(elemento, 'OpeningCreditBalance').text = str(round(float(acc_dict[code]['credit']),2))
                et.SubElement(elemento, 'ClosingDebitBalance').text = "0.00"
                et.SubElement(elemento, 'ClosingCreditBalance').text = "0.00"

                conta = self.env['account.account'].search([('code', '=', code), ('company_id', '=', self.comp.id)],
                                                           limit=1)
                et.SubElement(elemento, 'GroupingCategory').text = conta.tipo_conta

                if conta.tipo_conta in ('GA', 'AA', 'GM', 'AM'):
                    if conta and conta.parent_id.id:
                        account_account = self.env['account.account'].search([('id', '=', conta.parent_id.id)], limit=1)
                        if account_account:
                            et.SubElement(elemento, 'GroupingCode').text = str(account_account.code)
                elif conta.tipo_conta in ('GR', 'AR'):
                    pass
                elif conta.tipo_conta != 'GM':
                    raise ValidationError(_('There is an error in GroupingCategory in account number: '+ _(conta)))

                if self.versao != '1.03_01':
                    taxonomia_name = None
                    periodo_linhas = self.env['taxonomia.periodo.linhas'].search([
                        ('contas.code', '=', code),
                        ('periodo_id.company_id', '=', self.comp.id),
                        ('periodo_id.start_date', '=', self.date_inicio),
                        ('periodo_id.end_date', '=', self.date_fim)])
                    if periodo_linhas and periodo_linhas.name:
                        taxonomia_name = periodo_linhas.name.name

                    if conta.tipo_conta == 'GM':
                        if taxonomia_name is not None:
                            et.SubElement(elemento, 'TaxonomyCode').text = str(taxonomia_name)
                        else:
                            raise ValidationError(_('A conta %s não tem taxonomia.') % _(code))

        # 2.2 Customer
        _logger.info("saft :", ' A exportar Clientes')
        self._write_partners(master)

        # 2.3 Supplier
        _logger.info("saft :", ' A exportar Fornecedores')
        self._write_partners(master, partner_role='Supplier')

        # 2.4 Product   -   Não entra no tipo 'C'
        if self.tipo != 'C':
            self._write_products(master)

        # 2.5 TaxTable
        taxes = self._get_taxes()
        for tax in taxes:
            tax.tail = '\n'
        master.append(taxes)
        return master

    
    def _write_partners(self, master, partner_role='Customer'):
        """ Exporta os elementos 2.2 Customer e 2.3 Supplier
         1 CustomerID (Supplier)      * partner.id | partner.ref
         2 AccountID                  * ler em properties ???
         3 CustomerTaxID (Supplier)   * partner.vat
         4 CompanyName                * partner.name
         5 Contact       (Opcional)    [address.name (default)]
         6 BillingAddress             * address[invoice|default]
         7 ShipToAddress  (From)        address[delivery]
         8 Telephone                    address[default].phone | mobile
         9 Fax                          address[default].fax
        10 Email                        address[default].email
        11 Website                      partner.website
        12 SelfBillingIndicator """
        parceiros_contabilidade = []
        parceiros_sales = []
        parceiros_faturas = []
        parceiros_pagamentos = []
        parceiros_guias = []
        if partner_role == 'Customer':
            invoice_partners = self.env["account.move"].sudo().search([('company_id', '=', self.comp.id),
                                                                        ('state', '!=', 'draft'),
                                                                        ('move_type', 'in', ('out_invoice','out_refund')),
                                                                        ('invoice_date', '>=', self.date_inicio),
                                                                        ('invoice_date', '<=', self.date_fim)])
            for pf in invoice_partners:
                parceiros_faturas.append(pf.commercial_partner_id.id)

            payments_partners = self.env["account.payment"].sudo().search([('company_id', '=', self.comp.id),
                                                                              ('payment_type', '=', 'inbound'),
                                                                              ('date', '>=', self.date_inicio),
                                                                              ('date', '<=', self.date_fim)])
            for pp in payments_partners:
                parceiros_pagamentos.append(pp.partner_id.id)

            stock_picking_partners = self.env["stock.picking"].sudo().search([('company_id', '=', self.comp.id),
                                                                        ('picking_type_id.code', 'in', ('incoming','internal','outgoing')),
                                                                        ('date', '>=', self.date_inicio),
                                                                        ('date', '<=', self.date_fim)])
            for pg in stock_picking_partners:
                parceiros_guias.append(pg.partner_id.id)

            sale_order_partners = self.env["sale.order"].sudo().search([('company_id', '=', self.comp.id),
                                                                    ('certificated', '=', True),
                                                                    ('date_order', '>=', self.date_inicio),
                                                                    ('date_order', '<=', self.date_fim)])
            for sop in sale_order_partners:
                parceiros_sales.append(sop.partner_id.id)

            if self.tipo in ('C', 'I'):
                accounting_partners = self.env["account.move"].sudo().search([('company_id', '=', self.comp.id),
                                                                        ('state', '=', 'posted'),
                                                                        ('certificated', '=', True),
                                                                        ('date', '>=', self.date_inicio),
                                                                        ('date', '<=', self.date_fim)])
                for pcc in accounting_partners:
                    parceiros_contabilidade.append(pcc.partner_id.id)

        elif partner_role == 'Supplier':
            parceiros_faturas = []
            parceiros_pagamentos = []

            stock_picking_partners = self.env["stock.picking"].sudo().search([('company_id', '=', self.comp.id),
                                                                       ('picking_type_id.code', 'in',
                                                                        ('incoming', 'internal', 'outgoing')),
                                                                       ('date', '>=', self.date_inicio),
                                                                       ('date', '<=', self.date_fim)])
            for pg in stock_picking_partners:
                parceiros_guias.append(pg.partner_id.id)

            if self.tipo in ('C', 'I'):
                accounting_partners = self.env["account.move"].sudo().search([('company_id', '=', self.comp.id),
                                                                                  ('state', '=', 'posted'),
                                                                                  ('certificated', '=', True),
                                                                                  ('date', '>=', self.date_inicio),
                                                                                  ('date', '<=',
                                                                                   self.date_fim)])
                for pcc in accounting_partners:
                    parceiros_contabilidade.append(pcc.partner_id.id)
        else:
            return

        partner_ids = []
        for partner in parceiros_faturas + parceiros_pagamentos + parceiros_guias \
                       + parceiros_contabilidade + parceiros_sales:
            if partner not in partner_ids:
                partner_ids.append(partner)

        res_partner = self.env['res.partner'].search([('name', '=', 'Consumidor Final'),
                                                      ('company_id', '=', self.comp.id)], limit=1)
        if res_partner:
            if res_partner.id not in partner_ids:
                partner_ids.append(res_partner.id)

        for partner in self.env['res.partner'].search([('id', 'in', partner_ids), '|', ('active', '=', True),
                                                       ('active', '=', False)]):
            if partner_role == 'Customer':
                try:
                    account_code = partner.property_account_receivable_id.code
                except:
                    raise ValidationError(_('A conta a receber não está definida no parceiro %s.') % _(partner.name,))
                self_bill = (partner.self_bill_sales and '1' or '0')
            else:
                try:
                    account_code = partner.property_account_payable_id.code
                except:
                    raise ValidationError(_('A conta a pagar não está definida no parceiro %s.') % _(partner.name,))
                self_bill = (partner.self_bill_purch and '1' or '0')

            partner_element = et.SubElement(master, partner_role)
            # .1  ID
            et.SubElement(partner_element, '%sID' % partner_role).text = str(partner.id)
            et.SubElement(partner_element, 'AccountID').text = account_code
            partner_vat = partner.vat

            if partner_vat is not None and partner_vat is not False:
                partner_vat = re.sub("[^0-9]", "", partner_vat)

            et.SubElement(partner_element, '%sTaxID' % partner_role).text = (
                    partner_vat and partner_vat or '999999999')
            # .4  CompanyName
            if partner and not partner.name:
                raise ValidationError(_('O nome não está definido no parceiro com id %s.') % _(partner.id, ))
            et.SubElement(partner_element, 'CompanyName').text = partner.name[0:60]
            # .5 Contact   - Opcional
            # .6  BillingAddress
            billing_address, phone_fax_mail = self.get_address('BillingAddress', partner)
            partner_element.append(billing_address)

            # 8-9-10  elementos facultativos no OpenERP constam do endereço, no saft estão fora.
            for element in phone_fax_mail:
                partner_element.append(element)
            # .11 Website
            if partner.website:
                et.SubElement(partner_element, 'Website').text = partner.website[:60]
            et.SubElement(partner_element, 'SelfBillingIndicator').text = self_bill
            partner_element.tail = '\n'
        return True

    
    def _write_products(self, master):
        _logger.info("saft :", ' A exportar tabela de produtos')

        # get_faturas
        list_produtos = []
        list_faturas = self.env['account.move'].search([('date', '>=', self.date_inicio),
                                                           ('date', '<=', self.date_fim)])
        for fatura in list_faturas:
            for linha_fatura in fatura.invoice_line_ids:
                if not linha_fatura.display_type:
                    list_produtos.append(linha_fatura.product_id)

        # get guias
        list_guias = self.env['stock.picking'].search([('date', '>=', self.date_inicio), ('date', '<=', self.date_fim)])
        for guia in list_guias:
            for linha_move in guia.move_lines:
                list_produtos.append(linha_move.product_id)

        list_sales = self.env['sale.order'].search([('date_order', '>=', self.date_inicio),
                                                    ('date_order', '<=', self.date_fim)])
        for sale in list_sales:
            for linha_sale in sale.order_line:
                if not linha_sale.display_type:
                    list_produtos.append(linha_sale.product_id)

        for product in set(list_produtos):
            if product:
                eproduct = et.SubElement(master, "Product")
                eproduct.tail = '\t    '
                eproduct_type = et.SubElement(eproduct, "ProductType")

                if product.product_tmpl_id.type == 'product':
                    eproduct_type.text = 'P'
                elif product.product_tmpl_id.type == 'service':
                    eproduct_type.text = 'S'
                else:
                    eproduct_type.text = 'O'
                if not product.default_code or product.default_code == '':
                    raise ValidationError(_('Product ' + _(product.name) + ' does not have internal number.'))
                else:
                    eproduct_code = et.SubElement(eproduct, "ProductCode")
                    eproduct_code.text = product.default_code[:60]
                eproduct_group = et.SubElement(eproduct, "ProductGroup")
                eproduct_group.text = product.categ_id.name[:50]

                eproduct_description = et.SubElement(eproduct, "ProductDescription")
                prod_descr = product.name[:60].ljust(2)
                try:
                    eproduct_description.text = prod_descr
                except:
                    _logger.exception("\nO produto com o id %s tem erro no nome." % product.id)

                eproduct_number_code = et.SubElement(eproduct, "ProductNumberCode")
                if product.barcode and product.barcode != "":
                    eproduct_number_code.text = product.barcode[:60]
                else:
                    eproduct_number_code.text = product.default_code[:60]

    
    def _get_taxes(self):
        _logger.info("saft :", ' A exportar TaxTable')
        tax_table = et.Element('TaxTable')

        taxes = self.env['account.tax'].search(
            [('tax_group_id.name', '!=', 'Retenção'), ('type_tax_use', '!=', 'purchase'),
             ('company_id', '<=', self.comp.id)],
            order='country_region, amount')
        tax_amount_unique = []
        for tax in taxes:
            if tax.amount not in tax_amount_unique:
                tax_amount_unique.append(tax.amount)
                tax_table_entry = et.SubElement(tax_table, 'TaxTableEntry')
                tax_type = tax.saft_tax_type
                if tax_type is None:
                    tax_type = 'IVA'
                et.SubElement(tax_table_entry, 'TaxType').text = tax_type
                et.SubElement(tax_table_entry, 'TaxCountryRegion').text = 'AO'
                et.SubElement(tax_table_entry, 'TaxCode').text = tax.saft_tax_code
                et.SubElement(tax_table_entry, 'Description').text = tax.name
                if tax.expiration_date:
                    et.SubElement(tax_table_entry, 'TaxExpirationDate').text = tax.expiration_date  # opcional
                if tax.amount_type == 'percent':
                    et.SubElement(tax_table_entry, 'TaxPercentage').text = str(int(abs(tax.amount)))
                else:
                    et.SubElement(tax_table_entry, 'TaxAmount').text = str(tax.amount)
        return tax_table

    
    def _get_move_lines_elements(self, transaction_el, linha, journal_type, trans_el, partner_el, total_debit,
                                 total_credit, tipo, parametros_pesquisa, move_id):
        result = 0
        partner = False
        move_lines = self.env['account.move.line'].search(parametros_pesquisa + [('move_id', '=', move_id)])
        for move_line in move_lines:
            partner = move_line.partner_id and move_line.partner_id.id or False
            line_el = et.SubElement(transaction_el, linha)
            # 3.4.3.11.1  RecordID  - usa o id interno da tabela account_line
            et.SubElement(line_el, 'RecordID').text = str(move_line.id)
            et.SubElement(line_el, 'AccountID').text = move_line.account_id.code
            et.SubElement(line_el, 'SystemEntryDate').text = date_format(move_line.write_date or move_line.create_date,
                                                                         'DateTimeType')
            et.SubElement(line_el, 'Description').text = move_line.name[:20]

            # versao 1.04_01 do Saft, movimentos de credito e debito estao separados
            if tipo == 'debit':
                et.SubElement(line_el, 'DebitAmount').text = str(move_line.debit)
                total_debit += move_line.debit
                result = total_debit
            if tipo == 'credit':
                et.SubElement(line_el, 'CreditAmount').text = str(move_line.credit)
                total_credit += move_line.credit
                result = total_credit

            # versao 1.03_01 do Saft, movimentos de credito e debito estao em conjunto
            if tipo == 'debit_credit':
                if move_line.credit == 0:
                    et.SubElement(line_el, 'DebitAmount').text = str(move_line.debit)
                    total_debit += move_line.debit
                if move_line.debit == 0:
                    et.SubElement(line_el, 'CreditAmount').text = str(move_line.credit)
                    total_credit += move_line.credit
                result = total_debit, total_credit

            # /Line
            for element in line_el.getchildren():
                element.tail = '\n                '
        if journal_type in ('sale', 'purchase') and partner:
            partner_el.text = str(partner)
        for element in trans_el.getchildren():
            element.tail = '\n'

        return result

    
    def _get_entries(self):
        _logger.info("saft :", ' A exportar movimentos da contabilidade')
        # 3. GeneralLedgerEntries
        xmlns = "urn:OECD:StandardAuditFile-Tax:AO_01_01"
        entries = et.Element('GeneralLedgerEntries', xmlns=xmlns)
        entries.tail = '\n'
        # 3.1 NumberOfEntries
        number_of_entries = et.SubElement(entries, 'NumberOfEntries')
        num_entries = 0
        # 3.2 TotalDebit
        total_debit_element = et.SubElement(entries, 'TotalDebit')
        total_debit = 0
        # 3.3 TotalCredit
        total_credit_element = et.SubElement(entries, 'TotalCredit')
        total_credit = 0
        total_cd = 0
        total_db = 0

        # obtem diarios excepto diario de abertura
        if not self.comp.open_journal:
            raise ValidationError(_('Falta definir o diario de abertura na empresa.'))

        journals = self.env['account.journal'].search([('id', '!=', self.comp.open_journal.id)])
        for journal in journals:
            # 3.4 Journal
            ejournal = et.SubElement(entries, 'Journal')
            # 3.4.1  JournalID   and   3.4.2 Description
            et.SubElement(ejournal, 'JournalID').text = journal.code.strip()
            et.SubElement(ejournal, 'Description').text = journal.name

            # transaccoes do diario e exercicio
            self.env.cr.execute("""
                SELECT m.id, m.name, m.date, COALESCE(uc.login, uw.login), m.ref, COALESCE(m.write_date, m.create_date)
                FROM account_move m
                    LEFT JOIN res_users uc ON uc.id = m.create_uid
                    LEFT JOIN res_users uw ON uw.id = m.write_uid
                WHERE m.date>=%s AND
                    m.date<=%s AND
                    m.state = 'posted' AND
                    m.journal_id = %s
                ORDER BY m.name""", (self.date_inicio, self.date_fim, journal.id))
            journal_transactions = self.env.cr.fetchall()
            for move_id, trans_id, date, user, desc, post_date in journal_transactions:
                account_move_lines = self.env['account.move.line'].search(['|', ('credit', '>', 0), ('debit', '>', 0),
                                                                           ('move_id', '=', move_id)])
                if len(account_move_lines) > 1:
                    num_entries += 1
                    # 3.4.3   Transaction
                    self.transactionID = (date + ' ' + journal.code.strip() + ' ' + str(move_id))
                    trans_el = et.SubElement(ejournal, 'Transaction')
                    et.SubElement(trans_el, 'TransactionID').text = self.transactionID[:70]
                    et.SubElement(trans_el, 'Period').text = date[5:7]
                    et.SubElement(trans_el, 'TransactionDate').text = date
                    et.SubElement(trans_el, 'SourceID').text = user[:30]
                    et.SubElement(trans_el, 'Description').text = (_(trans_id) + _(' ') + _(desc))[:20]

                    # 3.4.3.6 DocArchivalNumber
                    et.SubElement(trans_el, 'DocArchivalNumber').text = str(move_id)[:20]
                    et.SubElement(trans_el, 'TransactionType').text = journal.transaction_type

                    # 3.4.3.8 GLPostingDate data no formata AAAA-MM-DD
                    if self.versao not in ['1.03_01', '1.02_01']:
                        et.SubElement(trans_el, 'GLPostingDate').text = date_format(post_date, 'DateType')

                    # 3.4.3.8 versão 1.03_01 GLPostingDate data no formata AAAA-MM-DD Thh:mm:ss
                    else:
                        et.SubElement(trans_el, 'GLPostingDate').text = date_format(post_date, 'DateTimeType')

                    # 3.4.3.9|10  CustomerID|SupllierID  se diario é de vendas  - clientes ; se compras : fornecedores
                    # usa o id interno para referenciar parceiros  ????
                    partner_el = False
                    if journal.type == 'sale':
                        partner_el = et.SubElement(trans_el, 'CustomerID')
                    elif journal.type == 'purchase':
                        partner_el = et.SubElement(trans_el, 'SupplierID')

                    if self.versao in ['1.03_01']:
                        # 3.4.3.11 versão 1.03_01 Line  Adiciona linhas dos movimentos
                        total_db, total_cd = self._get_move_lines_elements(trans_el, 'Line', journal.type, trans_el,
                                                                           partner_el, total_debit, total_credit,
                                                                           'debit_credit',
                                                                           ['|', ('debit', '>', 0), ('credit', '>', 0)],
                                                                           move_id)
                    else:
                        trans_el_lines = et.SubElement(trans_el, 'Lines')

                        # 3.4.3.11 Line   Adiciona linhas dos movimentos debit
                        total_db = self._get_move_lines_elements(trans_el_lines, 'DebitLine', journal.type, trans_el,
                                                                 partner_el, total_debit, total_credit, 'debit',
                                                                 [('debit', '>', 0)], move_id)

                        # 3.4.3.11 Line   Adiciona linhas dos movimentos credit
                        total_cd = self._get_move_lines_elements(trans_el_lines, 'CreditLine', journal.type, trans_el,
                                                                 partner_el, total_credit, total_credit, 'credit',
                                                                 [('credit', '>', 0)], move_id)

            for element in ejournal.getchildren():
                element.tail = '\n        '
        number_of_entries.text = str(num_entries)
        total_debit_element.text = str(total_db)
        total_credit_element.text = str(total_cd)
        for element in entries.getchildren():
            element.tail = '\n    '
        return entries

    
    def _write_invoice(self, invoice, eparent, versao):
        # elemento 4.1.4 Invoice
        # 4.1.4.1
        if invoice.journal_id.saft_inv_type and invoice.internal_number:
            if invoice.move_type == 'out_refund':
                prefixo_numero = 'NC'
            else:
                prefixo_numero = invoice.journal_id.saft_inv_type
            et.SubElement(eparent, u"InvoiceNo").text = (prefixo_numero + ' ' + invoice.internal_number)
        else:
            et.SubElement(eparent, u"InvoiceNo").text = ' '

        if self.versao not in ['1.03_01']:
            et.SubElement(eparent, u"ATCUD").text = invoice.atcud or '0'
        # 4.1.4.2 - InvoiceStatus
        if invoice.state == 'cancel':
            status_code = 'A'
        elif invoice.journal_id.self_billing:
            status_code = 'S'
        else:
            status_code = 'N'

        # DocumentStatus
        document_status = et.SubElement(eparent, u"DocumentStatus")
        et.SubElement(document_status, u"InvoiceStatus").text = status_code
        et.SubElement(document_status, u"InvoiceStatusDate").text = str(invoice.write_date)[:19].replace(" ", "T")

        if invoice.write_uid:
            login = invoice.write_uid.login

        elif invoice.create_uid:
            login = invoice.create_uid.login

        et.SubElement(document_status, u"SourceID").text = login[:30]
        if invoice.journal_id.manual is True:
            et.SubElement(document_status, u"SourceBilling").text = 'M'
        else:
            if invoice.journal_id.integrado is True:
                et.SubElement(document_status, u"SourceBilling").text = 'I'
            else:
                et.SubElement(document_status, u"SourceBilling").text = 'P'
        # fim DocumentStatus

        # 4.1.4.3 - Hash
        et.SubElement(eparent, u"Hash").text = invoice.hash
        # 4.1.4.4 - HasControl
        et.SubElement(eparent, u"HashControl").text = str(invoice.hash_control)
        # 4.1.4.5 - Period          # todo: period name
        et.SubElement(eparent, u"Period").text = str(invoice.date)[5:7]
        # 4.1.4.6  InvoiceDate
        et.SubElement(eparent, u"InvoiceDate").text = str(invoice.invoice_date)
        # 4.1.4.7 InvoiceType
        if invoice.move_type == 'out_refund':
            et.SubElement(eparent, u"InvoiceType").text = 'NC'
        else:
            et.SubElement(eparent, u"InvoiceType").text = invoice.journal_id.saft_inv_type

        # 4.1.4.8  SpecialRegimes
        special_regimes = et.SubElement(eparent, u"SpecialRegimes")
        # 4.1.4.8.1  SelfBillingIndicator
        et.SubElement(special_regimes, "SelfBillingIndicator").text = str(
            invoice.journal_id.self_billing and '1' or '0')
        # 4.1.4.8.2  CashVATSchemeIndicator
        if self.comp.cash_vat_scheme_indicator:
            et.SubElement(special_regimes, "CashVATSchemeIndicator").text = "1"
        else:
            et.SubElement(special_regimes, "CashVATSchemeIndicator").text = "0"
        # 4.1.4.8.3  ThirdPartiesBillingIndicator
        if self.comp.third_parties_billing_indicator:
            et.SubElement(special_regimes, "ThirdPartiesBillingIndicator").text = "1"
        else:
            et.SubElement(special_regimes, "ThirdPartiesBillingIndicator").text = "0"

        et.SubElement(eparent, u"SourceID").text = login[:30]

        # 4.1.4.9  SystemEntryDate
        if invoice.system_entry_date is not False or invoice.hash_date is not False:
            et.SubElement(eparent, u"SystemEntryDate").text = date_format(invoice.hash_date or
                                                                          invoice.system_entry_date, 'DateTimeType')
        else:
            et.SubElement(eparent, u"SystemEntryDate").text = '0000-00-00'
        # 4.1.4.10 TransactioID - apenas no caso de ficheiro integrado
        if self.tipo == 'I':
            eTransactionID = et.SubElement(eparent, "TransactionID")
            eTransactionID.text = self.transactionID
        # 4.1.4.11 CustomerID
        et.SubElement(eparent, u"CustomerID").text = str(invoice.commercial_partner_id.id)
        return True

    
    def _write_payments(self):
        _logger.info("saft :", ' A exportar payments')

        pagamentoscliente = self.env['account.payment'].search([
            ('payment_type', '=', 'inbound'),
            ('hash', '!=', False),
            ('state', '!=', 'draft'),
            ('company_id', '=', self.comp.id),
            ('date', '>=', self.date_inicio),
            ('date', '<=', self.date_fim)])
        # ('payment_move_line', '!=', self.env['account.payment.move.line']

        if len(pagamentoscliente) == '0':
            return None

        # 4.4
        payments_el = et.Element('Payments')
        # 4.4.1
        et.SubElement(payments_el, 'NumberOfEntries').text = str(len(pagamentoscliente))
        # 4.4.2
        amount = 0
        amount_debit = 0

        for obj_payment in pagamentoscliente:
            for rec in obj_payment.move_id._get_reconciled_invoices_partials():
                if obj_payment.payment_type == 'inbound':
                    inv = rec[2].move_id
                    if inv.move_type != 'entry':
                        for par in obj_payment.move_id._get_reconciled_invoices_partials():
                            amount += par[1]

        # 4.4.4.14.4
        et.SubElement(payments_el, 'TotalDebit').text = str(amount_debit)
        # 4.4.4.14.5
        et.SubElement(payments_el, 'TotalCredit').text = str(amount)

        for payments in pagamentoscliente:
            # 4.4.4
            payment = et.SubElement(payments_el, 'Payment')
            # 4.4.4.1
            et.SubElement(payment, 'PaymentRefNo').text = ('RG ' + payments.name)
            if self.versao not in ['1.03_01']:
                et.SubElement(payment, u"ATCUD").text = payments.atcud or '0'
            # 4.4.4.3
            if self.tipo == 'I':
                et.SubElement(payment, 'TransactionID').text = (
                        payments.create_date + ' ' + payments.journal_id.code)
            # 4.4.4.4
            et.SubElement(payment, 'TransactionDate').text = str(payments.date)[:19].replace(" ", "T")
            # 4.4.4.5
            et.SubElement(payment, 'PaymentType').text = 'RG'
            # 4.4.4.7
            et.SubElement(payment, 'SystemID').text = str(payments.id)
            # 4.4.4.8
            document_status = et.SubElement(payment, 'DocumentStatus')
            # 4.4.4.8.1
            et.SubElement(document_status, 'PaymentStatus').text = "N"
            # 4.4.4.8.2
            et.SubElement(document_status, 'PaymentStatusDate').text = str(payments.write_date)[:19].replace(" ",
                                                                                                             "T")
            # 4.4.4.8.4in
            et.SubElement(document_status, 'SourceID').text = _(payments.write_uid.login)[:30]
            # 4.4.4.9
            source_payment = "P"
            if payments.journal_id.manual is True:
                source_payment = "M"
            if payments.journal_id.integrado is True:
                source_payment = "I"
            et.SubElement(document_status, 'SourcePayment').text = _(source_payment)
            # 4.4.4.10
            payment_method = et.SubElement(payment, 'PaymentMethod')
            # 4.4.4.10.1
            et.SubElement(payment_method, 'PaymentMechanism').text = 'OU'
            # 4.4.4.10.2
            et.SubElement(payment_method, 'PaymentAmount').text = str(payments.amount)
            # 4.4.4.10.3
            et.SubElement(payment_method, 'PaymentDate').text = str(payments.date)[:19].replace(" ", "T")
            # 4.4.4.11

            et.SubElement(payment, 'SourceID').text = _(payments.write_uid.login)[:30]
            # 4.4.4.12
            et.SubElement(payment, 'SystemEntryDate').text = str(payments.create_date)[:19].replace(" ", "T")
            # 4.4.4.13
            et.SubElement(payment, 'CustomerID').text = str(payments.partner_id.id)

            # linhas
            amount = 0
            for rec in payments.move_id._get_reconciled_invoices_partials():
                linha = rec
                #<t t-set="inv" t-value="rec[2].move_id"/>
                inv = rec[2].move_id
                if inv.move_type != 'entry':
                    #<tr t-foreach="inv._get_reconciled_invoices_partials()" t-as="par">
                    for par in inv._get_reconciled_invoices_partials():
                        invoice = self.env['account.move'].search(
                            [('id', '=', inv.id)])
                        if len(invoice) == 1:
                            originating_on = _(invoice.journal_id.saft_inv_type) + ' ' + _(invoice.internal_number)
                            invoice_date = _(invoice.invoice_date)[:10]
                            if not invoice.narration and _(invoice.narration) != '':
                                description = _(invoice.narration)[:200]
                            else:
                                description = ' '
                            if invoice.move_type in ['in_invoice', 'out_refund']:
                                debit_credit = 'DebitAmount'
                            else:
                                debit_credit = 'CreditAmount'
                        else:
                            invoice = False
                            if inv.id:
                                # caso a linha do pagamento nao tenha uma fatura atribuida
                                move_name = inv.ref or inv.name
                                originating_on = _(inv.journal_id.saft_inv_type) + ' ' + \
                                                 _(move_name)
                                invoice_date = _(inv.invoice_date)[:10]
                                description = ' '
                                debit_credit = 'CreditAmount'
                            else:
                                # caso a linha do pagamento nao tenha movimento atribuido
                                originating_on = 'FT ' + _(inv.ref)
                                invoice_date = _(inv.invoice_date)[:10]
                                description = ' '
                                debit_credit = 'CreditAmount'

                    total = abs(par[1])
                    para_pagar = abs(inv.amount_residual)
                    amount += abs(total - para_pagar)

                    line = et.SubElement(payment, 'Line')
                    # 4.4.4.14.1
                    et.SubElement(line, 'LineNumber').text = str(par[2].id)
                    source_document_id = et.SubElement(line, 'SourceDocumentID')

                    et.SubElement(source_document_id, 'OriginatingON').text = originating_on
                    # 4.4.4.14.2.2
                    et.SubElement(source_document_id, 'InvoiceDate').text = invoice_date
                    # 4.4.4.14.2.3
                    et.SubElement(source_document_id, 'Description').text = description

                    et.SubElement(line, debit_credit).text = str(amount)

                    # tax
                    account_invoice_tax = []
                    if invoice:
                        for invoice_line in invoice.invoice_line_ids:
                            for tax in invoice_line.tax_ids:
                                account_invoice_tax.append(tax)
                    else:
                        account_invoice_tax = self.env['account.tax'].search([('amount', '=', 0)])
                    if account_invoice_tax:
                        tax = account_invoice_tax[0]
                        # 4.4.4.14.6
                        tax_el = et.SubElement(line, 'Tax')
                        # 4.4.4.14.6.1
                        et.SubElement(tax_el, 'TaxType').text = _(tax.saft_tax_type)
                        # 4.4.4.14.6.2
                        et.SubElement(tax_el, 'TaxCountryRegion').text = 'AO'
                        # 4.4.4.14.6.3
                        et.SubElement(tax_el, 'TaxCode').text = _(tax.saft_tax_code)
                        # 4.4.4.14.6.4
                        if tax.amount is False:
                            et.SubElement(tax_el, 'TaxPercentage').text = "0"
                            NetTotal = 0
                        else:
                            et.SubElement(tax_el, 'TaxPercentage').text = str(tax.amount)
                            NetTotal = round(amount / (1 + (tax.amount/100)), 2)
                        # 4.4.4.14.6.5 Se coloca o TaxPercentage não coloca o TaxAmount
                        # 4.4.4.14.6.6
                        # TODO: fazer as exemption reasons virem de uma tabela
                        if tax.exemption_reason is not None and tax.exemption_reason != '' and \
                                (tax.amount is False or tax.amount == 0.0):
                            et.SubElement(line, 'TaxExemptionReason').text = str(tax.exemption_reason)[4:]
                            tax_exemption_code = tax.exemption_reason.split(' ')[0]
                            et.SubElement(line, u"TaxExemptionCode").text = tax_exemption_code
                            if (tax.exemption_reason and not tax_exemption_code) or (
                                    tax_exemption_code and not tax.exemption_reason):
                                raise ValidationError(
                                    _('There is an error in tax exemption on payment ' + _(payments.name)))
                        if tax.amount != 0 and not tax.exemption_reason:
                            pass
                        elif tax.amount == 0.0 and tax.exemption_reason:
                            pass
                        # else:
                        #     raise ValidationError(_('Error in TaxPercentage on payment '+ _(payments.name)))
                        # if payments.tipo_pagamento == 'RC' and not tax:
                        #     raise ValidationError(_('Error in payment '+ _(payments.name)+ ', payment without tax.'))
                        # if (tax.saft_tax_type and not payments.tipo_pagamento) or \
                        #         payments.tipo_pagamento == 'RG':
                        #     pass
                        # else:
                        #     raise ValidationError(_('Error in payment type on payment ' + _(payments.name)))
                    ####################
                    # 4.4.4.15
                    document_totals = et.SubElement(payment, 'DocumentTotals')
                    # 4.4.4.15.1
                    et.SubElement(document_totals, 'TaxPayable').text = '0.00' #str(round(abs(payments.amount - NetTotal), 2))
                    # 4.4.4.15.2
                    et.SubElement(document_totals, 'NetTotal').text = str(payments.amount) #str(round(abs(NetTotal), 2))
                    # 4.4.4.15.3
                    et.SubElement(document_totals, 'GrossTotal').text = str(payments.amount)

        return payments_el

    
    def _write_movement_of_goods(self):
        def _preencher_endereco(ship_to, cliente):
            # 4.2.3.15.5
            address = et.SubElement(ship_to, 'Address')
            # 4.2.3.15.5.1
            # et.SubElement(Address, 'BuildingNumber').text =       #nao e obrigatorio
            # 4.2.3.15.5.2
            et.SubElement(address, 'StreetName').text = cliente.street and cliente.street[:90] or ' '
            # 4.2.3.15.5.3
            et.SubElement(address, 'AddressDetail').text = cliente.street and cliente.street[:100] or ' '
            # 4.2.3.15.5.4
            et.SubElement(address, 'City').text = cliente.city and cliente.city[:50] or ' '
            # 4.2.3.15.5.5
            et.SubElement(address, 'PostalCode').text = cliente.zip and cliente.zip[:20] or ' '
            # 4.2.3.15.5.7
            cli_pais = cliente.country_id and cliente.country_id.code or 'AO'

            if cli_pais == "UK":
                cli_pais = "GB"
            if cli_pais == "R.":
                cli_pais = "RU"
            et.SubElement(address, 'Country').text = cli_pais

        _logger.info("saft :", ' A exportar movement_of_goods')
        movement_of_goods = None
        if True:
            tipos_entrada = self.env['stock.picking.type'].search([('code', '=', 'incoming')])
            stock_picking = self.env['stock.picking'].search([
                ('picking_type_id', 'not in', tipos_entrada.ids),
                ('hash', '!=', False),
                ('at_code', '=', ''),
                ('company_id', '=', self.comp.id),
                ('date', '>=', self.date_inicio),
                ('date', '<=', self.date_fim)])

            if len(stock_picking) > 0:
                # 4.2
                movement_of_goods = et.Element('MovementOfGoods')

                # 4.2.1
                et.SubElement(movement_of_goods, 'NumberOfMovementLines').text = str(len(stock_picking))
                # 4.2.2
                self.env.cr.execute("""
                        SELECT cast(coalesce(sum(sm.product_qty),0) as char)
                        FROM stock_move sm
                        WHERE sm.picking_id in %s""", (tuple(stock_picking.ids),))
                et.SubElement(movement_of_goods, 'TotalQuantityIssued').text = str(self.env.cr.fetchone()[0])

            for picking in stock_picking:
                # 4.2.3
                stock_movement = et.SubElement(movement_of_goods, 'StockMovement')
                # 4.2.3.1
                et.SubElement(stock_movement, 'DocumentNumber').text = picking.picking_type_id.code + ' ' + picking.name

                # 4.2.3.2
                document_status = et.SubElement(stock_movement, 'DocumentStatus')
                # 4.2.3.2.1
                estado = 'N'
                if _(picking.state) == 'cancel':
                    estado = 'A'
                et.SubElement(document_status, 'MovementStatus').text = estado
                # 4.2.3.2.2
                if picking.write_date is not None:
                    data = str(picking.write_date)[:19]
                else:
                    data = str(picking.create_date)[:19]
                et.SubElement(document_status, 'MovementStatusDate').text = data
                # 4.2.3.2.3
                # et.SubElement(DocumentStatus, 'Reason').text =   #nao e obrigatorio
                # 4.2.3.2.4
                login = picking.write_uid and picking.write_uid.login or picking.create_uid.login

                et.SubElement(document_status, 'SourceID').text = _(login)[:30]
                # 4.2.3.2.5
                if picking.manual is True:
                    et.SubElement(document_status, 'SourceBilling').text = _("M")
                else:
                    et.SubElement(document_status, 'SourceBilling').text = _("P")

                # 4.2.3.3
                et.SubElement(stock_movement, 'Hash').text = _(picking.hash)
                # 4.2.3.4
                et.SubElement(stock_movement, 'HashControl').text = _(picking.hash_control)
                # 4.2.3.6
                et.SubElement(stock_movement, 'MovementDate').text = str(picking.date)[:10]
                # 4.2.3.7
                # GR – Guia de remessa;                                  out
                # GT – Guia de transporte;                               int
                # GA – Guia de movimentação de ativos próprios;          para já não usamos
                # GC – Guia de consignação;                              visto
                # GD – Guia ou nota de devolução efetuada pelo cliente.  para já não usamos
                doc_tipo = 'GR'
                if picking.is_gc is True:
                    doc_tipo = 'GC'
                elif picking.picking_type_id.code == 'internal':
                    doc_tipo = 'GT'
                et.SubElement(stock_movement, 'MovementType').text = doc_tipo
                # 4.2.3.8
                et.SubElement(stock_movement, 'SystemEntryDate').text = data
                # 4.2.3.10

                if not picking.partner_id:
                    res_partner = self.env['res.partner'].search([
                        ('name', '=', 'Consumidor Final'),
                        ('company_id', '=', self.comp.id)], limit=1)
                    if res_partner:
                        cliente = res_partner
                    else:
                        raise ValidationError(_(
                            'Não existe um cliente com o nome "Consumidor Final" para a sua empresa'))
                else:
                    cliente = picking.partner_id
                # 4.2.3.11
                # da erro se for uma guia de devolucao. Falta ver se sao materias primas para
                # serem assembladcas no fornecedor
                if picking.is_gd:
                    et.SubElement(stock_movement, 'SupplierID').text = str(cliente.id)
                else:
                    et.SubElement(stock_movement, 'CustomerID').text = str(cliente.id)

                et.SubElement(stock_movement, 'SourceID').text = str(login)[:30]
                # 4.2.3.14
                if picking.note and picking.note != '':
                    et.SubElement(stock_movement, 'MovementComments').text = _(picking.note)[:50]
                    # o limite é 60 mas se tiver acentos a AT conta mais

                # 4.2.3.15
                ship_to = et.SubElement(stock_movement, 'ShipTo')
                _preencher_endereco(ship_to, cliente)

                # 4.2.3.16
                ship_from = et.SubElement(stock_movement, 'ShipFrom')
                parceiro_empresa = self.comp and self.comp.partner_id or False
                _preencher_endereco(ship_from, parceiro_empresa)

                # 4.2.3.17
                if picking.date_done:
                    et.SubElement(stock_movement, 'MovementEndTime').text = str(picking.date_done)
                else:
                    et.SubElement(stock_movement, 'MovementEndTime').text = str(picking.date).replace(' ', 'T')
                # 4.2.3.18
                if picking.data_carga is not None:
                    et.SubElement(stock_movement, 'MovementStartTime').text = picking.data_carga and \
                                                                              str(picking.data_carga).replace(' ',
                                                                                                              'T') or \
                                                                              str(picking.date).replace(' ', 'T')
                else:
                    et.SubElement(stock_movement, 'MovementStartTime').text = picking.date.replace(' ', 'T')
                # 4.2.3.19
                if picking.at_code and _(picking.at_code) != "":
                    et.SubElement(stock_movement, 'ATDocCodeID').text = _(picking.at_code)

                # linhas
                n_linha = 0
                for linha_move in picking.move_lines:
                    n_linha += 1
                    # 4.2.3.20
                    line = et.SubElement(stock_movement, 'Line')
                    # 4.2.3.20.1
                    et.SubElement(line, 'LineNumber').text = str(n_linha)
                    # 4.2.3.20.3
                    if not linha_move.product_id.default_code or linha_move.product_id.default_code == '':
                        raise ValidationError(_('Product ' + _(linha_move.product_id.name) +
                                                ' does not have internal number.'))
                    et.SubElement(line, 'ProductCode').text = linha_move.product_id.default_code[:60] or ''
                    # 4.2.3.20.4
                    et.SubElement(line, 'ProductDescription').text = linha_move.product_id.name.ljust(2) or ''
                    # 4.2.3.20.5
                    et.SubElement(line, 'Quantity').text = str(linha_move.product_qty)
                    # 4.2.3.20.6
                    et.SubElement(line, 'UnitOfMeasure').text = linha_move.product_uom.name
                    # 4.2.3.20.7
                    et.SubElement(line, 'UnitPrice').text = str(linha_move.product_id.list_price)
                    # 4.2.3.20.8
                    et.SubElement(line, 'Description').text = ' '
                    # 4.2.3.20.9
                    et.SubElement(line, 'DebitAmount').text = '0.00'  # as nossas guias não são valorizadas

                # 4.2.3.21
                document_totals = et.SubElement(stock_movement, 'DocumentTotals')
                # 4.2.3.20.1
                et.SubElement(document_totals, 'TaxPayable').text = '0.00'
                # 4.2.3.20.2
                et.SubElement(document_totals, 'NetTotal').text = '0.00'
                # 4.2.3.20.3
                et.SubElement(document_totals, 'GrossTotal').text = '0.00'

                movement_of_goods.tail = '\n'
        return movement_of_goods

    
    def _write_sale_order(self, sale, eparent):
        _logger.info("saft :", ' A exportar sale_orders')
        #   4.3.
        #   4.3.4.1.    (DocumentNumber)*
        et.SubElement(eparent, u"DocumentNumber").text = sale.name
        #  4.3.4.2. (ACTUD)*
        et.SubElement(eparent, u"ATCUD").text = sale.atcud or '0'
        #  4.3.4.3. (DocumentStatus)*
        #  4.3.4.3.1. (WorkStatus)
        status_code = 'N'
        for line in sale.order_line:
            self.env.cr.execute('Select invoice_line_id from sale_order_line_invoice_rel '
                                'where order_line_id = %s' % line.id)
            invoice_lines = self.env.cr.fetchall()
            for invoice_line_id in invoice_lines:
                if self.env['account.move.line'].sudo().search([('display_type', '=', False),
                                                         ('id', '=', invoice_line_id[0])]).move_id.hash:
                    status_code = 'F'  # Faturado
                    continue
        if sale.state == 'cancel':
            status_code = 'A'  # Cancelado
        elif status_code == 'F':
            pass
        else:
            status_code = 'N'  # Normal

        document_status = et.SubElement(eparent, u"DocumentStatus")
        et.SubElement(document_status, u"WorkStatus").text = status_code
        et.SubElement(document_status, u"WorkStatusDate").text = str(sale.write_date)[:19].replace(" ", "T")
        if sale.write_uid:
            login = sale.write_uid.login
        elif sale.create_uid:
            login = sale.create_uid.login
        # 4.3.4.3.4. (SourceID)*
        et.SubElement(document_status, u"SourceID").text = login[:30]
        # 4.3.4.3.5. (SourceBilling)*
        et.SubElement(document_status, u"SourceBilling").text = 'P'
        # fim DocumentStatus
        # 4.3.4.3.2. (WorkStatusDate)
        date = str(sale.write_date)[:19].replace(" ", "T")
        # 4.3.4.3.4. (Reason)
        # if sale.state == 'cancel':
        #     et.SubElement(eparent, u"Reason").text = sale.descricao_cancel
        # 4.3.4.4. (Hash)*
        et.SubElement(eparent, u"Hash").text = sale.hash
        # 4.3.4.5. (HashControl)*
        et.SubElement(eparent, u"HashControl").text = str(sale.hash_control)
        # 4.3.4.6. (Period)
        et.SubElement(eparent, u"Period").text = str(sale.date_order)[5:7]
        # 4.3.4.7. (WorkDate)*
        et.SubElement(eparent, u"WorkDate").text = str(sale.date_order.date())
        # 4.3.4.8. (WorkType)*
        et.SubElement(eparent, u"WorkType").text = sale.type_doc
        # 4.3.4.9. (SourceID)*
        et.SubElement(eparent, u"SourceID").text = login[:30]
        # 4.3.4.11. (SystemEntryDate)*
        if sale.hash_date is not False:
            et.SubElement(eparent, u"SystemEntryDate").text = date_format(sale.hash_date, 'DateTimeType')
        # # 4.3.4.13. (CustomerID)**
        et.SubElement(eparent, u"CustomerID").text = str(sale.partner_id.id)
        return True

    
    def _sale_orders(self, start_date, final_date, empresa, esource_documents):
        args_sales = [('date_order', '>=', start_date),
                      ('date_order', '<=', final_date),
                      ('company_id', '=', empresa),
                      ('certificated', '=', True)]
        sale_order = self.env['sale.order'].sudo().search(args_sales)
        if sale_order:
            esource_documents = et.Element('SourceDocuments')
            for element in esource_documents:
                element.tail = '\n'
            esale_orders = et.SubElement(esource_documents, u'WorkingDocuments')

            # totals
            enumber_of_entries_sale = et.SubElement(esale_orders, u"NumberOfEntries")
            etotal_debit_sales = et.SubElement(esale_orders, u"TotalDebit")
            etotal_credit_sales = et.SubElement(esale_orders, u"TotalCredit")

            count_sale = 0
            total_debit_sale = 0
            total_credit_sales = 0

            for sale in sale_order:
                count_sale += 1
                esale = et.SubElement(esale_orders, u"WorkDocument")
                self._write_sale_order(sale, esale)

                # get better cambio from sale order date
                cambio = sale.currency_rate
                if cambio == 0:
                    cambio = 1

                line_no = 0
                for sale_line in sale.order_line:
                    if sale_line.product_id:
                        eline = et.SubElement(esale, u"Line")
                        # 4.3.4.14.1. (LineNumber)*
                        line_no += 1
                        et.SubElement(eline, u"LineNumber").text = str(line_no)
                        # 4.3.4.14.3. (ProductCode)* and 4.3.4.14.4. (ProductDescription)*
                        if not sale_line.product_id:
                            raise ValidationError(_('Linha da ordem de vendanão tem produto: ' + _(sale_line.name)))
                        if sale_line.product_id:
                            if not sale_line.product_id.default_code or sale_line.product_id.default_code == '':
                                raise ValidationError(
                                    _('Product ' + _(sale_line.product_id.name) + ' does not have internal number.'))
                            et.SubElement(eline, u"ProductCode").text = sale_line.product_id.default_code[:60]
                        product_description = (sale_line.product_id and
                                               sale_line.product_id.name or
                                               sale_line.name)[:60]
                        et.SubElement(eline, u"ProductDescription").text = product_description.ljust(2)
                        # 4.3.4.14.5 (Quantity)*
                        et.SubElement(eline, u"Quantity").text = str(sale_line.product_uom_qty)
                        # 4.3.4.14.6. (UnityOfMeasure)*
                        if sale_line.product_id.uom_id:
                            et.SubElement(eline, u"UnitOfMeasure").text = sale_line.product_id.uom_name

                        if sale_line.price_subtotal:
                            amount = round(float(sale_line.price_subtotal) / cambio, 2)
                        else:
                            amount = 0
                        # 4.3.4.14.7. (UnitPrice)*
                        if sale_line.price_unit:
                            et.SubElement(eline, u"UnitPrice").text = str(round(sale_line.price_unit, 2))
                        else:
                            et.SubElement(eline, u"UnitPrice").text = '0.00'
                        # 4.3.4.14.9. (TaxPointDate)*
                        et.SubElement(eline, u"TaxPointDate").text = str(sale_line.order_id.date_order.date())
                        # 4.3.4.14.11. (Description)*
                        et.SubElement(eline, u"Description").text = sale_line.name[:60]
                        # 4.3.4.14.13. (DebitAmount)**
                        et.SubElement(eline, u"CreditAmount").text = str(amount)
                        if sale_line.state != 'cancel':
                            total_credit_sales += amount
                        # 4.3.4.14.14. (CreditAmount)**
                        # 4.3.4.14.15. (Tax)**

                        count = 0
                        for tax in sale_line.tax_id:
                            count += 1
                            if count == 1:
                                # 4.1.4.14.13. (Tax)
                                etax = et.SubElement(eline, u"Tax")
                                # 4.1.4.14.13.1. (TaxType)
                                et.SubElement(etax, u"TaxType").text = str(tax.saft_tax_type)
                                # 4.1.4.14.13.2. (TaxCountryRegion)
                                et.SubElement(etax, u"TaxCountryRegion").text = str(tax.country_region)
                                # 4.3.4.14.15.3. (TaxCode)*
                                et.SubElement(etax, u"TaxCode").text = str(tax.saft_tax_code)
                                # 4.3.4.14.15.4. (TaxPercentage)**
                                et.SubElement(etax, u"TaxPercentage").text = str(int(tax.amount))

                            if tax.saft_tax_type == 'IVA' and tax.amount == 0.0:
                                if not tax.exemption_reason or len(tax.exemption_reason) < 6:
                                    raise ValidationError(_('Missing configuration for exemption reason '
                                                            '(must be at least 6 chars long).'))
                                else:
                                    et.SubElement(eline, u"TaxExemptionReason").text = str(tax.exemption_reason)[4:]
                                    TaxExemptionCode = tax.exemption_reason.split(' ')[0]
                                    et.SubElement(eline, u"TaxExemptionCode").text = str(TaxExemptionCode)

                            if tax.amount == 0.0 and not tax.exemption_reason:
                                raise ValidationError(_('Tax exemption reason in lack on tax named ' + tax.name + '.'))

                        # 4.1.4.14.15  SettlementAmount (optional) - valor do desconto da linha
                        et.SubElement(eline, u"SettlementAmount").text = \
                            str(round(Decimal(((sale_line.discount / 100) *
                                               (sale_line.price_unit * sale_line.product_uom_qty)) / cambio),2))

                if line_no != 0:
                    edocument_totals = et.SubElement(esale, u"DocumentTotals")
                    # 4.3.4.15.1. (TaxPayable)*
                    etax_payable = et.SubElement(edocument_totals, u"TaxPayable")
                    etax_payable.text = sale.amount_tax and str(round(sale.amount_tax / cambio, 2)) or '0.0'
                    # 4.3.4.15.2. (NetTotal)*
                    enet_total = et.SubElement(edocument_totals, u"NetTotal")
                    enet_total.text = sale.amount_untaxed and \
                                      str(round(sale.amount_untaxed / cambio, 2)) or '0.0'
                    # 4.3.4.15.3. (GroossTotal)*
                    egross_total = et.SubElement(edocument_totals, u"GrossTotal")
                    egross_total.text = str(round(float(sale.grosstotal()) / cambio, 2))

                    if sale.currency_id.name != 'EUR':
                        ecurrency = et.SubElement(edocument_totals, u"Currency")
                        # 4.3.4.15.4.1. (CurrencyCode)*
                        ecurrency_code = et.SubElement(ecurrency, u"CurrencyCode")
                        # 4.3.4.15.4.2. (CurrencyAmount)*
                        ecurrency_credit_amount = et.SubElement(ecurrency, u"CurrencyAmount")
                        # 4.3.4.15.4.3. (ExchangeRate)*
                        ecurrency_debit_amount = et.SubElement(ecurrency, u"ExchangeRate")
                        ecurrency_code.text = sale.currency_id.name
                        ecurrency_credit_amount.text = sale.grosstotal()
                        ecurrency_debit_amount.text = str(round(cambio, 4))
            enumber_of_entries_sale.text = str(count_sale)
            #  Totals
            etotal_debit_sales.text = str(float(round(total_debit_sale,2)))
            etotal_credit_sales.text = str(float(round(total_credit_sales,2)))
            return esale_orders

    
    def _write_source_documents(self, start_date, final_date, versao, empresa):
        _logger.info("saft :", ' A exportar Source Documents')

        args = [
            ('invoice_date', '>=', start_date),
            ('invoice_date', '<=', final_date),
            ('hash', '!=', False),
            ('company_id', '=', empresa),
            ('state', '!=', 'draft')]
        if self.tipo == 'S':
            args.append(('move_type', 'in', ['in_invoice', 'in_refund']))
            args.append(('journal_id.self_billing', '=', True))
        else:
            args.append(('move_type', 'in', ['out_invoice', 'out_refund']))
        invoices = self.env['account.move'].search(args, order='internal_number')
        esource_documents = et.Element('SourceDocuments')
        if invoices:
            for element in esource_documents:
                element.tail = '\n'
            esales_invoices = et.SubElement(esource_documents, "SalesInvoices")

            # totals
            enumber_of_entries = et.SubElement(esales_invoices, u"NumberOfEntries")
            etotal_debit = et.SubElement(esales_invoices, u"TotalDebit")
            etotal_credit = et.SubElement(esales_invoices, u"TotalCredit")

            conta_inv = 0
            total_debit = 0
            total_credit = 0

            for invoice in invoices:
                if invoice.date >= start_date and invoice.hash is not None:
                    if final_date is False or invoice.date <= final_date:
                        conta_inv += 1
                        # 4.1.4   Invoice
                        einvoice = et.SubElement(esales_invoices, u"Invoice")
                        self._write_invoice(invoice, einvoice, versao)
                        cambio = 1
                        if invoice.company_id.currency_id.id != invoice.currency_id.id:
                            cambio = invoice.cambio
                            if cambio == 0:
                                cambio = 1
                        # 4.1.4.14  Line
                        line_no = 1
                        for invoice_line in invoice.invoice_line_ids:
                            if not invoice_line.display_type:
                                eline = et.SubElement(einvoice, u"Line")
                                # 4.1.4.14.1  LineNumber
                                et.SubElement(eline, u"LineNumber").text = str(line_no)
                                line_no += 1

                                # 4.1.4.14.2  OrderReferences
                                if invoice.invoice_origin and invoice.move_type != 'out_refund':
                                    eorder_references = et.SubElement(eline, u"OrderReferences")
                                    eoriginating_on = et.SubElement(eorder_references, u"OriginatingON")
                                    eoriginating_on.text = _(invoice.invoice_origin)[:30]

                                # 4.1.4.14.3 ProductCode and 4.1.4.14.4 Description
                                if invoice_line.product_id:
                                    if not invoice_line.product_id.default_code:
                                        raise ValidationError(
                                            _('Product ' + _(invoice_line.product_id.name) +
                                              ' does not have internal reference.'))
                                    et.SubElement(eline, u"ProductCode").text = \
                                        invoice_line.product_id.default_code[:60]
                                prod_descr = (invoice_line.product_id and
                                              invoice_line.product_id.name or invoice_line.name)[:60]
                                et.SubElement(eline, u"ProductDescription").text = prod_descr.ljust(2)

                                # 4.1.4.14.5  Quantity
                                et.SubElement(eline, u"Quantity").text = str(invoice_line.quantity)
                                # 4.1.4.14.6  UnitOfMeasure
                                if invoice_line.product_uom_id:  # unit of measure (optional)
                                    et.SubElement(eline, u"UnitOfMeasure").text = invoice_line.product_uom_id.name

                                if invoice_line.price_subtotal:
                                    amount = round(float(invoice_line.price_subtotal) / cambio, 2)
                                else:
                                    amount = 0

                                # 4.1.4.14.7  UnitPrice
                                if invoice_line.price_unit:
                                    et.SubElement(eline, u"UnitPrice").text = str(round(invoice_line.price_unit, 2))
                                else:
                                    et.SubElement(eline, u"UnitPrice").text = '0.00'

                                    # Valor tributável unitário que não concorre para o Total do documento sem impostos
                                    # (NetTotal). Este valor é o que serve de base de cálculo dos impostos da linha.
                                    # O sinal (debito ou crédito) com que o imposto assim calculado concorre para o
                                    # TaxPayable, resulta da existência na linha do DebitAmount ou do CreditAmount.

                                # TODO: TaxPointDate - data do acto gerador do imposto - da entrega ou prestação do serviço
                                # usar data da guia de remessa, igual à data usada em ShipTo/DeliveryDate
                                et.SubElement(eline, u"TaxPointDate").text = str(invoice.date)

                                # TODO: 4.1.4.14.9 References (optional)
                                if (invoice.invoice_origin or invoice.name) and invoice.move_type == 'out_refund':
                                    ereferences = et.SubElement(eline, u"References")
                                    # TODO: 4.1.4.14.9.1 CreditNote
                                    # ecredit_note = et.SubElement(ereferences, u"CreditNote")
                                    if invoice.invoice_origin:
                                        et.SubElement(ereferences, u"Reference").text = _(invoice.invoice_origin)[:60]
                                    if invoice.reason_cancel:
                                        et.SubElement(ereferences, u"Reason").text = _(invoice.reason_cancel[:50])
                                    if not invoice.reason_cancel and invoice.move_type == 'out_invoice' and  \
                                            invoice.state == 'cancel' and invoice.hash:
                                        raise ValidationError(_('Invoice reason cancel must be defined on invoice numbered'
                                                                + invoice.internal_number + '.'))

                                # 4.1.4.14.10  Description
                                et.SubElement(eline, u"Description").text = invoice_line.name[:60]

                                # debit and credit amount
                                # 4.1.4.14.11**  DebitAmount
                                if invoice.move_type == 'out_refund':
                                    et.SubElement(eline, u"DebitAmount").text = str(amount)
                                    if invoice.state != 'cancel':  # se o estado for A ou F nao somar
                                        total_debit += amount
                                # 4.1.4.14.12**  CreditAmount
                                elif invoice.move_type == 'out_invoice':
                                    et.SubElement(eline, u"CreditAmount").text = str(amount)
                                    if invoice.state != 'cancel':
                                        total_credit += amount

                                # Impostos
                                cont = 0
                                for imposto in invoice_line.tax_ids:
                                    if not invoice_line.display_type:
                                        cont += 1
                                        if cont == 1:
                                            # 4.1.4.14.13 Tax   see invoice_line_tax (optional)
                                            etax = et.SubElement(eline, u"Tax")
                                            # 4.1.4.14.13.1 TaxType
                                            et.SubElement(etax, u"TaxType").text = str(imposto.saft_tax_type)
                                            # 4.1.4.14.13.2  TaxCountryRegion
                                            et.SubElement(etax, u"TaxCountryRegion").text = str(imposto.country_region)
                                            # 4.1.4.14.13.3  TaxCode
                                            et.SubElement(etax, u"TaxCode").text = str(imposto.saft_tax_code)
                                            # 4.1.4.14.13.4**  TaxPercentage ou 4.1.4.14.13.5** TaxAmount
                                            et.SubElement(etax, u"TaxPercentage").text = str(int(imposto.amount))

                                            # 4.1.4.14.14** ExemptionReason - obrigatorio se TaxPercent e TaxAmount ambos zero
                                            if imposto.saft_tax_type == 'IVA' and imposto.amount == 0.0:
                                                if not imposto.exemption_reason or len(imposto.exemption_reason) < 6:
                                                    raise ValidationError(_('Falta configurar o motivo de isenção '
                                                                            '(este tem de ter pelo menos 6 caracteres).'))
                                                else:
                                                    et.SubElement(eline, u"TaxExemptionReason").text = str(imposto.exemption_reason)[4:]
                                                    if versao not in ["1.03_01"]:
                                                        TaxExemptionCode = imposto.exemption_reason.split(' ')[0]
                                                        et.SubElement(eline, u"TaxExemptionCode").text = \
                                                            str(TaxExemptionCode)
                                                        if (imposto.exemption_reason and not TaxExemptionCode) or \
                                                                (TaxExemptionCode and not imposto.exemption_reason):
                                                            raise ValidationError(_('Tax exemption code in lack on tax '
                                                                                    + imposto.name +
                                                                                    'define it in order to proceed'))
                                            if imposto.amount == 0.0 and not imposto.exemption_reason:
                                                raise ValidationError(
                                                    _('Tax exemption reason in lack on tax ' + imposto.name +
                                                      'define it in order to proceed'))
                                        # 4.1.4.14.15  SettlementAmount (optional) - valor do desconto da linha
                                        et.SubElement(eline, u"SettlementAmount").text = \
                                            str(round(Decimal(((invoice_line.discount / 100) *
                                                               (invoice_line.price_unit * invoice_line.quantity)) / cambio), 2))

                        # document totals
                        edocument_totals = et.SubElement(einvoice, u"DocumentTotals")
                        etax_payable = et.SubElement(edocument_totals, u"TaxPayable")
                        enet_total = et.SubElement(edocument_totals, u"NetTotal")
                        # 4.1.4.19.3
                        egross_total = et.SubElement(edocument_totals, u"GrossTotal")
                        etax_payable.text = invoice.amount_tax and str(
                            round(invoice.amount_tax / cambio, 2)) or '0.0'
                        enet_total.text = invoice.amount_untaxed and str(
                            round(invoice.amount_untaxed / cambio, 2)) or '0.0'
                        egross_total.text = str(
                            round(float(invoice.grosstotal()) / cambio, 2))

                        if invoice.currency_id.name != 'EUR':
                            ecurrency = et.SubElement(edocument_totals, u"Currency")
                            ecurrency_code = et.SubElement(ecurrency, u"CurrencyCode")
                            ecurrency_credit_amount = et.SubElement(ecurrency, u"CurrencyAmount")
                            ecurrency_debit_amount = et.SubElement(ecurrency, u"ExchangeRate")
                            ecurrency_code.text = invoice.currency_id.name
                            ecurrency_credit_amount.text = invoice.grosstotal()
                            ecurrency_debit_amount.text = str(round(cambio, 4))

            enumber_of_entries.text = str(conta_inv)

            # totals
            etotal_debit.text = str(float(round(total_debit,2)))
            etotal_credit.text = str(float(round(total_credit,2)))
        docs_m_o_g = self._write_movement_of_goods()
        if docs_m_o_g:
            esource_documents.append(docs_m_o_g)
        # Os pagamento só vão para o saft se o mesmo for Integrado ou se a empresa
        # for de iva de caixa e o saft nao for de contabilidade
        sales = self._sale_orders(start_date, final_date, empresa, esource_documents)
        if sales:
            esource_documents.append(sales)
        if self.tipo in ('I', 'F') or (self.comp.cash_vat_scheme_indicator and self.tipo != 'C'):
            docs_p = self._write_payments()
            if docs_p is not None:
                esource_documents.append(docs_p)

        return esource_documents
