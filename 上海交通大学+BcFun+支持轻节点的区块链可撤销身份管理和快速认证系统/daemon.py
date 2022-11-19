import threading
import time
import random
import requests
import json
from blockchain import BlockChain


class BcDaemon(threading.Thread):
    def __init__(self, bc: BlockChain):
        super(BcDaemon, self).__init__()
        self.bc = bc
        self.sync_time = dict()

    # leader 的守护进程
    def leader_daemon(self):
        while True:
            time.sleep(random.random() + 6)
            # 更新leader的peer_list
            peer_list_copy = self.bc.peer_list.copy()
            for peer in peer_list_copy:
                if time.time() - self.sync_time.get(peer["term"], 0) <= 5:
                    continue
                else:
                    url = "http://{host}:{port}/daemon".format(**peer)
                    message = json.dumps({
                        "code": 6,
                        "leader": self.bc.leader,
                        "peers": peer_list_copy
                    })
                    try:
                        r = requests.post(url=url, data=message)
                        if r.status_code != 200 or json.loads(r.text)["message"] != "Success":
                            raise Exception
                        self.set_sync_time(time.time(), peer["term"])
                    except:
                        self.bc.peer_list.remove(peer)

    def follower_daemon(self):
        while True:
            time.sleep(random.random() * 5)
            url = "http://{host}:{port}/daemon".format(**self.bc.leader)
            message = json.dumps({
                "code": 6,
                "info": self.bc.info
            })
            try:
                r = requests.post(url=url, data=message)
                if r.status_code == 200:
                    if json.loads(r.text)["code"] == 1:
                        self.bc.peer_list = json.loads(r.text)["peers"].copy()
                    else:  # 如果leader信息有误，重新初始化
                        if json.loads(r.text)["leader"]["host"] == self.bc.info["host"] and \
                                json.loads(r.text)["leader"]["post"] == self.bc.info["post"]:
                            return  # 在主线程中自己的角色已经变为 leader
                        else:
                            self.bc.gossip(json.loads(r.text)["leader"])
                else:
                    raise Exception
            except:
                break

    def set_sync_time(self, new_time, term):
        self.sync_time[term] = new_time

    def run(self):
        while True:
            if self.bc.character == "leader":
                print("Being leader")
                self.leader_daemon()
            else:
                print("Being follower")
                self.follower_daemon()
                if self.bc.character == "follower" and not self.bc.election():
                    print("Offline")
                    return
