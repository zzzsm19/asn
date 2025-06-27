import json
from datetime import datetime
from asn.llm.llm import LLMManager, get_sft
from asn.llm.prompt import Prompts
from asn.utils.logger import get_logger


class Act:
    type: str       # "read", "like", "retweet", "post"
    text: str
    timestamp: datetime
    def __init__(self, type: str, text: str, timestamp: datetime):
        self.type = type
        self.text = text
        self.timestamp = timestamp

    def __repr__(self):
        return f"Act(type={self.type}, text={self.text}, timestamp={self.timestamp})"
    
    def save_to_dict(self):
        return {
            "type": self.type,
            "text": self.text,
            "timestamp": datetime.strftime(self.timestamp, "%Y-%m-%d %H:%M:%S"),
        }
    
    @classmethod
    def load_from_dict(self, dict) -> "Act":
        act = Act(dict["type"], dict["text"], datetime.strptime(dict["timestamp"], "%Y-%m-%d %H:%M:%S"))
        return act
    
class ActionModule:
    def __init__(self):
        self.llm = LLMManager.get_llm()
        embed_size, self.embed_model = LLMManager.get_embed_model()

    def react_to_post(self, post: dict, memories_retrieved: list, characteristics: str, now: datetime, extra_experience=None, log=None):
        def parse_react_result(result: str):
            result = result.strip("`|json| ")
            action = json.loads(result)
            get_logger().info(f"Parsed actions: {action}")
            return action
        try:
            prompt_sys = Prompts.react_system.format(characteristics=characteristics)
            prompt = Prompts.react.format(timestamp=datetime.strftime(now, "%y-%m-%d %H:%M"), memories="\n".join(["{idx}. {memory}".format(idx=i+1, memory=memory) for i, memory in enumerate(memories_retrieved)]), post=post)
            if extra_experience is not None:
                prompt += "\n" + "There are some examples:\n" + extra_experience
            response = self.llm._call(prompt=prompt, prompt_sys=prompt_sys, sft=get_sft())
            if log is not None:
                log.append({
                    "prompt": prompt,
                    "response": response
                })
            action = parse_react_result(response)
        except Exception as e:
            get_logger().debug(f"Error in invoking chain_react: {e} \n\n post={post}, memories={memories_retrieved}, characteristics={characteristics}")
            action = {"Like": "No", "Repost": "No"}
        acts: list[Act] = []
        acts.append(Act("read", post["text"], now))
        if action["Like"].lower() == "yes":
            acts.append(Act("like", post["text"], now))
        if action["Repost"].lower() == "yes":
            acts.append(Act("retweet", post["text"], now))
        return acts
    
    def react_to_posts(self, posts: list, memories_retrieved: list, characteristics: str, now: datetime, extra_experience=None, log=None):
        def parse_reacts_result(result: str):
            result = result.strip("`|json| ")
            actions = json.loads(result)
            get_logger().info(f"Parsed actions: {actions}")
            return actions
        # 将posts分批处理
        def react_to_posts_batch(posts: list, memories_retrieved: list, characteristics: str, now: datetime, extra_experience=None, log=None):
            acts: list[list[Act]] = [[] for _ in posts]
            try:
                prompt_sys = Prompts.reacts_system.format(characteristics=characteristics)
                prompt = Prompts.reacts.format(timestamp=datetime.strftime(now, "%y-%m-%d %H:%M"), memories="\n".join(["{idx}. {memory}".format(idx=i+1, memory=memory) for i, memory in enumerate(memories_retrieved)]), posts="\n".join(["{idx}. {post}".format(idx=i+1, post=post) for i, post in enumerate(posts)]))
                if extra_experience is not None:
                    prompt += "\n" + "There are some examples:\n" + extra_experience
                response = self.llm._call(prompt=prompt, prompt_sys=prompt_sys, sft=get_sft())
                actions = parse_reacts_result(response)
                if len(actions) != len(posts):
                    get_logger().debug("Error in invoking chain_reacts: actions length not equal to posts length: %d != %d" % (len(actions), len(posts)))
                    return None
                if log is not None:
                    log.append({
                        "prompt": prompt,
                        "response":response
                    })
                for i, action in enumerate(actions):
                    post = posts[i]
                    acts[i].append(Act("read", post["text"], now))
                    if action["Like"].lower() == "yes":
                        acts[i].append(Act("like", post["text"], now))
                    if action["Repost"].lower() == "yes":
                        acts[i].append(Act("retweet", post["text"], now))
                return acts
            except Exception as e:
                get_logger().debug(f"Error in invoking chain_reacts: {e} \n\n posts={posts}, memories={memories_retrieved}, characteristics={characteristics}")
                get_logger().debug(f"Response: {response} Retry with chain_react")
                # 批量处理失败，逐个处理
                for i, post in enumerate(posts):
                    acts[i] = self.react_to_post(post, memories_retrieved, characteristics, now, extra_experience, log)
                return acts
            
        batch_size = 10
        acts = []
        for i in range(0, len(posts), batch_size):
            posts_batch = posts[i:i + batch_size]
            acts_batch = react_to_posts_batch(posts_batch, memories_retrieved, characteristics, now, extra_experience, log)
            if acts_batch is None:
                return None
            acts.extend(acts_batch)
        return acts

    def write_post(self, memories_retrieved: list, characteristics: str, previous_posts: list, now: datetime, force=False, extra_experience=None, log=None):
        def parse_post(result: str):
            result = result.strip("`|json| ")
            posts = [json.loads(result)]
            posts = [post["Post"] for post in posts if "no post" not in post["Post"].lower()]
            get_logger().info(f"Parsed posts: {posts}")
            return posts
        
        if len(previous_posts):
            previous_posts = "\n".join(["{idx}. {post}".format(idx=i+1, post=post) for i, post in enumerate(previous_posts)])
        else:
            previous_posts = "No previous posts"
        memories_text = "\n".join(["{idx}. {memory}".format(idx=i+1, memory=memory) for i, memory in enumerate(memories_retrieved)])
        # try:
        prompt_sys = Prompts.post_system.format(characteristics=characteristics)
        prompt = Prompts.post.format(timestamp=datetime.strftime(now, "%Y-%m-%d %H:%M"), memories=memories_text, previous_posts=previous_posts)
        if force:
            prompt = Prompts.post_force.format(timestamp=datetime.strftime(now, "%Y-%m-%d %H:%M"), memories=memories_text, previous_posts=previous_posts)
        if extra_experience is not None:
            prompt += "\n" + "There are some examples:\n" + extra_experience
        response = self.llm._call(prompt=prompt, prompt_sys=prompt_sys, sft=get_sft())
        if log is not None:
            log.append({
                "prompt": prompt,
                "response": response
            })
        posts = parse_post(response)
        acts = []
        for post in posts:
            acts.append(Act("post", post, now))
        return acts
        # except Exception as e:
        #     get_logger().debug(f"Error in invoking chain_post: {e} \n\n memories={memories_retrieved}, characteristics={characteristics}")
        #     # 处理失败，返回空列表
        #     return []
