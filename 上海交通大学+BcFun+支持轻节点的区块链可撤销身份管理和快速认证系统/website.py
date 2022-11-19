from flask import Flask, jsonify, render_template, request, redirect, url_for
from blockchain import BlockChain
from daemon import BcDaemon
import json
from argparse import ArgumentParser
import time

app = Flask(__name__)

bc_init = False


@app.route('/init', methods=['POST', 'GET'])
def init():
    global bc_init
    if not bc_init:
        if request.method == "GET":
            return render_template('init.html')
        if request.method == "POST":
            if request.form.get('genesis'):
                bc_init = bc.init()
                if bc_init:
                    th.start()
                    return redirect(url_for('home'))
                else:
                    return redirect(url_for('init'))
            elif request.form.get('host') and request.form.get('port'):
                bc_init = bc.init({"host": request.form.get('host'), "port": request.form.get('port')})
                if bc_init:
                    th.start()
                    return redirect(url_for('home'))
                else:
                    return redirect(url_for('init'))
            return render_template('init.html')
    return redirect(url_for('home'))


@app.route('/', methods=['POST', 'GET'])
def home():
    global bc_init
    if bc_init:
        return render_template('index.html', peers=bc.peer_list, leader=bc.leader, character=bc.character,
                               selfinfo=bc.info, blocks=bc.chain, transactions=bc.transaction_pool, chameleoninfo=bc.chameleon)
    else:
        return redirect(url_for('init'))


@app.route('/gossip', methods=["POST"])
def gossip():
    global bc_init
    if not bc_init:
        return redirect(url_for('init'))

    # 解析收到的消息
    msg_recv = json.loads(request.get_data())

    message = {
        "status": "OK",
        "character": bc.character,
        "peers": bc.peer_list,
        "peer_info": bc.info,
        "leader": bc.leader,
        "current_term": -1
    }

    if msg_recv["code"] == 1:
        if "data" in msg_recv:
            peer_info = msg_recv["data"]
            if "host" in peer_info and "port" in peer_info:
                if "term" in peer_info and peer_info["term"] > 0:
                    bc.add_peer(peer_info)
                elif bc.character == "leader":
                    peer_info["term"] = bc.current_term
                    bc.add_peer(peer_info)
                    message["current_term"] = bc.current_term
                    bc.current_term += 1
        return json.dumps(message)
    else:
        return json.dumps({"status": "OK", "message": "Error request", "code": 1})


@app.route('/block', methods=["GET", "POST"])
def block():
    if request.method == "GET":
        latest_hash = request.args.get("block_hash")
        if latest_hash == "Empty":
            blocks = bc.chain
        else:
            blocks = bc.send_block(latest_hash)
        if blocks:
            return json.dumps({"status": "OK", "blocks": blocks})
        else:
            return json.dumps({"status": "Error", "blocks": bc.chain})
    if request.method == "POST":
        try:
            msg_recv = json.loads(request.get_data())
            if msg_recv["code"] == 4:
                bc.recv_block(msg_recv["block"])
                return json.dumps({"status": "OK", "message": "Block RECV Success", "code": 1})
            elif msg_recv["code"] == 6:
                if msg_recv["action"] == "REVOKE":
                    bc.revoke_from_block(msg_recv["msg"])
                    return json.dumps({"status": "OK", "message": "Block REVOKE Success", "code": 1})
            else:
                return json.dumps({"status": "OK", "message": "Code error", "code": 0})
        except json.decoder.JSONDecodeError:
            return json.dumps({"status": "OK", "message": "Request error", "code": 0})
        except KeyError:
            return json.dumps({"status": "OK", "message": "Parameters error", "code": 0})


@app.route('/transaction', methods=["POST"])
def transaction():
    if request.method == "POST":
        try:
            msg_recv = json.loads(request.get_data())
            if msg_recv["code"] == 3:
                if "transaction" in msg_recv:
                    r_transaction = msg_recv["transaction"]
                    if bc.add_transaction(r_transaction):
                        return json.dumps({"status": "OK", "message": "Success", "code": 1})
                    else:
                        return json.dumps({"status": "OK", "message": "Transaction error", "code": 0})
                else:
                    return json.dumps({"status": "OK", "message": "Data missing", "code": 0})
            else:
                return json.dumps({"status": "OK", "message": "Code error", "code": 0})
        except json.decoder.JSONDecodeError:
            return json.dumps({"status": "OK", "message": "Request error", "code": 0})
        except KeyError:
            return json.dumps({"status": "OK", "message": "Parameters error", "code": 0})


# 接收用户提交的信息
@app.route('/transaction/add', methods=["GET", "POST"])
def add():
    if request.method == "POST":
        t_from = request.form.get("from")
        t_message = request.form.get("message")
        t_signature = request.form.get("signature")
        t_hash = request.form.get("hash")
        t = {
            "from": t_from,
            "message": t_message,
            "signature": t_signature,
            "hash": t_hash
        }
        if bc.add_transaction(t):
            return json.dumps({"status": "OK", "message": "Success", "code": 1})
        else:
            return json.dumps({"status": "OK", "message": "Transaction error", "code": 0})


@app.route('/daemon', methods=["POST"])
def daemon():
    msg_recv = json.loads(request.get_data())
    if msg_recv["code"] == 6:
        if "leader" in msg_recv:  # Leader_daemon发来的消息
            if msg_recv["leader"] == bc.leader:
                bc.peer_list = msg_recv["peers"]
                return json.dumps({"status": "OK", "message": "Success", "code": 1})
            else:
                return json.dumps({"status": "OK", "message": "Leader error", "code": 0})
        else:  # follower_daemon发来的消息
            if bc.character == "leader" and msg_recv["info"] in bc.peer_list:
                th.set_sync_time(time.time(), msg_recv["info"]["term"])  # 更新同步时间
                return json.dumps({"status": "OK", "message": "Success", "peers": bc.peer_list, "code": 1})
            else:
                return json.dumps({"status": "OK", "message": "Leader error", "leader": bc.leader, "code": 0})
    else:
        return json.dumps({"status": "OK", "message": "Code error", "code": 0})


@app.route('/election', methods=["POST"])
def election():
    msg_recv = json.loads(request.get_data())
    if msg_recv["code"] == 2:
        if "leader" in msg_recv:  # 新leader发来
            if bc.character == "leader" or bc.test_connection(bc.leader, 2):
                return json.dumps({"status": "OK", "message": "Leader connect well", "code": 0})
            else:
                bc.leader = msg_recv["leader"]
                return json.dumps({"status": "OK", "message": "Success", "code": 1})
        else:
            if bc.test_connection(bc.leader, 2):
                return json.dumps({"status": "OK", "message": "Leader connect well", "code": 0})
            else:
                bc.be_leader()
                return json.dumps({"status": "OK", "message": "Success", "leader": bc.leader, "code": 1})
    else:
        return json.dumps({"status": "OK", "message": "Code error", "code": 0})


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('-a', '--address', help='host address')
    parser.add_argument('-p', '--port', help='port')
    parser.add_argument('-t', '--test', action="store_const", const="True",
                        help='run as random identity and do not store chian data in file')
    args = parser.parse_args()

    try:
        config = json.load(open('./config.json'))
    except FileNotFoundError:
        config = {"host": "127.0.0.1", "port": 8080}
        if not args.test:
            json.dump(config, open("./config.json", "w"))

    host = args.address if args.address else config['host']
    port = args.port if args.port else config['port']
    test_mode = args.test if args.test else False

    # max_transactions 可设置为4，以方便测试。
    bc = BlockChain(host=host, port=port, test_mode=test_mode, max_transactions=4)
    th = BcDaemon(bc=bc)
    th.daemon = True
    app.run(debug=True, host=host, port=port)
