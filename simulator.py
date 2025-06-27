import os
import json
import time
import random
from datetime import datetime
import threading
from asn.utils.logger import get_logger
from asn.utils.time import *
from asn.env.environment import Environment, User, Message
from asn.agent.agent import Agent, LLMAgent, NaiveAgent
from asn.agent.action import Act
from asn.data.data import Data
from langchain_core.utils import mock_now
from concurrent.futures import ThreadPoolExecutor


class Simulator:
    def __init__(self, conf):
        self.conf = conf
        self.data = Data.load_from_data(conf["data_path"])
        self.data.make_history(time_begin=conf["time_init_begin"], time_end=conf["time_init_end"])

        if "load_model" in conf and conf["load_model"]:
            # 从checkpoint加载系统
            # Load model
            get_logger().info(f"Loading model from {conf['load_model']}")
            with open(conf["load_model"], "r") as f:
                model_dict = json.load(f)
                self.env = Environment.load_from_dict(model_dict["env"])
            get_logger().info("Model loaded.")
            print("Model loaded.")
        else:
            # 初始化系统
            self.env = Environment()
            # initialize environment
            self.init_env_from_data(self.env, self.data)
            self.env.update_time(str_to_datetime(conf["time_sim_begin"]), conf["interval"])
            print("Get users' profile...")
            self.get_users_profile(self.env, self.data, conf["time_init_begin"], conf["time_init_end"], conf["time_intv"], conf["parallel"])
            self.data.save_data(conf["data_path"])
            print("Replaying history...")
            self.replay_history(self.env, self.data, conf["time_init_begin"], conf["time_init_end"], conf["time_intv"], conf["parallel"])
            self.data.save_data(conf["data_path"])
            print("Environment initialized.")
            # Save initialized model
            save_path = conf["save_path"] + "/model_init"
            if not os.path.exists(save_path):
                os.makedirs(save_path)
            with open(os.path.join(save_path, f"model.json"), "w") as f:
                model_dict = {
                    "env": self.env.save_to_dict(save_path),
                }
                json.dump(model_dict, f, indent=4)
            get_logger().info(f"Model initialized and saved to {save_path}")
            print(f"Model initialized and saved to {save_path}")


    # Initialize enviroment from data
    def init_env_from_data(self, env: Environment, data: Data):
        get_logger().info("Initializing environment...")
        get_logger().info("Users registering...")
        for user in data.users:
            agent = LLMAgent(user["info"])
            user = User(id=user["id"], info=user["info"], agent=agent, mastodon_info=data.get_meta_or_default(user["id"], 'mastodon_info'), following=user["following"], followers=user["followers"])
            env.add_user(user)
        get_logger().info("Users registered.")
        for msg in data.posts[-200:]:
            with env.lock_message:
                message = Message(id=str(len(env.messages)), type="post", text=msg["text"], author_id=msg["author_id"], timestamp=datetime.strptime(msg["timestamp"], TIME_FORMAT))
                env.add_message(message)
        get_logger().info("Environment initialized.")


    # 根据历史记录，重演agent行为，初始化agent的memory模块
    def replay_history(self, env: Environment, data: Data, time_begin: str, time_end: str, interval: str, parallel=True):
        # Replay user's history
        def replay_user_history(user: User):
            replay_batch_size = 20
            time_step = time_begin
            while(time_step < time_end):
                hist_step = data.get_history_by_time(user.id, time_step, add_interval(time_step, interval))
                if len(hist_step) > 0:
                    acts_step = []
                    for i in range(len(hist_step) // replay_batch_size + 1):
                        acts = []
                        for act in hist_step[i * replay_batch_size: (i + 1) * replay_batch_size]:
                            act = Act(act["type"], act["text"], datetime.strptime(act["timestamp"], TIME_FORMAT))
                            acts.append(act)
                        if acts:
                            user.agent.replay_batch(acts, act.timestamp)
                        acts_step.extend(acts)
                    user.agent.memory.daily_reflect(acts_step, datetime.strptime(hist_step[-1]["timestamp"], TIME_FORMAT))
                time_step = add_interval(time_step, interval)

        def replay_message_history():
            pid2mid = {} # 原post_id到新message_id的映射
            time_step = time_begin
            while time_step < time_end:
                hist_step = []
                for user in env.users:
                    hist_step.extend(data.get_history_by_time(user.id, time_step, add_interval(time_step, interval)))
                hist_step = sorted(hist_step, key=lambda x: x["timestamp"])
                for hist in hist_step:
                    user = env.id2user[hist["user_id"]]
                    if hist["type"] == "post":
                        with env.lock_message:
                            message = Message(id=str(len(env.messages)), type="post", text=hist["text"], author_id=user.id, timestamp=datetime.strptime(hist["timestamp"], TIME_FORMAT))
                            env.add_message(message)
                            pid2mid[hist["post_id"]] = message.id
                            user.post(message.id)
                            env.log_act(user, message, Act("post", message.text, datetime.strptime(hist["timestamp"], TIME_FORMAT)), use_act_time=True)
                    elif hist["type"] == "retweet" or hist["type"] == "repost":
                        with env.lock_message:
                            quote_id = hist["quote_id"] if hist["quote_id"] != -1 else None
                            if quote_id and quote_id in pid2mid:    # 转发的是已有的消息
                                quote_id = quote_id = env.id2message[pid2mid[hist["quote_id"]]].origin_id()
                                message = Message(id=str(len(env.messages)), type="repost", text=hist["text"], author_id=user.id, timestamp=datetime.strptime(hist["timestamp"], TIME_FORMAT), quote_id=quote_id)
                                env.add_message(message)
                                pid2mid[hist["post_id"]] = message.id
                                env.id2message[quote_id].reposted_by.append((user.id, hist["timestamp"]))
                                user.repost(message.origin_id())
                                env.log_act(user, message, Act("repost", message.text, datetime.strptime(hist["timestamp"], TIME_FORMAT)), use_act_time=True)
                            else:   # 转发的消息不存在于系统之中，则视为发帖
                                message = Message(id=str(len(env.messages)), type="post", text=hist["text"], author_id=user.id, timestamp=datetime.strptime(hist["timestamp"], TIME_FORMAT))
                                env.add_message(message)
                                pid2mid[hist["post_id"]] = message.id
                                user.post(message.id)
                                env.log_act(user, message, Act("post", message.text, datetime.strptime(hist["timestamp"], TIME_FORMAT)), use_act_time=True)
                    elif hist["type"] == "like":
                        with env.lock_message:
                            if hist["post_id"] in pid2mid:  # 只处理存在于系统之中的消息
                                msg = env.id2message[env.id2message[pid2mid[hist["post_id"]]].origin_id()]
                                msg.liked_by.append((user.id, hist["timestamp"]))
                                user.like(msg.origin_id())
                                env.log_act(user, msg, Act("like", msg.text, datetime.strptime(hist["timestamp"], TIME_FORMAT)), use_act_time=True)
                time_step = add_interval(time_step, interval)

        get_logger().info("Replaying history...")
        replay_message_history()
        if parallel:
            threads = []
            for user in env.users:
                t = threading.Thread(target=replay_user_history, args=(user, ))
                threads.append(t)
                t.start()
            for t in threads:
                t.join()
        else:
            for user in env.users:
                replay_user_history(user)
        get_logger().info("History replayed.")


    # 初始化每个用户的profile
    def get_users_profile(self, env: Environment, data: Data, time_begin: str, time_end: str, interval: str, parallel=True):
        def get_user_profile(user: User):
            # 从文件中加载有一个问题：当修改了config中的信息，比如time_begin,time_end时，原来的profile可能会失效！！！
            if data.get_meta_or_default(user.id, "user_profile"):
                user.agent.profile.characteristics = data.get_meta(user.id, "user_profile")
            else:
                user.agent.get_profile(data.get_history_by_time(user.id, time_begin, time_end), time_begin, time_end, interval)
                data.set_meta(user.id, "user_profile", user.agent.profile.characteristics)

        get_logger().info("Getting user profile...")
        if parallel:
            threads = []
            for user in env.users:
                t = threading.Thread(target=get_user_profile, args=(user,))
                threads.append(t)
                t.start()
            for t in threads:
                t.join()
        else:
            for user in env.users:
                get_user_profile(user)
        get_logger().info("User profile got.")


    def simulate_user(self, user: User, env: Environment, data: Data, conf: dict):
        # Step 1：为用户分发消息
        msgs = env.distribute_messages_for_user_by_time(user, str_to_datetime(sub_interval(datetime_to_str(env.now), conf["time_intv"])), env.now)
        get_logger().info(f"User {user.id} read {len(msgs)} messages at {env.now}. Messages from {sub_interval(datetime_to_str(env.now), conf['time_intv'])} to {env.now}")
        # Step 2：用户对消息做出反应
        if conf["react_strategy"] == "one": # 一次对一条消息做出反应
            for msg in msgs:
                acts = user.read_post(msg.text, env.now)
            for act in acts:
                if act.type == "like":
                    user.like(msg.origin_id())
                if act.type == "retweet" or act.type == "repost":
                    user.repost(msg.origin_id())
                if act.type == "retweet" or act.type == "repost":
                    with env.lock_message:
                        env.id2message[msg.origin_id()].reposted_by.append((user.id, datetime_to_str(env.now)))
                        message = Message(id=str(len(env.messages)), type="repost", text=msg.text, author_id=user.id, timestamp=env.now, quote_id=msg.origin_id())
                        env.add_message(message)
                if act.type == "like":
                    with env.lock_message:
                        env.id2message[msg.origin_id()].liked_by.append((user.id, datetime_to_str(env.now)))
                env.log_act(user, msg, act)
        elif conf["react_strategy"] == "batch": # 批量对消息做出反应，兼顾效率和准确性
            actss = user.read_posts([msg.text for msg in msgs], env.now)
            for i, msg in enumerate(msgs):
                for act in actss[i]:
                    if act.type == "like":
                        user.like(msg.origin_id())
                    if act.type == "retweet" or act.type == "repost":
                        user.repost(msg.origin_id())
                    if act.type == "retweet" or act.type == "repost":
                        with env.lock_message:
                            env.id2message[msg.origin_id()].reposted_by.append((user.id, datetime_to_str(env.now)))
                            message = Message(id=str(len(env.messages)), type="repost", text=msg.text, author_id=user.id, timestamp=env.now, quote_id=msg.origin_id())
                            env.add_message(message)
                    if act.type == "like":
                        with env.lock_message:
                            env.id2message[msg.origin_id()].liked_by.append((user.id, datetime_to_str(env.now)))
                    env.log_act(user, msg, act)
        # Step 3：用户发布新内容
        previous_posts = [hist["text"] for hist in data.get_history_by_time(user.id, time_end=conf["time_init_end"]) if hist["type"] == "post"][-3:]
        acts = user.agent.generate(env.now, previous_posts=previous_posts)
        for act in acts:
            with env.lock_message:
                message = Message(id=str(len(env.messages)), type="post", text=act.text, author_id=user.id, timestamp=env.now)
                env.add_message(message)
                user.post(message.id)
                env.log_act(user, message, act)
                get_logger().info(f"User {user.id} post: {act.text} at {env.now}")


    def simulate_step(self, time_step):
        # 如果是一天的开始，则进行planning
        if time_step[-8:] == "00:00:00":
            with ThreadPoolExecutor(max_workers=self.conf["max_workers"]) as executor:
                for user in self.env.users:
                    # user.agent.make_plan(self.env.now)
                    executor.submit(user.agent.make_plan, self.env.now)
        with ThreadPoolExecutor(max_workers=self.conf["max_workers"]) as executor:
            for user in self.env.users:
                # 检查time_step是否在agent.plan活跃时间范围内
                for intv in user.agent.plan.plan:
                    if user.agent.plan.within_intv(intv, time_step):
                        get_logger().info(f"User {user.id} is active at {time_step}. Plan: {intv} in {user.agent.plan.plan}")
                        # self.simulate_user(user, self.env, self.data, self.conf)
                        executor.submit(self.simulate_user, user, self.env, self.data, self.conf)
                        break


    def simulate(self):
        intv = self.conf["interval"]
        time_step = self.env.now.strftime(TIME_FORMAT)
        time_end = self.conf["time_sim_end"]
        while time_step < time_end:
            get_logger().info(f"Simulating at {time_step}.")
            print(f"Simulating at {time_step}.")
            with mock_now(self.env.now):
                self.simulate_step(time_step)
            # 更新环境时间
            time_step = add_interval(time_step, intv)
            self.env.update_time(str_to_datetime(time_step), intv)
            # 如果是一天的开始，则保存模型
            if time_step[-8:] == "00:00:00":
                # Save model
                get_logger().info(f"Saving models...")
                save_path = conf["save_path"] + f"/model_{self.env.now.strftime(TIME_FORMAT)}/".replace(" ", "_")
                if not os.path.exists(save_path):
                    os.makedirs(save_path)
                with open(os.path.join(save_path, f"model.json".replace(" ", "_")), "w") as f:
                    model_dict = {
                        "env": self.env.save_to_dict(save_path),
                    }
                    json.dump(model_dict, f, indent=4)
                get_logger().info(f"Model saved to {save_path}")


if __name__ == "__main__":
    import yaml
    import argparse
    import numpy as np
    from asn.llm.llm import LLMManager
    from asn.utils.logger import get_logger, set_logger
    
    # Initialize settings
    set_logger()
    args = argparse.ArgumentParser()
    args.add_argument("--config_path", "-c", type=str, default="config/example.yaml")
    args = args.parse_args()
    conf_path = args.config_path
    with open(conf_path, "r") as f:
        conf = yaml.load(f, Loader=yaml.FullLoader)
    for key, value in args.__dict__.items():
        conf[key] = value

    # Print settings
    settings = "Settings:\n"
    for key, value in conf.items():
        settings += f"{key}: {value}\n"
    get_logger().info(settings)
    get_logger().debug(settings)
    print(settings)

    # Random seed
    if "seed" in conf:
        seed = conf["seed"]
    else:
        seed = 0
    random.seed(conf["seed"])
    np.random.seed(conf["seed"])

    # Set LLMManager
    LLMManager.set_manager(conf["llm"])

    # Simulation
    simulator = Simulator(conf)
    simulator.simulate()
