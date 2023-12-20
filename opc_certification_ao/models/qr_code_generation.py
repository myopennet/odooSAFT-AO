# -*- coding: utf-8 -*-
from odoo import _
import re
from odoo.exceptions import ValidationError


def qr_code_at(nif_empresa, nif_cliente, pais_cliente, tipo_documento, doc_state, doc_date, numero, atcud,
               espaco_fiscal, valor_base_isento, valor_base_red, valor_iva_red, valor_base_int, valor_iva_int,
               valor_base_normal, valor_iva_normal, valor_n_sujeito_iva, imposto_selo, total_impostos,
               total_com_impostos, retencao_na_fonte, quatro_caratecters_hash, n_certificado, outras_infos):
    if not nif_empresa:
        raise ValidationError("O campo NIF na empresa é obrigatorio.")
    nif_empresa = str(re.findall('\d+', nif_empresa)).replace("['", "").replace("']", "")
    nif_empresa = 'A:' + _(nif_empresa)

    if not nif_cliente:
        raise ValidationError("O campo NIF no cliente é obrigatorio.")
    nif_cliente = str(re.findall('\d+', nif_cliente)).replace("['", "").replace("']", "")
    nif_cliente = '*B:' + _(nif_cliente)

    pais_cliente = '*C:' + _(pais_cliente)
    tipo_documento_export = '*D:' + _(tipo_documento)
    doc_state = '*E:' + _(doc_state)
    doc_date = '*F:' + _(doc_date)[:10].replace('-','')
    numero = '*G:' + _(tipo_documento) + ' ' + _(numero)
    atcud = '*H:' + _(atcud)
    codigo_espaco_fiscal = '*I'
    if espaco_fiscal == 'PT-AC':
        codigo_espaco_fiscal = '*J'
    if espaco_fiscal == 'PT-MA':
        codigo_espaco_fiscal = '*K'
    espaco_fiscal = codigo_espaco_fiscal + '1:' + _(espaco_fiscal)

    if valor_base_isento != 0:
        valor_base_isento = codigo_espaco_fiscal + '2:' + _('%.2f' % valor_base_isento)
    else:
        valor_base_isento = ''
    if valor_base_red != 0:
        valor_base_red = codigo_espaco_fiscal + '3:' + _('%.2f' % valor_base_red)
    else:
        valor_base_red = ''
    if valor_iva_red != 0:
        valor_iva_red = codigo_espaco_fiscal + '4:' + _('%.2f' % valor_iva_red)
    else:
        valor_iva_red = ''
    if valor_base_int != 0:
        valor_base_int = codigo_espaco_fiscal + '5:' + _('%.2f' % valor_base_int)
    else:
        valor_base_int = ''
    if valor_iva_int != 0:
        valor_iva_int = codigo_espaco_fiscal + '6:' + _('%.2f' % valor_iva_int)
    else:
        valor_iva_int = ''
    if valor_base_normal != 0:
        valor_base_normal = codigo_espaco_fiscal + '7:' + _('%.2f' % valor_base_normal)
    else:
        valor_base_normal = ''
    if valor_iva_normal != 0:
        valor_iva_normal = codigo_espaco_fiscal + '8:' + _('%.2f' % valor_iva_normal)
    else:
        valor_iva_normal = ''

    if valor_n_sujeito_iva != 0:
        valor_n_sujeito_iva = '*L:' + _('%.2f' % valor_n_sujeito_iva)
    else:
        valor_n_sujeito_iva = ''
    if imposto_selo != 0:
        imposto_selo = '*M:' + _('%.2f' % imposto_selo)
    else:
        imposto_selo = ''

    total_impostos = '*N:' + _('%.2f' % total_impostos)
    total_com_impostos = '*O:' + _('%.2f' % total_com_impostos)
    if retencao_na_fonte != 0:
        retencao_na_fonte = '*P:' + _('%.2f' % retencao_na_fonte)
    else:
        retencao_na_fonte = ''

    quatro_caratecters_hash = '*Q:' + _(quatro_caratecters_hash)
    n_certificado = '*R:' + _(n_certificado)
    if outras_infos:
        outras_infos = '*S:' + _(outras_infos)
    else:
        outras_infos = ''

    qr_code = nif_empresa + nif_cliente + pais_cliente + tipo_documento_export + doc_state + \
              doc_date + numero + atcud + espaco_fiscal + valor_base_isento + \
              valor_base_red + valor_iva_red + valor_base_int + valor_iva_int + \
              valor_base_normal + valor_iva_normal + valor_n_sujeito_iva + imposto_selo + \
              total_impostos + total_com_impostos + retencao_na_fonte + quatro_caratecters_hash + n_certificado + \
              outras_infos
    return qr_code