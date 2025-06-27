import time
import random
import threading
from openai import OpenAI
from typing import Any, List, Mapping
from langchain.llms.base import LLM
from langchain_core.embeddings import Embeddings
from asn.utils.logger import get_logger

# 保存 llm 的 prompt 和 response 需要的线程锁
import json
lock_llm_save = threading.Lock()
llm_out_json = []

USE_SFT = False
def set_sft(use_sft: bool) -> None:
    global USE_SFT
    USE_SFT = use_sft
def get_sft() -> bool:
    return USE_SFT
lock_llm = threading.Lock()

class LLMManager:
    llm_name: str = "Local"
    llm_model: str = ""
    embed_name: str = "Local"
    embed_model: str = ""
    lora_path: str = ""
    llm: LLM = None
    embed_model: Embeddings = None

    @classmethod
    def set_manager(cls, conf) -> None:
        cls.llm_name = conf["llm_name"]
        cls.llm_model = conf["llm_model"] if "llm_model" in conf else ""
        cls.llm_url = conf["llm_url"] if "llm_url" in conf else "http://localhost:8001/v1"
        cls.embed_name = conf["embed_name"]
        cls.embed_model = conf["embed_model"] if "embed_model" in conf else ""
        cls.embed_url = conf["embed_url"] if "embed_url" in conf else "http://localhost:8002/v1"
        cls.lora_path = conf["lora_path"] if "lora_path" in conf else ""
        if cls.llm_name == "OpenAI":
            cls.llm = OpenAILLM(model=cls.llm_model, base_url=cls.llm_url, api_key=conf["api_key"] if "api_key" in conf else "EMPTY")
        else:
            raise ValueError(f"Unknown model name: {cls.llm_name}")
        if cls.embed_name == "OpenAI":
            cls.embed_model = OpenAIEmbed(model=cls.embed_model, base_url=cls.embed_url, api_key=conf["api_key"] if "api_key" in conf else "EMPTY")
        else:
            raise ValueError(f"Unknown model name: {cls.embed_name}")
        print(f"LLM Manager set to: {cls.llm_name}, {cls.llm_model}, {cls.embed_name}, {cls.embed_model}")

    @classmethod
    def get_llm(cls) -> LLM:
        return cls.llm

    @classmethod
    def get_embed_model(cls) -> tuple[int, Embeddings]:
        return cls.embed_model.embed_size(), cls.embed_model 

class OpenAILLM(LLM):
    client: OpenAI = None
    model: str = None
    task_ids: List[int] = []
    def __init__(self, api_key: str="EMPTY", base_url: str="http://localhost:8001/v1", model: str="") -> None:
        super().__init__()
        openai_api_key = api_key
        openai_api_base = base_url
        self.model = model
        self.client = OpenAI(
            api_key=openai_api_key,
            base_url=openai_api_base,
        )

    def _llm_type(self) -> str:
        return "openai"
    
    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {
            "model_name": "openai"
        }
    
    def _call(self, prompt: str, prompt_sys="You are a helpful assistant.", sft=False, **kwargs) -> str:
        # get_logger().debug(f"PROMPT: {prompt}\nUse SFT: {sft}")
        # a random and unexisted task id
        task_id = random.randint(0, 1000000)
        while task_id in self.task_ids:
            task_id = random.randint(0, 1000000)
        self.task_ids.append(task_id)

        # 最多retry3次
        retry_count = 0
        while retry_count < 3:
            try:
                model = self.model if not sft else "sft"
                time_start_call = time.time()
                chat_response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": prompt_sys},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.0,
                    timeout=3000
                )
                response = chat_response.choices[0].message.content
                time_end_call = time.time()
                get_logger().debug(f"PROMPT_SYS: {prompt_sys}\nPROMPT: {prompt}\n\nRESPONSE: {response} \n\nTask ID: {task_id}\nTime cost: {time_end_call - time_start_call} s")
                self.task_ids.remove(task_id)
                # 保存 llm 的 prompt 和 response
                with lock_llm_save:
                    llm_out_json.append({
                        "prompt": prompt,
                        "response": response,
                    })
                    with open("llm_out.json", "w") as f:
                        json.dump(llm_out_json, f, indent=4)
                # 如果是think模型，筛掉think的内容
                if "<think>" in response and "</think>" in response:
                    response = response.split("</think>")[-1]
                return response
            except Exception as e:
                get_logger().error(f"Error in OpenAILLM: {e}\nTask ID: {task_id}\nPrompt: {prompt}")
                retry_count += 1
                time.sleep(3)
                continue
                
        # 失败则返回空字符串
        get_logger().error(f"OpenAILLM failed after 3 retries. Task ID: {task_id}\nPrompt: {prompt}")
        self.task_ids.remove(task_id)
        return ""


class OpenAIEmbed(Embeddings):
    embedding_size: int = 3584
    client: OpenAI = None
    model: str = None
    task_ids: List[int] = []
    def __init__(self, api_key: str="EMPTY", base_url: str="http://localhost:8002/v1", model: str="") -> None:
        super().__init__()
        openai_api_key = api_key
        openai_api_base = base_url
        self.client = OpenAI(
            api_key=openai_api_key,
            base_url=openai_api_base,
        )
        self.model = model

    def _llm_type(self) -> str:
        return "openai_embed"
    
    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {
            "model_name": "openai_embed"
        }
    
    def embed_query(self, text: str) -> List[float]:
        try:
            assert text != ""
        except Exception as e:
            get_logger().error(f"Error in OpenAIEmbed: {e}\nText: {text}")
            return [0.0] * self.embedding_size
        task_id = random.randint(0, 1000000)
        while task_id in self.task_ids:
            task_id = random.randint(0, 1000000)
        self.task_ids.append(task_id)
        while True:
            try:
                time_start_call = time.time()
                embeddings = self.client.embeddings.create(
                    model=self.model,
                    input=[text],
                    timeout=3000
                )
                time_end_call = time.time()
                get_logger().debug(f"TEXT: {text}\n\nTask ID: {task_id}\nTime cost: {time_end_call - time_start_call} s")
                return embeddings.data[0].embedding
            except Exception as e:
                get_logger().error(f"Error in OpenAIEmbed: {e}\nTask ID: {task_id}\nText: {text}")
                time.sleep(60)
                continue
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        for text in texts:
            try:
                assert text != ""
            except Exception as e:
                get_logger().error(f"Error in OpenAIEmbed: {e}\nText: {text}")
                return [[0.0] * self.embedding_size] * len(texts)
        time_start_call = time.time()
        embeddings = self.client.embeddings.create(
            model=self.model,
            input=texts
        )
        time_end_call = time.time()
        get_logger().debug(f"TEXTS: {texts}\n\nTime cost: {time_end_call - time_start_call} s")
        return [item.embedding for item in embeddings.data]
    
    @classmethod
    def embed_size(cls) -> int:
        return cls.embedding_size
