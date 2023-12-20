# -- coding: utf-8 --
import sys
import base64
from Crypto.Signature import pkcs1_15
from Crypto.PublicKey import RSA
from Crypto.Hash import SHA1


def hash(self, manual, datadocumento, datasistema, number, numHash, antigoHash, totalbruto):
    """
    In this method we generate the hash for the invoice.
    """
    if sys.platform == "win32":
        return {'hash': '', 'hash_date': datasistema, 'hash_control': '0'}

    caminho_chave = "/bin/ChavePrivadaAO.pem"

    data = str(datadocumento) + ';' + str(datasistema).replace(' ', 'T') + ';' + number + ';' + str(totalbruto) + ';'
    if numHash > 0:
        data += antigoHash
    # Import private key to RSA object
    rsa_key = RSA.import_key(open(caminho_chave).read())
    # Generate sha1 hash of the invoice data
    sha1_hash = SHA1.new(data.encode('utf-8'))
    # Sign the hash with the private key
    signed_hash = pkcs1_15.new(rsa_key).sign(sha1_hash)
    # Encode the signed hash to base64
    encoded_hash = base64.b64encode(signed_hash)
    # Convert the encoded hash to string
    novohash = encoded_hash.decode('utf-8')
    values = {'hash': novohash, 'hash_date': datasistema}

    if manual:
        values.update({'hash_control': '1-' + self.journal_id.saft_inv_type + 'M ' + self.origin})
    else:
        values.update({'hash_control': '1'})
    return values