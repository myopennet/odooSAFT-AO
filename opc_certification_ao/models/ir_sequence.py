# -*- coding: utf-8 -*-

from odoo import fields, models, api, _


# configuracoes - tecnicos - sequencias e identificadores - sequencias
class IrSequenceDateRange(models.Model):
    _inherit = "ir.sequence.date_range"

    codigo_validacao_serie = fields.Char(string="Código de Validação de Série",
                                         help="Código único para esta série a fornecer pela AT.", copy=False)

class IrSequence(models.Model):
    _inherit = "ir.sequence"

    implementation = fields.Selection([('standard', 'Standard'), ('no_gap', 'No gap')],
                                      string='Implementation', required=True, default='no_gap',
                                      help="Two sequence object implementations are offered: Standard "
                                           "and 'No gap'. The later is slower than the former but forbids any "
                                           "gap in the sequence (while they are possible in the former).")
    codigo_validacao_serie = fields.Char(string="Código de Validação de Série",
                                         help="Código único para esta série a fornecer pela AT.", copy=False)

    @api.model
    def create(self, vals):
        if 'prefix' in vals and vals['prefix']:
            while vals['prefix'].count('/') > 1:
                pos = vals['prefix'].find('/')
                vals['prefix'] = _(vals['prefix'][:pos]) + _(vals['prefix'][pos + 1:])

        sequence = super(IrSequence, self).create(vals)

        # Actualizar sequencias nos tipos de entrega das guias
        if 'code' in vals and vals['code'] == 'stock.picking.gd.validate':
            stock_picking_types = self.env['stock.picking.type'].search([('sequence_id_gd_validate', '=', False)])
            for stock_picking_type in stock_picking_types:
                # Se houver um problema na atribuiçao de uma nova sequencia ao tipo de recolha,
                # a atribuiçao deve ser ignorada.
                try:
                    stock_picking_type.sequence_id_gd_validate = sequence.id
                except:
                    pass
        elif 'code' in vals:
            code = False
            if 'code' in vals and vals['code'] == 'stock.picking.out.validate':
                code = 'outgoing'
            elif 'code' in vals and vals['code'] == 'stock.picking.in.validate':
                code = 'incoming'
            elif 'code' in vals and vals['code'] == 'stock.picking.internal.validate':
                code = 'internal'
            if code:
                stock_picking_types = self.env['stock.picking.type'].search([('code', '=', code),
                                                                            ('sequence_id_validate', '=', False)])
                for stock_picking_type in stock_picking_types:
                    # Se houver um problema na atribuiçao de uma nova sequencia ao tipo de recolha,
                    # a atribuiçao deve ser ignorada.
                    try:
                        stock_picking_type.sequence_id_validate = sequence.id
                    except:
                        pass

        # actualizar localizações por defeito
        local_stock = self.env['stock.location'].search([('usage', '=', 'internal')], order='id ASC', limit=1).id
        local_clientes = self.env['stock.location'].search([('usage', '=', 'customer')], order='id ASC', limit=1).id
        local_fornecedores = self.env['stock.location'].search([('usage', '=', 'supplier')], order='id ASC', limit=1).id

        for code, locations in zip(['outgoing', 'incoming', 'internal'],
                                   [[local_stock, local_clientes], [local_fornecedores, local_stock],
                                    [local_stock, local_stock]]):
            for default, local in zip(['default_location_src_id', 'default_location_dest_id'], locations):
                self.env.cr.execute("""
                    SELECT id
                    FROM stock_picking_type
                    WHERE code=%s and coalesce(""" + default + """,0)=0""", (code,))
                stock_location_ids = self.env.cr.fetchall()
                for stock_local_id in stock_location_ids:
                    self.env.cr.execute("""
                        UPDATE stock_picking_type
                        SET """ + default + """=%s
                        WHERE id=%s""", (local, stock_local_id[0]))
        return sequence

    
    def write(self, vals):
        for sequence in self:
            # restrição na atualização de campos
            if 'prefix' in vals or 'suffix' in vals or 'padding' in vals or 'number_increment' in vals:
                if sequence.number_next_actual > 1 or sequence.number_next > 1:
                    return True

                self.env.cr.execute("""
                    SELECT number_next
                    FROM ir_sequence_date_range
                    WHERE sequence_id=%s""", (sequence.id,))
                number_next = self.env.cr.fetchone()
                if number_next and number_next[0] > 1:
                    return True

            # Ver se ja existem documentos com um prefixo diferente
            if 'prefix' in vals:
                for field, operator in zip(['sequence_id', 'refund_sequence_id'], ['not like', 'ilike']):
                    journal_ids = self.env['account.journal'].search([(field, '=', sequence.id)])
                    for journal in journal_ids:
                        prev_invoice = self.env['account.move'].search([
                            ('move_type', operator, '%refund%'),
                            ('state', '!=', 'draft'),
                            ('journal_id', '=', journal.id)], order='date DESC', limit=1)
                        # Extrair prefixo
                        prefix = ''
                        if prev_invoice:
                            invoice_number = prev_invoice.internal_number
                            while invoice_number[0:1] not in ('1', '2', '3', '4', '5', '6', '7', '8', '9', '0') and \
                                    invoice_number[0:1]:
                                prefix = invoice_number[0:1]
                                invoice_number = invoice_number[2:]
                            # se o prefix do vals for diferente do prefixo do documento, ignorar o write
                            if vals['prefix'] != prefix:
                                del vals['prefix']

            if 'prefix' in vals and vals['prefix']:
                while vals['prefix'].count('/') > 1:
                    pos = vals['prefix'].find('/')
                    vals['prefix'] = _(vals['prefix'][:pos]) + _(vals['prefix'][pos + 1:])

            self.env.cr.execute("""
                SELECT count(*)
                FROM account_journal d, account_move i
                WHERE i.state!='draft' and i.journal_id=d.id and d.sequence_id=%s""", (sequence.id,))
            if self.env.cr.fetchone()[0] > 0:
                if 'prefix' in vals and not sequence.prefix:
                    del vals['prefix']
                if 'suffix' in vals and not sequence.suffix:
                    del vals['suffix']
                if 'padding' in vals and not sequence.padding:
                    del vals['padding']
                if 'number_increment' in vals and not sequence.number_increment:
                    del vals['number_increment']
                if 'number_next' in vals and not sequence.number_next:
                    del vals['number_next']
                if 'implementation' in vals and not sequence.implementation:
                    del vals['implementation']
                if 'code' in vals and not sequence.code:
                    del vals['code']

        return super(IrSequence, self).write(vals)
