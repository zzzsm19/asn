from langchain.prompts import PromptTemplate
from asn.utils.time import *
from asn.llm.llm import LLM, LLMManager
from asn.llm.prompt import Prompts
from asn.utils.logger import get_logger

class ProfileModule:
    def __init__(self, characteristics: str = None):
        self.llm = LLMManager.get_llm()
        self.characteristics = characteristics
    
    def portrait(self, history, time_begin, time_end, time_intv): # TODO 把这一部分对act的处理放到data中和Act类中
        if self.characteristics:
            get_logger().debug("ProfileModule: Using cached characteristics: " + self.characteristics)
            return self.characteristics
        history_text = ""
        time_step = time_begin
        hists = []
        while time_step < time_end:
            history_step = [hist for hist in history if time_step <= hist["timestamp"] < add_interval(time_step, time_intv)]
            get_logger().debug(f"Profile: History step: {history_step} from {time_step} to {add_interval(time_step, time_intv)}, History: {history}")
            if len(history_step) == 0:
                history_text += f"{time_step} to {add_interval(time_step, time_intv)}: No activities.\n"
            hists.extend(history_step[-20:])
            time_step = add_interval(time_step, time_intv)
        for hist in hists[-100:]:
            if hist["type"] == "read":
                history_text += f"{hist['timestamp']} read a post: \"{hist['text']}\"\n"
            elif hist["type"] == "like":
                history_text += f"{hist['timestamp']} like a post: \"{hist['text']}\"\n"
            elif hist["type"] == "post":
                history_text += f"{hist['timestamp']} write a post: \"{hist['text']}\"\n"
            elif hist["type"] == "repost" or hist["type"] == "retweet" or hist["type"] == "share":
                history_text += f"{hist['timestamp']} repost a post: \"{hist['text']}\"\n"
            else:
                get_logger().error(f"Profile: Unknown history type: {hist['type']}")
        result = self.llm._call(Prompts.profile.format(history=history_text))
        self.characteristics = result
        get_logger().debug(f"Profile: History: {history} to History text: {history_text} to Characteristics: {self.characteristics}")
        get_logger().debug("ProfileModule: New characteristics: " + self.characteristics)
        return self.characteristics
        
    def save_to_dict(self):
        return {
            "characteristics": self.characteristics,
        }

    @classmethod
    def load_from_dict(self, dict) -> "ProfileModule":
        return ProfileModule(dict["characteristics"])
