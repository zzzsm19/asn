import json
import copy
import random
from datetime import datetime
from asn.utils.time import *

def check_time(time_str_or_datetime):
    if isinstance(time_str_or_datetime, str):
        try:
            time_str_or_datetime = datetime.strptime(time_str_or_datetime, TIME_FORMAT)
        except:
            raise ValueError("Time format error: %s" % time_str_or_datetime)
    elif not isinstance(time_str_or_datetime, datetime):
        raise ValueError("Error: time_begin should be str or datetime")
    return time_str_or_datetime

class Data:
    """
        user attributes: id(str), info, posts, likes, following, followers
        post attributes: id(str), author_id, quote_id, timestamp, text, type
        meta attributes: other attributes such as history, etc.
    """
    def __init__(self, users, posts):
        self.users = users
        self.posts = sorted(posts, key=lambda x: x["timestamp"])
        self.id2user = {user["id"]: user for user in users}
        self.id2post = {post["id"]: post for post in posts}
        self.meta = {}

    def save_data(self, data_path):
        with open(data_path, "w") as f:
            json.dump({
                "users": self.users,
                "posts": self.posts,
                "meta": self.meta
            }, f, indent=4)

    @classmethod
    def load_from_data(cls, data_path):
        with open(data_path, "r") as f:
            data_dict = json.load(f)
        data = Data(data_dict["users"], data_dict["posts"])
        data.meta = data_dict["meta"]
        return data

    def get_user(self, user_id):
        if user_id not in self.id2user:
            raise ValueError("User id not found: %s" % user_id)
        return self.id2user[user_id]
    
    def get_post(self, post_id):
        if post_id not in self.id2post:
            raise ValueError("Post id not found: %s" % post_id)
        return self.id2post[post_id]
    
    def get_user_posts_ids(self, user_id):
        return self.get_user(user_id)["posts"]
    
    def get_user_likes_ids(self, user_id):
        return self.get_user(user_id)["likes"]
    
    def get_user_following_ids(self, user_id):
        return self.get_user(user_id)["following"]
    
    def get_user_followers_ids(self, user_id):
        return self.get_user(user_id)["followers"]
    
    def filter_by_time(self, time_begin=TIME_STR_MIN, time_end=TIME_STR_MAX):
        time_begin = check_time(time_begin).strftime(TIME_FORMAT)
        time_end = check_time(time_end).strftime(TIME_FORMAT)
        
        posts = copy.deepcopy(self.posts)
        users = copy.deepcopy(self.users)
        posts = [post for post in posts if time_begin <= str(post["timestamp"]) < time_end]
        set_pid = set([post["id"] for post in posts])
        for user in users:
            user["posts"] = [post for post in user["posts"] if post in set_pid]
            user["likes"] = [like for like in user["likes"] if like in set_pid]
        return Data(users, posts)
    
    def make_history(self, time_begin=TIME_STR_MIN, time_end=TIME_STR_MAX):
        """
        Make history for each user
        """
        history = {user_id: [] for user_id in self.id2user.keys()}
        # Construct user history
        for user in self.users:
            for pid in user["posts"]:
                post = self.get_post(pid)
                if post["timestamp"] < time_begin or post["timestamp"] >= time_end:
                    continue
                if post["type"] == "post":
                    history[user["id"]].append({"user_id": user["id"], "type": "post", "post_id": post["id"], "text": post["text"], "timestamp": post["timestamp"]})
                elif post["type"] == "retweet" or post["type"] == "repost":
                    history[user["id"]].append({"user_id": user["id"], "type": "repost", "post_id": post["id"], "text": post["text"], "timestamp": post["timestamp"], "quote_id": post["quote_id"]})
            for lid in user["likes"]:
                like = self.get_post(lid)
                if like["timestamp"] < time_begin or like["timestamp"] >= time_end:
                    continue
                history[user["id"]].append({"user_id": user["id"], "type": "like", "post_id": like["id"], "text": like["text"], "timestamp": like["timestamp"]})
            history[user["id"]] = sorted(history[user["id"]], key=lambda x: x["timestamp"])
            self.meta["history"] = history
        for user in self.users:
            print("User %s has %d behaviors" % (user["id"], len(history[user["id"]])))

    def get_history_by_time(self, id: str, time_begin=TIME_STR_MIN, time_end=TIME_STR_MAX):
        time_begin = check_time(time_begin).strftime(TIME_FORMAT)
        time_end = check_time(time_end).strftime(TIME_FORMAT)
        history_user = self.meta["history"][id]
        history_user = [act for act in history_user if time_begin <= act["timestamp"] < time_end]
        return history_user
    
    def set_meta(self, uid, key, value):
        if key not in self.meta:
            self.meta[key] = {}
        self.meta[key][uid] = value

    def get_meta(self, uid, key):
        if key not in self.meta:
            raise ValueError("Key not found: %s" % key)
        if uid not in self.meta[key]:
            raise ValueError("User id of key %s not found: %s" % (key, uid))
        return self.meta[key][uid]

    def get_meta_or_default(self, uid, key, default_value=None):
        if key not in self.meta:
            return default_value
        if uid not in self.meta[key]:
            return default_value
        return self.meta[key][uid]
    
    def has_meta_key(self, key):
        print(f"Key {key} in meta({self.meta.keys()}): {key in self.meta}")
        return key in self.meta
        

class DataTransformerBluesky:
    """
    Load and process data for initial simulation and testing. Coupling with data.
    Data format:
    name.json
    """
    def __init__(self, data_path):
        self.data_path = data_path
        with open(self.data_path, "r") as f:
            data = json.load(f)
        self.data = data
    

    def transform_data(self, num_users: int, strategy: str, time_window) -> Data:
        """
        Transform data to the format of the simulator
        time_window example: "2024-02-01 00:00:00=2024-02-28 23:59:59" 用于统计时间窗口内用户活跃度
        """

        users, posts, edges = self.data["users"], self.data["posts"], self.data["edges"]
        print("Users: %d, Posts: %d, Edges: %d" % (len(users), len(posts), len(edges)))


        """
        Select core user for simulation
        筛选用户，策略：随机/选择活跃用户
        """
        if strategy == "random":
            # 策略：随机选择用户
            num_core = 0
            for user in users:
                if user["class"] == "content creator":
                    user["type"] = "core"
                    num_core += 1
                elif user["class"] == "active":
                    user["type"] = "non-core"
                elif user["class"] == "inactive":
                    user["type"] = "non-core"
                else:
                    user["type"] = "non-core"
                    print("User class error: %s" % user["class"])
            # 至少选1/10个核心用户
            if num_core >= num_users // 10:
                users = random.sample([user for user in users if user["type"] == "core"], num_users // 10) + random.sample([user for user in users if user["type"] != "core"], num_users - num_users // 10)
            else:
                users = [user for user in users if user["type"] == "core"] + random.sample([user for user in users if user["type"] != "core"], num_users - num_core)
            print("Content creator: %d, Active: %d, Inactive: %d" % (len([user for user in users if user["class"] == "content creator"]), len([user for user in users if user["class"] == "active"]), len([user for user in users if user["class"] == "inactive"])))
        elif strategy == "active":
            # 策略：选择活跃用户
            sampled_users = random.sample([user for user in users if user["class"] == "content creator"], num_users)
            if len(sampled_users) < num_users:
                sampled_users += random.sample([user for user in users if user["class"] == "active"], num_users - len(sampled_users))
            if len(sampled_users) < num_users:
                sampled_users += random.sample([user for user in users if user["class"] == "inactive"], num_users - len(sampled_users))
            users = sampled_users
            print("Content creator: %d, Active: %d, Inactive: %d" % (len([user for user in users if user["class"] == "content creator"]), len([user for user in users if user["class"] == "active"]), len([user for user in users if user["class"] == "inactive"])))
        elif strategy == "active_by_time":
            # 根据时间区间内发帖数量判断用户活跃程度，并选择活跃用户
            time_begin, time_end = time_window.split("=")
            user2num_posts_by_time = {}
            for post in posts:
                # post["date"]: 202402292310   time_begin, time_end: "2024-02-01 00:00:00", "2024-02-28 23:59:59"
                post_time = datetime.strptime(str(post["date"]), "%Y%m%d%H%M")
                if time_begin <= datetime_to_str(post_time) < time_end:
                    user2num_posts_by_time[post["user_id"]] = user2num_posts_by_time.get(post["user_id"], 0) + 1
            # 增加随机扰动
            for key in user2num_posts_by_time:
                user2num_posts_by_time[key] += random.randint(-2, 2)
            # 根据发帖数排序
            user2num_posts_by_time = sorted(user2num_posts_by_time.items(), key=lambda x: x[1], reverse=True)
            # 选择前num_users个用户
            user2num_posts_by_time = user2num_posts_by_time[:num_users]
            users = [user for user in users if user["user_id"] in [user[0] for user in user2num_posts_by_time]]
            print("Content creator: %d, Active: %d, Inactive: %d" % (len([user for user in users if user["class"] == "content creator"]), len([user for user in users if user["class"] == "active"]), len([user for user in users if user["class"] == "inactive"])))
        else:
            raise ValueError("Sampling strategy error: %s" % strategy)

        """
        Hash data idx and convert attributes name
        """
        uid2idx = {user["user_id"]: str(idx) for idx, user in enumerate(users)}
        pid2idx = {post["post_id"]: str(idx) for idx, post in enumerate(posts)}
        # User Keys: id, info, posts, likes, following, followers
        keys_origin_user = set()
        for user in users:
            user["id"] = uid2idx[user["user_id"]]
            del user["user_id"]
            user["posts"] = [pid2idx[post] for post in user["posts"] if post in pid2idx]
            user["likes"] = [pid2idx[like] for like in user["likes"] if like in pid2idx]
            user["following"] = [uid2idx[follow] for follow in user["following"] if follow in uid2idx and uid2idx[follow] != user["id"]]
            user["followers"] = [uid2idx[follow] for follow in user["followers"] if follow in uid2idx and uid2idx[follow] != user["id"]]
            keys_origin_user.update(user.keys())
        print("User keys: ", keys_origin_user)
        keys_new_user = ["id", "info", "posts", "likes", "following", "followers"]
        for user in users:
            user["info"] = {}
            for key in list(user.keys()):
                if key not in keys_new_user:
                    user["info"][key] = user[key]
                    del user[key]
        # Post Keys: id, author_id, quote_id, timestamp, text, type
        keys_origin_post = set()
        for post in posts:
            post["id"] = pid2idx[post["post_id"]]
            del post["post_id"]
            post["author_id"] = uid2idx[post["user_id"]] if post["user_id"] in uid2idx else str(-1)
            del post["user_id"]
            post["quote_id"] = pid2idx[post["quotes"]] if post["quotes"] is not None and post["quotes"] in pid2idx else str(-1)
            post["timestamp"] = datetime.strftime(datetime.strptime(str(post["date"]), "%Y%m%d%H%M"), TIME_FORMAT)
            del post["date"]
            post["text"] = post["text"]
            post["type"] = "post" if post["type"] == "post" else "repost"
            keys_origin_post.update(post.keys())
        print("Post keys: ", keys_origin_post)
        keys_new_post = ["id", "author_id", "quote_id", "timestamp", "text", "type"]
        for post in posts:
            post["info"] = {}
            for key in list(post.keys()):
                if key not in keys_new_post:
                    post["info"][key] = post[key]
                    del post[key]

        """
        Sort posts, likes by timestamp
        """
        for user in users:
            user["posts"] = sorted(user["posts"], key=lambda x: posts[int(x)]["timestamp"])
            user["likes"] = sorted(user["likes"], key=lambda x: posts[int(x)]["timestamp"])
        
        return Data(users, posts)
    

if __name__ == '__main__':
    import argparse
    import os
    import yaml
    parser = argparse.ArgumentParser()
    parser.add_argument('--config_path', '-c', type=str, default='config/example.yaml')
    parser.add_argument('--seed', '-s', type=int, default=0)
    args = parser.parse_args()

    # 筛选用户的随机种子
    seed = args.seed if args.seed else random.randint(0, 1000000)
    random.seed(seed)
    print(f"Random seed: {seed}")

    # 加载config
    conf_path = args.config_path
    with open(conf_path, "r") as f:
        conf = yaml.load(f, Loader=yaml.FullLoader)
    for key, value in args.__dict__.items():
        conf[key] = value

    data = DataTransformerBluesky(conf["data_path_raw"]).transform_data(conf["num_users"], conf["sampling_strategy"], time_window=conf["time_init_begin"]+ '=' + conf["time_init_end"])
    if not os.path.exists(os.path.dirname(conf["data_path"])):
        os.makedirs(os.path.dirname(conf["data_path"]))
    data.save_data(conf["data_path"])

    # save seed
    with open(conf["data_path"] + '.seed', 'w') as f:
        f.write(str(seed))