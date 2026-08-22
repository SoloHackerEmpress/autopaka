import asyncio
import base64
import json
import os
import subprocess
import sys
from telethon import Button, TelegramClient
from telethon.tl.types import DocumentAttributeVideo
import requests
import yt_dlp

API_ID = 21895887
API_HASH = '54f05f3363abfafc4574e1ce0800b407'
BOT_TOKEN = '8946231074:AAF2waV6NNiQN95mHnMRGxI5yVK0aPC9d8M'
CHANNEL_ID = -1003752062073

GITHUB_TOKEN = (
    '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'
)
REPO_OWNER = 'SoloHackerEmpress'
REPO_NAME = 'ad_view'
COUNT_FILE_PATH = 'link/count/last_change_file_count.json'
LINKS_DIR_PATH = 'link/links'
QUEUE_FILE = 'queue.json'


def get_github_file(path):
  try:
    url = (
        f'https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}'
    )
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
      data = r.json()
      content = base64.b64decode(data['content']).decode('utf-8')
      return json.loads(content), data['sha']
  except Exception as e:
    print(f'GitHub Fetch Error: {e}')
  return None, None


def update_github_file(path, content_dict, sha, message):
  try:
    url = (
        f'https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}'
    )
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    content_str = json.dumps(content_dict, indent=4)
    payload = {
        'message': message,
        'content': base64.b64encode(content_str.encode('utf-8')).decode('utf-8'),
        'sha': sha,
    }
    r = requests.put(url, headers=headers, json=payload)
    return r.status_code in [200, 201]
  except Exception as e:
    print(f'GitHub Update Error: {e}')
    return False


def create_github_file(path, content_dict, message):
  try:
    url = (
        f'https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}'
    )
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    content_str = json.dumps(content_dict, indent=4)
    payload = {
        'message': message,
        'content': base64.b64encode(content_str.encode('utf-8')).decode(
            'utf-8'
        ),
    }
    r = requests.put(url, headers=headers, json=payload)
    return r.status_code in [200, 201]
  except Exception as e:
    print(f'GitHub Create Error: {e}')
    return False


def get_video_metadata(file_path):
  cmd = (
      'ffprobe -v error -select_streams v:0 -show_entries'
      f' stream=width,height,duration -of json "{file_path}"'
  )
  result = subprocess.check_output(cmd, shell=True).decode('utf-8')
  data = json.loads(result)
  stream = data.get('streams', [{}])[0]
  return {
      'width': int(stream.get('width', 1280)),
      'height': int(stream.get('height', 720)),
      'duration': float(stream.get('duration', 0)),
  }


def create_grid_image(video_path, output_image, duration):
  start_time = 180 if duration > 400 else 20
  end_buffer = duration - 30
  interval = (end_buffer - start_time) / 4
  points = [start_time + (interval * i) + (interval / 2) for i in range(4)]
  select_expr = '+'.join([f'between(t,{p}-0.1,{p}+0.1)' for p in points])
  cmd = (
      f'ffmpeg -y -i "{video_path}" -vf'
      f' "select=\'{select_expr}\',scale=640:360,tile=2x2" -frames:v 1'
      f' "{output_image}"'
  )
  subprocess.run(
      cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
  )
  return os.path.exists(output_image)


async def send_via_telethon(
    client, file_path, title, web_thumb_url, video_url_original, is_grid_only
):
  print('Fetching GitHub count data...')
  count_data, count_sha = get_github_file(COUNT_FILE_PATH)
  if not count_data:
    print('Error: Could not fetch count data from GitHub.')
    return False
  new_count = count_data['last_count'] + 1
  new_link_path = f'{LINKS_DIR_PATH}/{new_count}.json'
  if not create_github_file(
      new_link_path, {'link': video_url_original}, f'Add link {new_count}'
  ):
    print('Error: Could not create link file in GitHub.')
    return False
  count_data['last_count'] = new_count
  update_github_file(
      COUNT_FILE_PATH, count_data, count_sha, f'Update count to {new_count}'
  )

  print('Extracting video metadata...')
  meta = get_video_metadata(file_path)
  duration = meta['duration']
  button_url = f'https://solohackerempress.github.io/ad_view/?{new_count}'

  if is_grid_only:
    print('Sending grid image to Telegram...')
    grid_file = 'grid.jpg'
    if create_grid_image(file_path, grid_file, duration):
      grid_cap = f'**{title}**\n\n> **THIS VIDEO CAN ONLY WATCH ONLINE**'
      await client.send_file(
          CHANNEL_ID,
          grid_file,
          caption=grid_cap,
          buttons=[Button.url('🌐 WATCH ONLINE', button_url)],
      )
      if os.path.exists(grid_file):
        os.remove(grid_file)
  else:
    print(
        'Uploading Original Quality video to Telegram (this may take a few'
        ' minutes)...'
    )
    thumb_path = 'thumb.jpg'
    got_thumb = False
    if web_thumb_url:
      try:
        r = requests.get(web_thumb_url, stream=True, timeout=10)
        if r.status_code == 200:
          with open(thumb_path, 'wb') as f:
            [f.write(chunk) for chunk in r.iter_content(1024)]
          got_thumb = True
      except:
        pass
    if not got_thumb:
      subprocess.run(
          f'ffmpeg -y -i "{file_path}" -ss 00:00:05 -vframes 1 "{thumb_path}"',
          shell=True,
          stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL,
      )
      got_thumb = os.path.exists(thumb_path)

    video_attributes = DocumentAttributeVideo(
        duration=int(duration),
        w=meta['width'],
        h=meta['height'],
        supports_streaming=True,
    )

    # Telethon upload එක සාර්ථක වීමට ලොකු Timeout එකක් සහ Chunk size එක වැඩි කිරීම
    await client.send_file(
        CHANNEL_ID,
        file_path,
        caption=title,
        thumb=thumb_path if got_thumb else None,
        supports_streaming=True,
        attributes=[video_attributes],
        buttons=[Button.url('🌐 Watch Online', button_url)],
        part_size_kb=512,  # ලොකු වීඩියෝ ඉක්මනින් හා ස්ථාවරව යැවීමට
    )
    if got_thumb and os.path.exists(thumb_path):
      os.remove(thumb_path)
    print('Original Quality Video uploaded successfully!')
  return True


async def main():
  client = TelegramClient('bot_session', API_ID, API_HASH)
  await client.start(bot_token=BOT_TOKEN)

  if not os.path.exists(QUEUE_FILE):
    print('No queue.json file found!')
    await client.disconnect()
    return

  with open(QUEUE_FILE, 'r') as f:
    links_data = json.load(f)

  pending_idx = -1
  pending_item = None
  for i, item in enumerate(links_data):
    if not item.get('is_done'):
      pending_idx = i
      pending_item = item
      break

  if pending_item is None or not pending_item.get('url'):
    print('No pending URLs to process.')
    await client.disconnect()
    return

  url = pending_item['url']
  is_grid_only = (pending_idx + 1) % 4 == 0

  # මෙතැනදී height<=1080 දමා Original High Quality එක ඉල්ලා ඇත
  ydl_opts = {
      'format': (
          'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'
      ),
      'outtmpl': 'vid.mp4',
      'quiet': True,
      'nocheckcertificate': True,
      'geo_bypass': True,
      'socket_timeout': 60,
      'http_headers': {
          'User-Agent': (
              'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
              ' (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
          ),
          'Accept': (
              'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8'
          ),
          'Accept-Language': 'en-US,en;q=0.9',
          'Referer': 'https://www.pornhub.com/',
      },
  }

  try:
    print(f'Starting Original Quality download for: {url}')
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
      info = ydl.extract_info(url, download=True)
      title = info.get('title', 'Video')
      web_thumb_url = info.get('thumbnail')

      success = await send_via_telethon(
          client, 'vid.mp4', title, web_thumb_url, url, is_grid_only
      )
      if success:
        links_data[pending_idx]['is_done'] = True
        with open(QUEUE_FILE, 'w') as f:
          json.dump(links_data, f, indent=2)
        print(f'Successfully posted item {pending_idx + 1}')
        if os.path.exists('vid.mp4'):
          os.remove('vid.mp4')
  except Exception as e:
    import traceback

    traceback.print_exc()
    print(f'Error processing video: {e}')

  await client.disconnect()


if __name__ == '__main__':
  asyncio.run(main())

