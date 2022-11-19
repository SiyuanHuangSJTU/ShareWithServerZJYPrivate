import base64
from hashlib import sha256
import ecdsa
import json
from argparse import ArgumentParser
import requests
from datetime import datetime
from util import hashTool


def generate_ECDSA_keys():
    sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)  # this is your sign (private key)
    private_key = sk.to_string().hex()  # convert your private key to hex
    vk = sk.get_verifying_key()  # this is your verification key (public key)
    public_key = vk.to_string().hex()
    return public_key, private_key


def sign(private_key, data):
    sk = ecdsa.SigningKey.from_string(bytes.fromhex(private_key), curve=ecdsa.SECP256k1)
    return base64.b64encode(sk.sign(data)).decode()


def sign_transaction(public_key, private_key, transaction):
    if "message" in transaction:
        transaction["from"] = public_key
        transaction["signature"] = sign(private_key, transaction["message"].encode())
        transaction["hash"] = sha256(
            bytes.fromhex(transaction["from"]) + transaction["message"].encode() +
            transaction["signature"].encode()).hexdigest()
        return transaction
    else:
        return None


def validate_signature(public_key, signature, message):
    signature = base64.b64decode(signature)
    try:
        vk = ecdsa.VerifyingKey.from_string(
            bytes.fromhex(public_key), curve=ecdsa.SECP256k1)
        return vk.verify(signature, message)
    except:
        return False


if __name__ == "__main__":
    try:
        key_info = json.load(open("./client_id.json", "r"))
        public_key = key_info["public_key"]
        private_key = key_info["private_key"]
    except FileNotFoundError:
        public_key, private_key = generate_ECDSA_keys()
        json.dump({"public_key": public_key, "private_key": private_key}, open("./client_id.json", "w"))

    parser = ArgumentParser()
    parser.add_argument('-a', '--address', help='target ip and port of transaction, e.g. 127.0.0.1:8000')
    args = parser.parse_args()

    message = "Identity_Example_" + datetime.now().strftime("%H%M%S")
    transaction = sign_transaction(public_key, private_key, {"message": message})
    while True:
        print("Action:\n[1] Add New\n[2] Revoke")
        action = int(input("action:"))
        if action == 1:
            message = "Identity_Example_" + datetime.now().strftime("%H%M%S")
            public_key, private_key = generate_ECDSA_keys()
            transaction = sign_transaction(public_key, private_key, {"message": message})
            if transaction:
                print("------transaction------")
                trans_show = {
                    "Pub key": transaction["from"],
                    "Identity": transaction["message"],
                    "Signature": transaction["signature"],
                    "Hash": transaction["hash"]
                }
                print(json.dumps(trans_show, indent=4))
                r = requests.post("http://{0}/transaction/add".format(args.address), data=transaction)
                if r.status_code != 200:
                    print("Node Error, please check if {0} is still alive!".format(args.address))
                else:
                    print(r.text)
        elif action == 2:
            blk_hash = input("Block Hash:")
            tran_hash = input("Transaction Hash:")
            msg = {"code": 6, "action": "REVOKE", "msg": {"block_hash": blk_hash, "transaction_hash": tran_hash}}
            r = requests.post("http://{0}/block".format(args.address), data=json.dumps(msg))
            if r.status_code != 200:
                print("Node Error, please check if {0} is still alive!".format(args.address))
            else:
                print(r.text)