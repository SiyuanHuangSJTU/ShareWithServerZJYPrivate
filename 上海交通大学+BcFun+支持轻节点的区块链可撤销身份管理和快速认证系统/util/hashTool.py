import json
from hashlib import sha256
import ecdsa
import base64
from util.lss import SecretShare
from charm.toolbox.eccurve import prime192v1
from charm.toolbox.ecgroup import ECGroup, G, ZR

group = ECGroup(prime192v1)
model = SecretShare(group)


# 创建 merkel 树
# data: ["{"from":"xx", "to": "xx", "message":"xx", "sig": "xx", "hash": "xxx}, ...]
def merkel_tree(data):
    while len(data) != 1:
        tmp = []
        for i in range(0, len(data), 2):
            if i + 1 >= len(data):
                tmp.append(data[i])
            else:
                new_hash = sha256(bytes.fromhex(data[i]["hash"]) + bytes.fromhex(data[i + 1]["hash"])).hexdigest()
                tmp.append({"hash": new_hash, "data": [data[i], data[i + 1]]})
        data = tmp
    return data[0]


# 将 merkel 树转换成 list
# 迭代自身
def from_merkel_to_list(merkel, result_list):
    if "data" in merkel:
        for i in merkel['data']:
            from_merkel_to_list(i, result_list)
    else:
        result_list.append(merkel)


# 密钥生成
# 生成并返回一对公私钥
def generate_ECDSA_keys():
    sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)  # this is your sign (private key)
    private_key = sk.to_string().hex()  # convert your private key to hex
    vk = sk.get_verifying_key()  # this is your verification key (public key)
    public_key = vk.to_string().hex()
    return public_key, private_key


# 签名
# private_key: hex string 格式的私钥
# data: bytes 类型的消息数据
# 返回 base64 编码的签名
def sign(private_key, data):
    sk = ecdsa.SigningKey.from_string(bytes.fromhex(private_key), curve=ecdsa.SECP256k1)
    return base64.b64encode(sk.sign(data)).decode()


# 验证签名
# public_key: hex string 格式的公钥
# signature: base64 编码的签名
# message: bytes 类型的消息数据
# 返回 True（验证成功）或 False（验证失败）
def validate_signature(public_key, signature, message):
    signature = base64.b64decode(signature)
    try:
        vk = ecdsa.VerifyingKey.from_string(
            bytes.fromhex(public_key), curve=ecdsa.SECP256k1)
        return vk.verify(signature, message)
    except:
        return False


# 生成 chameleon hash 初始参数
# 返回两个大整数，x 用来修改，y 用来生成
def chameleon_init():
    x = model.elem.random(ZR)
    shares = model.genShares(x, k=2, n=5)
    g = model.elem.random(G)
    y = g ** x
    return g, shares, y


# 计算变色龙哈希
# y：
# msg: 待计算的消息
def chameleon_hash(g, y, msg):
    r, s = model.elem.random(ZR), model.elem.random(ZR)
    ch = r - model.elem.hash(y ** model.elem.hash((msg, r)) * (g ** s))
    return r, s, ch


# 变色龙哈希验证过程的计算
def chameleon_verify(g, y, msg, r, s):
    return r - model.elem.hash(y ** model.elem.hash((msg, r)) * (g ** s))


# 变色龙哈希的修改
def chameleon_adjust(g, keys, msg, ch):
    x = model.recover(keys)
    y = {}
    ki = {}
    Ki = {}
    si = {}
    for i in keys.keys():
        y[i] = g ** keys[i]
        ki[i] = model.elem.random(ZR)
        Ki[i] = g ** ki[i]
    K = model.recoverInExp(Ki)
    r = ch + model.elem.hash(K)
    temp = model.elem.hash((msg, r))
    for i in keys.keys():
        si[i] = ki[i] - keys[i] * temp
    s = model.recover(si)
    return r, s


# 对变色龙哈希输出值进行序列化，转换成str
# group_element: 变色龙哈希过程中产生的值
# 返回值：序列化之后的字符串
def chameleon_serialize(group_element):
    if type(group_element) == dict:
        tmp_dict = {}
        for i in group_element:
            tmp_dict[i] = group.serialize(group_element[i]).decode()
        return json.dumps(tmp_dict)
    return group.serialize(group_element).decode()


# 对变色龙哈希输出值进行序列化，转换成str
# string_element: str类型的字符串
# 返回值：反序列化之后的group类型的值
def chameleon_deserialize(string_element):
    try:
        json_dict = json.loads(string_element)
        tmp = {}
        for i in json_dict:
            tmp[int(i)] = group.deserialize(json_dict[i].encode())
        return tmp
    except json.decoder.JSONDecodeError:
        return group.deserialize(string_element.encode())