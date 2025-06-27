"""
Planning module.
计划agent一天在社交网络上的活跃时间
"""
from typing import List, Dict
from asn.llm.llm import LLMManager
from asn.llm.prompt import Prompts
import json

class Plan:
    def __init__(self):
        self.plan = []
        self.llm = LLMManager.get_llm()

    def save_to_dict(self):
        return {
            "plan": self.plan
        }
    
    def load_from_dict(self, data: Dict):
        self.plan = data["plan"]

    def make_plan(self, characteristics: str, date: str) -> str:
        prompt_system = Prompts.plan_system.format(characteristics=characteristics)
        prompt = Prompts.plan.format(date=date)
        try:
            plan = self.llm._call(prompt=prompt, prompt_sys=prompt_system)
            self.plan = json.loads(plan)
            return plan
        except Exception as e:
            print(f"Error decoding JSON: {plan}\n{e}")
            self.plan = []
            return []
    
    def within_intv(self, intv, time_step):
        time_start, time_end = intv.split("-")
        # timestep: '%Y-%m-%d %H:%M:%S' 取一天内的时间
        time_step = time_step.split(" ")[-1]
        if time_start <= time_step < time_end:
            return True
        else:
            return False

if __name__ == "__main__":
    LLMManager.set_manager({
        "llm_name": "OpenAI",
        "llm_model": "qwen-plus-0919",
        "llm_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": 'sk-2b26e585f3aa4c17b949f2e675a5284e',
        "embed_name": "OpenAI",
    })
    plan = Plan()
    characteristics = "You are a social media user who enjoys sharing your thoughts on technology and gaming. Your activity level is high, and you often engage with content related to these topics. You express a strong interest in the latest trends, and your posts reflect a positive attitude towards innovation and creativity."
    date = "2023-08-11"
    plan.make_plan(characteristics, date)
    print(plan.plan)    # ['09:00-10:00', '13:00-14:00', '17:00-18:00']
    print(plan.within_intv("09:00-10:00", "2023-08-11 09:30:00"))   # True