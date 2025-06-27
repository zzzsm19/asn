from langchain_core.memory import BaseMemory
from datetime import datetime
from typing import Optional
from asn.agent.profile import ProfileModule
from asn.agent.memory import NaiveMemoryModule
from asn.agent.action import ActionModule
from asn.agent.plan import Plan
from asn.llm.llm import LLMManager
from asn.llm.prompt import *
from asn.utils.logger import get_logger
from asn.utils.utils import fake_history_to_example_post, fake_history_to_example_react, fake_history_to_example_reacts

class Agent:
    def __init__(self):
        pass

    def save_to_dict(self, *args):
        raise NotImplementedError

    def recieve(self, text: str, now: datetime, update_memory=True, incontext=False, fake_history=None, log=None):
        raise NotImplementedError

    def recieve_all(self, texts, now: datetime, update_memory=True, incontext=False, fake_history=None, log=None):
        raise NotImplementedError

    def generate(self, now: datetime, update_memory=True, incontext=False, fake_history=None, log=None):
        raise NotImplementedError

    def get_profile(self):
        raise NotImplementedError
    
    def replay(self, act):
        raise NotImplementedError

    def decide_next_action(self, now):
        raise NotImplementedError
    
    @classmethod
    def load_from_dict(self, dict):
        if dict["type"] == "LLMAgent":
            return LLMAgent.load_from_dict(dict)
        elif dict["type"] == "NaiveAgent":
            return NaiveAgent.load_from_dict(dict)
        else:
            raise ValueError("Unknown agent type: {type}".format(type=dict["type"]))


class LLMAgent(Agent):
    def __init__(self, info: Optional[dict] = None, memory = None, profile = None):
        super().__init__()
        self.info = info
        self.llm = LLMManager.get_llm()
        # modules
        self.action = ActionModule()
        if memory is None:
            memory = NaiveMemoryModule()
        self.memory = memory
        self.profile = ProfileModule() if profile is None else profile
        self.plan = Plan()
        self.behavior_record = []

    def add_to_memory(self, observation, now):
        get_logger().debug("Add to memory: {observation}".format(observation=observation))
        observation = datetime.strftime(now, "%Y-%m-%d %H:%M") + "\n" + observation
        self.memory.add_memory(observation, now)

    def recieve(self, text: str, now: datetime, update_memory=True, incontext=False, fake_history=None, log=None):
        """
        The agent reads a post and reacts to it.
        """
        experience = None
        if incontext:
            assert fake_history is not None
            experience = fake_history_to_example_react(fake_history, 10)
        memories_retrieved = self.memory.fetch_memories(text, now)
        characteristics = self.profile.characteristics
        acts = self.action.react_to_post({"text": text}, memories_retrieved, characteristics, now, experience, log=log)
        # agent add memory
        recieve_memory = "I read a post: \"\"\"{text}\"\"\"".format(text=text)
        for act in acts:
            if act.type == "read":
                pass
                # get_logger().info("User {id} reads: {text}".format(id=self.profile.info["id"], text=text[:50] + "......"))
            elif act.type == "like":
                recieve_memory += "\nI like this post very much."
                # get_logger().info("User {id} likes: {text}".format(id=self.profile.info["id"], text=text[:50] + "......"))
            elif act.type == "retweet" or act.type == "share" or act.type == "repost":
                recieve_memory += "\nI retweet this post."
                # get_logger().info("User {id} reposts: {text}".format(id=self.profile.info["id"], text=text[:50] + "......"))
            else:
                get_logger().error("Unknown action type: {type}".format(type=act.type))
        if update_memory:
            self.add_to_memory(recieve_memory, now)
            self.behavior_record.extend(acts)
        return acts

    def recieve_all(self, texts, now: datetime, update_memory=True, incontext=False, fake_history=None, log=None):
        """
        The agent reads a batch of posts and reacts to them.
        """
        if not texts:
            return []
        experience = None
        if incontext:
            assert fake_history is not None
            experience = fake_history_to_example_reacts(fake_history, 10)
        memories_retrieved = self.memory.fetch_memories("\n".join(["%d. %s" % (i, text) for i, text in enumerate(texts)]), now)
        characteristics = self.profile.characteristics
        actss = self.action.react_to_posts([{"text": text} for text in texts], memories_retrieved, characteristics, now, experience, log=log)
        # agent add memory
        memories_saved = []
        for i, acts in enumerate(actss):
            text = texts[i]
            acts = actss[i]
            recieve_memory = "I read a post: \"\"\"{text}\"\"\"".format(text=text)
            for act in acts:
                if act.type == "read":
                    pass
                    # get_logger().info("User {id} reads: {text}".format(id=self.profile.info["id"], text=text[:50] + "......"))
                elif act.type == "like":
                    recieve_memory += "\nI like this post very much."
                    # get_logger().info("User {id} likes: {text}".format(id=self.profile.info["id"], text=text[:50] + "......"))
                elif act.type == "retweet" or act.type == "share" or act.type == "repost":
                    recieve_memory += "\nI retweet this post."
                    # get_logger().info("User {id} reposts: {text}".format(id=self.profile.info["id"], text=text[:50] + "......"))
                else:
                    get_logger().error("Unknown action type: {type}".format(type=act.type))
            memories_saved.append(recieve_memory)
        if update_memory:
            self.memory.add_memories(memories_saved, now)
            acts = [act for acts in actss for act in acts]  # flatten the list
            self.behavior_record.extend(acts)
        return actss
            
    def generate(self, now: datetime, previous_posts, update_memory=True, force=False, incontext=False, fake_history=None, log=None):
        """
        The agent actively generates a post.
        """
        experience = None
        if incontext:
            assert fake_history is not None
            experience = fake_history_to_example_post(fake_history, 10)
        memories_retrieved = self.memory.fetch_memories("Something that impresses.", now)
        characteristics = self.profile.characteristics
        acts = self.action.write_post(memories_retrieved, characteristics, previous_posts, now, extra_experience=experience, log=log, force=force)
        # agent add memory
        for act in acts:
            generate_memory = "I write a post: \"\"\"{text}\"\"\"".format(text=act.text)
            if update_memory:
                self.add_to_memory(generate_memory, now)
                self.behavior_record.extend(acts)
        return acts
    
    def make_plan(self, now: datetime):
        date = datetime.strftime(now, "%Y-%m-%d")
        characteristics = self.profile.characteristics
        plan = self.plan.make_plan(characteristics, date)
        return plan

    def replay(self, act):  # TODO
        """
        Replay the agent's history.
        """
        if act.type == "read":
            self.add_to_memory("I read a post: \"\"\"{text}\"\"\"".format(text=act.text), act.timestamp)
        elif act.type == "like":
            self.add_to_memory("I like this post: \"\"\"{text}\"\"\"".format(text=act.text), act.timestamp)
        elif act.type == "retweet" or act.type == "share" or act.type == "repost":
            self.add_to_memory("I retweet this post: \"\"\"{text}\"\"\"".format(text=act.text), act.timestamp)
        elif act.type == "quote":
            self.add_to_memory("I read a post: \"\"\"{text}\"\"\" I retweet this post and give a little of my own thoughts: \"\"\"{quote_text}\"\"\".".format(text=act.text, quote_text=act.quote_text), act.timestamp)
        elif act.type == "post":
            if act.text.lower() == "no post":
                self.add_to_memory("I didn't write a post this time.", act.timestamp)
            else:
                self.add_to_memory("I write a post: \"\"\"{text}\"\"\"".format(text=act.text), act.timestamp)
        self.behavior_record.append(act)

    def replay_batch(self, acts, timestamp: datetime):
        """
        Summary from the acts of a time step and replay.
        """
        if len(acts) == 0:
            # self.memory.add_memories(["Didn't do anything."], timestamp)
            return
        memories = []
        for act in acts:
            if act.type == "read":
                memories.append("I read a post: \"\"\"{text}\"\"\"".format(text=act.text))
            elif act.type == "like":
                memories.append("I like this post: \"\"\"{text}\"\"\"".format(text=act.text))
            elif act.type == "retweet" or act.type == "share" or act.type == "repost":
                memories.append("I retweet this post: \"\"\"{text}\"\"\"".format(text=act.text))
            elif act.type == "quote":
                memories.append("I read a post: \"\"\"{text}\"\"\" I retweet this post and give a little of my own thoughts: \"\"\"{quote_text}\"\"\".".format(text=act.text, quote_text=act.quote_text))
            elif act.type == "post":
                if act.text.lower() == "no post":
                    memories.append("I didn't write a post this time.")
                else:
                    memories.append("I write a post: \"\"\"{text}\"\"\"".format(text=act.text))
        get_logger().debug("Replays actions: {acts}, add memories: {memories}".format(acts=acts, memories=memories))
        self.memory.add_memories(memories, timestamp)
        self.behavior_record.extend(acts)

    def get_opinion(self, topic, now):
        memories_retrieved = self.memory.fetch_memories(topic, now)
        return self.state.update(topic, memories_retrieved, self.profile.characteristics), memories_retrieved

    def get_profile(self, history, time_begin, time_end, time_intv):
        return self.profile.portrait(history, time_begin, time_end, time_intv)
    
    def decide_next_action(self, now):
        memories_retrieved = self.memory.fetch_memories("What should I do next?", now)
        characteristics = self.profile.characteristics
        behavior_record = [f"On {act.timestamp}, {act.type} a post: \"\"\"{act.text}\"\"\"" for act in self.behavior_record][-50:]
        ate = self.action.decide_next_active_time(behavior_record=behavior_record, memories_retrieved=memories_retrieved, characteristics=characteristics, now=now)
        return ate

    def save_to_dict(self, path, index, *args):
        return {
            "type": "LLMAgent",
            "info": self.info,
            "memory": self.memory.save_to_dict(path, index),
            "profile": self.profile.save_to_dict(),
        }
    
    @classmethod
    def load_from_dict(self, dict) -> "LLMAgent":
        memory = NaiveMemoryModule.load_from_dict(dict["memory"])
        profile = ProfileModule.load_from_dict(dict["profile"])
        return LLMAgent(dict["info"], memory, profile)


class NaiveAgent(Agent):
    def __init__(self, info=None):
        super().__init__()
        self.info = info

    def save_to_dict(self, *args):
        return {
            "type": "NaiveAgent",
            "info": self.info
        }
    
    @classmethod
    def load_from_dict(self, dict) -> "NaiveAgent":
        return NaiveAgent(dict["info"])
