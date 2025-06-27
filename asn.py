# import warnings
# warnings.filterwarnings("ignore")
import os
import yaml
import json
import argparse
import threading
import random
import numpy as np
from datetime import datetime
from typing import List
from langchain_core.utils import mock_now
from asn.utils.time import *
from asn.data.data import Data, DataTransformerBluesky
from asn.env.environment import Environment, User, Message
from asn.llm.llm import LLMManager, set_sft, get_sft
from asn.utils.logger import get_logger, set_logger
from asn.utils.jsoncoder import DatetimeDecoder, DatetimeEncoder
from asn.example.utils import init_env_from_data, get_users_profile, replay_history, simulate_user


# Initialize settings
set_logger()
args = argparse.ArgumentParser()
args.add_argument("--config_path", "-c", type=str, default="config/example.yaml")
args = args.parse_args()
conf_path = args.config_path
with open(conf_path, "r") as f:
    conf = yaml.load(f, Loader=yaml.FullLoader)
for key, value in args.__dict__.items():
    conf[key] = value

# Print settings
settings = "Settings:\n"
for key, value in conf.items():
    settings += f"{key}: {value}\n"
get_logger().info(settings)
get_logger().debug(settings)
print(settings)

# Random seed
if "seed" in conf:
    seed = conf["seed"]
else:
    seed = 0
random.seed(conf["seed"])
np.random.seed(conf["seed"])

# Set LLMManager
LLMManager.set_manager(conf["llm"])
# set use_sft
if "use_sft" in conf["llm"] and conf["llm"]["use_sft"]:
    print("Using SFT")
    set_sft(True)
    print(get_sft())

# Load model or Initialize environment with loaded data
if conf["load_model"]:
    # Load model
    with open(conf["load_model"], "r") as f:
        model_dict = json.load(f)
    env = Environment.load_from_dict(model_dict["env"])
    get_logger().debug("Model loading...")
    get_logger().debug(f"Time: {env.now}")
    get_logger().debug(f"Users: {len(env.users)}")
    get_logger().debug(f"Messages: {len(env.messages)}")
    get_logger().debug(f"Recommender: {env.recommender}")
    get_logger().debug(f"Log: {len(env.log)}")
    get_logger().debug("Model loaded.")
else:
    # Load data
    # data = DataTransformerBluesky(conf["data_path"]).transform_data(conf["num_users"])
    # data = data.filter_by_time(conf["time_init_begin"], conf["time_sim_end"])
    data = Data.load_from_data(conf["data_path"])
    print("Data loaded.")

    # Initialize environment, user agents
    env = Environment()
    data.make_history()
    init_env_from_data(env, data)
    get_users_profile(env, data, conf["time_init_begin"], conf["time_init_end"], conf["interval"], conf["parallel"])
    data.save_data(conf["data_path"])
    replay_history(env, data, conf["time_init_begin"], conf["time_init_end"], conf["interval"], conf["parallel"])
    data.save_data(conf["data_path"])
    print("Environment initialized.")


# Simulate round by round
time_step = env.now.strftime(TIME_FORMAT) if conf["load_model"] else conf["time_sim_begin"]
env.update_time(datetime.strptime(time_step, TIME_FORMAT), conf["interval"])
while time_step < conf["time_sim_end"]:
    get_logger().info(f"Time {time_step} to {add_interval(time_step, conf['interval'])}")
    print(f"Time {time_step} to {add_interval(time_step, conf['interval'])}")
    with mock_now(env.now):
        if conf["parallel"]:
            threads: List[threading.Thread] = []
            for user in env.users:
                t = threading.Thread(target=simulate_user, args=(user, env, data, conf))
                threads.append(t)
                t.start()
            for t in threads:
                t.join()
        else:
            for user in env.users:
                simulate_user(user, env, data, conf)
    # Update time
    time_step = datetime.strftime(add_interval(time_step, conf["interval"]), TIME_FORMAT)
    env.update_time(datetime.strptime(time_step, TIME_FORMAT))
    # Save model
    get_logger().info(f"Saving models...")
    save_path = conf["save_path"] + f"/model_{env.now.strftime(TIME_FORMAT)}/".replace(" ", "_")
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    with open(os.path.join(save_path, f"model_{env.now.strftime(TIME_FORMAT)}.json".replace(" ", "_")), "w") as f:
        model_dict = {
            "env": env.save_to_dict(save_path),
        }
        json.dump(model_dict, f, indent=4)
    get_logger().info(f"Model saved to {save_path}")


# Simulate by time, with interval 1 hour
intv = conf["interval"]
time_step = env.now.strftime(TIME_FORMAT) if conf["load_model"] else conf["time_sim_begin"]
env.update_time(datetime.strptime(time_step, TIME_FORMAT), conf["interval"])
while time_step < conf["time_sim_end"]:
    get_logger().info(f"Time {time_step} to {add_interval(time_step, conf['interval'])}")
    print(f"Time {time_step} to {add_interval(time_step, conf['interval'])}")
    with mock_now(env.now):
        if conf["parallel"]:
            threads: List[threading.Thread] = []
            for user in env.users:
                t = threading.Thread(target=simulate_user, args=(user, env, data, conf))
                threads.append(t)
                t.start()
            for t in threads:
                t.join()
        else:
            for user in env.users:
                simulate_user(user, env, data, conf)
    # Update time
    time_step = datetime.strftime(add_interval(time_step, conf["interval"]), TIME_FORMAT)
    env.update_time(datetime.strptime(time_step, TIME_FORMAT))
    # Save model
    get_logger().info(f"Saving models...")
    save_path = conf["save_path"] + f"/model_{env.now.strftime(TIME_FORMAT)}/".replace(" ", "_")
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    with open(os.path.join(save_path, f"model_{env.now.strftime(TIME_FORMAT)}.json".replace(" ", "_")), "w") as f:
        model_dict = {
            "env": env.save_to_dict(save_path),
        }
        json.dump(model_dict, f, indent=4)
    get_logger().info(f"Model saved to {save_path}")
