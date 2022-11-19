#!/usr/bin/python
# -*- coding:utf-8 -*-
import requests
from util import hashTool
from datetime import datetime
from hashlib import sha256
import json


class BlockChain:
    def __init__(self, host="127.0.0.1", port=8000, test_mode=False, max_transactions=8):
        self.info = {"host": host, "port": port, "term": 0}
        self.peer_list = []
        self.chain = []
        self.transaction_pool = []
        self.public_key = ""
        self.private_key = ""
        self.max_transactions = max_transactions
        self.character = "candidate"
        self.leader = {}
        self.chameleon = {}
        self.current_term = 1
        self.testmode = test_mode

    def init(self, peer=None):
        try:
            if self.testmode:
                # 测试模式下通过raise error方式跳过读取
                raise FileNotFoundError
            # 从本地配置文件加载配置
            identity = json.load(open('./identity.json', 'r'))
            self.public_key = identity["public_key"]
            self.private_key = identity["private_key"]
            self.chameleon["g"] = identity["g"]
            self.chameleon["x"] = identity["x"]
            self.chameleon["y"] = identity["y"]
        except (FileNotFoundError, KeyError):
            self.public_key, self.private_key = hashTool.generate_ECDSA_keys()
            g, x, y = hashTool.chameleon_init()
            self.chameleon["g"] = hashTool.chameleon_serialize(g)
            self.chameleon["x"] = hashTool.chameleon_serialize(x)
            self.chameleon["y"] = hashTool.chameleon_serialize(y)
            if not self.testmode:
                # 如果非测试模式下引起错误，则将文件保存在本地
                json.dump({
                    "public_key": self.public_key,
                    "private_key": self.private_key,
                    "g": self.chameleon["g"],
                    "x": self.chameleon["x"],
                    "y": self.chameleon["y"]
                }, open('./identity.json', 'w'))
        try:
            self.chain = self.load_chain_data()
        except FileNotFoundError:
            pass
        if peer:
            # 当指定了同步节点时，同步网络信息
            return self.gossip(peer)
        else:
            # 作为初始节点进行初始化
            self.leader = {"host": self.info['host'], "port": self.info['port'], "public_key": self.public_key,
                           "term": self.info['term'], "chameleon": self.chameleon}
            self.character = "leader"
            # 如果本地没有链的信息则创建新的
            if len(self.chain) == 0:
                self.broadcast_block(self.generate_block())
            return True

    def load_chain_data(self):
        if self.testmode:
            return self.chain
        else:
            try:
                return json.load(open('./chain.json', 'r'))
            except FileNotFoundError:
                return []

    def save_chain_data(self):
        if not self.testmode:
            json.dump(self.chain, open('./chain.json', 'w'))

    # 与 peer 通信
    def gossip(self, peer):
        url = "http://{host}:{port}/gossip".format(**peer)
        message = json.dumps({
            "code": 1,
            "message": "hello",
            "data": self.info
        })
        try:
            r = requests.post(url=url, data=message,
                              headers={'Content-type': 'application/json', 'Accept': 'text/plain'})
            if r.status_code == 200:
                info = json.loads(r.text)
                # 处理节点身份
                if info["status"] == "OK":
                    # 将通信成功的节点信息尝试加入本地列表
                    self.add_peer(info["peer_info"])
                    # 当前失去leader节点，且获取到了leader信息后，更新leader信息
                    if info['character'] == "leader":
                        # 将获取到的leader信息写入
                        self.leader = info["leader"]
                        self.chameleon = info["leader"]["chameleon"]
                        self.info["term"] = info["current_term"]
                        self.character = "follower"
                        # 同步区块
                        self.sync_block()
                    else:
                        # 尝试与leader通信
                        if not self.gossip(info["leader"]):
                            # 如果无法与leader通信，则说明该节点提供的leader挂了
                            # 此处直接返回，或者进入节点选举
                            raise ValueError
                    # 将节点列表信息写入本地
                    for node in info["peers"]:
                        self.add_peer(node)
                return True
            else:
                # 如果该节点无法正常访问，则从列表中删除
                self.peer_list.remove(peer)
                return False
        except:
            return False

    # 添加新节点
    def add_peer(self, peer):
        peer_list_copy = self.peer_list.copy()
        for node in peer_list_copy:
            if node["host"] == peer["host"] and node["port"] == peer["port"]:
                self.peer_list.remove(node)
        self.peer_list.append(peer)
        return True

    def test_connection(self, peer, code):
        url = "http://{host}:{port}/daemon".format(**peer)
        message = json.dumps({
            "code": code,
            "message": "Test connection"
        })
        try:
            r = requests.post(url=url, data=message,
                              headers={'Content-type': 'application/json', 'Accept': 'text/plain'})
            if r.status_code == 200:
                return True
            else:
                return False
        except:
            return False

    # 选举节点
    def election(self):
        leader_term = self.leader["term"] + 1
        peer_term = {}
        for i in range(0, len(self.peer_list)):
            peer_term[self.peer_list[i]["term"]] = i
        for i in range(leader_term, self.info["term"]):
            if i in peer_term:
                url = "http://{host}:{port}/election".format(**self.peer_list[peer_term[i]])
                message = json.dumps({
                    "code": 2
                })
                try:
                    r = requests.post(url=url, data=message,
                                      headers={'Content-type': 'application/json', 'Accept': 'text/plain'})
                    if r.status_code == 200 and json.loads(r.text)["code"] == 1:
                        self.leader = json.loads(r.text)["leader"]
                        return True
                except:
                    pass
        self.be_leader()
        return len(self.peer_list) > 0

    def be_leader(self):
        self.leader = {"host": self.info['host'], "port": self.info['port'], "public_key": self.public_key,
                       "term": self.info['term']}
        self.character = "leader"
        peer_list_copy = self.peer_list.copy()
        for node in peer_list_copy:
            self.current_term = max(self.current_term, node["term"] + 1)
            if node["host"] == self.info["host"] and node["port"] == self.info["port"]:
                self.peer_list.remove(node)
                continue
            url = "http://{host}:{port}/election".format(**node)
            message = json.dumps({
                "code": 2,
                "leader": self.leader
            })
            try:
                r = requests.post(url=url, data=message,
                                  headers={'Content-type': 'application/json', 'Accept': 'text/plain'})
                if r.status_code == 200 and json.loads(r.text)["code"] == 1:
                    pass
                else:
                    raise Exception
            except:
                self.peer_list.remove(node)

    # 选举
    # 接收到的term小于等于自己，就认可
    def voting(self, peer):
        if peer['term'] <= self.info['term']:
            self.leader = peer

    def sign_transaction(self, transaction):
        if "message" in transaction:
            transaction["from"] = self.public_key
            transaction["signature"] = hashTool.sign(self.private_key, transaction["message"].encode())
            transaction["hash"] = sha256(
                bytes.fromhex(transaction["from"]) + transaction[
                    "message"].encode() + transaction["signature"].encode()).hexdigest()
            return transaction
        else:
            return None

    # 生成区块
    # data: transaction 构成的 array
    def generate_block(self):
        if len(self.chain):
            # 当前链长度不为零，则读取最新块的数据
            latest_block = self.chain[-1]
        else:
            # 当前链长为0，表示新建节点，初始化创世区块
            latest_block = {
                "index": -1,
                "block_hash": "",
            }
            transaction = {
                "message": "genesis block"
            }
            self.transaction_pool.append(self.sign_transaction(transaction))

        # 当前交易池中没有数据，则填充null
        if len(self.transaction_pool) == 0:
            transaction = {
                "message": "NULL"
            }
            self.transaction_pool.append(self.sign_transaction(transaction))

        # 区块头信息：index timestamp previous_hash merkle_root，用这些计算hash
        index = latest_block['index'] + 1
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        previous_hash = latest_block["block_hash"]
        merkle_tree = hashTool.merkel_tree(self.transaction_pool)
        merkle_root = merkle_tree["hash"]
        block_msg = str(index) + timestamp + previous_hash + merkle_root
        r, s, block_hash = hashTool.chameleon_hash(
            hashTool.chameleon_deserialize(self.chameleon["g"]),
            hashTool.chameleon_deserialize(self.chameleon["y"]),
            block_msg)
        # 组成区块
        block = {
            "index": index,
            "timestamp": timestamp,
            "previous_hash": previous_hash,
            "merkle_root": merkle_root,
            "merkle_tree": merkle_tree,
            "block_hash": hashTool.chameleon_serialize(block_hash),
            "r": hashTool.chameleon_serialize(r),
            "s": hashTool.chameleon_serialize(s)
        }
        self.transaction_pool = []
        return block

    # 将生成的区块链广播出去
    def broadcast_block(self, block):
        # 验证区块
        if len(self.chain) == 0 or block["previous_hash"] == self.chain[-1]["block_hash"]:
            self.chain.append(block)
        self.save_chain_data()
        for peer in self.peer_list:
            url = "http://{host}:{port}/block".format(**peer)
            message = json.dumps({
                "code": 4,
                "block": block
            })
            r = requests.post(url=url, data=message,
                              headers={'Content-type': 'application/json', 'Accept': 'text/plain'})
        return True

    # 同步区块
    def sync_block(self):
        if len(self.chain):
            latest_hash = self.chain[-1]["block_hash"]
        else:
            latest_hash = "Empty"
        url = "http://{host}:{port}/block".format(**self.leader)
        try:
            r = requests.get(url=url, params={"block_hash": latest_hash})
            if r.status_code == 200:
                info = json.loads(r.text)
                if info["status"] == "OK":
                    self.chain.extend(info["blocks"])
                elif info["status"] == "Error":
                    self.chain = info["blocks"]
                self.save_chain_data()
        except:
            pass

    # 发送区块
    # latest_hash 对方拥有的最新块的哈希
    # 如果返回值为[]说明对方同步到最新了
    # 否则返回剩余所有区块
    # 如果查不到，返回 False
    def send_block(self, latest_hash):
        if latest_hash:
            for i in range(0, len(self.chain)):
                if self.chain[i]["block_hash"] == latest_hash:
                    return self.chain[i + 1:]
            return False
        else:
            return self.chain

    # 接收区块
    def recv_block(self, block):
        # 区块头验证
        block_msg = str(block['index']) + block["timestamp"] + block["previous_hash"] + block[
            "merkle_root"]
        block_hash = hashTool.chameleon_verify(g=hashTool.chameleon_deserialize(self.chameleon["g"]),
                                               y=hashTool.chameleon_deserialize(self.chameleon["y"]),
                                               msg=block_msg,
                                               r=hashTool.chameleon_deserialize(block["r"]),
                                               s=hashTool.chameleon_deserialize(block["s"]))
        # 当区块头验证成功
        if hashTool.chameleon_serialize(block_hash) == block["block_hash"]:
            # 先看是否是最新区块
            if block["previous_hash"] == self.chain[-1]["block_hash"]:
                self.chain.append(block)
                return True
            else:
                # 如果新区块接续不上，查找是否是修改后的区块
                for blk in self.chain:
                    if blk["block_hash"] == block["block_hash"]:
                        # 更新区块信息：
                        for key in block:
                            blk[key] = block[key]
                        return True
                # 如果不是更新的区块，则触发同步
                self.sync_block()
                return True
        else:
            # 如果区块头验证失败，直接返回False
            return False

    # 修改区块中的交易
    # msg: {"block": "xxx(block_hash)", "transaction": "xxx(transaction_hash)"}
    def revoke_from_block(self, msg):
        # 如果自己不是leader，则转发给leader处理
        if self.character != "leader":
            data = {"code": 6, "action": "REVOKE", "msg": msg}
            url = "http://{host}:{port}/block".format(**self.leader)
            requests.post(url=url, data=json.dumps(data),
                              headers={'Content-type': 'application/json', 'Accept': 'text/plain'})
        else:
            block_hash = msg["block_hash"]
            transaction_hash = msg["transaction_hash"]
            # 在链上查询要修改的块
            for block in self.chain:
                # 找到对应的块
                if block['block_hash'] == block_hash:
                    # 查询具体交易并修改
                    status, new_tree = self.revoke_transaction(block["merkle_tree"], transaction_hash)
                    if status:
                        block["merkle_tree"] = new_tree
                        block["merkle_root"] = new_tree["hash"]
                        # 重新计算hash
                        index = block["index"]
                        timestamp = block["timestamp"]
                        previous_hash = block["previous_hash"]
                        merkle_root = block["merkle_root"]
                        block_msg = str(index) + timestamp + previous_hash + merkle_root
                        r, s = hashTool.chameleon_adjust(
                            hashTool.chameleon_deserialize(self.chameleon["g"]),
                            hashTool.chameleon_deserialize(self.chameleon["x"]),
                            block_msg,
                            hashTool.chameleon_deserialize(block["block_hash"]))
                        # 更新区块中的r和s值
                        block["r"] = hashTool.chameleon_serialize(r)
                        block["s"] = hashTool.chameleon_serialize(s)
                        # 插入更新区块的交易
                        info = {
                            "index": block["index"],
                            "new_r": block["r"],
                            "new_s": block["s"],
                            "new_MH_root": block["merkle_root"]
                        }
                        update_transaction = {"message": json.dumps(info)}
                        self.transaction_pool.append(self.sign_transaction(update_transaction))
                        # 将修改后的区块广播出去
                        self.broadcast_block(block)
                        return True
            return False

    # 查询具体交易并且进行撤销操作
    # merkle_tree (list): 待修改区块中的 merkle tree
    # tran_hash (string): 需要撤销的交易的哈希值
    # 返回值  (bool, list): 返回执行是否成功，以及重构后的 merkle tree
    def revoke_transaction(self, merkle_tree, tran_hash):
        tmp_transaction_list = []
        hashTool.from_merkel_to_list(merkle_tree, tmp_transaction_list)
        copy_list = tmp_transaction_list.copy()
        for i in range(len(copy_list)):
            # 找到具体交易
            if copy_list[i]["hash"] == tran_hash:
                # 操作：将找到的交易直接删除
                tmp_transaction_list.remove(copy_list[i])
        # 尝试重构 merkle tree
        # 如果当前交易数不为0，则进行树结构的重构
        if len(tmp_transaction_list):
            # 检查是否真的删除了某条交易，如果没有变化则说明提供的撤销信息有误
            if copy_list == tmp_transaction_list:
                return False, merkle_tree
            # 否则尝试对删除后的交易池重构
            else:
                try:
                    return True, hashTool.merkel_tree(tmp_transaction_list)
                except:
                    # 如果重构失败，则返回空
                    return False, []
        # 如果撤销之后交易数为0，为了保持区块结构，添加一个 NULL 交易补充
        else:
            return True, hashTool.merkel_tree([self.sign_transaction({"message": "NULL"})])

    # 验证交易签名
    def verify_transaction(self, transaction):
        try:
            t_from = transaction["from"]
            t_message = transaction["message"]
            t_signature = transaction["signature"]
            t_hash = transaction["hash"]
            # 验证哈希
            current_hash = sha256(
                bytes.fromhex(t_from) + t_message.encode() + t_signature.encode()).hexdigest()
            if t_hash != current_hash:
                # 哈希验证失败
                return False
            # 验证签名
            if hashTool.validate_signature(public_key=t_from, signature=t_signature, message=t_message.encode()):
                return True
            else:
                return False
        except KeyError:
            return False

    # 将交易缓存在本地交易池
    def add_transaction(self, transaction):
        # 如果自己不是leader节点，则将数据发送给leader处理
        if self.character != 'leader':
            url = "http://{host}:{port}/transaction".format(**self.leader)
            r = requests.post(url=url, data=json.dumps({"code": 3, "transaction": transaction}),
                              headers={'Content-type': 'application/json', 'Accept': 'text/plain'})
            if r.status_code == 200 and json.loads(r.text)["code"] == 1:
                return True
            return False
        elif self.verify_transaction(transaction):
            self.transaction_pool.append(transaction)
            # 触发生成新区块
            if len(self.transaction_pool) >= self.max_transactions:
                new_block = self.generate_block()
                self.broadcast_block(new_block)
            return True
        else:
            return False
