from datetime import datetime, timedelta
from typing import List, Optional, Any
import numpy as np
import random
import faiss
import copy
from langchain.llms.base import LLM
from langchain.retrievers import TimeWeightedVectorStoreRetriever
from langchain_community.docstore import InMemoryDocstore
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.memory import BaseMemory
from langchain.prompts import PromptTemplate
from langchain.retrievers import TimeWeightedVectorStoreRetriever
from langchain.schema import BaseMemory, Document
from langchain.schema import BaseOutputParser
from langchain_core.utils import mock_now
from unittest.mock import patch
from langchain_experimental.generative_agents.memory import GenerativeAgentMemory
from langchain_community.vectorstores.utils import DistanceStrategy
from asn.llm.prompt import *
from asn.llm.llm import LLMManager


class NaiveMemoryModule(GenerativeAgentMemory):
    prompt: PromptTemplate = PromptTemplate.from_template(PROMPT_NAIVE_MEMORY)
    prompt_multi: PromptTemplate = PromptTemplate.from_template(PROMPT_NAIVE_MULTI_MEMORY)
    prompt_daily: PromptTemplate = PromptTemplate.from_template(PROMPT_DAILY_REFLECTION)
    llm: LLM
    def __init__(self, k: int = 5, decay_rate: float = 1e-6, memory_retriever: Optional[TimeWeightedVectorStoreRetriever] = None):
        llm = LLMManager.get_llm()
        if memory_retriever is None:
            embed_size, embed_model = LLMManager.get_embed_model()
            vector_store = FAISS(embed_model, faiss.IndexFlatIP(embed_size), InMemoryDocstore(), {}, normalize_L2=True)
            memory_retriever = TimeWeightedVectorStoreRetriever(vectorstore=vector_store, decay_rate=decay_rate, k=k)
        super().__init__(llm=llm, memory_retriever=memory_retriever)

    def add_memory(
        self, memory_content: str, now: datetime
    ) -> List[str]:
        """Add an observation or memory to the agent's memory."""
        memory_content = (self.prompt | self.llm).invoke({"behavior": memory_content, "timestamp": datetime.strftime(now, "%Y-%m-%d")})
        document = Document(
            page_content=memory_content, metadata={"created_at": now}
        )
        result = self.memory_retriever.add_documents([document], current_time=now)
        return result
    
    def add_memories(
        self, memories: List[str], now: datetime
    ) -> List[str]:
        """Add multiple observations or memories to the agent's memory ONCE."""
        memories = "\n".join(["%d. %s" % (i, memory) for i, memory in enumerate(memories)])
        memory_content = (self.prompt_multi | self.llm).invoke({"behavior": memories, "timestamp": datetime.strftime(now, "%Y-%m-%d")})
        documents = [
            Document(
                page_content=memory_content, metadata={"created_at": now}
            )
        ]
        result = self.memory_retriever.add_documents(documents, current_time=now)
        return result

    def daily_reflect(self, daily_action, now: datetime):
        if len(daily_action) == 0:
            activities = ["Didn't do anything today."]
        else:
            activities = []
            for act in daily_action:
                if act.type == "read":
                    activities.append("I read a post: \"\"\"{text}\"\"\"".format(text=act.text))
                elif act.type == "like":
                    activities.append("I like this post: \"\"\"{text}\"\"\"".format(text=act.text))
                elif act.type == "retweet" or act.type == "share":
                    activities.append("I retweet this post: \"\"\"{text}\"\"\"".format(text=act.text))
                elif act.type == "post":
                    if act.text.lower() == "no post":
                        activities.append("I didn't write a post today.")
                    else:
                        activities.append("I write a post: \"\"\"{text}\"\"\"".format(text=act.text))
        activities = "\n".join(activities)
        daily_reflection = (self.prompt_daily | self.llm).invoke({"behavior": activities, "timestamp": datetime.strftime(now, "%Y-%m-%d")})
        document = Document(
            page_content=daily_reflection, metadata={"created_at": now}
        )
        result = self.memory_retriever.add_documents([document], current_time=now)
        return daily_reflection

    def fetch_memories(
        self, observation: str, now: Optional[datetime] = None
    ) -> List[Document]:
        """Fetch related memories."""
        if now is not None:
            # with mock_now(now):
            # !!! 多线程mock_now（猴子补丁修改datetime.datetime），导致datetime.datetime被永久污染，无法恢复
            memories_retrieved = self.memory_retriever.invoke(observation)
        else:
            memories_retrieved = self.memory_retriever.invoke(observation)
        return [memory.page_content for memory in memories_retrieved]

    @staticmethod
    def save_document_to_dict(document: Document) -> dict:
        # Datetime or MockDatetime in metadata
        metadata = copy.deepcopy(document.metadata)
        for key, value in metadata.items():
            if isinstance(value, datetime):
                metadata[key] = value.timestamp()
        return {    
            "page_content": document.page_content,
            "metadata": metadata
        }
    
    @staticmethod
    def load_document_from_dict(data: dict) -> Document:
        # Datetime or MockDatetime in metadata
        for key, value in data["metadata"].items():
            if isinstance(value, float):
                data["metadata"][key] = datetime.fromtimestamp(value)
        return Document(
            page_content=data["page_content"],
            metadata=data["metadata"]
        )

    def save_to_dict(self, path, index) -> dict:
        # Transform mockdatetime to datetime
        for doc in self.memory_retriever.vectorstore.docstore._dict.values():
            doc.metadata["created_at"] = doc.metadata["created_at"].timestamp()
            doc.metadata["last_accessed_at"] = doc.metadata["last_accessed_at"].timestamp()
        self.memory_retriever.vectorstore.save_local(path, index)
        for doc in self.memory_retriever.vectorstore.docstore._dict.values():
            doc.metadata["created_at"] = datetime.fromtimestamp(doc.metadata["created_at"])
            doc.metadata["last_accessed_at"] = datetime.fromtimestamp(doc.metadata["last_accessed_at"])
        memory_stream = [self.save_document_to_dict(doc) for doc in self.memory_retriever.memory_stream]
        return {
            "path": path,
            "index": index,
            "memory_stream": memory_stream,
            "decay_rate": self.memory_retriever.decay_rate,
            "k": self.memory_retriever.k
        }
        
    @classmethod
    def load_from_dict(cls, data: dict) -> "NaiveMemoryModule":
        path = data["path"]
        index = data["index"]
        memory_stream = [cls.load_document_from_dict(doc) for doc in data["memory_stream"]]
        decay_rate = data["decay_rate"]
        k = data["k"]
        embed_size, embed_model = LLMManager.get_embed_model()
        vector_store = FAISS.load_local(path, embed_model, index, allow_dangerous_deserialization=True)
        for doc in vector_store.docstore._dict.values():
            doc.metadata["created_at"] = datetime.fromtimestamp(doc.metadata["created_at"])
            doc.metadata["last_accessed_at"] = datetime.fromtimestamp(doc.metadata["last_accessed_at"])
        memory_retriever = TimeWeightedVectorStoreRetriever(vectorstore=vector_store, decay_rate=decay_rate, k=k)
        memory_retriever.memory_stream = memory_stream
        return NaiveMemoryModule(memory_retriever=memory_retriever)
