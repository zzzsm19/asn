import random
import json

def get_gpu_mem_info(gpu_id=0):
    import pynvml
    pynvml.nvmlInit()
    if gpu_id < 0 or gpu_id >= pynvml.nvmlDeviceGetCount():
        print("GPU {gpu_id} does not exist!".format(gpu_id=gpu_id))
        return 0, 0, 0

    handler = pynvml.nvmlDeviceGetHandleByIndex(gpu_id)
    meminfo = pynvml.nvmlDeviceGetMemoryInfo(handler)
    total = round(meminfo.total / 1024 / 1024, 2)
    used = round(meminfo.used / 1024 / 1024, 2)
    free = round(meminfo.free / 1024 / 1024, 2)
    print("GPU memory info: total: {total}, used: {used}, free: {free}".format(total=total, used=used, free=free))
    return total, used, free

def react_list_to_str(react_list):
    s = ""
    if len(react_list) == 0:
        return "None"
    if "like" in react_list:
        s += "Like"
    if "share" in react_list:
        if s:
            s += ", "
        s += "Share"
    return s

def react_list_to_json_str(react_list):
    json_ = {
        "Like": "No",
        "Share": "No"
    }
    if "like" in react_list:
        json_["Like"] = "Yes"
    if "share" in react_list:
        json_["Share"] = "Yes"
    return json.dumps(json_)

def choices_history(history, choices_num):
    day = list(history.keys())[0]
    new_history = {day: []}
    acts = random.choices(history[day], k=min(choices_num, len(history[day])))
    for act in acts:
        new_history[day].append(act)
    return new_history

def fake_history_to_example_reacts(fake_history, choices_num=-1):
    if choices_num > 0:
        fake_history = choices_history(fake_history, choices_num)
    day = list(fake_history.keys())[0]
    acts = fake_history[day]
    experience = ""
    # experience = "Day %s\n: " % day[:10]
    experience += "The user read several posts:\n" + "\n".join(["%d. %s" % (idx + 1, act["text"]) for idx, act in enumerate(acts) if act["type"] == "read"]) + "\n"
    experience += "The user reaction for each post:\n" + "\n".join("[Action %d] %s [END]" % (idx, react_list_to_str(act["result"])) for idx, act in enumerate(acts) if act["type"] == "read") + "\n"
    return experience

def fake_history_to_example_react(fake_history, choices_num=-1):
    if choices_num > 0:
        fake_history = choices_history(fake_history, choices_num)
    day = list(fake_history.keys())[0]
    acts = fake_history[day]
    experience = ""
    # experience = "Day %s\n: " % day[:10]
    for act in acts:
        if "type" not in act:
            print(act)
        if act["type"] == "read":
            experience += "The user read a post:\n\"\"\"%s\"\"\"\n" % act["text"]
            experience += "The user reaction:\n%s\n" % react_list_to_json_str(act["result"])
    return experience

def fake_history_to_example_post(fake_history, choices_num=-1):
    if choices_num > 0:
        fake_history = choices_history(fake_history, choices_num)
    day = list(fake_history.keys())[0]
    acts = fake_history[day]
    experience = ""
    # experience = "Day %s:\n " % day[:10]
    for act in acts:
        if act["type"] == "post":
            if act["text"] == "no post":
                experience += "The user did not post anything\n"
            else:
                experience += "The user posted:\n\"\"\"%s\"\"\"\n" % act["text"]
    return experience


def history_to_experience(history):
    experience = ""
    day = list(history.keys())[0]
    acts = history[day]
    if len(acts) == 0:
        experience = "The user's behaviors on %s: No activities this day." % day[:10]
    else:
        experience = "The user's behaviors on %s: " % day[:10] + "\n".join(["%s: %s" % (act["type"], act["text"]) for act in acts])
    return experience