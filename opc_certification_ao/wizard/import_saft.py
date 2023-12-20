# -*- coding: utf-8 -*-

import base64
import datetime
import xml.dom.minidom

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

tipos_saft = [  # ('C', 'Contabilidade'),                         # ctb na v.1
    ('F', u'Facturação'),  # fact na v.1
    # ('I', u'Integrado - Contabilidade e Facturação'), # int
    # ('S', u'Autofacturação'),                         # novo v.2
    # ('P', u'Dados parciais de facturação')        # nao implementado
]
#
# account_paid_values = {
#           'NOR': {
#                         'PT': '24',
#                         'PT-MA': '24331132',
#                         'PT-AC': '24331133'},
#           'INT': {
#                         'PT': '24331121',
#                         'PT-MA': '24331122',
#                         'PT-AC': '24331123'},
#           'RED': {
#                         'PT': '24331111',
#                         'PT-MA': '24331112',
#                         'PT-AC': '24331113'},
#           'ISE': {
#                         'PT': '24331111',
#                         'PT-MA': '24331112',
#                         'PT-AC': '24331113'},
#           'OUT': {
#                         'PT': '24331111',
#                         'PT-MA': '24331112',
#                         'PT-AC': '24331113'}
#         }
complemento_values = {'PT-MA': 'M', 'PT-AC': 'A'}


class wizard_l10n_pt_import_saft(models.Model):
    _name = "wizard.l10n_pt.import.saft"
    _description = "Importar Saft AT - Menu: Contabilidade - Relatorios - Saft - Importar Ficheiro Saft"

    @api.model
    def _default_company(self):
        """Devolve a companhia do utilizador, ou a primeira encontrada"""
        user = self.env['res.users'].browse(self.env.uid)

        if self.env.user.company_id:
            return user.company_id.id
        return self.env['res.company'].search([('parent_id', '=', False)])[0]


    @api.depends('file')
    def _file_content(self):
        try:
            content = base64.decodestring(_(self.file))
        except:
            content = ''
        self.file_content = _(content)

    name = fields.Char(string="Resultado", size=128, readonly=True, copy=False)
    erros = fields.Char(string="Incompatibilidades encontradas", readonly=True, copy=False)
    tipo = fields.Selection(selection=tipos_saft, string="Tipo ficheiro", required=True, default="F", copy=False)
    comp = fields.Many2one('res.company', string="Companhia", required=True, default=_default_company, copy=False)
    file = fields.Binary(string="Ficheiro", copy=False)
    filename = fields.Char(string="Nome do Ficheiro", size=64, readonly=True, copy=False)
    file_content = fields.Text(compute='_file_content', string='Conteudo do Ficheiro', store=True, copy=False)
    state = fields.Selection([('choose', 'choose'),
                                        ('get', 'get')], string="Estado", default=lambda *a: 'choose', copy=False)
    versao = fields.Selection([('1.03_01', '1.03_01')], default='1.03_01', string="Versão", required=True, copy=False)
    partes = fields.Selection([('tudo', 'Tudo'), ('clientes', 'Clientes'), ('produtos', 'Produtos'),
                                         ('faturas', 'Faturas'), ('guias', 'Guias'), ('pagamentos', 'Pagamentos')],
                              string="Partes", required=True,
                              help="No caso de escolher importar incrementalmente os clientes e produtos tem de ser importados antes das faturas",
                              default="tudo", copy=False)
    rollback = fields.Boolean(string="Rollback",
                              help="Se não tiver visto vai fazendo commit à medida que vai importando.", default=True,
                              copy=False)

    def act_cancel(self):
        # self.unlink(ids, context)
        return {'type': 'ir.actions.act_window_close'}

    def act_destroy(self):
        return {'type': 'ir.actions.act_window_close'}

    def get_customer(self, vat, ref, create=False):
        customer = self.env['res.partner'].search([
            '|',
            ('vat', '=', vat),
            ('ref', '=', ref)], limit=1)
        if not customer and not create:
            raise ValidationError('Não exite cliente com o NIF ou Referência ' + ref)
        return customer

    def check_account_adjustments(self, company, type):
        if type.find('out') != -1:
            if company.account_adjustments_sale:
                return company.account_adjustments_sale.id
            else:
                raise ValidationError(
                    _('Precisa de configurar a conta de acertos de casa decimal para venda nas '
                      'configurações da faturação.'))
        else:
            if company.account_adjustments_purchase:
                return company.account_adjustments_purchase.id
            else:
                raise ValidationError(
                    _('Precisa de configurar a conta de acertos de casa decimal para compra nas '
                      'configurações da faturação.'))

    def check_total(self, dict):
        credit = 0
        debit = 0
        new_line = {}
        for line in dict:
            credit += line[2]['credit']
            debit += line[2]['debit']
            searched_accounts = self.env['account.account'].search([
                ('id', '=', line[2]['account_id']),
                ('reconcile', '=', True)
            ])
            if line[2]['account_id'] in searched_accounts.ids:
                from copy import deepcopy
                new_line = deepcopy(line)
        diff = credit - debit
        if round(diff, 2) == 0:
            return dict
        if new_line:
            new_line[2]['account_id'] = self.check_account_adjustments(self.env.user.company_id, 'out')

            if (new_line[2]['credit'] > 0 and diff > 0) or new_line[2]['debit'] > 0 > diff:
                new_line[2]['credit'] = 0
                new_line[2]['debit'] = abs(round(diff, 2))
            else:
                new_line[2]['credit'] = abs(round(diff, 2))
                new_line[2]['debit'] = 0
            dict.append(new_line)
        return dict

    
    def act_getfile(self):
        # historico
        for bug in self:
            new_task_id = self.env['hist.saft'].create({
                'nif': bug.comp.partner_id.vat or '',
                'tipo': 'import',
                'data_criacao': datetime.datetime.now(),
            })

        def converter(valor):
            valor = valor.encode("UTF-8")
            for symbol in [("Ã¡", "á"), ("Ã ", "à"), ("Ã¢", "â"), ("Ã£", "ã"), ("Ã€", "À"), ("Ã‚", "Â"),
                           ("Ãƒ", "Ã"), ("Ã©", "é"), ("Ã¨", "è"), ("Ãª", "ê"), ("Ã‰", "É"), ("Ãˆ", "È"),
                           ("ÃŠ", "Ê"), ("Ã­", "í"), ("Ã¬", "ì"), ("Ã®", "î"), ("ÃŒ", "Ì"), ("ÃŽ", "Î"),
                           ("Ã³", "ó"), ("Ã²", "ò"), ("Ã´", "ô"), ("Ãµ", "õ"), ("Ã“", "Ó"), ("""Ã’""", "Ò"),
                           ("""Ã”""", "Ô"), ("Ã•", "Õ"), ("Ãº", "ú"), ("Ã¹", "ù"), ("Ã»", "û"), ("Ãš", "Ú"),
                           ("Ã™", "Ù"), ("Ã›", "Û"), ("Âº", "º"), ("Âª", "ª"), ("Ã§", "ç"), ("Ã‡", "Ç"),
                           ("â‚¬", "€"), ("Â«", "«"), ("Â»", "»")]:
                valor = valor.replace(symbol[0], symbol[1])

            return valor

        imp = 0
        nimp = 0
        erros = "As incompatibilidades encontradas foram:"
        document = _(self.file_content)

        #   SAFT Faturacao
        if self.tipo == 'F':
            if document:
                document = document.encode("utf-8")
                document = document.replace('& ', '&amp; ')
                document = document.replace('Á', 'A')
                document = document.replace('Í', 'I')
                dom = xml.dom.minidom.parseString(document)
                f = open("document.log", "a")
                f.write("\n" + str(document))
                f.close()

                #   Clientes apto para 1.4
                if self.partes in ['tudo', 'clientes']:
                    clientes = dom.getElementsByTagName("Customer")
                    for cliente in clientes:
                        CustomerID = converter(
                            ((cliente.getElementsByTagName("CustomerID")[0]).childNodes[0]).nodeValue)
                        AccountID = converter(((cliente.getElementsByTagName("AccountID")[0]).childNodes[0]).nodeValue)
                        CustomerTaxID = converter(
                            ((cliente.getElementsByTagName("CustomerTaxID")[0]).childNodes[0]).nodeValue)
                        CompanyName = converter(
                            ((cliente.getElementsByTagName("CompanyName")[0]).childNodes[0]).nodeValue)
                        addr = cliente.getElementsByTagName("BillingAddress")[0]
                        AddressDetail = converter(
                            ((addr.getElementsByTagName("AddressDetail")[0]).childNodes[0]).nodeValue)
                        City = converter(((addr.getElementsByTagName("City")[0]).childNodes[0]).nodeValue)
                        PostalCode = converter(((addr.getElementsByTagName("PostalCode")[0]).childNodes[0]).nodeValue)
                        Country = converter(((addr.getElementsByTagName("Country")[0]).childNodes[0]).nodeValue)
                        SelfBillingIndicator = converter(
                            ((cliente.getElementsByTagName("SelfBillingIndicator")[0]).childNodes[0]).nodeValue)
                        if SelfBillingIndicator == "1":
                            SelfBillingIndicator = True
                        else:
                            SelfBillingIndicator = False

                        self.env.cr.execute("""
                            SELECT id from res_partner
                            where (vat=%s and vat!='999999999') or ref=%s""", (CustomerTaxID, CustomerTaxID))
                        query_partner_id = self.env.cr.fetchone()
                        # todo compare
                        partner_id = self.env['res.partner'].search([
                            '&',
                                '|',
                                    '&', ('vat', '=', CustomerTaxID), ('vat', '!=', '999999999'),
                                    ('ref', 'in', [CustomerTaxID, CustomerID]),
                                ('active', 'in', [True, False])], limit=1)
                        if not partner_id:
                            if AccountID.startswith("21"):
                                receivable_account = self.env['account.account'].search([
                                    ('code', '=like', AccountID),
                                    ('company_id', '=', self.comp.id),
                                    ('active', 'in', [True, False])], limit=1)
                                payable_account = self.env['account.account'].search([
                                    ('code', '=like', "22%"),
                                    ('company_id', '=', self.comp.id),
                                    ('active', 'in', [True, False])], limit=1)
                            elif AccountID.startswith("22"):
                                payable_account = self.env['account.account'].search([
                                    ('code', '=like', AccountID),
                                    ('company_id', '=', self.comp.id),
                                    ('active', 'in', [True, False])], limit=1)
                                receivable_account = self.env['account.account'].search([
                                    ('code', '=like', "21%"),
                                    ('company_id', '=', self.comp.id),
                                    ('active', 'in', [True, False])], limit=1)
                            else:
                                receivable_account = self.env['account.account'].search([
                                    ('code', '=like', "21%"),
                                    ('company_id', '=', self.comp.id),
                                    ('active', 'in', [True, False])], limit=1)

                                payable_account = self.env['account.account'].search([
                                    ('code', '=like', "22%"),
                                    ('company_id', '=', self.comp.id),
                                    ('active', 'in', [True, False])], limit=1)
                            country = self.env['res.country'].search([('code', '=', Country)])
                            if AddressDetail == 'Desconhecido':
                                AddressDetail = ''
                            if City == 'Desconhecido':
                                City = ''
                            if PostalCode == 'Desconhecido':
                                PostalCode = ''

                            if len(str(CustomerTaxID)) != 9:
                                CustomerTaxID = '999999999'

                            self.env['res.partner'].create({
                                'ref': CustomerID or '',
                                'vat': CustomerTaxID,
                                'name': CompanyName or '',
                                'self_bill_sales': SelfBillingIndicator or False,
                                'property_account_receivable_id': receivable_account.id,
                                'property_account_payable_id': payable_account.id,
                                'active': True,
                                'customer': True,
                                'supplier': False,
                                'type': 'contact',
                                'street': AddressDetail or '',
                                'city': City or '',
                                'zip': PostalCode or '',
                                'country_id': country.id,
                                'is_company': True,
                            })
                            if not self.rollback:
                                self.env.cr.execute("commit")

                #   Produtos apto para 1.4
                if self.partes in ['tudo', 'produtos']:
                    produtos = dom.getElementsByTagName("Product")
                    for produto in produtos:
                        ProductType = converter(
                            ((produto.getElementsByTagName("ProductType")[0]).childNodes[0]).nodeValue)
                        ProductCode = converter(
                            ((produto.getElementsByTagName("ProductCode")[0]).childNodes[0]).nodeValue)
                        try:
                            ProductGroup = converter(
                                ((produto.getElementsByTagName("ProductGroup")[0]).childNodes[0]).nodeValue)
                        except:
                            ProductGroup = "All products"
                        ProductDescription = converter(
                            ((produto.getElementsByTagName("ProductDescription")[0]).childNodes[0]).nodeValue)
                        product = self.env['product.product'].search([
                            ('default_code', '=', ProductCode),
                            ('company_id', '=', self.comp.id)], limit=1)
                        if not product:
                            if ProductType == "S":
                                PpType = "service"
                            elif ProductType == "P":
                                PpType = "product"
                            else:
                                PpType = "consu"
                            product_category = self.env['product.category'].search([
                                ('name', '=', ProductGroup)], limit=1)

                            product = self.env['product.product'].create({
                                'name': ProductDescription,
                                'default_code': ProductCode or '',
                                'type': PpType or '',
                                'categ_id': product_category.id or 1,
                            })

                            if not self.rollback:
                                self.env.cr.execute("commit")

                    #    Impostos
                    impostos = dom.getElementsByTagName("TaxTableEntry")
                    for imposto in impostos:
                        TaxType = converter(((imposto.getElementsByTagName("TaxType")[0]).childNodes[0]).nodeValue)
                        TaxCountryRegion = converter(
                            ((imposto.getElementsByTagName("TaxCountryRegion")[0]).childNodes[0]).nodeValue)
                        TaxCode = converter(((imposto.getElementsByTagName("TaxCode")[0]).childNodes[0]).nodeValue)
                        Description = converter(
                            ((imposto.getElementsByTagName("Description")[0]).childNodes[0]).nodeValue)
                        TaxPercentage = converter(
                            ((imposto.getElementsByTagName("TaxPercentage")[0]).childNodes[0]).nodeValue)
                        TaxPercentage = TaxPercentage.replace("%", "")

                        account_paid = "243300"  # account_paid_values
                        account_code = account_paid
                        conta = len(account_code)
                        account = self.env['account.account'].search([
                            ('code', '=', account_code),
                            ('company_id', '=', self.comp.id),
                            ('active', 'in', [True, False])], limit=1)
                        while not account and conta > 3:
                            conta -= 1
                            account_code = account_code[:-1]
                            account = self.env['account.account'].search([
                                ('code', '=', account_code),
                                ('company_id', '=', self.comp.id),
                                ('active', 'in', [True, False])], limit=1)

                        complemento = TaxCountryRegion in complemento_values and \
                                      complemento_values[TaxCountryRegion] or TaxCountryRegion
                        standard_tax = self.env['account.tax'].search([
                            ('saft_tax_code', '=', TaxCode),
                            ('account_id', '!=', False),
                            ('refund_account_id', '!=', False),
                        ], limit=1)
                        if not standard_tax:
                            raise ValidationError(_('Configurar o imposto com o Nivel de Taxa %s com as contas '
                                                    'definidas.') % TaxCode)

                        account_tax_values = {
                            'saft_tax_type': TaxType or '',
                            'country_region': TaxCountryRegion or '',
                            'saft_tax_code': TaxCode or '',
                            'description': Description or '',
                            'name': TaxPercentage + '%' + complemento,
                            'amount': (float(TaxPercentage) / 100),
                            'sequence': 1,
                            'active': True,
                            'include_base_amount': False,
                            'price_include': False,
                            'account_id': standard_tax.account_id.id,
                            'refund_account_id': standard_tax.refund_account_id.id,
                        }
                        sale_account_tax = self.env['account.tax'].search([
                            ('name', '=', TaxPercentage + '%' + complemento),
                            ('type_tax_use', '=', "sale",)], limit=1)
                        if not sale_account_tax:
                            sale_account_tax_values = account_tax_values
                            sale_account_tax_values['type_tax_use'] = "sale"
                            self.env['account.tax'].create(sale_account_tax_values)
                        purchase_account_tax = self.env['account.tax'].search([
                            ('name', '=', TaxPercentage + '%' + complemento),
                            ('type_tax_use', '=', "purchase",)], limit=1)
                        if not purchase_account_tax:
                            purchase_account_tax_values = account_tax_values
                            purchase_account_tax_values['type_tax_use'] = "purchase"
                            self.env['account.tax'].create(purchase_account_tax_values)

                        if self.rollback is False:
                            self.env.cr.execute("commit")

                if self.partes in ['tudo', 'faturas']:
                    faturas = dom.getElementsByTagName("Invoice")
                    for fatura in faturas:
                        InvoiceNo = converter(((fatura.getElementsByTagName("InvoiceNo")[0]).childNodes[0]).nodeValue)
                        DocumentStatus = fatura.getElementsByTagName("DocumentStatus")[0]
                        InvoiceStatus = converter(
                            ((DocumentStatus.getElementsByTagName("InvoiceStatus")[0]).childNodes[0]).nodeValue)
                        Hash = converter(((fatura.getElementsByTagName("Hash")[0]).childNodes[0]).nodeValue)
                        HashControl = converter(
                            ((fatura.getElementsByTagName("HashControl")[0]).childNodes[0]).nodeValue)
                        InvoiceDate = converter(
                            ((fatura.getElementsByTagName("InvoiceDate")[0]).childNodes[0]).nodeValue)
                        InvoiceType = converter(
                            ((fatura.getElementsByTagName("InvoiceType")[0]).childNodes[0]).nodeValue)
                        SpecialRegimes = fatura.getElementsByTagName("SpecialRegimes")[0]
                        SelfBillingIndicator = converter(((SpecialRegimes.getElementsByTagName(
                            "SelfBillingIndicator")[0]).childNodes[0]).nodeValue)
                        SystemEntryDate = converter(
                            ((fatura.getElementsByTagName("SystemEntryDate")[0]).childNodes[0]).nodeValue)
                        CustomerID = converter(((fatura.getElementsByTagName("CustomerID")[0]).childNodes[0]).nodeValue)
                        DocumentTotals = fatura.getElementsByTagName("DocumentTotals")[0]
                        TaxPayable = converter(
                            ((DocumentTotals.getElementsByTagName("TaxPayable")[0]).childNodes[0]).nodeValue)
                        NetTotal = converter(
                            ((DocumentTotals.getElementsByTagName("NetTotal")[0]).childNodes[0]).nodeValue)
                        GrossTotal = converter(
                            ((DocumentTotals.getElementsByTagName("GrossTotal")[0]).childNodes[0]).nodeValue)
                        index = InvoiceNo.find(' ')
                        if index > -1:
                            InvoiceNo = InvoiceNo[index + 1:]

                        residual = '0.00'
                        if InvoiceStatus == 'A':
                            InvoiceStatus = 'cancel'
                        else:
                            InvoiceStatus = 'open'
                            residual = GrossTotal

                        # Diario
                        if SelfBillingIndicator == '1':
                            SelfBillingIndicator = True
                        else:
                            SelfBillingIndicator = False

                        # Na V9 o diario de vendas e usado para faturas e notas de credito
                        saft_inv_type = InvoiceType

                        if saft_inv_type == 'NC':
                            saft_inv_type = 'FT'

                        account_journal = self.env['account.journal'].search([
                            ('integrado', '=', True),
                            ('saft_inv_type', '=', saft_inv_type),
                            ('company_id', '=', self.comp.id),
                            ('type', '=', 'sale'),
                            ('self_billing', '=', SelfBillingIndicator)], limit=1)
                        if not account_journal:
                            raise ValidationError("Falta diário.\n Não existe um diario do tipo 'Vendas', com "
                                                  "'Autofaturação' " + str(SelfBillingIndicator) + " e do tipo:" +
                                                  saft_inv_type + " com visto em integrado.")

                        account_invoice = self.env['account.move'].search([
                            ('internal_number', '=', InvoiceNo),
                            ('journal_id', '=', account_journal.id),
                            ('company_id', '=', self.comp.id)], limit=1)
                        if not account_invoice:
                            print(InvoiceNo)
                            SystemEntryDate = SystemEntryDate.replace('T', ' ')
                            customer = self.get_customer(CustomerID, CustomerID)
                            client_account = self.env['account.account'].search([
                                ('name', '=', 'Clientes gerais'),
                                ('company_id', '=', self.comp.id)], order='id ASC', limit=1)
                            currency = self.env['res.currency'].search([
                                ('name', '=', 'EUR')], order='id ASC', limit=1)
                            if InvoiceType == 'NC':
                                tipo = 'out_refund'
                                m_credit = float(GrossTotal)
                                m_debit = 0.00
                                ml_credit = 0.00
                                ml_debit = float(TaxPayable)
                            else:
                                tipo = 'out_invoice'
                                m_credit = 0.00
                                m_debit = float(GrossTotal)
                                ml_credit = float(TaxPayable)
                                ml_debit = 0.00
                            account_invoice = self.env['account.move'].create({
                                'name': InvoiceNo,
                                'internal_number': InvoiceNo,
                                'state': InvoiceStatus,
                                'hash': Hash,
                                'hash_control': HashControl,
                                'date': InvoiceDate,
                                'journal_id': account_journal.id,
                                'type': tipo,
                                'hash_date': SystemEntryDate,
                                'partner_id': customer.id,
                                'account_id': client_account.id,
                                'currency_id': currency.id,
                                'amount_tax': TaxPayable,
                                'amount_untaxed': NetTotal,
                                'amount_total': GrossTotal,
                                'residual': residual,
                                'isprinted': True,
                            })
                            # criar linha do movimento da fatura
                            account_move_line_dict = [(0, 0, {
                                'partner_id': customer.id,
                                'journal_id': account_journal.id,
                                'account_id': client_account.id,
                                'name': '/',
                                'ref': InvoiceNo.replace("/", "") or '',
                                'date': InvoiceDate,
                                'credit': m_credit,
                                'debit': m_debit,
                                'blocked': False,
                            })]
                            normal_tax_account = self.env['account.account'].search([
                                ('code', '=', '243300'),
                                ('company_id', '=', self.comp.id)], order='id ASC', limit=1)
                            if not normal_tax_account:
                                raise ValidationError("Não existe conta com o código 243300")
                            linhas = fatura.getElementsByTagName("Line")
                            for linha in linhas:
                                OriginatingON = None
                                LineNumber = converter(
                                    ((linha.getElementsByTagName("LineNumber")[0]).childNodes[0]).nodeValue)
                                OrderReferences = linha.getElementsByTagName("OrderReferences")
                                if OrderReferences != []:
                                    OrderReferences = OrderReferences[0]
                                    OriginatingON = converter(((OrderReferences.getElementsByTagName("OriginatingON")[
                                                                    0]).childNodes[0]).nodeValue)
                                ProductCode = converter(
                                    ((linha.getElementsByTagName("ProductCode")[0]).childNodes[0]).nodeValue)
                                Quantity = converter(
                                    ((linha.getElementsByTagName("Quantity")[0]).childNodes[0]).nodeValue)
                                UnitOfMeasure = converter(
                                    ((linha.getElementsByTagName("UnitOfMeasure")[0]).childNodes[0]).nodeValue)
                                UnitPrice = converter(
                                    ((linha.getElementsByTagName("UnitPrice")[0]).childNodes[0]).nodeValue)
                                Description = converter(
                                    ((linha.getElementsByTagName("Description")[0]).childNodes[0]).nodeValue)
                                CreditAmount = linha.getElementsByTagName("CreditAmount")
                                DebitAmount = linha.getElementsByTagName("DebitAmount")
                                price_subtotal = 0
                                if CreditAmount:
                                    price_subtotal = float(((CreditAmount[0]).childNodes[0]).nodeValue)
                                if DebitAmount != []:
                                    price_subtotal = float(((DebitAmount[0]).childNodes[0]).nodeValue)
                                try:
                                    SettlementAmount = converter(
                                        ((linha.getElementsByTagName("SettlementAmount")[0]).childNodes[0]).nodeValue)
                                except:
                                    SettlementAmount = '0.0'

                                # Produto
                                product_id = self.env['product.product'].search([
                                    ('default_code', '=', ProductCode)], limit=1).id or 1
                                product_uom = self.env['product.uom'].search([('name', '=', UnitOfMeasure)], limit=1)
                                if not product_uom:
                                    product_uom = self.env['product.uom'].create({
                                        'name': UnitOfMeasure,
                                        'category_id': 1,
                                        'uom_type': 'reference',
                                        'active': True,
                                        'rounding': 0.010,
                                        'factor': 1,
                                    })
                                product_account = self.env['account.account'].search([('code', '=like', '71%')], limit=1)
                                if price_subtotal == 0.0:
                                    desconto = '0.0'
                                else:
                                    desconto = str(round(((float(SettlementAmount) * 100) / float(price_subtotal)), 2))
                                account_invoice_line = self.env['account.move.line'].create({
                                    'sequence': LineNumber,
                                    'origin': OriginatingON or '',
                                    'product_id': product_id and product_id.id or 1,
                                    'quantity': Quantity,
                                    'price_unit': UnitPrice,
                                    'name': Description,
                                    'uom_id': product_uom.id,
                                    'price_subtotal': price_subtotal,
                                    'discount': desconto,
                                    'invoice_id': account_invoice.id,
                                    'account_id': product_id and product_id.property_account_income_id and
                                                  product_id.property_account_income_id.id or product_account.id,
                                })
                                account_move_line_dict.append((0, 0, {
                                    'partner_id': customer.id,
                                    'journal_id': account_journal.id,
                                    'account_id': product_id and product_id.property_account_income_id and
                                                  product_id.property_account_income_id.id or product_account.id,
                                    'name': Description,
                                    'ref': InvoiceNo.replace("/", "") or '',
                                    'date': InvoiceDate,
                                    'credit': m_debit and price_subtotal,
                                    'debit': m_credit and price_subtotal,
                                    'blocked': False,
                                    'product_id': product_id and product_id.id or 1,
                                    'quantity': Quantity,
                                }))
                                impostos = linha.getElementsByTagName("Tax")
                                for imposto in impostos:
                                    TaxType = converter(
                                        ((imposto.getElementsByTagName("TaxType")[0]).childNodes[0]).nodeValue)
                                    TaxPercentage = converter(
                                        ((imposto.getElementsByTagName("TaxPercentage")[0]).childNodes[0]).nodeValue)
                                    if TaxPercentage == '23.00' or TaxPercentage == '23':
                                        TaxPercentage = '23\%'
                                    elif TaxPercentage == '13.00' or TaxPercentage == '13':
                                        TaxPercentage = '13\%'
                                    elif TaxPercentage == '6.00' or TaxPercentage == '6':
                                        TaxPercentage = '6\%'
                                    else:
                                        TaxPercentage = '0\%'

                                    if TaxType == 'NS':
                                        TaxType = 'IVA'

                                    product_account_tax = self.env['account.tax'].search([
                                        ('saft_tax_type', '=', TaxType),
                                        ('name', 'like', TaxPercentage),
                                        ('type_tax_use', 'in', ['sale', 'all']),
                                        ('company_id', '=', self.comp.id)], limit=1)
                                    if product_account_tax:
                                        self.env.cr.execute("""
                                            INSERT INTO account_invoice_line_tax(invoice_line_id, tax_id)
                                            VALUES (%s, %s)""", (account_invoice_line.id, product_account_tax.id))
                                    else:
                                        raise ValidationError("Falta o Imposto  Com o nome " + TaxPercentage)

                            self.env.cr.execute("""
                                SELECT distinct(lt.tax_id),sum(l.price_subtotal)
                                FROM account_invoice_line_tax lt, account_invoice_line l
                                WHERE lt.invoice_line_id=l.id and l.invoice_id=%s
                                GROUP BY lt.tax_id""", (account_invoice.id,))
                            impostos = self.env.cr.fetchall()
                            seq = 1
                            for imposto in impostos:
                                account_tax = self.env['account.tax'].browse(imposto[0])
                                if not account_tax.account_id:
                                    raise ValidationError(_("O imposto ") + _(account_tax.name) +
                                                          _(" não tem conta definida"))
                                self.env.cr.execute("""
                                    INSERT INTO account_invoice_tax(
                                        create_uid,create_date,account_id,
                                        sequence,invoice_id,amount,
                                        base,tax_id, name)
                                    VALUES (
                                        1, %s, %s,
                                        %s, %s, %s,
                                        %s, %s, %s )""",
                                    (InvoiceDate, normal_tax_account.id,
                                     seq, account_invoice.id, float(imposto[1]) * float(account_tax.amount),
                                     imposto[1], account_tax.id, account_tax.name + '-' + account_tax.description))
                                seq += 1
                                account_move_line_dict.append((0, 0, {
                                    'partner_id': customer.id,
                                    'journal_id': account_journal.id,
                                    'account_id': account_tax.account_id.id,
                                    'name': account_tax.name,
                                    'ref': InvoiceNo.replace("/", "") or '',
                                    'date': InvoiceDate,
                                    'credit': ml_credit,
                                    'debit': ml_debit,
                                    'blocked': False,
                                }))

                            account_move_line_dict = self.check_total(account_move_line_dict)

                            account_move = self.env['account.move'].create({
                                'state': "posted",
                                'name': InvoiceNo or '',
                                'ref': InvoiceNo.replace("/", "") or '',
                                'journal_id': account_journal.id,
                                'date': InvoiceDate,
                                'partner_id': customer.id,
                                'line_ids': account_move_line_dict})
                            account_move_line = self.env['account.move.line'].search([
                                ('account_id', '=', client_account.id),
                                ('move_id', '=', account_move.id)])

                            account_invoice.write({
                                'amount_untaxed': NetTotal,
                                'amount_tax': TaxPayable,
                                'amount_total': GrossTotal,
                                'move_id': account_move.id})

                            # wkf
                            self.env.cr.execute("""
                                INSERT INTO wkf_instance(wkf_id,uid,res_id,res_type,state)
                                VALUES (1,1, %s,'account.move','active');
                                COMMIT""", (account_invoice.id,))
                            self.env.cr.execute("""SELECT max(id) FROM wkf_instance""")
                            id_wkf_instance = self.env.cr.fetchone()[0]
                            self.env.cr.execute("""
                                INSERT INTO wkf_workitem(act_id,inst_id,state)
                                VALUES (%s, %s, 'complete');
                                COMMIT""", ("3", id_wkf_instance))
                            # triggers
                            self.env.cr.execute("SELECT max(id) FROM wkf_workitem")
                            id_wkf_workitem = self.env.cr.fetchone()[0]
                            self.env.cr.execute("""
                                INSERT INTO wkf_triggers(instance_id,workitem_id,model,res_id)
                                VALUES (%s, %s, 'account.move.line', %s)""",
                                    (id_wkf_instance, id_wkf_workitem, account_move_line.id))
                            if not self.rollback:
                                self.env.cr.execute("commit")

                #   Guias
                if self.partes in ['tudo', 'guias']:
                    guias = dom.getElementsByTagName("StockMovement")

                    for guia in guias:
                        DocumentNumber = converter(
                            ((guia.getElementsByTagName("DocumentNumber")[0]).childNodes[0]).nodeValue)
                        DocumentStatus = guia.getElementsByTagName("DocumentStatus")[0]
                        MovementStatus = converter(
                            ((DocumentStatus.getElementsByTagName("MovementStatus")[0]).childNodes[0]).nodeValue)
                        if guia.getElementsByTagName("Hash")[0].childNodes:
                            Hash = converter(((guia.getElementsByTagName("Hash")[0]).childNodes[0]).nodeValue)
                        else:
                            Hash = False

                        if guia.getElementsByTagName("HashControl")[0].childNodes:
                            HashControl = converter(
                                ((guia.getElementsByTagName("HashControl")[0]).childNodes[0]).nodeValue)
                        else:
                            HashControl = False

                        # HashControl = converter(((guia.getElementsByTagName("HashControl")[0]).childNodes[0]).nodeValue)
                        MovementDate = converter(
                            ((guia.getElementsByTagName("MovementDate")[0]).childNodes[0]).nodeValue)
                        MovementType = converter(
                            ((guia.getElementsByTagName("MovementType")[0]).childNodes[0]).nodeValue)
                        SystemEntryDate = converter(
                            ((guia.getElementsByTagName("SystemEntryDate")[0]).childNodes[0]).nodeValue)
                        CustomerID = converter(((guia.getElementsByTagName("CustomerID")[0]).childNodes[0]).nodeValue)

                        MovementEndTime = guia.getElementsByTagName("MovementEndTime")
                        if MovementEndTime != []:
                            MovementEndTime = converter(((MovementEndTime[0]).childNodes[0]).nodeValue)
                        else:
                            MovementEndTime = "2014-01-01 00:00:00"
                        MovementStartTime = converter(
                            ((guia.getElementsByTagName("MovementStartTime")[0]).childNodes[0]).nodeValue)

                        index = DocumentNumber.find(' ')
                        if index > -1:
                            DocumentNumber = DocumentNumber[index + 1:]

                        stock_picking = self.env['stock.picking'].search([
                            ('name', '=', DocumentNumber),
                            ('company_id', '=', self.comp.id)])
                        if not stock_picking:
                            estado = 'done'
                            if str(MovementStatus) == "A":
                                estado = 'cancel'

                            MovementDate = MovementDate.replace("T", " ")

                            tipo = 'out'
                            if str(MovementType) == 'GD':
                                tipo = 'in'
                            elif str(MovementType) == 'GT':
                                tipo = 'internal'

                            customer = self.get_customer(CustomerID, CustomerID)
                            stock_picking_type = self.env['stock.picking.type'].search([
                                ('code', '=', 'outgoing')])
                            if not stock_picking_type:
                                raise ValidationError('Tipo de Recolha com Tipo de Operaçao:"Cliente" nao existe.')

                            if not stock_picking_type.default_location_src_id:
                                location_src = self.env['stock.location'].search([
                                    ('usage', '=', 'internal'),
                                    ('company_id', '=', self.comp.id)], limit=1)
                            else:
                                location_src = stock_picking_type.default_location_src_id

                            if not stock_picking_type.default_location_dest_id:
                                location_dest = self.env['stock.location'].search([
                                    ('usage', '=', 'customer'),
                                    ('company_id', '=', self.comp.id)], limit=1)
                            else:
                                location_dest = stock_picking_type.default_location_dest_id

                            stock_picking = self.env['stock.picking'].create({
                                'name': DocumentNumber,
                                'state': estado,
                                'hash': Hash,
                                'hash_control': HashControl,
                                'date': MovementDate,
                                'hash_date': SystemEntryDate.replace("T", " "),
                                'partner_id': customer.id,
                                'data_descarga': MovementEndTime.replace("T", " "),
                                'data_carga': MovementStartTime.replace("T", " "),
                                'picking_type_id': stock_picking_type.id,
                                'location_id': location_src.id,
                                'location_dest_id': location_dest.id,
                                'move_type': 'one',
                                'invoice_state': 'none',
                            })

                            Lines = guia.getElementsByTagName("Line")
                            for Line in Lines:
                                ProductCode = converter(
                                    ((Line.getElementsByTagName("ProductCode")[0]).childNodes[0]).nodeValue)
                                ProductDescription = converter(
                                    ((Line.getElementsByTagName("ProductDescription")[0]).childNodes[0]).nodeValue)
                                Quantity = converter(
                                    ((Line.getElementsByTagName("Quantity")[0]).childNodes[0]).nodeValue)
                                UnitOfMeasure = converter(
                                    ((Line.getElementsByTagName("UnitOfMeasure")[0]).childNodes[0]).nodeValue)
                                Description = converter(
                                    ((Line.getElementsByTagName("Description")[0]).childNodes[0]).nodeValue)

                                # Produto
                                product = self.env['product.product'].search([
                                    ('default_code', '=', ProductCode),
                                    ('company_id', '=', self.comp.id)])
                                if not product:
                                    raise ValidationError("O produto com o código '" + ProductCode +
                                                          "' não existe atualmente no sistema. Considere em cria-lo.")

                                product_uom = self.env['product.uom'].search([
                                    ('name', '=', UnitOfMeasure)])
                                if not product_uom:
                                    product_uom = self.env['product.uom'].create({
                                        'name': UnitOfMeasure,
                                        'category_id': 1,
                                        'uom_type': 'reference',
                                        'active': True,
                                        'rounding': 0.010,
                                        'factor': 1,
                                    })

                                # locat

                                if tipo == 'out':
                                    location_id = location_src.id
                                    location_dest_id = location_dest.id
                                elif tipo == 'internal':
                                    location_id = location_src.id
                                    location_dest_id = location_src.id
                                else:
                                    location_id = False
                                    location_dest_id = False

                                self.env['stock.move'].create({
                                    'picking_id': stock_picking.id,
                                    'product_id': product.id,
                                    'name': ProductDescription,
                                    'product_uom_qty': Quantity,
                                    'product_uom': product_uom.id,
                                    'note': Description,
                                    'location_id': location_id,
                                    'location_dest_id': location_dest_id,
                                })

                                if not self.rollback:
                                    self.env.cr.execute("commit")

                                    ######################
                                    ##   Fim Guias      ##
                                    ######################

                # Pagamentos
                if self.partes in ['tudo', 'pagamentos']:
                    pagamentos = dom.getElementsByTagName("Payment")
                    for pagamento in pagamentos:
                        PaymentRefNo = converter(
                            ((pagamento.getElementsByTagName("PaymentRefNo")[0]).childNodes[0]).nodeValue)
                        TransactionDate = converter(
                            ((pagamento.getElementsByTagName("TransactionDate")[0]).childNodes[0]).nodeValue)
                        PaymentType = converter(
                            ((pagamento.getElementsByTagName("PaymentType")[0]).childNodes[0]).nodeValue)
                        DocumentStatus = pagamento.getElementsByTagName("DocumentStatus")[0]
                        PaymentStatus = converter(
                            ((DocumentStatus.getElementsByTagName("PaymentStatus")[0]).childNodes[0]).nodeValue)
                        SystemEntryDate = converter(
                            ((pagamento.getElementsByTagName("SystemEntryDate")[0]).childNodes[0]).nodeValue)
                        CustomerID = converter(
                            ((pagamento.getElementsByTagName("CustomerID")[0]).childNodes[0]).nodeValue)

                        PaymentMethod = pagamento.getElementsByTagName("PaymentMethod")[0]
                        PaymentMechanism = converter(
                            ((PaymentMethod.getElementsByTagName("PaymentMechanism")[0]).childNodes[0]).nodeValue)
                        PaymentAmount = converter(
                            ((PaymentMethod.getElementsByTagName("PaymentAmount")[0]).childNodes[0]).nodeValue)
                        PaymentDate = converter(
                            ((PaymentMethod.getElementsByTagName("PaymentDate")[0]).childNodes[0]).nodeValue)


                        indexRefNo = PaymentRefNo.find(' ')
                        if indexRefNo > -1:
                            PaymentRefNo = PaymentRefNo[indexRefNo + 1:]
                        account_payment = self.env['account.payment'].search([
                            ('name', '=', PaymentRefNo),
                            ('company_id', '=', self.comp.id)], limit=1)
                        if not account_payment:
                            estado = 'draft'  # 'posted'
                            if str(PaymentStatus) == "A":
                                estado = 'cancel'

                            # Cliente
                            customer = self.get_customer(CustomerID, CustomerID)
                            receipt_account_journal = self.env['account.journal'].search([
                                ('integrado', '=', True),
                                ('saft_inv_type', '=', 'receipt'),
                                ('company_id', '=', self.comp.id)], limit=1)
                            if not receipt_account_journal:
                                raise ValidationError(_(
                                    'Falta diário\n Não existe um diario do tipo: recebimento com visto em integrado.'))

                            receipt_account = self.env['account.account'].search([
                                ('code', '=like', '2111%'),
                                ('company_id', '=', self.comp.id)], limit=1)
                            if not receipt_account:
                                raise ValidationError("Não existe conta com o código a começar com '2111..'")

                            payment_method = self.env['account.payment.method'].search([
                                ('name', '=', 'Manual'),
                                ('payment_type', '=', 'inbound')], limit=1)
                            account_payment = self.env['account.payment'].create({
                                'name': PaymentRefNo,
                                'payment_date': PaymentDate,
                                'payment_type': 'inbound',
                                'tipo_pagamento': PaymentType,
                                'type': 'receipt',
                                'state': estado,
                                'journal_id': receipt_account_journal.id,
                                'account_id': receipt_account.id,
                                'hash_date': SystemEntryDate,
                                'partner_id': customer.id,
                                'payment_mechanism': PaymentMechanism,
                                'amount': PaymentAmount,
                                'payment_method_id': payment_method.id
                            })

                            # criar movimento do pagamento
                            self.env['account.move'].create({
                                'state': "draft",
                                'name': PaymentRefNo or '',
                                'ref': PaymentRefNo.replace("/", "") or '',
                                'journal_id': receipt_account_journal.id,
                                'date': TransactionDate,
                                'partner_id': customer.id,
                            })
                            payment_account = receipt_account_journal.default_debit_account_id.id or \
                                 self.env['account.account'].search([
                                    ('code', '=', '120100'),
                                    ('company_id', '=', self.comp.id)], limit=1)
                            if not payment_account:
                                raise ValidationError("A conta de pagamento com o código '120100' não existe")

                            lines = pagamento.getElementsByTagName("Line")
                            for line in lines:
                                SourceDocumentID = line.getElementsByTagName("SourceDocumentID")
                                SourceDocumentID = SourceDocumentID[0]
                                OriginatingON = converter(((SourceDocumentID.getElementsByTagName("OriginatingON")[
                                                                0]).childNodes[0]).nodeValue)
                                InvoiceDate = converter(((SourceDocumentID.getElementsByTagName("InvoiceDate")[
                                    0]).childNodes[0]).nodeValue)

                                index = OriginatingON.find(' ')
                                account_invoice = self.env['account.move']
                                if OriginatingON is not None:
                                    if OriginatingON.find(' ') > -1:
                                        account_invoice = self.env['account.move'].search([
                                            ('internal_number', 'in',
                                                [OriginatingON[index + 1:], OriginatingON[index + 1:].replace(".", "/")]),
                                            ('company_id', '=', self.comp.id)], limit=1)
                                if account_invoice:
                                    account_invoice.write({'state': 'paid', 'residual': 0})
                                    # criar linha do movimento da linha do pagamento
                                    self.env.cr.execute("""
                                                        SELECT ml.id
                                                        FROM account_move_line ml, account_account aa
                                                        WHERE ml.move_id = %s and
                                                            ml.account_id = aa.id and
                                                            aa.reconcile = TRUE""",
                                    (account_invoice.move_id.id,))
                                    move_line_id = self.env.cr.fetchone()
                                    if move_line_id and move_line_id[0]:
                                        account_move_line = self.env['account.move.line'].browse(move_line_id[0])
                                        invoice_name = account_move_line.move_id.name
                                    else:
                                        raise ValidationError("Nenhuma linha da fatura " +
                                                account_invoice.invoice_number + " permite reconciliação.")

                                else:
                                    account_move_line = self.env['account.move.line'].search([
                                        ('name', 'in',
                                         [OriginatingON[index + 1:], OriginatingON[index + 1:].replace(".", "/")]),
                                        ('company_id', '=', self.comp.id),
                                        ('account_id.reconcile', '=', True)
                                    ], limit=1)
                                    if not account_move_line:
                                        raise ValidationError("Não foi encontrada fatura com o número " +
                                                OriginatingON[index + 1:] + ", nem movimentos dos Saldos Iniciais. ")
                                    invoice_name = account_move_line.name

                                account_payment.write({
                                    'payment_move_line': [(0, 0, {
                                            'name': invoice_name,
                                            'valor_pagar': float(PaymentAmount),
                                            'valor_original': account_move_line.balance,
                                            'doc_origem': invoice_name,
                                            'amount_residual': abs(account_move_line.balance) - float(PaymentAmount),
                                            # 'account_id': receipt_account.id,
                                            'enc_contas': True,
                                            'move_line_id': account_move_line.id,
                                            'residual_original': float(PaymentAmount),
                                            'date': InvoiceDate,
                                            'ref': invoice_name,
                                            'tipo_doc': 'FT',
                                    })]
                                })
                            ctx = self.env.context.copy()
                            ctx['import'] = True
                            account_payment.with_context(ctx).post()

                            if not self.rollback:
                                self.env.cr.execute("commit")

            res = "Importou " + str(imp) + " documentos e não importou " + str(nimp) + " documentos"
            if erros == "As incompatibilidades encontradas foram:":
                erros = "Não foram encontradas incompatibilidades"
            return self.write({'state': 'get', 'name': res, 'erros': erros})

        ############################
        ##   SAFT Contabilidade   ##
        ############################
        if self.tipo == 'C':
            document = document.encode("utf-8")
            document = document.replace('& ', '&amp; ')
            document = document.replace('Á', 'A')
            document = document.replace('Í', 'I')

            dom = xml.dom.minidom.parseString(document)

            ############################
            ##   Contas               ##
            ############################
            #todo todas???
            self.env.cr.execute("update account_account_type set close_method='unreconciled'")

            contas = dom.getElementsByTagName("GeneralLedger")

            # self.env.cr.execute("select id from account_account_type where code='view' order by id")
            # user_type = self.env.cr.fetchone()[0]
            view_user_type = self.env['account.account.type'].search([('code', '=', 'view')], order='id', limit=1)
            # self.env.cr.execute("select c.name from res_company c, res_users u where c.id=u.company_id and u.id=" + str(self.env.uid))
            # nome_empresa = self.env.cr.fetchone()[0]
            conta_mae = self.env['account.account'].create({
                'user_type': view_user_type.id,
                'code': '0',
                'name': self.env.user.company_id.name,
                'type': "view",
                'currency_mode': "current",
                'centralized': False,
                'reconcile': False,
                'level': 0,
            })

            parent_id = None
            last_acc = None
            for conta in contas:
                AccountID = converter(((conta.getElementsByTagName("AccountID")[0]).childNodes[0]).nodeValue)
                AccountDescription = converter(
                    ((conta.getElementsByTagName("AccountDescription")[0]).childNodes[0]).nodeValue)

                # se esta conta é filha (maior do que a anterior) da anterior, marcar essa anterior como view
                if last_acc != None and len(AccountID) > len(last_acc):
                    self.env.cr.execute(
                        "select id from account_account where code='" + str(last_acc) + "' and company_id=" + str(
                            self.comp.id))
                    aux = self.env.cr.fetchone()[0]
                    self.env['account.account'].write([aux], {'type': 'view'})
                else:
                    # caso não seja encontrar a conta pai
                    parent_id = None
                    paiAccountID = AccountID[:-1]
                    aux = None
                    encontrou = False
                    while len(paiAccountID) > 0 and (aux == None or aux[0] == None):
                        self.env.cr.execute(
                            "select id,code from account_account where code='" + paiAccountID + "' and company_id=" + str(
                                self.comp.id))
                        aux = self.env.cr.fetchone()
                        if aux != None and aux[0] != None:
                            parent_id = aux[0]
                            last_acc = aux[1]
                            encontrou = True
                            paiAccountID = ''
                        else:
                            paiAccountID = paiAccountID[:-1]
                    # caso não exista criar a conta pai
                    if encontrou == False:
                        conta_pai = AccountID[:1]
                        self.env.cr.execute("select id from account_account_type where code='view' order by id")
                        user_type = self.env.cr.fetchone()[0]
                        account_description_dict = {
                            1: 'MEIOS FINANCEIROS LÍQUIDOS',
                            2: 'CONTAS A RECEBER E A PAGAR',
                            3: 'INVENTÁRIOS E ACTIVOS BIOLÓGICOS',
                            4: 'INVESTIMENTOS',
                            5: 'CAPITAL, RESERVAS E RESULTADOS TRANSITADOS',
                            6: 'GASTOS',
                            7: 'RENDIMENTOS',
                            8: 'RESULTADOS',
                            9: '9'}
                        AccountDescription = account_description_dict[conta_pai]
                        # if conta_pai == 1:
                        #     AccountDescription = 'MEIOS FINANCEIROS LÍQUIDOS'
                        # elif conta_pai == 2:
                        #     AccountDescription = 'CONTAS A RECEBER E A PAGAR'
                        # elif conta_pai == 3:
                        #     AccountDescription = 'INVENTÁRIOS E ACTIVOS BIOLÓGICOS'
                        # elif conta_pai == 4:
                        #     AccountDescription = 'INVESTIMENTOS'
                        # elif conta_pai == 5:
                        #     AccountDescription = 'CAPITAL, RESERVAS E RESULTADOS TRANSITADOS'
                        # elif conta_pai == 6:
                        #     AccountDescription = 'GASTOS'
                        # elif conta_pai == 7:
                        #     AccountDescription = 'RENDIMENTOS'
                        # elif conta_pai == 8:
                        #     AccountDescription = 'RESULTADOS'
                        # elif conta_pai == 9:
                        #     AccountDescription = '9'
                        # inserir a conta pai
                        parent_id = self.env['account.account'].create({
                            'parent_id': conta_mae,
                            'user_type': user_type,
                            'code': str(conta_pai),
                            'name': AccountDescription,
                            'type': "view",
                            'currency_mode': "current",
                            'centralized': False,
                            'reconcile': False,
                            'level': 1,
                        })
                        last_acc = str(conta_pai)

                # DADOS PARA A CONTA CORRENTE
                tipo = "view"
                if len(AccountID) > 1:
                    # if data_contas[AccountID]!=None:
                    tipo = "other"
                    if AccountID[:2] == '11':
                        tipo = "liquidity"
                    if AccountID[:2] == '21':
                        tipo = "receivable"
                    if AccountID[:2] == '22':
                        tipo = "payable"

                # self.env.cr.execute("select id from account_account_type where code='view' order by id")
                # user_type = self.env.cr.fetchone()[0]
                account_type = self.env['account.account.type'].search([
                    ('code', '=', 'view')], order='id')

                # contas gerais
                account_type_code_dict = {
                    '266': 'Accionistas/socios',
                    '269': 'Accionistas/socios',
                    '2741': 'Activos por impostos diferidos',
                    '372': 'Activos biologicos',
                    '4111': 'Participacoes financeiras m.e.p.',
                    '4112': 'Part. fin. out. metod.',
                    '4113': 'Outros activos financeiros',
                    '4121': 'Participacoes financeiras m.e.p.',
                    '4122': 'Part. fin. out. metod.',
                    '4123': 'Outros activos financeiros',
                    '4131': 'Participacoes financeiras m.e.p.',
                    '4132': 'Part. fin. out. metod.',
                    '4133': 'Outros activos financeiros',
                    '4141': 'Part. fin. out. metod.',
                    '415': 'Outros activos financeiros',
                    '42': 'Propriedades de investimento',
                    '43': 'Activos fixos tangiveis',
                    '44': 'Activos intangiveis',
                    '441': 'Trespasse (goodwill)',
                    '45': 'Activos fixos tangiveis',
                    '452': 'Activos fixos tangiveis',
                    '453': 'Activos intangiveis',
                    '454': 'Propriedades de investimento',
                    '451': 'Outros activos financeiros',
                    '6': 'liability',
                    '7': 'asset',
                    '8': 'equity',

                }
                if tipo != "view" and AccountID[:1] in account_type_code_dict:
                    account_type = self.env['account.account.type'].search([
                        ('code', '=', account_type_code_dict[AccountID[:1]])], order='id DESC')

                    # Activo não corrente
                if tipo != "view" and (AccountID[:2] == "43" or AccountID[:3] == "452" or (int(AccountID[:3]) >= 454 and int(AccountID[:2]) < 46)):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Activos fixos tangiveis' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:2] == "42" or AccountID[:2] == "454"):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Propriedades de investimento' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:3] == "441":
                    self.env.cr.execute("select id from account_account_type where code='Trespasse (goodwill)' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and ((AccountID[:2] == "44" and AccountID[:3] != "441") or AccountID[:3] == "453"):
                    self.env.cr.execute("select id from account_account_type where code='Activos intangiveis' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:3] == "372":
                    self.env.cr.execute("select id from account_account_type where code='Activos biologicos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:4] == "4111" or AccountID[:4] == "4121" or (int(AccountID[:4]) >= 4131 and int(AccountID[:2]) < 42)):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Participacoes financeiras m.e.p.' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:4] == "4112" or AccountID[:4] == "4122" or AccountID[:4] == "4132" or (int(AccountID[:4]) >= 4141 and int(AccountID[:2]) < 42)):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Part. fin. out. metod.' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:3] == "266" or (int(AccountID[:3]) >= 268 and int(AccountID[:3]) < 270)):
                    self.env.cr.execute("select id from account_account_type where code='Accionistas/socios' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:4] == "4113" or AccountID[:4] == "4123" or AccountID[:4] == "4133" or AccountID[:4] == "4113" or (int(AccountID[:3]) >= 415 and int(AccountID[:2]) < 42) or AccountID[:4] == "451"):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Outros activos financeiros' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:4] == "2741":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Activos por impostos diferidos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                    # Activo corrente
                if tipo != "view" and ((int(AccountID[:2]) >= 32 and int(AccountID[:2]) < 37) or AccountID[:2] == "39"):
                    self.env.cr.execute("select id from account_account_type where code='Inventarios' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:4] == "371":
                    self.env.cr.execute("select id from account_account_type where code='Activos biologicos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and ((int(AccountID[:3]) >= 211 and int(AccountID[:2]) < 22)):
                    self.env.cr.execute("select id from account_account_type where code='Clientes' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and ((int(AccountID[:3]) >= 228 and int(AccountID[:2]) < 23) or (
                        int(AccountID[:4]) >= 2713 and int(AccountID[:2]) < 28)):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Adiantamentos a fornecedores' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "24":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Estado e outros entes publicos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (
                        AccountID[:3] == "263" or (int(AccountID[:3]) >= 268 and int(AccountID[:2]) < 27)):
                    self.env.cr.execute("select id from account_account_type where code='Accionistas/socios' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:3] == "232" or (int(AccountID[:3]) >= 238 and int(AccountID[:2]) < 24) or AccountID[:4] == "2721" or (int(AccountID[:3]) >= 278 and int(AccountID[:2]) < 28)):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Outras contas a receber' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:3] == "281":
                    self.env.cr.execute("select id from account_account_type where code='Diferimentos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:4] == "1411" or AccountID[:4] == "1421"):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Activos financeiros detidos neg.' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:4] == "1431":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Outros activos financeiros' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "46":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Activos nao correntes det vend.' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:2] == "11" or AccountID[:2] == "12" or AccountID[:2] == "13"):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Caixa e depositos bancarios' order by id desc")
                    user_type = self.env.cr.fetchone()[0]

                    # Capital próprio
                if tipo != "view" and (AccountID[:2] == "52" or AccountID[:3] == "261" or AccountID[:3] == "262"):
                    self.env.cr.execute("select id from account_account_type where code='Capital realizado' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "52":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Accoes (quotas) proprias' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "53":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Outros instrumentos de cap. pro.' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "54":
                    self.env.cr.execute("select id from account_account_type where code='Premios de emissao' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:3] == "551":
                    self.env.cr.execute("select id from account_account_type where code='Reservas legais' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:3] == "552":
                    self.env.cr.execute("select id from account_account_type where code='Outras reservas' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "56":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Resultados transitados' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "57":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Ajustamentos em act. fin.' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "58":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Excedentes de revalorizacao' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "59":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Outras variacoes no capital pro.' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:3] == "818":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Resultado liquido do periodo' order by id desc")
                    user_type = self.env.cr.fetchone()[0]

                    # Passivo (Passivo não corrente)
                if tipo != "view" and AccountID[:2] == "29":
                    self.env.cr.execute("select id from account_account_type where code='Provisoes' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "25":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Financiamentos obtidos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:3] == "273":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Respons. por ben. pos-emprego' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:4] == "2742":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Passivos por impostos diferidos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:3] == "237" or AccountID[:4] == "2711" or AccountID[:4] == "2712" or AccountID[:3] == "275"):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Outras contas a pagar' order by id desc")
                    user_type = self.env.cr.fetchone()[0]

                    # Passivo (Passivo corrente)
                if tipo != "view" and (AccountID[:3] == "221" or AccountID[:3] == "222" or AccountID[:3] == "225"):
                    self.env.cr.execute("select id from account_account_type where code='Fornecedores' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:3] == "218" or AccountID[:3] == "276"):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Adiantamentos de clientes' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "24":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Estado e outros entes publicos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:3] == "264" or AccountID[:3] == "265" or AccountID[:3] == "268"):
                    self.env.cr.execute("select id from account_account_type where code='Accionistas/socios' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "25":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Financiamentos obtidos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:3] == "231" or AccountID[:3] == "238" or AccountID[:4] == "2711" or AccountID[:4] == "2712" or AccountID[:4] == "2722" or AccountID[:3] == "278"):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Outras contas a pagar' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:3] == "282" or AccountID[:3] == "283"):
                    self.env.cr.execute("select id from account_account_type where code='Diferimentos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:4] == "1412" or AccountID[:4] == "1422"):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Passivos financeiros det. neg.' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:4] == "1432":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Outros passivos financeiros' order by id desc")
                    user_type = self.env.cr.fetchone()[0]

                # inserir a conta atual
                acc_id = self.env['account.account'].create({
                    'parent_id': parent_id,
                    'user_type': user_type,
                    'code': AccountID or '',
                    'name': AccountDescription or '',
                    'type': tipo,
                    'currency_mode': "current",
                    'centralized': False,
                    'reconcile': False,
                    'level': len(AccountID),
                })

                # GUARDAR A CONTA ATUAL, PARA SER A ANTERIOR DA PROXIMA
                parent_id = acc_id
                last_acc = AccountID

            # actulizar levels
            self.env.cr.execute("select id,parent_id from account_account where id!=" + str(conta_mae))
            contas = self.env.cr.fetchall()
            for conta in contas:
                nivel = 1
                parent_id = conta[1]
                while parent_id != conta_mae:
                    nivel = nivel + 1
                    self.env.cr.execute("select parent_id from account_account where id=" + str(parent_id))
                    parent_id = self.env.cr.fetchone()[0]
                self.env['account.account'].write([conta[0]], {'level': nivel})

            ############################
            ##       Fim Contas       ##
            ##       Clientes         ##
            ############################
            clientes = dom.getElementsByTagName("Customer")

            for cliente in clientes:
                # <CustomerID>003</CustomerID>
                # <AccountID>211110023</AccountID>
                # <CustomerTaxID>000000000</CustomerTaxID>
                # <CompanyName>Institut Camille Milret</CompanyName>
                # <BillingAddress>
                #	<AddressDetail>Desconhecido</AddressDetail>
                #	<City>Desconhecido</City>
                #	<PostalCode>Desconhecido</PostalCode>
                #	<Country>FR</Country>
                # </BillingAddress>
                # <SelfBillingIndicator>0</SelfBillingIndicator>
                CustomerID = converter(((cliente.getElementsByTagName("CustomerID")[0]).childNodes[0]).nodeValue)
                AccountID = converter(((cliente.getElementsByTagName("AccountID")[0]).childNodes[0]).nodeValue)
                CustomerTaxID = converter(((cliente.getElementsByTagName("CustomerTaxID")[0]).childNodes[0]).nodeValue)
                CompanyName = converter(((cliente.getElementsByTagName("CompanyName")[0]).childNodes[0]).nodeValue)
                addr = cliente.getElementsByTagName("BillingAddress")[0]
                AddressDetail = converter(((addr.getElementsByTagName("AddressDetail")[0]).childNodes[0]).nodeValue)
                City = converter(((addr.getElementsByTagName("City")[0]).childNodes[0]).nodeValue)
                PostalCode = converter(((addr.getElementsByTagName("PostalCode")[0]).childNodes[0]).nodeValue)
                Country = converter(((addr.getElementsByTagName("Country")[0]).childNodes[0]).nodeValue)
                SelfBillingIndicator = converter(
                    ((cliente.getElementsByTagName("SelfBillingIndicator")[0]).childNodes[0]).nodeValue)
                if SelfBillingIndicator == "1":
                    SelfBillingIndicator = True
                else:
                    SelfBillingIndicator = False

                self.env.cr.execute("select id from account_account where code='" + AccountID + "'")
                aux = self.env.cr.fetchone()
                if aux != None and aux[0] != None:
                    AccountID = aux[0]
                else:
                    AccountID = None

                self.env.cr.execute("select id from res_country where code='" + Country + "'")
                aux = self.env.cr.fetchone()
                if aux != None and aux[0] != None:
                    Country = aux[0]
                else:
                    Country = None

                if AddressDetail == 'Desconhecido':
                    AddressDetail = ''
                if City == 'Desconhecido':
                    City = ''
                if PostalCode == 'Desconhecido':
                    PostalCode = ''

                id_cliente = self.env['res.partner'].create({
                    'ref': CustomerID or '',
                    'vat': CustomerTaxID or '',
                    'name': CompanyName or '',
                    'self_bill_sales': SelfBillingIndicator or False,
                    'property_account_receivable': AccountID,
                    'property_account_payable': AccountID,
                    'active': True,
                    'customer': True,
                    'supplier': False,
                    # 7
                    'type': 'default',
                    'street': AddressDetail or '',
                    'city': City or '',
                    'zip': PostalCode or '',
                    'country_id': Country,
                })


            ############################
            ##    Fim Clientes        ##
            ##    Fornecedores        ##
            ############################
            fornecedores = dom.getElementsByTagName("Supplier")

            for fornecedor in fornecedores:
                # <Supplier>
                #    <SupplierID>001</SupplierID>
                #    <AccountID>221110001</AccountID>
                #    <SupplierTaxID>510011993</SupplierTaxID>
                #    <CompanyName>Flamínio &amp; Teixeira, Lda</CompanyName>
                #    <BillingAddress>
                #            <AddressDetail>Desconhecido</AddressDetail>
                #            <City>Desconhecido</City>
                #            <PostalCode>Desconhecido</PostalCode>
                #            <Country>PT</Country>
                #    </BillingAddress>
                #    <SelfBillingIndicator>0</SelfBillingIndicator>
                # </Supplier>
                SupplierID = converter(((fornecedor.getElementsByTagName("SupplierID")[0]).childNodes[0]).nodeValue)
                AccountID = converter(((fornecedor.getElementsByTagName("AccountID")[0]).childNodes[0]).nodeValue)
                SupplierTaxID = converter(
                    ((fornecedor.getElementsByTagName("SupplierTaxID")[0]).childNodes[0]).nodeValue)
                CompanyName = converter(((fornecedor.getElementsByTagName("CompanyName")[0]).childNodes[0]).nodeValue)
                addr = fornecedor.getElementsByTagName("BillingAddress")[0]
                AddressDetail = converter(((addr.getElementsByTagName("AddressDetail")[0]).childNodes[0]).nodeValue)
                City = converter(((addr.getElementsByTagName("City")[0]).childNodes[0]).nodeValue)
                PostalCode = converter(((addr.getElementsByTagName("PostalCode")[0]).childNodes[0]).nodeValue)
                Country = converter(((addr.getElementsByTagName("Country")[0]).childNodes[0]).nodeValue)
                SelfBillingIndicator = converter(
                    ((fornecedor.getElementsByTagName("SelfBillingIndicator")[0]).childNodes[0]).nodeValue)
                if SelfBillingIndicator == "1":
                    SelfBillingIndicator = True
                else:
                    SelfBillingIndicator = False

                self.env.cr.execute("select id from account_account where code='" + AccountID + "' and company_id=" + str(
                    self.comp.id))
                aux = self.env.cr.fetchone()
                if aux != None and aux[0] != None:
                    AccountID = aux[0]
                else:
                    AccountID = None

                self.env.cr.execute(
                    "select id from res_country where code='" + Country + "' and company_id=" + str(self.comp.id))
                aux = self.env.cr.fetchone()
                if aux != None and aux[0] != None:
                    Country = aux[0]
                else:
                    Country = None

                if AddressDetail == 'Desconhecido':
                    AddressDetail = ''
                if City == 'Desconhecido':
                    City = ''
                if PostalCode == 'Desconhecido':
                    PostalCode = ''

                supplier = self.get_customer(SupplierTaxID, SupplierTaxID)
                if supplier:
                    self.env.cr.execute("update res_partner set supplier=true where id=" + str(aux[0]))
                else:
                    id_fornecedor = self.env['res.partner'].create({
                        'ref': 'F' + SupplierID,
                        'vat': SupplierTaxID or '',
                        'name': CompanyName or '',
                        'self_bill_sales': SelfBillingIndicator or False,
                        'property_account_receivable': AccountID,
                        'property_account_payable': AccountID,
                        'active': True,
                        'customer': False,
                        'supplier': True,
                        # 7
                        'type': 'default',
                        'street': AddressDetail or '',
                        'city': City or '',
                        'zip': PostalCode or '',
                        'country_id': Country,
                    })

            ############################
            ##    Fim Fornecedores    ##
            ##    Impostos            ##
            ############################

            impostos = dom.getElementsByTagName("TaxTableEntry")

            for imposto in impostos:
                TaxType = converter(((imposto.getElementsByTagName("TaxType")[0]).childNodes[0]).nodeValue)
                TaxCountryRegion = converter(
                    ((imposto.getElementsByTagName("TaxCountryRegion")[0]).childNodes[0]).nodeValue)
                TaxCode = converter(((imposto.getElementsByTagName("TaxCode")[0]).childNodes[0]).nodeValue)
                Description = converter(((imposto.getElementsByTagName("Description")[0]).childNodes[0]).nodeValue)
                TaxPercentage = converter(((imposto.getElementsByTagName("TaxPercentage")[0]).childNodes[0]).nodeValue)

                TaxPercentage = TaxPercentage.replace("%", "")

                account_paid = "243300"  # account_paid_values[TaxCode][TaxCountryRegion] or None

                if account_paid != None:
                    conta = 8
                    self.env.cr.execute(
                        "select id from account_account where code='" + account_paid + "' and company_id=" + str(
                            self.comp.id))
                    aux = self.env.cr.fetchone()
                    while (aux == None or aux[0] == None) and conta > 3:
                        conta = conta - 1
                        account_paid = account_paid[:-1]
                        self.env.cr.execute(
                            "select id from account_account where code='" + account_paid + "' and company_id=" + str(
                                self.comp.id))
                        aux = self.env.cr.fetchone()
                    if aux != None and aux[0] != None:
                        account_paid = aux[0]

                complemento = complemento_values[TaxCountryRegion] or ''

                self.env['account.tax'].create({
                    'type_tax_use': "sale",
                    'saft_tax_type': TaxType or '',
                    'country_region': TaxCountryRegion or '',
                    'saft_tax_code': TaxCode or '',
                    'description': Description or '',
                    'name': TaxPercentage + '%' + complemento,
                    'amount': (float(TaxPercentage) / 100),
                    'sequence': 1,
                    'active': True,
                    'include_base_amount': False,
                    'price_include': False,
                })

                account_paid = "243300"  # account_paid_values[TaxCode][TaxCountryRegion] or None

                if account_paid != None:
                    conta = 8
                    self.env.cr.execute(
                        "select id from account_account where code='" + account_paid + "' and company_id=" + str(
                            self.comp.id))
                    aux = self.env.cr.fetchone()
                    while (aux == None or aux[0] == None) and conta > 3:
                        conta = conta - 1
                        account_paid = account_paid[:-1]
                        self.env.cr.execute(
                            "select id from account_account where code='" + account_paid + "' and company_id=" + str(
                                self.comp.id))
                        aux = self.env.cr.fetchone()
                    if aux != None and aux[0] != None:
                        account_paid = aux[0]

                complemento = complemento_values[TaxCountryRegion] or ''

                self.env['account.tax'].create({
                    'type_tax_use': "purchase",
                    'saft_tax_type': TaxType or '',
                    'country_region': TaxCountryRegion or '',
                    'saft_tax_code': TaxCode or '',
                    'description': Description or '',
                    'name': TaxPercentage + '%(c)' + complemento,
                    'amount': (float(TaxPercentage) / 100),
                    'sequence': 1,
                    'active': True,
                    'include_base_amount': False,
                    'price_include': False,
                })

            #########################################
            ##    Fim Impostos                     ##
            ##    Diários, movimentos e linhas     ##
            #########################################
            diarios = dom.getElementsByTagName("Journal")

            for diario in diarios:

                JournalID = converter(((diario.getElementsByTagName("JournalID")[0]).childNodes[0]).nodeValue)
                Description = converter(((diario.getElementsByTagName("Description")[0]).childNodes[0]).nodeValue)

                tipo = "general"
                if Description.find("Venda") != -1:
                    tipo = "sale"
                if Description.find("Credito") != -1:
                    tipo = "sale_refund"
                if Description.find("Compra") != -1:
                    tipo = "purchase"
                if Description.find("Banco") != -1:
                    tipo = "bank"

                journal_id = self.env['account.journal'].create({
                    'code': JournalID or '',
                    'name': Description or '',
                    'type': tipo,
                    'active': True,
                    'allow_date': True,
                    'update_posted': True,
                    'centralisation': False,
                    'group_invoice_lines': False,
                })

                transactions = diario.getElementsByTagName("Transaction")
                for transaction in transactions:
                    Period = converter(((transaction.getElementsByTagName("Period")[0]).childNodes[0]).nodeValue)
                    TransactionDate = converter(
                        ((transaction.getElementsByTagName("TransactionDate")[0]).childNodes[0]).nodeValue)
                    Description = converter(
                        ((transaction.getElementsByTagName("Description")[0]).childNodes[0]).nodeValue)
                    DocArchivalNumber = converter(
                        ((transaction.getElementsByTagName("DocArchivalNumber")[0]).childNodes[0]).nodeValue)
                    ano = TransactionDate[:4]
                    if len(Period) == 1:
                        Period = "0" + Period

                    period_id = None
                    self.env.cr.execute(
                        "select id from account_period where code='" + Period + "/" + ano + "' and company_id=" + str(
                            self.comp.id))
                    aux = self.env.cr.fetchone()
                    if aux != None and aux[0] != None:
                        period_id = aux[0]

                    move_id = self.env['account.move'].create({
                        'state': "posted",
                        'name': DocArchivalNumber or '',
                        'ref': Description.replace("/", "") or '',
                        'journal_id': journal_id,
                        'period_id': period_id,
                        'date': TransactionDate,
                        'to_check': False,
                    })
                    imp = imp + 1

                    lines = transaction.getElementsByTagName("Line")
                    for line in lines:
                        AccountID = converter(((line.getElementsByTagName("AccountID")[0]).childNodes[0]).nodeValue)
                        SystemEntryDate = converter(
                            ((line.getElementsByTagName("SystemEntryDate")[0]).childNodes[0]).nodeValue)
                        Description = converter(((line.getElementsByTagName("Description")[0]).childNodes[0]).nodeValue)
                        CreditAmount = line.getElementsByTagName("CreditAmount")
                        DebitAmount = line.getElementsByTagName("DebitAmount")

                        account_id = None
                        self.env.cr.execute("select id from account_account where code='" + AccountID + "'")
                        aux = self.env.cr.fetchone()
                        if aux != None and aux[0] != None:
                            account_id = aux[0]

                        SystemEntryDate = SystemEntryDate[:10]

                        credit = 0
                        if CreditAmount != []:
                            credit = ((CreditAmount[0]).childNodes[0]).nodeValue
                        debit = 0
                        if DebitAmount != []:
                            debit = ((DebitAmount[0]).childNodes[0]).nodeValue

                        tax_amount = 0.0
                        if AccountID[:2] == '24':
                            if credit == 0:
                                tax_amount = debit
                            else:
                                tax_amount = credit

                        self.env['account.move.line'].create({
                            'move_id': move_id,
                            'journal_id': journal_id,
                            'period_id': period_id,
                            'account_id': account_id,
                            'name': Description or '',
                            'ref': Description or '',
                            'date': TransactionDate,
                            'credit': credit,
                            'debit': debit,
                            'blocked': False,
                        })

            #########################################
            ##   Fim Diários, movimentos e linhas  ##
            #########################################

            res = "Importou " + str(imp) + " transacções"
            if erros == "As incompatibilidades encontradas foram:":
                erros = "Não foram encontradas incompatibilidades"
            return self.write({'state': 'get', 'name': res, 'erros': erros})

        ############################
        ##   SAFT Integrado       ##
        ############################
        if self.tipo == 'I':
            document = document.encode("utf-8")
            document = document.replace('& ', '&amp; ')
            document = document.replace('Á', 'A')
            document = document.replace('Í', 'I')

            product_category_obj = self.env['product.category']
            tax_code_obj = self.env['account.tax.code']
            dom = xml.dom.minidom.parseString(document)

            ############################
            ##   Contas               ##
            ############################
            self.env.cr.execute("update account_account_type set close_method='unreconciled'")

            contas = dom.getElementsByTagName("GeneralLedger")

            self.env.cr.execute("select id from account_account_type where code='view' order by id")
            user_type = self.env.cr.fetchone()[0]
            self.env.cr.execute("select c.name from res_company c, res_users u where c.id=u.company_id and u.id=" + str(self.env.uid))
            nome_empresa = self.env.cr.fetchone()[0]
            # validar se ja existe
            self.env.cr.execute("select id from account_account where code='0' and company_id=" + str(self.comp.id))
            aux = self.env.cr.fetchone()
            if aux == None or aux[0] == None:
                conta_mae = self.env['account.account'].create({
                    'user_type': user_type,
                    'code': '0',
                    'name': nome_empresa,
                    'type': "view",
                    'currency_mode': "current",
                    'centralized': False,
                    'reconcile': False,
                    'level': 0,
                })
            else:
                conta_mae = aux[0]

            parent_id = None
            last_acc = None
            for conta in contas:
                AccountID = converter(((conta.getElementsByTagName("AccountID")[0]).childNodes[0]).nodeValue)
                AccountDescription = converter(
                    ((conta.getElementsByTagName("AccountDescription")[0]).childNodes[0]).nodeValue)

                # se esta conta é filha (maior do que a anterior) da anterior, marcar essa anterior como view
                if last_acc != None and len(AccountID) > len(last_acc):
                    self.env.cr.execute(
                        "select id from account_account where code='" + str(last_acc) + "' and company_id=" + str(
                            self.comp.id))
                    aux = self.env.cr.fetchone()[0]
                    try:
                        self.env['account.account'].write([aux], {'type': 'view'})
                    except:
                        True
                else:
                    # caso não seja encontrar a conta pai
                    parent_id = None
                    paiAccountID = AccountID[:-1]
                    aux = None
                    encontrou = False
                    while len(paiAccountID) > 0 and (aux == None or aux[0] == None):
                        self.env.cr.execute(
                            "select id,code from account_account where code='" + paiAccountID + "' and company_id=" + str(
                                self.comp.id))
                        aux = self.env.cr.fetchone()
                        if aux != None and aux[0] != None:
                            parent_id = aux[0]
                            last_acc = aux[1]
                            encontrou = True
                            paiAccountID = ''
                        else:
                            paiAccountID = paiAccountID[:-1]
                    # caso não exista criar a conta pai
                    if encontrou == False:
                        conta_pai = AccountID[:1]
                        self.env.cr.execute("select id from account_account_type where code='view' order by id")
                        user_type = self.env.cr.fetchone()[0]
                        if conta_pai == 1:
                            AccountDescription = 'MEIOS FINANCEIROS LÍQUIDOS'
                        elif conta_pai == 2:
                            AccountDescription = 'CONTAS A RECEBER E A PAGAR'
                        elif conta_pai == 3:
                            AccountDescription = 'INVENTÁRIOS E ACTIVOS BIOLÓGICOS'
                        elif conta_pai == 4:
                            AccountDescription = 'INVESTIMENTOS'
                        elif conta_pai == 5:
                            AccountDescription = 'CAPITAL, RESERVAS E RESULTADOS TRANSITADOS'
                        elif conta_pai == 6:
                            AccountDescription = 'GASTOS'
                        elif conta_pai == 7:
                            AccountDescription = 'RENDIMENTOS'
                        elif conta_pai == 8:
                            AccountDescription = 'RESULTADOS'
                        elif conta_pai == 9:
                            AccountDescription = '9'
                        # inserir a conta pai
                        # validar se ja existe
                        self.env.cr.execute(
                            "select id from account_account where code='" + str(conta_pai) + "' and company_id=" + str(
                                self.comp.id))
                        aux = self.env.cr.fetchone()
                        if aux == None or aux[0] == None:
                            parent_id = self.env['account.account'].create({
                                'parent_id': conta_mae,
                                'user_type': user_type,
                                'code': str(conta_pai),
                                'name': AccountDescription,
                                'type': "view",
                                'currency_mode': "current",
                                'centralized': False,
                                'reconcile': False,
                                'level': 1,
                            })
                        else:
                            parent_id = aux[0]
                        last_acc = str(conta_pai)

                # DADOS PARA A CONTA CORRENTE
                tipo = "view"
                if len(AccountID) > 1:
                    paiAccountID = AccountID[:-1]
                    # if data_contas[AccountID]!=None:
                    tipo = "other"
                    if AccountID[:2] == '11':
                        tipo = "liquidity"
                    if AccountID[:2] == '21':
                        tipo = "receivable"
                    if AccountID[:2] == '22':
                        tipo = "payable"

                self.env.cr.execute("select id from account_account_type where code='view' order by id")
                user_type = self.env.cr.fetchone()[0]

                # contas gerais
                if tipo != "view" and AccountID[:1] == "6":
                    self.env.cr.execute("select id from account_account_type where code='liability' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:1] == "7":
                    self.env.cr.execute("select id from account_account_type where code='asset' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:1] == "8":
                    self.env.cr.execute("select id from account_account_type where code='equity' order by id desc")
                    user_type = self.env.cr.fetchone()[0]

                    # Activo não corrente
                if tipo != "view" and (AccountID[:2] == "43" or AccountID[:3] == "452" or (
                        int(AccountID[:3]) >= 454 and int(AccountID[:2]) < 46)):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Activos fixos tangiveis' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:2] == "42" or AccountID[:2] == "454"):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Propriedades de investimento' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:3] == "441":
                    self.env.cr.execute("select id from account_account_type where code='Trespasse (goodwill)' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and ((AccountID[:2] == "44" and AccountID[:3] != "441") or AccountID[:3] == "453"):
                    self.env.cr.execute("select id from account_account_type where code='Activos intangiveis' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:3] == "372":
                    self.env.cr.execute("select id from account_account_type where code='Activos biologicos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:4] == "4111" or AccountID[:4] == "4121" or (
                        int(AccountID[:4]) >= 4131 and int(AccountID[:2]) < 42)):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Participacoes financeiras m.e.p.' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (
                                AccountID[:4] == "4112" or AccountID[:4] == "4122" or AccountID[:4] == "4132" or (
                        int(AccountID[:4]) >= 4141 and int(AccountID[:2]) < 42)):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Part. fin. out. metod.' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (
                        AccountID[:3] == "266" or (int(AccountID[:3]) >= 268 and int(AccountID[:3]) < 270)):
                    self.env.cr.execute("select id from account_account_type where code='Accionistas/socios' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:4] == "4113" or AccountID[:4] == "4123" or AccountID[
                                                                                             :4] == "4133" or AccountID[
                                                                                                              :4] == "4113" or (
                        int(AccountID[:3]) >= 415 and int(AccountID[:2]) < 42) or AccountID[:4] == "451"):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Outros activos financeiros' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:4] == "2741":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Activos por impostos diferidos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                    # Activo corrente
                if tipo != "view" and ((int(AccountID[:2]) >= 32 and int(AccountID[:2]) < 37) or AccountID[:2] == "39"):
                    self.env.cr.execute("select id from account_account_type where code='Inventarios' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:4] == "371":
                    self.env.cr.execute("select id from account_account_type where code='Activos biologicos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and ((int(AccountID[:3]) >= 211 and int(AccountID[:2]) < 22)):
                    self.env.cr.execute("select id from account_account_type where code='Clientes' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and ((int(AccountID[:3]) >= 228 and int(AccountID[:2]) < 23) or (
                        int(AccountID[:4]) >= 2713 and int(AccountID[:2]) < 28)):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Adiantamentos a fornecedores' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "24":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Estado e outros entes publicos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (
                        AccountID[:3] == "263" or (int(AccountID[:3]) >= 268 and int(AccountID[:2]) < 27)):
                    self.env.cr.execute("select id from account_account_type where code='Accionistas/socios' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:3] == "232" or (
                        int(AccountID[:3]) >= 238 and int(AccountID[:2]) < 24) or AccountID[:4] == "2721" or (
                        int(AccountID[:3]) >= 278 and int(AccountID[:2]) < 28)):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Outras contas a receber' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:3] == "281":
                    self.env.cr.execute("select id from account_account_type where code='Diferimentos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:4] == "1411" or AccountID[:4] == "1421"):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Activos financeiros detidos neg.' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:4] == "1431":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Outros activos financeiros' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "46":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Activos nao correntes det vend.' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:2] == "11" or AccountID[:2] == "12" or AccountID[:2] == "13"):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Caixa e depositos bancarios' order by id desc")
                    user_type = self.env.cr.fetchone()[0]

                    # Capital próprio
                if tipo != "view" and (AccountID[:2] == "52" or AccountID[:3] == "261" or AccountID[:3] == "262"):
                    self.env.cr.execute("select id from account_account_type where code='Capital realizado' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "52":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Accoes (quotas) proprias' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "53":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Outros instrumentos de cap. pro.' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "54":
                    self.env.cr.execute("select id from account_account_type where code='Premios de emissao' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:3] == "551":
                    self.env.cr.execute("select id from account_account_type where code='Reservas legais' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:3] == "552":
                    self.env.cr.execute("select id from account_account_type where code='Outras reservas' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "56":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Resultados transitados' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "57":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Ajustamentos em act. fin.' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "58":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Excedentes de revalorizacao' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "59":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Outras variacoes no capital pro.' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:3] == "818":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Resultado liquido do periodo' order by id desc")
                    user_type = self.env.cr.fetchone()[0]

                    # Passivo (Passivo não corrente)
                if tipo != "view" and AccountID[:2] == "29":
                    self.env.cr.execute("select id from account_account_type where code='Provisoes' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "25":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Financiamentos obtidos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:3] == "273":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Respons. por ben. pos-emprego' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:4] == "2742":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Passivos por impostos diferidos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:3] == "237" or AccountID[:4] == "2711" or AccountID[
                                                                                            :4] == "2712" or AccountID[
                                                                                                             :3] == "275"):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Outras contas a pagar' order by id desc")
                    user_type = self.env.cr.fetchone()[0]

                    # Passivo (Passivo corrente)
                if tipo != "view" and (AccountID[:3] == "221" or AccountID[:3] == "222" or AccountID[:3] == "225"):
                    self.env.cr.execute("select id from account_account_type where code='Fornecedores' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:3] == "218" or AccountID[:3] == "276"):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Adiantamentos de clientes' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "24":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Estado e outros entes publicos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:3] == "264" or AccountID[:3] == "265" or AccountID[:3] == "268"):
                    self.env.cr.execute("select id from account_account_type where code='Accionistas/socios' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:2] == "25":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Financiamentos obtidos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:3] == "231" or AccountID[:3] == "238" or AccountID[
                                                                                           :4] == "2711" or AccountID[
                                                                                                            :4] == "2712" or AccountID[
                                                                                                                             :4] == "2722" or AccountID[
                                                                                                                                              :3] == "278"):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Outras contas a pagar' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:3] == "282" or AccountID[:3] == "283"):
                    self.env.cr.execute("select id from account_account_type where code='Diferimentos' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and (AccountID[:4] == "1412" or AccountID[:4] == "1422"):
                    self.env.cr.execute(
                        "select id from account_account_type where code='Passivos financeiros det. neg.' order by id desc")
                    user_type = self.env.cr.fetchone()[0]
                if tipo != "view" and AccountID[:4] == "1432":
                    self.env.cr.execute(
                        "select id from account_account_type where code='Outros passivos financeiros' order by id desc")
                    user_type = self.env.cr.fetchone()[0]

                # inserir a conta atual
                # validar se ja existe
                self.env.cr.execute("select id from account_account where code='" + str(AccountID) + "' and company_id=" + str(
                    self.comp.id))
                aux = self.env.cr.fetchone()
                if aux == None or aux[0] == None:
                    acc_id = self.env['account.account'].create({
                        'parent_id': parent_id,
                        'user_type': user_type,
                        'code': AccountID or '',
                        'name': AccountDescription or '',
                        'type': tipo,
                        'currency_mode': "current",
                        'centralized': False,
                        'reconcile': False,
                        'level': len(AccountID),
                    })
                else:
                    acc_id = aux[0]

                # GUARDAR A CONTA ATUAL, PARA SER A ANTERIOR DA PROXIMA
                parent_id = acc_id
                last_acc = AccountID

            # actulizar levels
            self.env.cr.execute(
                "select id,parent_id from account_account where id!=" + str(conta_mae) + " and company_id=" + str(
                    self.comp.id))
            contas = self.env.cr.fetchall()
            for conta in contas:
                nivel = 1
                parent_id = conta[1]
                while parent_id != conta_mae and parent_id != None:
                    nivel = nivel + 1
                    self.env.cr.execute(
                        "select parent_id from account_account where id=" + str(parent_id) + " and company_id=" + str(
                            self.comp.id))
                    parent_id = self.env.cr.fetchone()[0]
                self.env['account.account'].write([conta[0]], {'level': nivel})

            ############################
            ##       Fim Contas       ##
            ##       Clientes         ##
            ############################
            clientes = dom.getElementsByTagName("Customer")

            for cliente in clientes:
                # <CustomerID>003</CustomerID>
                # <AccountID>211110023</AccountID>
                # <CustomerTaxID>000000000</CustomerTaxID>
                # <CompanyName>Institut Camille Milret</CompanyName>
                # <BillingAddress>
                #	<AddressDetail>Desconhecido</AddressDetail>
                #	<City>Desconhecido</City>
                #	<PostalCode>Desconhecido</PostalCode>
                #	<Country>FR</Country>
                # </BillingAddress>
                # <SelfBillingIndicator>0</SelfBillingIndicator>
                CustomerID = converter(((cliente.getElementsByTagName("CustomerID")[0]).childNodes[0]).nodeValue)
                AccountID = converter(((cliente.getElementsByTagName("AccountID")[0]).childNodes[0]).nodeValue)
                CustomerTaxID = converter(((cliente.getElementsByTagName("CustomerTaxID")[0]).childNodes[0]).nodeValue)
                CompanyName = converter(((cliente.getElementsByTagName("CompanyName")[0]).childNodes[0]).nodeValue)
                addr = cliente.getElementsByTagName("BillingAddress")[0]
                AddressDetail = converter(((addr.getElementsByTagName("AddressDetail")[0]).childNodes[0]).nodeValue)
                City = converter(((addr.getElementsByTagName("City")[0]).childNodes[0]).nodeValue)
                PostalCode = converter(((addr.getElementsByTagName("PostalCode")[0]).childNodes[0]).nodeValue)
                Country = converter(((addr.getElementsByTagName("Country")[0]).childNodes[0]).nodeValue)
                SelfBillingIndicator = converter(
                    ((cliente.getElementsByTagName("SelfBillingIndicator")[0]).childNodes[0]).nodeValue)
                if SelfBillingIndicator == "1":
                    SelfBillingIndicator = True
                else:
                    SelfBillingIndicator = False

                self.env.cr.execute("select id from account_account where code='" + AccountID + "' and company_id=" + str(
                    self.comp.id))
                aux = self.env.cr.fetchone()
                if aux != None and aux[0] != None:
                    AccountID = aux[0]
                else:
                    AccountID = None

                self.env.cr.execute(
                    "select id from res_country where code='" + Country + "' and company_id=" + str(self.comp.id))
                aux = self.env.cr.fetchone()
                if aux != None and aux[0] != None:
                    Country = aux[0]
                else:
                    Country = None

                if AddressDetail == 'Desconhecido':
                    AddressDetail = ''
                if City == 'Desconhecido':
                    City = ''
                if PostalCode == 'Desconhecido':
                    PostalCode = ''

                # validar se ja existe
                supplier = self.get_customer(CustomerID, CustomerTaxID, True)
                # self.env.cr.execute("select id from res_partner where ref='" + str(CustomerID) + "' and vat='" + str(
                #     CustomerTaxID) + "' and company_id=" + str(self.comp.id))
                # aux = self.env.cr.fetchone()
                #
                # if aux == None or aux[0] == None:
                if not supplier:
                    supplier = self.env['res.partner'].create({
                        'ref': CustomerID or '',
                        'vat': CustomerTaxID or '',
                        'name': CompanyName or '',
                        'self_bill_sales': SelfBillingIndicator or False,
                        'property_account_receivable': AccountID,
                        'property_account_payable': AccountID,
                        'active': True,
                        'customer': True,
                        'supplier': False,
                        # 7
                        'type': 'default',
                        'street': AddressDetail or '',
                        'city': City or '',
                        'zip': PostalCode or '',
                        'country_id': Country,
                    })

            ############################
            ##    Fim Clientes        ##
            ##    Fornecedores        ##
            ############################
            fornecedores = dom.getElementsByTagName("Supplier")

            for fornecedor in fornecedores:
                # <Supplier>
                #    <SupplierID>001</SupplierID>
                #    <AccountID>221110001</AccountID>
                #    <SupplierTaxID>510011993</SupplierTaxID>
                #    <CompanyName>Flamínio &amp; Teixeira, Lda</CompanyName>
                #    <BillingAddress>
                #            <AddressDetail>Desconhecido</AddressDetail>
                #            <City>Desconhecido</City>
                #            <PostalCode>Desconhecido</PostalCode>
                #            <Country>PT</Country>
                #    </BillingAddress>
                #    <SelfBillingIndicator>0</SelfBillingIndicator>
                # </Supplier>
                SupplierID = converter(((fornecedor.getElementsByTagName("SupplierID")[0]).childNodes[0]).nodeValue)
                AccountID = converter(((fornecedor.getElementsByTagName("AccountID")[0]).childNodes[0]).nodeValue)
                SupplierTaxID = converter(
                    ((fornecedor.getElementsByTagName("SupplierTaxID")[0]).childNodes[0]).nodeValue)
                CompanyName = converter(((fornecedor.getElementsByTagName("CompanyName")[0]).childNodes[0]).nodeValue)
                addr = fornecedor.getElementsByTagName("BillingAddress")[0]
                AddressDetail = converter(((addr.getElementsByTagName("AddressDetail")[0]).childNodes[0]).nodeValue)
                City = converter(((addr.getElementsByTagName("City")[0]).childNodes[0]).nodeValue)
                PostalCode = converter(((addr.getElementsByTagName("PostalCode")[0]).childNodes[0]).nodeValue)
                Country = converter(((addr.getElementsByTagName("Country")[0]).childNodes[0]).nodeValue)
                SelfBillingIndicator = converter(
                    ((fornecedor.getElementsByTagName("SelfBillingIndicator")[0]).childNodes[0]).nodeValue)
                if SelfBillingIndicator == "1":
                    SelfBillingIndicator = True
                else:
                    SelfBillingIndicator = False

                self.env.cr.execute("select id from account_account where code='" + AccountID + "' and company_id=" + str(
                    self.comp.id))
                aux = self.env.cr.fetchone()
                if aux != None and aux[0] != None:
                    AccountID = aux[0]
                else:
                    AccountID = None

                self.env.cr.execute(
                    "select id from res_country where code='" + Country + "' and company_id=" + str(self.comp.id))
                aux = self.env.cr.fetchone()
                if aux != None and aux[0] != None:
                    Country = aux[0]
                else:
                    Country = None

                if AddressDetail == 'Desconhecido':
                    AddressDetail = ''
                if City == 'Desconhecido':
                    City = ''
                if PostalCode == 'Desconhecido':
                    PostalCode = ''

                # self.env.cr.execute("select id from res_partner where ref='" + str(CustomerID) + "' or vat='" + str(
                #     SupplierTaxID) + "' and company_id=" + str(self.comp.id))
                # aux = self.env.cr.fetchone()
                # if aux != None and aux[0] != None:
                #     self.env.cr.execute("update res_partner set supplier=true where id=" + str(aux[0]))
                # else:
                supplier = self.get_customer(CustomerID, SupplierTaxID, True)
                if not supplier:
                    supplier = self.env['res.partner'].create({
                        'ref': 'F' + SupplierID,
                        'vat': SupplierTaxID or '',
                        'name': CompanyName or '',
                        'self_bill_sales': SelfBillingIndicator or False,
                        'property_account_receivable': AccountID,
                        'property_account_payable': AccountID,
                        'active': True,
                        'customer': False,
                        'supplier': True,
                        # 7
                        'type': 'default',
                        'street': AddressDetail or '',
                        'city': City or '',
                        'zip': PostalCode or '',
                        'country_id': Country,
                    })

            ############################
            ##    Fim Fornecedores    ##
            ##    Produtos            ##
            ############################
            produtos = dom.getElementsByTagName("Product")

            for produto in produtos:
                ProductType = converter(((produto.getElementsByTagName("ProductType")[0]).childNodes[0]).nodeValue)
                ProductCode = converter(((produto.getElementsByTagName("ProductCode")[0]).childNodes[0]).nodeValue)
                ProductGroup = converter(((produto.getElementsByTagName("ProductGroup")[0]).childNodes[0]).nodeValue)
                ProductDescription = converter(
                    ((produto.getElementsByTagName("ProductDescription")[0]).childNodes[0]).nodeValue)

                if ProductType == "S":
                    ProductType = "service"
                elif ProductType == "P":
                    ProductType = "product"
                else:
                    ProductType = "consu"

                self.env.cr.execute("select id from product_category where name='" + ProductGroup + "'")
                aux = self.env.cr.fetchone()
                if aux != None and aux[0] != None:
                    ProductGroup = aux[0]
                else:
                    self.env.cr.execute("select id from product_category where name='All products'")
                    aux = self.env.cr.fetchone()
                    if aux != None and aux[0] != None:
                        ProductGroup = aux[0]
                    else:
                        ProductGroup = product_category_obj.create({
                            'name': 'All products',
                            'sequence': 0,
                            'type': 'normal',
                        })

                # validar se ja existe
                self.env.cr.execute("select id from product_product where default_code='" + str(ProductCode) + "'")
                aux = self.env.cr.fetchone()
                if aux == None or aux[0] == None:
                    self.env['product.product'].create({
                        'name': ProductDescription,
                        'default_code': ProductCode or '',
                        'type': ProductType or '',
                        'categ_id': ProductGroup or False,
                    })

            ############################
            ##    Fim Produtos        ##
            ##    Impostos            ##
            ############################
            # validar se ja existe
            self.env.cr.execute("select id from account_tax_code where name='" + _(nome_empresa) + "'")
            aux = self.env.cr.fetchone()
            if aux == None or aux[0] == None:
                tax_code_emp_id = tax_code_obj.create({
                    'name': nome_empresa,
                    'sign': 1,
                    'notprintable': False,
                })
            else:
                tax_code_emp_id = aux[0]
            # validar se ja existe
            self.env.cr.execute("select id from account_tax_code where name='Balanço de Pagamento do IVA' and company_id=" + str(
                self.comp.id))
            aux = self.env.cr.fetchone()
            if aux == None or aux[0] == None:
                tax_code_bal_id = tax_code_obj.create({
                    'name': "Balanço de Pagamento do IVA",
                    'sign': 1,
                    'notprintable': False,
                    'parent_id': tax_code_emp_id,
                })
            else:
                tax_code_bal_id = aux[0]
            # validar se ja existe


            impostos = dom.getElementsByTagName("TaxTableEntry")

            for imposto in impostos:
                # <TaxTable>
                #	    <TaxTableEntry>
                #		<TaxType>IVA</TaxType>
                #		<TaxCountryRegion>PT</TaxCountryRegion>
                #		<TaxCode>ISE</TaxCode>
                #		<Description>Isenta</Description>
                #	        <TaxPercentage>0.00</TaxPercentage>
                #	    </TaxTableEntry>
                # </TaxTable>
                TaxType = converter(((imposto.getElementsByTagName("TaxType")[0]).childNodes[0]).nodeValue)
                TaxCountryRegion = converter(
                    ((imposto.getElementsByTagName("TaxCountryRegion")[0]).childNodes[0]).nodeValue)
                TaxCode = converter(((imposto.getElementsByTagName("TaxCode")[0]).childNodes[0]).nodeValue)
                Description = converter(((imposto.getElementsByTagName("Description")[0]).childNodes[0]).nodeValue)
                TaxPercentage = converter(((imposto.getElementsByTagName("TaxPercentage")[0]).childNodes[0]).nodeValue)

                TaxPercentage = TaxPercentage.replace("%", "")

                account_paid = "243300"  # account_paid_values[TaxCode][TaxCountryRegion] or None


                if account_paid != None:
                    conta = 8
                    self.env.cr.execute(
                        "select id from account_account where code='" + account_paid + "' and company_id=" + str(
                            self.comp.id))
                    aux = self.env.cr.fetchone()
                    while (aux == None or aux[0] == None) and conta > 3:
                        conta = conta - 1
                        account_paid = account_paid[:-1]
                        self.env.cr.execute(
                            "select id from account_account where code='" + account_paid + "' and company_id=" + str(
                                self.comp.id))
                        aux = self.env.cr.fetchone()
                    if aux != None and aux[0] != None:
                        account_paid = aux[0]

                complemento = complemento_values[TaxCountryRegion] or ''

                # validar se ja existe
                self.env.cr.execute("select id from account_tax where name='" + str(TaxPercentage + '%' + complemento) + "'")
                aux = self.env.cr.fetchone()
                if aux == None or aux[0] == None:
                    self.env['account.tax'].create({
                        'type_tax_use': "sale",
                        'saft_tax_type': TaxType or '',
                        'country_region': TaxCountryRegion or '',
                        'saft_tax_code': TaxCode or '',
                        'description': Description or '',
                        'name': TaxPercentage + '%' + complemento,
                        'amount': (float(TaxPercentage) / 100),
                        'sequence': 1,
                        'active': True,
                        'child_depend': False,
                        'include_base_amount': False,
                        'price_include': False,
                    })

                    account_paid = "243300"  # account_paid_values[TaxCode][TaxCountryRegion] or None

                if account_paid != None:
                    conta = 8
                    self.env.cr.execute(
                        "select id from account_account where code='" + account_paid + "' and company_id=" + str(
                            self.comp.id))
                    aux = self.env.cr.fetchone()
                    while (aux == None or aux[0] == None) and conta > 3:
                        conta = conta - 1
                        account_paid = account_paid[:-1]
                        self.env.cr.execute(
                            "select id from account_account where code='" + account_paid + "' and company_id=" + str(
                                self.comp.id))
                        aux = self.env.cr.fetchone()
                    if aux != None and aux[0] != None:
                        account_paid = aux[0]

                complemento = complemento_values[TaxCountryRegion] or ''

                # validar se ja existe
                self.env.cr.execute("select id from account_tax where name='" + str(TaxPercentage + '%(c)' + complemento) + "'")
                aux = self.env.cr.fetchone()
                if aux == None or aux[0] == None:
                    self.env['account.tax'].create({
                        'type_tax_use': "purchase",
                        'saft_tax_type': TaxType or '',
                        'country_region': TaxCountryRegion or '',
                        'saft_tax_code': TaxCode or '',
                        'description': Description or '',
                        'name': TaxPercentage + '%(c)' + complemento,
                        'amount': (float(TaxPercentage) / 100),
                        'sequence': 1,
                        'active': True,
                        'include_base_amount': False,
                        'price_include': False,
                    })

            # adicionar impostos aos produtos
            self.env.cr.execute("select id from account_tax where type_tax_use='sale' and amount=0.2300 and company_id=" + str(
                self.comp.id))
            aux = self.env.cr.fetchone()
            if aux == None or aux[0] == None:
                raise ValueError(_('UserError'), _('Nao foi encontrado um imposto 23% de vendas.'))
            else:
                imposto_vendas = aux[0]
            self.env.cr.execute("select id from account_tax where type_tax_use='purchase' and amount=0.2300")
            aux = self.env.cr.fetchone()
            if aux == None or aux[0] == None:
                raise ValidationError(_('UserError'), _('Nao foi encontrado um imposto 23% de compras.'))
            else:
                imposto_compras = aux[0]

            self.env.cr.execute("select id from product_product")
            produtos = self.env.cr.fetchall()
            for p in produtos:
                self.env.cr.execute("INSERT INTO product_taxes_rel(prod_id, tax_id) VALUES (" + str(p[0]) + ", " + str(
                    imposto_vendas) + ")")
                self.env.cr.execute("INSERT INTO product_taxes_rel(prod_id, tax_id) VALUES (" + str(p[0]) + ", " + str(
                    imposto_compras) + ")")

            #########################################
            ##    Fim Impostos                     ##
            ##    Diários, movimentos e linhas     ##
            #########################################
            diarios = dom.getElementsByTagName("Journal")

            for diario in diarios:
                # <Journal>
                #	<JournalID>00031</JournalID>
                #	<Description>Bancos - Depósitos</Description>
                #	<Transaction>
                #		<TransactionID>2012-05-21 00031 50001</TransactionID>
                #		<Period>5</Period>
                #		<TransactionDate>2012-05-21</TransactionDate>
                #		<SourceID>patricia</SourceID>
                #		<Description>Rec. FT 11</Description>
                #		<DocArchivalNumber>50001</DocArchivalNumber>
                #		<TransactionType>N</TransactionType>
                #		<GLPostingDate>2012-09-15T17:38:35</GLPostingDate>
                #		<CustomerID>009</CustomerID>
                #		<Line>
                #			<RecordID>1</RecordID>
                #			<AccountID>1201</AccountID>
                #			<SystemEntryDate>2012-09-15T17:38:35</SystemEntryDate>
                #			<Description>Rec. FT 11</Description>
                #			<DebitAmount>162.50</DebitAmount>
                #		</Line>
                #	</Transaction>
                # </Journal>

                JournalID = converter(((diario.getElementsByTagName("JournalID")[0]).childNodes[0]).nodeValue)
                Description = converter(((diario.getElementsByTagName("Description")[0]).childNodes[0]).nodeValue)

                tipo = "general"
                sadt_inv_type = "FT"
                ##                    self.env.cr.execute("select id  from account_journal_view where name='Journal View'")
                ##                    view_id=cr.fetchone()
                if Description.find("Venda") != -1:
                    tipo = "sale"
                    sadt_inv_type = "FT"
                ##                        self.env.cr.execute("select id  from account_journal_view where name='Sale/Purchase Journal View'")
                ##                        view_id=cr.fetchone()
                if Description.find("Nota de Crédito") != -1:
                    tipo = "sale_refund"
                    sadt_inv_type = "NC"
                ##                        self.env.cr.execute("select id  from account_journal_view where name='Sale/Purchase Refund Journal View'")
                ##                        view_id=cr.fetchone()
                if Description.find("Compra") != -1:
                    tipo = "purchase"
                ##                        self.env.cr.execute("select id  from account_journal_view where name='Sale/Purchase Journal View'")
                ##                        view_id=cr.fetchone()
                if Description.find("Banco") != -1:
                    tipo = "bank"
                ##                        self.env.cr.execute("select id  from account_journal_view where name='Bank/Cash Journal View'")
                ##                        view_id=cr.fetchone()

                # validar se ja existe
                self.env.cr.execute("select id from account_journal where code='" + str(JournalID) + "' and company_id=" + str(
                    self.comp.id))
                aux = self.env.cr.fetchone()
                if aux == None or aux[0] == None:
                    journal_id = self.env['account.journal'].create({
                        'code': JournalID or '',
                        'name': Description or '',
                        'type': tipo,
                        'sadt_inv_type': sadt_inv_type,
                        ##                                'view_id' : view_id,
                        'active': True,
                        'allow_date': True,
                        'update_posted': True,
                        'centralisation': False,
                        'group_invoice_lines': False,
                    })
                else:
                    journal_id = aux[0]

                transactions = diario.getElementsByTagName("Transaction")
                for transaction in transactions:
                    TransactionID = converter(
                        ((transaction.getElementsByTagName("TransactionID")[0]).childNodes[0]).nodeValue)
                    Period = converter(((transaction.getElementsByTagName("Period")[0]).childNodes[0]).nodeValue)
                    TransactionDate = converter(
                        ((transaction.getElementsByTagName("TransactionDate")[0]).childNodes[0]).nodeValue)
                    SourceID = converter(((transaction.getElementsByTagName("SourceID")[0]).childNodes[0]).nodeValue)
                    Description = converter(
                        ((transaction.getElementsByTagName("Description")[0]).childNodes[0]).nodeValue)
                    DocArchivalNumber = converter(
                        ((transaction.getElementsByTagName("DocArchivalNumber")[0]).childNodes[0]).nodeValue)
                    TransactionType = converter(
                        ((transaction.getElementsByTagName("TransactionType")[0]).childNodes[0]).nodeValue)
                    ano = TransactionDate[:4]

                    if len(Period) == 1:
                        Period = "0" + Period

                    period_id = None
                    self.env.cr.execute("select id from account_period where code='" + Period + "/" + ano + "'")
                    aux = self.env.cr.fetchone()
                    if aux != None and aux[0] != None:
                        period_id = aux[0]

                    # validar se ja existe
                    self.env.cr.execute("select id from account_move where name='" + str(Description) + "'")
                    aux = self.env.cr.fetchone()
                    if aux == None or aux[0] == None:
                        move_id = self.env['account.move'].create({
                            'state': "posted",
                            'name': DocArchivalNumber or '',
                            'ref': Description.replace("/", "") or '',
                            'journal_id': journal_id,
                            'period_id': period_id,
                            'date': TransactionDate,
                            'to_check': False,
                        })
                        imp = imp + 1

                        lines = transaction.getElementsByTagName("Line")
                        for line in lines:
                            RecordID = converter(((line.getElementsByTagName("RecordID")[0]).childNodes[0]).nodeValue)
                            AccountID = converter(((line.getElementsByTagName("AccountID")[0]).childNodes[0]).nodeValue)
                            SystemEntryDate = converter(
                                ((line.getElementsByTagName("SystemEntryDate")[0]).childNodes[0]).nodeValue)
                            Description = converter(
                                ((line.getElementsByTagName("Description")[0]).childNodes[0]).nodeValue)
                            CreditAmount = line.getElementsByTagName("CreditAmount")
                            DebitAmount = line.getElementsByTagName("DebitAmount")

                            account_id = None
                            self.env.cr.execute("select id from account_account where code='" + AccountID + "'")
                            aux = self.env.cr.fetchone()
                            if aux != None and aux[0] != None:
                                account_id = aux[0]

                            SystemEntryDate = SystemEntryDate[:10]

                            credit = 0
                            if CreditAmount != []:
                                credit = ((CreditAmount[0]).childNodes[0]).nodeValue
                            debit = 0
                            if DebitAmount != []:
                                debit = ((DebitAmount[0]).childNodes[0]).nodeValue

                            tax_amount = 0.0
                            if AccountID[:2] == '24':
                                if credit == 0:
                                    tax_amount = debit
                                else:
                                    tax_amount = credit

                            self.env['account.move.line'].create({
                                'move_id': move_id,
                                'journal_id': journal_id,
                                'period_id': period_id,
                                'account_id': account_id,
                                'name': Description or '',
                                'ref': Description or '',
                                'date': TransactionDate,
                                'credit': credit,
                                'debit': debit,
                                'blocked': False,
                                # 'tax_code_id': tax_code_id,
                            })

            #########################################
            ##   Fim Diários, movimentos e linhas  ##
            ##            Faturas                  ##
            #########################################
            faturas = dom.getElementsByTagName("Invoice")

            for fatura in faturas:
                # <Invoice>
                #    <InvoiceNo>FT FT2013/001</InvoiceNo>
                #    <InvoiceStatus>N</InvoiceStatus>
                #    <Hash>cYZ4MpFkDCvLaY7LSfITGfTiwam9SGtnrRv/QMgkqiFhPQ3mbCu0PxECURvcwh8HNeAgK512v+RRCBW4C+q0xrcWxU6zhwIdLRcWjENRP9NfrckAexMVQ3UsKhfOkyawepEz9DBnhdEL7y133C8T++ih32bTJFMvGDvFjnwXmwU=</Hash>
                #    <HashControl>1</HashControl>
                #    <Period>01</Period>
                #    <InvoiceDate>2013-01-02</InvoiceDate>
                #    <InvoiceType>FT</InvoiceType>
                #    <SelfBillingIndicator>0</SelfBillingIndicator>
                #    <SystemEntryDate>2013-01-05T12:17:22</SystemEntryDate>
                #    <CustomerID>13</CustomerID>
                #    <Line>
                #            <LineNumber>1</LineNumber>
                #            <OrderReferences>
                #                    <OriginatingON>Acordo Serviços Riluc</OriginatingON>
                #            </OrderReferences>
                #            <ProductCode>AMSO-N</ProductCode>
                #            <ProductDescription>Avença Mensal Serviços Utilização Opencloud </ProductDescription>
                #            <Quantity>1.0</Quantity>
                #            <UnitOfMeasure>PCE</UnitOfMeasure>
                #            <UnitPrice>20.0</UnitPrice>
                #            <TaxPointDate>2013-01-02</TaxPointDate>
                #            <Description>[AMSO-N] Avença Mensal Serviços Utilização Opencloud </Description>
                #            <CreditAmount>20.0</CreditAmount>
                #            <Tax>
                #                    <TaxType>IVA</TaxType>
                #                    <TaxCountryRegion>PT</TaxCountryRegion>
                #                    <TaxCode>NOR</TaxCode>
                #                    <TaxPercentage>23</TaxPercentage>
                #            </Tax>
                #            <SettlementAmount>0.0</SettlementAmount>
                #    </Line>
                #    <DocumentTotals>
                #            <TaxPayable>4.6</TaxPayable>
                #            <NetTotal>20.0</NetTotal>
                #            <GrossTotal>24.60</GrossTotal>
                #    </DocumentTotals>
                # </Invoice>

                InvoiceNo = converter(((fatura.getElementsByTagName("InvoiceNo")[0]).childNodes[0]).nodeValue)
                InvoiceStatus = converter(((fatura.getElementsByTagName("InvoiceStatus")[0]).childNodes[0]).nodeValue)
                Hash = converter(((fatura.getElementsByTagName("Hash")[0]).childNodes[0]).nodeValue)
                HashControl = converter(((fatura.getElementsByTagName("HashControl")[0]).childNodes[0]).nodeValue)
                Period = converter(((fatura.getElementsByTagName("Period")[0]).childNodes[0]).nodeValue)
                InvoiceDate = converter(((fatura.getElementsByTagName("InvoiceDate")[0]).childNodes[0]).nodeValue)
                InvoiceType = converter(((fatura.getElementsByTagName("InvoiceType")[0]).childNodes[0]).nodeValue)
                SelfBillingIndicator = converter(
                    ((fatura.getElementsByTagName("SelfBillingIndicator")[0]).childNodes[0]).nodeValue)
                SystemEntryDate = converter(
                    ((fatura.getElementsByTagName("SystemEntryDate")[0]).childNodes[0]).nodeValue)
                CustomerID = converter(((fatura.getElementsByTagName("CustomerID")[0]).childNodes[0]).nodeValue)

                DocumentTotals = fatura.getElementsByTagName("DocumentTotals")[0]
                TaxPayable = converter(((DocumentTotals.getElementsByTagName("TaxPayable")[0]).childNodes[0]).nodeValue)
                NetTotal = converter(((DocumentTotals.getElementsByTagName("NetTotal")[0]).childNodes[0]).nodeValue)
                GrossTotal = converter(((DocumentTotals.getElementsByTagName("GrossTotal")[0]).childNodes[0]).nodeValue)

                # Estado
                if InvoiceStatus == 'A':
                    InvoiceStatus = 'cancel'
                else:
                    InvoiceStatus = 'open'

                # Periodo
                ano = InvoiceDate[:4]
                self.env.cr.execute(
                    "select id from account_period where code='" + Period + "/" + ano + "' and company_id=" + str(
                        self.comp.id))
                Period = self.env.cr.fetchone()
                if Period != None and Period[0] != None:
                    Period = Period[0]
                else:
                    Period = None

                # Diario
                sbi = False
                if SelfBillingIndicator == '1':
                    SelfBillingIndicator = 'true'
                    sbi = True
                else:
                    SelfBillingIndicator = 'false'
                memInvoiceType = InvoiceType
                self.env.cr.execute(
                    "select * from account_journal where saft_inv_type='" + InvoiceType + "' and company_id=" + str(
                        self.comp.id) + " and type in ('sale','sale_refund') and self_billing=" + SelfBillingIndicator)
                InvoiceType = self.env.cr.fetchone()
                if InvoiceType != None and InvoiceType[0] != None:
                    InvoiceType = InvoiceType[0]
                else:
                    ##                        if memInvoiceType=='NC':
                    ##                            InvoiceType =journal_obj.create({
                    ##                                'code' :  'diario nc',
                    ##                                'name': 'Diario NC',
                    ##                                'type' : 'sale_refund',
                    ##                                'sadt_inv_type': 'NC',
                    ##                                'active' : True,
                    ##                                'allow_date' : True,
                    ##                                'update_posted' : True,
                    ##                                'centralisation' : False,
                    ##                                'group_invoice_lines' : False,
                    ##                                'self_billing': sbi,
                    ##                            })
                    ##                        else:
                    InvoiceType = False
                    raise ValueError(_('UserError'), _('Nao foi encontrado um diario ') + _(InvoiceType))

                # Data do hash
                SystemEntryDate = SystemEntryDate.replace('T', ' ')

                # Cliente
                customer = self.get_customer(CustomerID, CustomerID)
                # conta_cliente
                account_id = None
                self.env.cr.execute(
                    "select value_reference from ir_property where name='property_account_receivable' and res_id='res.partner," + str(
                        CustomerID) + "'")
                linha = self.env.cr.fetchone()
                if linha == None or linha[0] == None:
                    self.env.cr.execute(
                        "select value_reference from ir_property where name='property_account_receivable'  and coalesce(value_reference,'')!='' and company_id=" + str(
                            self.comp.id))
                    linha = self.env.cr.fetchone()
                    if linha != None and linha[0] != None:
                        vec = str(linha[0]).split(',')
                        account_id = vec[1]
                else:
                    vec = str(linha[0]).split(',')
                    account_id = vec[1]

                # Moeda
                currency_id = None
                self.env.cr.execute("select id from res_currency  where name='EUR'  and company_id=" + str(
                    self.comp.id) + " order by id asc")
                linha = self.env.cr.fetchone()
                if linha != None and linha[0] != None:
                    currency_id = linha[0]

                tipo = 'out_invoice'
                if memInvoiceType == 'FT':
                    tipo = 'out_invoice'

                if memInvoiceType == 'NC':
                    tipo = 'out_refund'

                    # todo fatura simplificada, ...

                InvoiceNo = str(InvoiceNo)[3:]

                # validar se ja existe
                self.env.cr.execute("select id from account_invoice where journal_id=" + str(
                    InvoiceType) + " and internal_number='" + str(InvoiceNo) + "' and company_id=" + str(
                    self.comp.id))
                aux = self.env.cr.fetchone()
                if aux == None or aux[0] == None:
                    id_fatura = self.env['account.move'].create({
                        'name': InvoiceNo,
                        'internal_number': InvoiceNo,
                        'state': InvoiceStatus,
                        'hash': Hash,
                        'hash_control': HashControl,
                        'period_id': Period,
                        'date': InvoiceDate,
                        'journal_id': InvoiceType,
                        'type': tipo,
                        'hash_date': SystemEntryDate,
                        'partner_id': CustomerID,
                        'account_id': account_id,
                        'currency_id': currency_id,
                        'amount_tax': TaxPayable,
                        'amount_untaxed': NetTotal,
                        'amount_total': GrossTotal,
                    })
                    linhas = fatura.getElementsByTagName("Line")
                    for linha in linhas:
                        OriginatingON = None
                        LineNumber = converter(((linha.getElementsByTagName("LineNumber")[0]).childNodes[0]).nodeValue)
                        OrderReferences = linha.getElementsByTagName("OrderReferences")
                        if OrderReferences != []:
                            OrderReferences = OrderReferences[0]
                            OriginatingON = converter(
                                ((OrderReferences.getElementsByTagName("OriginatingON")[0]).childNodes[0]).nodeValue)
                        ProductCode = converter(
                            ((linha.getElementsByTagName("ProductCode")[0]).childNodes[0]).nodeValue)
                        Quantity = converter(((linha.getElementsByTagName("Quantity")[0]).childNodes[0]).nodeValue)
                        UnitOfMeasure = converter(
                            ((linha.getElementsByTagName("UnitOfMeasure")[0]).childNodes[0]).nodeValue)
                        UnitPrice = converter(((linha.getElementsByTagName("UnitPrice")[0]).childNodes[0]).nodeValue)
                        Description = converter(
                            ((linha.getElementsByTagName("Description")[0]).childNodes[0]).nodeValue)

                        CreditAmount = linha.getElementsByTagName("CreditAmount")
                        DebitAmount = linha.getElementsByTagName("DebitAmount")
                        price_subtotal = 0
                        if CreditAmount != []:
                            price_subtotal = ((CreditAmount[0]).childNodes[0]).nodeValue
                        if DebitAmount != []:
                            price_subtotal = ((DebitAmount[0]).childNodes[0]).nodeValue

                        SettlementAmount = converter(
                            ((linha.getElementsByTagName("SettlementAmount")[0]).childNodes[0]).nodeValue)

                        # Produto
                        self.env.cr.execute("select id from product_product where default_code='" + ProductCode + "'")
                        product_id = self.env.cr.fetchone()
                        if product_id != None and product_id[0] != None:
                            product_id = product_id[0]
                        else:
                            product_id = False

                        # unidade de medida
                        self.env.cr.execute("select id from product_uom where name='" + UnitOfMeasure + "'")
                        aux = self.env.cr.fetchone()
                        if aux != None and aux[0] != None:
                            UnitOfMeasure = aux[0]
                        else:
                            UnitOfMeasure = self.env['product.uom'].create({
                                'name': UnitOfMeasure,
                                'category_id': 1,
                                'uom_type': 'reference',
                                'active': True,
                                'rounding': 0.010,
                                'factor': 1,
                            })

                        # conta_produto
                        account_id = None
                        self.env.cr.execute(
                            "select id from account_account where code like '71%' and type!='view' and company_id=" + str(
                                self.comp.id))
                        aux = self.env.cr.fetchone()
                        if aux != None and aux[0] != None:
                            account_id = aux[0]

                        if float(price_subtotal) == 0.0:
                            desconto = '0.0'
                        else:
                            desconto = str(round(((float(SettlementAmount) * 100) / float(price_subtotal)), 2))

                        id_linha_fatura = self.env['account.move.line'].create({
                            'sequence': LineNumber,
                            'origin': OriginatingON or '',
                            'product_id': product_id,
                            'quantity': Quantity,
                            'price_unit': UnitPrice,
                            'name': Description,
                            'uos_id': UnitOfMeasure,
                            'price_subtotal': price_subtotal,
                            'discount': desconto,
                            'invoice_id': id_fatura,
                            'account_id': account_id,
                        })

                        impostos = linha.getElementsByTagName("Tax")
                        for imposto in impostos:
                            TaxType = converter(((imposto.getElementsByTagName("TaxType")[0]).childNodes[0]).nodeValue)
                            TaxCountryRegion = converter(
                                ((imposto.getElementsByTagName("TaxCountryRegion")[0]).childNodes[0]).nodeValue)
                            TaxCode = converter(((imposto.getElementsByTagName("TaxCode")[0]).childNodes[0]).nodeValue)
                            TaxPercentage = converter(
                                ((imposto.getElementsByTagName("TaxPercentage")[0]).childNodes[0]).nodeValue)

                            # get imposto
                            self.env.cr.execute(
                                "select id from account_tax where saft_tax_type='" + TaxType + "' and company_id=" + str(
                                    self.comp.id) + " and name like '%" + TaxPercentage + "%' and (type_tax_use='sale' or type_tax_use='all')")
                            id_imposto = self.env.cr.fetchone()
                            if id_imposto != None and id_imposto[0] != None:
                                id_imposto = id_imposto[0]

                                self.env.cr.execute(
                                    "INSERT INTO account_invoice_line_tax(invoice_line_id, tax_id) VALUES (" + str(
                                        id_linha_fatura) + ", " + str(id_imposto) + ")")

            ######################
            ##   Fim Faturas    ##
            ######################

            res = "Importou " + str(imp) + " transacções"
            if erros == "As incompatibilidades encontradas foram:":
                erros = "Não foram encontradas incompatibilidades"
            return self.write({'state': 'get', 'name': res, 'erros': erros})

    def saft_faturacao(self, document):
        return True

