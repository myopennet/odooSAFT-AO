from odoo import models


class AccountMoveReversal(models.TransientModel):
    _inherit = "account.move.reversal"

    def _prepare_default_reversal(self, move):
        """ Set reason cancel on credit note """
        res = super()._prepare_default_reversal(move)
        type = 'Anulação'
        if self.refund_method == 'refund':
            type = 'Rectificação'
        new_origin = ''
        contador = 0
        for moves in self.move_ids:
            contador = contador + 1
            if moves.name:
                if contador > 1:
                    new_origin += str(moves.journal_id.saft_inv_type) + ' ' + str(moves.name) + ', '
                else:
                    new_origin += str(moves.journal_id.saft_inv_type) + ' ' + str(moves.name)
        res.update({
            'reason_cancel': self.reason,
            'invoice_origin': new_origin,
            'ref': type,
        })
        return res