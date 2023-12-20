# -*- coding: utf-8 -*-

import base64
import datetime
import logging

from odoo.tools import float_round
from odoo import models, fields, api

logger = logging.getLogger(__name__)


class WizardExpStock(models.TransientModel):
    _name = "wizard.exp.stock"
    _description = "Exportar Stock AT - Menu: Contabilidade - Relatorios - Saft - Exportar Stock"

    @api.model
    def _default_company(self):
        """Devolve a empresa do utilizador, ou a primeira encontrada"""
        if self.env.user.company_id:
            return self.env.user.company_id.id
        return self.env['res.company'].search([('parent_id', '=', False)])[0]

    @api.model
    def _default_data(self):
        today = datetime.date.today()
        lastyear = datetime.date(day=31, month=12, year=today.year - 1)
        return lastyear

    @api.model
    def _get_tipo_produto_saft(self):
        return self.env['tipo.produto.saft'].search([])

    name = fields.Char(string="Filename", size=254, readonly=True, default="saftpt.xml", copy=False)
    info = fields.Text(string="Informação", default="Exportação do ficheiro com os stocks", copy=False)
    data = fields.Date(string="Data", default=_default_data, copy=False)
    comp = fields.Many2one('res.company', string="Companhia", required=True, default=_default_company, copy=False)
    filedata = fields.Binary(string="File", readonly=True, copy=False)
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], string="Estado", default='choose', copy=False)
    tipo_prod = fields.Selection([('todos', 'Todos'), ('armazenavel', 'Armazenável'), ('consumivel', 'Consumível')],
                                 string="Tipo de Produto", default="todos", copy=False)
    tipo_produto_saft_ids = fields.Many2many('tipo.produto.saft', 'tipo_produto_saft_rel', 'wiz_id',
                                             'tipo_produto_saft_id', string="Tipo de Produto Saft", copy=False,
                                             readonly=False, default=_get_tipo_produto_saft)
    tipo_stock = fields.Selection([('normal', 'Normal'), ('valorizado', 'Valorizado')],
                                  string="Tipo de Stock", copy=False)

    
    def act_destroy(self):
        return {'type': 'ir.actions.act_window_close'}

    
    def _get_product_qty(self, location, produto):
        self._cr.execute("""
            SELECT coalesce(sum(product_qty),0)
            FROM stock_move sm, stock_location l
            WHERE sm.date <= '""" + str(self.data) + """ 23:59:59'
                AND """ + str(location) + """ AND l.usage='internal'
                AND l.active=True AND sm.state='done' AND sm.product_id=%s""", (produto.id,))
        return self._cr.fetchone()[0]

    
    def act_getfile(self):
        logger.info("saft :", ' A exportar o ficheiro de Stock ****')

        if self.tipo_stock == 'normal':
            root = "ProductCategory;ProductCode;ProductDescription;ProductNumberCode;ClosingStockQuantity;" \
                   "UnitOfMeasure\r\n"
            nome = 'Exportar Stock'
        # stock valorizado
        else:
            root = "ProductCategory;ProductCode;ProductDescription;ProductNumberCode;ClosingStockQuantity;" \
                   "UnitOfMeasure;ClosingStockValue\r\n"
            nome = 'Exportar Stock Valorizado'

        tipo_artigo = ('type', 'in', ('product', 'consu'))
        if self.tipo_prod == 'armazenavel':
            tipo_artigo = ('type', '=', 'product')
        elif self.tipo_prod == 'consumivel':
            tipo_artigo = ('type', '=', 'consu')

        # tipo produto saft
        lista_tipo_produtos_saft = []
        for tipo_produto_saft in self.tipo_produto_saft_ids:
            lista_tipo_produtos_saft.append(tipo_produto_saft.id)

        # ('qty_available', '>', 0),
        produtos = self.env['product.product'].search([
            ('active', '=', True),
            ('company_id', '=', self.comp.id), tipo_artigo,
            ('tipo_produto_id', 'in', lista_tipo_produtos_saft)])

        for produto in produtos:
            # get stock
            entra_local = self._get_product_qty('sm.location_dest_id=l.id', produto)
            sai_local = self._get_product_qty('sm.location_id=l.id', produto)
            stock = float_round(entra_local - sai_local,
                                precision_digits=self.env['decimal.precision'].precision_get('Product Unit of Measure'))
            if stock > 0:
                # tipo produto saft
                categoria_saft = produto.tipo_produto_id.code or ''
                ean = produto.barcode
                if ean is False:
                    ean = produto.default_code
                valor_prodcateg = ''
                # stock valorizado
                if self.tipo_stock == 'valorizado':
                    valor = str(float_round(stock*produto.standard_price,
                                            precision_digits=self.env['decimal.precision'].precision_get(
                                                'Product Price'))).replace(".", ",")
                    prodcateg = produto.categ_id.name
                    valor_prodcateg = ";" + valor
                stock = str(stock).replace(".", ",")
                root = root + categoria_saft + ";" + produto.default_code.replace(";", ",") + ";" + \
                    produto.name.replace(";", ",") + ";" + ean.replace(";", ",") + ";" + stock + ";" + \
                    produto.uom_id.name + valor_prodcateg + "\r\n"

        nome_file = 'Stock-' + self.comp.name + '.csv'

        try:
            csv_txt = root.encode("windows-1252")
        except:
            csv_txt = root.encode("UTF-8")

        out = base64.encodebytes(csv_txt)

        self.write({'state': 'get', 'filedata': out, 'name': nome_file})

        return {
            'name': nome,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'wizard.exp.stock',
            'type': 'ir.actions.act_window',
            'res_id': self.id,
            'target': 'new',
        }
