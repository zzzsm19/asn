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

# Get history for each user
def init_env_from_data(env: Environment, data: Data):
    get_logger().info("Initializing environment...")
    get_logger().info("Users registering...")
    for user in data.users:
        agent = LLMAgent(user["info"])
        user = User(id=user["id"], info=user["info"], agent=agent, mastodon_info=data.get_meta_or_default(user["id"], 'mastodon_info'), following=user["following"], followers=user["followers"])
        env.add_user(user)
    get_logger().info("Users registered.")
    get_logger().info("Environment initialized.")

# Replay user's history
def replay_user_history(data: Data, user: User, time_begin, time_end, interval):
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

# Get user profile
def get_user_profile(data: Data, user: User, time_begin, time_end, interval):
    if data.get_meta_or_default(user.id, "user_profile"):
        user.agent.profile.characteristics = data.get_meta(user.id, "user_profile")
        return user.agent.profile.characteristics
    else:
        profile = user.agent.get_profile(data.get_history_by_time(user.id, time_begin, time_end), time_begin, time_end, interval)
        data.set_meta(user.id, "user_profile", profile)
        return profile


# Replay users' history
def replay_history(env: Environment, data: Data, time_begin: str, time_end: str, interval: str, parallel=True):
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

# Get users' agent profile
def get_users_profile(env: Environment, data: Data, time_begin: str, time_end: str, interval: str, parallel=True):
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

# Replay user's history between split_time1 and split_time2
def replay_user_history_time(user: User, split_time1, split_time2, debug=False):
    if debug:
        return  # Skip replaying history
    if user.type == "non-core":
        return
    # Replay user's history
    for time_step, hist_per_step in user.info["history_per_step"].items():
        if time_step >= split_time2 or time_step < split_time1:
            # print("%s not in [%s, %s)" % (time_step, split_time1, split_time2))
            continue
        acts_all = []
        for i in range(len(hist_per_step) // 20 + 1):
            acts = []
            for hist in hist_per_step[i * 20: (i + 1) * 20]:
                act = Act(hist["type"], hist["text"], datetime.strptime(hist["timestamp"], TIME_FORMAT))
                acts.append(act)
            if acts:
                user.agent.replay_batch(acts, datetime.strptime(hist["timestamp"], TIME_FORMAT))
            acts_all.extend(acts)
        user.agent.memory.daily_reflect(acts_all, datetime.strptime(hist["timestamp"], TIME_FORMAT))

def simulate_user(user: User, env: Environment, data: Data, conf: dict):
    msgs = env.distribute_messages_for_user_by_time(user, str_to_datetime(sub_interval(datetime_to_str(env.now), conf["time_intv"])), env.now)
    get_logger().info(f"User {user.id} read {len(msgs)} messages at {env.now}. Messages from {sub_interval(datetime_to_str(env.now), conf['interval'])} to {env.now}")
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
    elif conf["react_strategy"] == "all": # 一次对所有消息做出反应
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
    # 生成消息
    previous_posts = [hist["text"] for hist in data.get_history_by_time(user.id, time_end=conf["time_init_end"]) if hist["type"] == "post"][-5:]
    acts = user.agent.generate(env.now, previous_posts=previous_posts)
    for act in acts:
        with env.lock_message:
            message = Message(id=str(len(env.messages)), type="post", text=act.text, author_id=user.id, timestamp=env.now)
            env.add_message(message)
            user.post(message.id)
            env.log_act(user, message, act)
            get_logger().info(f"User {user.id} post: {act.text} at {env.now}")






























def simulate_with_data_per_user(user: User, env: Environment, dataloader:Data, conf):
    time_start = time.time()
    if user.type == "non-core":
        return
    data = dataloader.get_history_per_step(user.id)
    assert data == user.info["history_per_step"]
    reads = []
    reads_table = {}
    posts = []
    for act_data in data[env.now.strftime(TIME_FORMAT)]:
        if act_data["type"] == "like":
            if act_data["text"] not in reads_table:
                reads_table[act_data["text"]] = []
            reads_table[act_data["text"]].append("like")
        elif act_data["type"] == "retweet" or act_data["type"] == "repost" or act_data["type"] == "quote" or act_data["type"] == "share":
            if act_data["text"] not in reads_table:
                reads_table[act_data["text"]] = []
            reads_table[act_data["text"]].append("share")
        elif act_data["type"] == "post":
            posts.append({
                "type": "post",
                "text": act_data["text"],
                "timestamp": act_data["timestamp"]
            })
    for read_text, reacts in reads_table.items():
        reads.append({
            "type": "read",
            "text": read_text,
            "result": reacts
        })
    num_sample = max(user.info["num_read_average"] - len(reads), 5 - len(reads), 0)
    msgs = env.distribute_messages_for_user(user, num_sample)
    msgs = random.sample(msgs, min(num_sample, len(msgs)))
    msg_table = {msg.text: msg for msg in msgs}
    for msg in msgs:
        msg_table[msg.text] = msg
        if msg.text not in reads_table:
            reads.append({
                "type": "read",
                "text": msg.text,
                "result": []
            })
    random.shuffle(reads)
    # replay history
    for i in range(len(reads) // 20 + 1):
        acts = []
        for read in reads[i * 20: (i + 1) * 20]:
            act_read = Act("read", read["text"], env.now)
            if read["text"] in msg_table:
                msg = msg_table[read["text"]]
            else:
                msg = Message(-1, read["text"], -1, -1, env.now)
            env.log_act(user, msg, act_read)
            for react in read["result"]:
                act = Act(react, read["text"], env.now)
                env.log_act(user, msg, act)
            acts.extend([act_read] + [Act(react, read["text"], env.now) for react in read["result"]])
        user.agent.replay_batch(acts, env.now)
    for post in posts:
        act = Act("post", post["text"], env.now)
        env.log_act(user, None, act)
    user.agent.replay_batch([Act("post", post["text"], env.now) for post in posts], env.now)
    daily_acts = user.log_per_step[-1]["acts"]
    daily_reflection = user.agent.memory.daily_reflect(daily_acts, env.now)
    get_logger().debug("user %d done. time: %.2f" % (user.id, time.time() - time_start))










def make_fake_history_per_user(user: User, env: Environment):
    if user.type == "non-core":
        return
    reads = []
    reads_table = {}
    posts = []
    if env.now.strftime(TIME_FORMAT) not in user.info["history_per_step"]:
        print(env.now.strftime(TIME_FORMAT), user.info["history_per_step"])
        get_logger().error("No data for user %d at time %s" % (user.id, env.now.strftime(TIME_FORMAT)))
    # Truth history
    acts_data = user.info["history_per_step"][env.now.strftime(TIME_FORMAT)]
    for act in acts_data:
        act = Act(act["type"], act["text"], datetime.strptime(act["timestamp"], TIME_FORMAT))
        if act.type == "like":
            if act.text not in reads_table:
                reads_table[act.text] = []
            reads_table[act.text].append("like")
        elif act.type == "retweet" or act.type == "repost" or act.type == "quote" or act.type == "share":
            if act.text not in reads_table:
                reads_table[act.text] = []
            reads_table[act.text].append("share")
        elif act.type == "post":
            posts.append({
                "type": "post",
                "text": act.text,
                "timestamp": datetime.strftime(act.timestamp, TIME_FORMAT)
            })
    for read_text, reacts in reads_table.items():
        reads.append({
            "type": "read",
            "text": read_text,
            "result": reacts
        })
    # Fake history
    num_sample = max(user.info["num_read_average"], 5)
    msgs = env.distribute_messages_for_user(user, num_sample)
    msgs = random.sample(msgs, min(num_sample, len(msgs)))
    for msg in msgs:
        if msg.text not in reads_table:
            reads.append({
                "type": "read",
                "text": msg.text,
                "result": []
            })
    random.shuffle(reads)
    random.shuffle(posts)
    for post in posts:
        act = Act("post", post["text"], env.now)
        env.log_act(user, None, act)
        # user.agent.replay(act)
    get_logger().debug("user %d done" % user.id)
    if "fake_history_per_step" not in user.info:
        user.info["fake_history_per_step"] = {}
    user.info["fake_history_per_step"][env.now.strftime(TIME_FORMAT)] = reads + posts[1:]














def evaluate_action_per_user(user: User, env: Environment, conf, data=None, _reads=[], _posts=[], case_path="case"):
    if user.type == "non-core":
        return
    if data is None:
        data = user.info["history_per_step"]
    reads = []
    reads_table = {}
    posts = []
    log_llm = []
    # print(data)
    for act in data[env.now.strftime(TIME_FORMAT)]:
        if act["type"] == "like":
            if act["text"] not in reads_table:
                reads_table[act["text"]] = []
            reads_table[act["text"]].append("like")
        elif act["type"] == "retweet" or act["type"] == "repost" or act["type"] == "quote" or act["type"] == "share":
            if act["text"] not in reads_table:
                reads_table[act["text"]] = []
            reads_table[act["text"]].append("share")
        elif act["type"] == "post":
            posts.append({
                "type": "post",
                "from": "truth",
                "text": act["text"],
                "timestamp": act["timestamp"]
            })
    for read_text, reacts in reads_table.items():
        reads.append({
            "type": "read",
            "text": read_text,
            "truth": reacts
        })
    if conf["react_strategy"] == "one":
        for read in reads:
            acts = user.agent.recieve(read["text"], env.now, update_memory=False, log=log_llm)
            read["agent"] = [act.type for act in acts]
    elif conf["react_strategy"] == "all":
        if len(reads) > 0:
            texts = [read["text"] for read in reads]
            acts = user.agent.recieve_all(texts, env.now, update_memory=False, log=log_llm)
            for i, read in enumerate(reads):
                read["agent"] = [act.type for act in acts[i]]
    else:
        raise ValueError("No reaction strategy specified.")
    acts = user.agent.generate(env.now, log=log_llm)
    if len(acts) > 0:
        for i, act in enumerate(acts):
            posts.append({
                "type": "post",
                "from": "agent",
                "text": act.text,
                "timestamp": datetime.strftime(env.now, TIME_FORMAT)
            })
    else:
        posts.append({
            "type": "post",
            "from": "agent",
            "text": "No post",
            "timestamp": datetime.strftime(env.now, TIME_FORMAT)
        })
    get_logger().debug("user %d done, len(reads)=%d, len(posts)=%d" % (user.id, len(reads), len(posts)))
    _reads.extend(reads)
    _posts.extend(posts)
    uid = user.info["id"]
    env_time = env.now.strftime(TIME_FORMAT)
    try:
        if not os.path.exists(case_path):
            os.makedirs(case_path)
    except:
        pass
    with open(f"{case_path}/{uid}_{env_time}.json", "w") as f:
        json.dump({
            "reads": reads,
            "posts": posts,
            "log_llm": log_llm
        }, f, indent=4)
    return reads, posts

