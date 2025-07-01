from datetime import datetime
from mastodon import Mastodon
from typing import List, Dict, Optional
import threading
from asn.utils.time import TIME_FORMAT
from asn.utils.mastodon import post_status_with_time
from asn.env.recommender import Recommender
from asn.agent.action import Act
from asn.agent.agent import Agent
from asn.utils.logger import get_logger


class User:
    def __init__(self, id, info, agent: Agent, mastodon_info: dict, following=[], followers=[]):
        self.id = id
        self.info = info
        self.agent = agent
        self.following = following
        self.followers = followers
        self.posts = []
        self.likes = []
        self.reposts = []
        self.mastodon_info = mastodon_info

    def get_following_ids(self):
        return self.following
    
    def get_follower_ids(self):
        return self.followers
    
    def get_status_ids(self):
        return self.posts
    
    def get_like_ids(self):
        return self.likes
    
    def get_repost_ids(self):
        return self.reposts

    def post(self, status, created_at: Optional[datetime] = None):
        self.posts.append(status)
        return status

    def like(self, status_id):
        self.likes.append(status_id)

    def repost(self, status_id):
        self.reposts.append(status_id)

    # Agent calls
    def write_post(self, now: datetime):
        acts = self.agent.generate(now)
        return acts
    
    # Agent calls
    def read_post(self, msg, now: datetime):
        acts = self.agent.recieve(msg, now)
        return acts
    
    # Agent calls
    def read_posts(self, msgs, now: datetime):
        actss = self.agent.recieve_all(msgs, now)
        return actss
    
    def save_to_dict(self, path):
        return {
            "id": self.id,
            "info": self.info,
            "agent": self.agent.save_to_dict(path, str(self.id)),
            "mastodon_info": self.mastodon_info,
            "following": self.following,
            "followers": self.followers,
            "posts": self.posts,
            "likes": self.likes,
            "reposts": self.reposts
        }
    
    @classmethod
    def load_from_dict(cls, dict) -> "User":
        agent = Agent.load_from_dict(dict["agent"])
        user = User(dict["id"], dict["info"], agent, dict["mastodon_info"])
        user.following = dict["following"]
        user.followers = dict["followers"]
        user.posts = dict["posts"]
        user.likes = dict["likes"]
        user.reposts = dict["reposts"]
        return user
    
    def __repr__(self):
        return f"User(id={self.id}, info={self.info})"


class Message:
    def __init__(self, id, type, text, author_id, timestamp, quote_id=None, mastodon_info=None):
        self.id = id
        self.type = type # "post" or "repost"
        self.text = text
        self.author_id = author_id
        self.timestamp = timestamp
        self.quote_id = quote_id
        self.mastodon_info = mastodon_info
        self.embed = None
        self.liked_by = []
        self.reposted_by = []

    def origin_id(self):
        # origin_id 记录 转发或引用的原始消息的 id，mastodon逻辑：转发消息时转发的其实是最初的原始消息
        return self.quote_id if self.quote_id else self.id

    def save_to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "text": self.text,
            "author_id": self.author_id,
            "timestamp": datetime.strftime(self.timestamp, TIME_FORMAT),
            "quote_id": self.quote_id,
            "mastodon_info": self.mastodon_info,
            "embed": self.embed,
            "liked_by": self.liked_by,
            "reposted_by": self.reposted_by
        }

    @classmethod
    def load_from_dict(cls, dict) -> "Message":
        message = Message(dict["id"], dict["type"], dict["text"], dict["author_id"], datetime.strptime(dict["timestamp"], TIME_FORMAT), dict["quote_id"], dict["mastodon_info"])
        message.embed = dict["embed"]
        message.liked_by = dict["liked_by"]
        message.reposted_by = dict["reposted_by"]
        return message

    def __repr__(self):
        return f"Message(id={self.id}, type={self.type}, text={self.text}, author_id={self.author_id}, timestamp={self.timestamp}, quote_id={self.quote_id}), mastodon_info={self.mastodon_info})"

    def summary(self):
        return self.text


class Environment:
    """
    The platform that connects users, messages, and the recommender.
    """
    def __init__(self):
        self.users: List[User] = []
        self.messages: List[Message] = []
        self.id2user: Dict[int, User] = {}
        self.id2message: Dict[int, Message] = {}
        self.log = []
        self.now = None
        self.intv = None
        self.recommender = Recommender()
        self.lock_message = threading.Lock()

    def get_user_by_id(self, id: str) -> User:
        return self.id2user[id]
    
    def get_message_by_id(self, id: str) -> Message:
        return self.id2message[id]

    def add_message(self, message: Message, need_embed: bool = True):
        if need_embed:
            message.embed = self.recommender.embed_model.embed_query(message.text)
        self.messages.append(message)
        self.id2message[message.id] = message
        return message

    def add_user(self, user: User):
        self.users.append(user)
        self.id2user[user.id] = user
        return user

    def update_time(self, now: datetime, intv: str=None):
        self.now = now
        if intv:
            self.intv = intv

    def distribute_messages_for_user_by_time(self, user: User, time_begin: datetime, time_end: datetime, k: int=10) -> List[Message]:
        # 排除用户已经交互过的帖子
        msg_ids_interacted = set(user.get_status_ids() + user.get_like_ids() + user.get_repost_ids())

        msgs_origin = [msg for msg in self.messages if msg.origin_id() == msg.id]
        # followings' messages
        following_ids = set(user.get_following_ids())
        msgs_follow = [msg for msg in msgs_origin if msg.author_id in following_ids]
        # print(f"msgs_follow for user {user.id}: {msgs_follow}")
        # recommend messages
        msgs_recommended = self.recommender.recommend(user, [msg for msg in msgs_origin], top_k=k, interacted_ids=msg_ids_interacted)
        get_logger().info(f"Recommended messages {[msg.origin_id() for msg in msgs_recommended]} for user {user.id}")
        # print(f"msgs_recommended for user {user.id}: {msgs_recommended}")
        # remove duplicates
        msgs_distributed = list(set(msgs_follow + msgs_recommended))
        return msgs_distributed
        
    def log_act(self, user: User, message: Optional[Message], act: Act, use_act_time: bool = False):
        get_logger().info(f"Log act: User {user.id} {act.type} {message.id if message else ''}")
        if use_act_time:
            self.log.append({"user": user.id, "message": message.id, "act": act.save_to_dict(), "timestamp": datetime.strftime(act.timestamp, TIME_FORMAT)})
        else:
            self.log.append({"user": user.id, "message": message.id, "act": act.save_to_dict(), "timestamp": datetime.strftime(self.now, TIME_FORMAT)})

    def save_to_dict(self, path) -> dict:
        return {
            "users": [user.save_to_dict(path) for user in self.users],
            "messages": [message.save_to_dict() for message in self.messages],
            "log": self.log,
            "now": datetime.strftime(self.now, TIME_FORMAT),
            "intv": self.intv
        }

    @classmethod
    def load_from_dict(cls, dict) -> "Environment":
        env = Environment()
        users = [User.load_from_dict(user) for user in dict["users"]]
        messages = [Message.load_from_dict(message) for message in dict["messages"]]
        for user in users:
            env.add_user(user)
        for message in messages:
            env.add_message(message, need_embed=False)
        env.log = dict["log"]
        env.now = datetime.strptime(dict["now"], TIME_FORMAT)
        env.intv = dict["intv"]
        env.recommender = Recommender()
        return env
