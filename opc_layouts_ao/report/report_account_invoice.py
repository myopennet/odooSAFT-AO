# -*- coding: utf-8 -*-

from odoo import api, models


class ReportInvoice(models.AbstractModel):
    _name = 'report.account.report_invoice'
    _description = 'Account report'

    def get_is_printed(self, invoice):
        if (invoice.state == 'open' or invoice.state == 'paid' or invoice.state == 'cancel') and not invoice.isprinted:
            invoice.write({'isprinted': True})
            return True

    def get_description(self, invoice_line):
        result = []
        res = {}

        description = invoice_line.name
        if invoice_line.product_id:
            description = '[' + str(invoice_line.product_id.default_code) + '] ' + \
                          str(invoice_line.product_id.name) + ' ' + \
                          str(invoice_line.name.replace(invoice_line.product_id.name, '')) or ''

        res['description'] = description
        result.append(res)

        return result

    @api.model
    def _get_report_values(self, docids, data=None):
        report = self.env['ir.actions.report']._get_report_from_name('account.report_invoice')
        return {
            'doc_ids': docids,
            'doc_model': report.model,
            'docs': self.env[report.model].browse(docids),
            'report_type': data.get('report_type') if data else '',
            'get_is_printed': self.get_is_printed,
            'get_description': self.get_description,
        }


class ReportInvoiceWithPayment(models.AbstractModel):
    _inherit = 'report.account.report_invoice_with_payments'
    _description = 'Account report with payment lines'

    def get_is_printed(self, invoice):
        if (invoice.state == 'open' or invoice.state == 'paid' or invoice.state == 'cancel') and not invoice.isprinted:
            invoice.write({'isprinted': True})
            return True

    def get_description(self, invoice_line):
        result = []
        res = {}
        if invoice_line.product_id:
            description = '[' + str(invoice_line.product_id.default_code) + '] ' + \
                          str(invoice_line.product_id.name) + ' ' + \
                          str(invoice_line.name.replace(invoice_line.product_id.name, '')) or ''
        else:
            description = invoice_line.name

        res['description'] = description
        result.append(res)

        return result

    @api.model
    def _get_report_values(self, docids, data=None):
        report = self.env['ir.actions.report']._get_report_from_name('account.report_invoice_with_payments')
        return {
            'doc_ids': docids,
            'doc_model': report.model,
            'docs': self.env[report.model].browse(docids),
            'report_type': data.get('report_type') if data else '',
            'get_is_printed': self.get_is_printed,
            'get_description': self.get_description,
        }
