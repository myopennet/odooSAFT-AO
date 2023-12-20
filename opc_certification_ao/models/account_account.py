# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountAccount(models.Model):
    _inherit = "account.account"

    # actualizar contas pai
    # menu contabilidade - configuracao - plano de contas
    def init(self):
        for conta in self.env['account.account'].sudo().search([]):
            # if not l.parent_id:
            conta.sudo()._compute_parent_id()

    active = fields.Boolean(string="Active", default=True)
    tipo_conta = fields.Selection(selection=[('GR', 'GR - Conta de 1.º grau da contabilidade geral'),
                                             ('GA', 'GA - Conta agregadora ou integradora da contabilidade geral'),
                                             ('GM', 'GM - Conta de movimento da contabilidade geral'),
                                             ('AR', 'AR - Conta de 1.º grau da contabilidade analítica'),
                                             ('AA',
                                              'AA - Conta agregadora ou integradora da contabilidade analítica'),
                                             ('AM', 'AM - Conta de movimento da contabilidade analítica')],
                                  string="Grupo da conta", required=True, default="GM", copy=False)
    parent_id = fields.Many2one('account.account', compute='_compute_parent_id', string="Conta Pai", store=True)
    children_ids = fields.One2many('account.account', 'parent_id', 'Contas')
    taxonomia_id = fields.Many2one('taxonomia', string='Taxonomia')
    code = fields.Char(size=10, required=True, index=True)

    # actualizar tipo de conta para GR se a conta pai for alterada para vazio
    # actualizar conta pai caso exista
    
    def write(self, vals):
        if 'parent_id' in vals and vals['parent_id'] is False:
            vals['tipo_conta'] = "GR"
        result = super(AccountAccount, self).write(vals)
        if 'parent_id' in vals and vals['parent_id']:
            self._cr.execute("""
                UPDATE account_account
                SET tipo_conta='GA'
                WHERE coalesce(parent_id,-1)<>-1 and id=""" + str(vals['parent_id']))
            self.env.cr.execute("""
                select id
                from account_account
                where code ilike %s and parent_id = %s and id !=%s
                """, (self.code + '%', self.parent_id.id, self.id))
            accounts = self.search([
                ('id', 'in', list(self.env.cr.fetchall()))])
            for account in accounts:
                account.write({'parent_id': self.id})
        return result

    # actualizar tipo de conta para GR se a conta pai for alterada para vazio
    # actualizar conta pai caso exista
    @api.model
    def create(self, vals):
        if 'code' in vals:
            for i in range(1, 10):
                ids_pai = self.env['account.account'].search([('code', '=', vals['code'][:-i])], limit=1)
                for ids_pais in ids_pai:
                    vals['parent_id'] = ids_pais.id
                    break
        if 'parent_id' in vals and vals['parent_id'] is False:
            vals['tipo_conta'] = "GR"
        current_account = super(AccountAccount, self).create(vals)
        if 'parent_id' in vals and vals['parent_id'] is not False:
            self._cr.execute("""
                UPDATE account_account
                SET tipo_conta='GA'
                WHERE coalesce(parent_id,-1)<>-1 and id=""" + str(vals['parent_id']))
            self.env.cr.execute("""
                        select id
                        from account_account
                        where code ilike %s and parent_id = %s and id !=%s
                        """, (current_account.code + '%', current_account.parent_id.id, current_account.id))
            accounts = self.search([
                ('id', 'in', list(self.env.cr.fetchall()))])
            for account in accounts:
                account.write({'parent_id': current_account.id})
        return current_account

    # actualizar conta pai caso exista

    @api.depends('code', 'tipo_conta')
    def _compute_parent_id(self):
        for account in self:
            if account.code:
                ids_pai = []
                for i in range(1, 10):
                    ids_pai = self.env['account.account'].search([('code', '=', account.code[:-i])], limit=1)
                    if len(ids_pai) > 0:
                        break

                account.parent_id = ids_pai.id
