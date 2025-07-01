import numpy as np
from typing import List, Dict
from langchain_core.embeddings import Embeddings
from datetime import datetime
from asn.utils.time import *
from asn.llm.llm import LLMManager


class Recommender:
    embed_size: int
    embed_model: Embeddings

    def __init__(self):
        self.embed_size, self.embed_model = LLMManager.get_embed_model()

    def recommend(self, user, messages, top_k: int = 10, interacted_ids = [], time_now = None):
        """
        param interacted_ids: List[int] #交互过的消息origin_id，降低这些消息的推荐权重
        """
        # 一半是热点，一半基于兴趣
        messages_sim = []
        messages_hot = []
        # 获取用户喜欢的帖子，按时间排序取最后5个，平均embedding
        fav_ids = set(user.get_like_ids())
        fav_messages = [msg for msg in messages if msg.id in fav_ids]
        if len(fav_messages) > 0:
            fav_messages = sorted(fav_messages, key=lambda x: x.timestamp, reverse=True)[:5]
            user_embed = np.mean([msg.embed for msg in fav_messages], axis=0)
            # 计算相似度
            sim = [(msg, self.similarity(user_embed, msg.embed) * self.decay_weight(msg.timestamp, datetime.now())) for msg in messages]
            # 降低交互过的消息的相似度
            updated_sim = []
            for msg, _ in sim:
                if msg.origin_id() in interacted_ids:
                    updated_sim.append((msg, _ * 0.5))
                else:
                    updated_sim.append((msg, _))
            sim = updated_sim
            # 按相似度排序
            sim = sorted(sim, key=lambda x: x[1], reverse=True)
            messages_sim = [msg for msg, _ in sim[:top_k//2]]
        # 热点
        hot = [(msg, len(msg.liked_by) * self.decay_weight(msg.timestamp, datetime.now())) for msg in messages if msg.id not in [m.id for m in messages_sim]]
        # 降低交互过的消息的热度
        updated_hot = []
        for msg, _ in hot:
            if msg.origin_id() in interacted_ids:
                updated_hot.append((msg, _ * 0.5))
            else:
                updated_hot.append((msg, _))
        hot = updated_hot
        hot = sorted(hot, key=lambda x: x[1], reverse=True)
        messages_hot = [msg for msg, _ in hot[:top_k//2]]
        return list(set(messages_sim + messages_hot))
    
    def decay_weight(self, time_message: datetime, time_now: datetime) -> float:
        # 时间衰减
        decay_factor = 0.96
        if not time_now or time_message > time_now:
            return 1.0
        return decay_factor ** ((time_now - time_message).total_seconds() / 3600)
    
    def similarity(self, a: List[float], b: List[float]) -> float:
        # cosine similarity
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
