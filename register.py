from mastodon import Mastodon
from argparse import ArgumentParser
import os
from asn.data.data import Data
from faker import Faker
from multiavatar.multiavatar import multiavatar
from cairosvg import svg2png

CLIENT_NAME = 'ASN'
CLIENT_ID = 'ASN.secret'
API_BASE_URL = 'https://asn25.top'

# 部署或重置服务器后首次注册时，需要创建app
Mastodon.create_app(
    'ASN',
    api_base_url=API_BASE_URL,
    to_file=CLIENT_ID
)

parser = ArgumentParser()
parser.add_argument('--data_path', '-d', type=str, default='dataset/example.json')
parser.add_argument('--avatar_path', '-a', type=str, default='/data1/zhushengmao/avatar/')
args = parser.parse_args()

mastodon = Mastodon(client_id=CLIENT_ID)

def register(username, password, email):
    return mastodon.create_account(
        username,
        password=password,
        email=email,
        agreement=True
    )

def follow(follower, followee):
    mastodon_follower = Mastodon(access_token=data.get_meta(follower["id"], 'mastodon_info')["access_token"], api_base_url=API_BASE_URL)
    mastodon_follower.account_follow(data.get_meta(followee["id"], 'mastodon_info')["id"])

if __name__ == '__main__':
    data = Data.load_from_data(args.data_path)
    users = data.users
    name_set = set()
    for i, user in enumerate(users):
        try:
            username = Faker(locale='').name().replace(' ', '_').replace('.', '')
            while username.lower() in name_set:
                username = Faker(locale='').name().replace(' ', '_').replace('.', '')
            name_set.add(username.lower())
            email = username.lower() + '@dummy.com'
            password = 'asn25top'
            access_token = register(username, password, email)
            data.set_meta(user["id"], 'mastodon_info', {
                # "id": str(Mastodon(access_token=access_token, api_base_url=API_BASE_URL).me()["id"]),
                "username": username,
                "password": password,
                "email": email,
                "access_token": access_token,
                "api_base_url": API_BASE_URL,
                "client_id": CLIENT_ID,
            })
            print(f'User {username} with email {email} registered successfully.')
        except Exception as e:
            print(f'Error: {e}')
            print(username, email, password)
            print(f'{i} users have been registered.')
            break
    data.save_data(args.data_path)

    # 请联系mastodon服务器管理员确认新注册账号的邮箱。是否已经确认？
    confirmed = input('Please contact the mastodon server administrator to confirm the email of the newly registered account. Has it been confirmed? (Y/n) ')
    if confirmed.lower() == 'n':
        exit(0)

    # 登录并保存mastodon信息
    print('Logging in and saving mastodon information...')
    for user in users:
        mastodon_info = data.get_meta(user["id"], 'mastodon_info')
        mastodon_user = Mastodon(access_token=mastodon_info["access_token"], api_base_url=API_BASE_URL)
        mastodon_info["id"] = str(mastodon_user.me()["id"])
        # for key in mastodon_user.me():
        #     if key not in mastodon_info:
        #         mastodon_info[key] = mastodon_user.me()[key]
        data.set_meta(user["id"], 'mastodon_info', mastodon_info)
    data.save_data(args.data_path)
    
    # 建立follow关系
    print('Building follow relationships...')
    for user in users:
        followee_ids = data.get_user_following_ids(user["id"])
        for followee_id in followee_ids:
            followee = data.get_user(followee_id)
            follow(user, followee)
    
    # 创建头像
    avatar_path = args.avatar_path
    if not os.path.exists(avatar_path):
        os.makedirs(avatar_path)
    print('Creating avatars...')
    for user in users:
        mastodon_info = data.get_meta(user["id"], 'mastodon_info')
        svgCode = multiavatar(mastodon_info["username"], sansEnv=None, ver=None)
        png_path = avatar_path + mastodon_info["username"]
        svg2png(bytestring=svgCode, write_to=png_path)
        mastodon = Mastodon(access_token=mastodon_info["access_token"], api_base_url=API_BASE_URL)
        mastodon.account_update_credentials(avatar=png_path)
