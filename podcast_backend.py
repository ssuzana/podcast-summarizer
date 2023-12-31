import modal

def download_whisper():
  # Load the Whisper model
  import os
  import whisper
  print ("Download the Whisper model")

  # Perform download only once and save to Container storage
  whisper._download(whisper._MODELS["medium"], '/content/podcast/', False)


stub = modal.Stub("uplimit-podcast-project")
uplimit_image = modal.Image.debian_slim().pip_install("feedparser",
                                                     "https://github.com/openai/whisper/archive/9f70a352f9f8630ab3aa0d06af5cb9532bd8c21d.tar.gz",
                                                     "requests",
                                                     "ffmpeg",
                                                     "openai",
                                                     "tiktoken",
                                                     #"wikipedia",
                                                     "ffmpeg-python").apt_install("ffmpeg").run_function(download_whisper)

@stub.function(image=uplimit_image, gpu="any", timeout=1000)
def get_transcribe_podcast(rss_url, local_path):
  print ("Starting Podcast Transcription Function")
  print ("Feed URL: ", rss_url)
  print ("Local Path:", local_path)

  # Read from the RSS Feed URL
  import feedparser
  feed = feedparser.parse(rss_url)
  podcast_title = feed['feed']['title']
  episode_title = feed.entries[0]['title']
  episode_image = feed['feed']['image'].href
  episode_url = None  # Initialize episode_url to None
  for item in feed.entries[0].links:
    if (item['type'] == 'audio/mpeg' or item['type'] == 'audio/mp3'):
      episode_url = item.href
      break  # Exit the loop once a valid episode URL is found
  episode_name = "podcast_episode.mp3"
  print("RSS URL read and episode URL: ", episode_url)

  # Download the podcast episode by parsing the RSS feed
  from pathlib import Path
  p = Path(local_path)
  p.mkdir(exist_ok=True)

  print ("Downloading the podcast episode")
  import requests
  with requests.get(episode_url, stream=True) as r:
    r.raise_for_status()
    episode_path = p.joinpath(episode_name)
    with open(episode_path, 'wb') as f:
      for chunk in r.iter_content(chunk_size=8192):
        f.write(chunk)

  print ("Podcast Episode downloaded")

  # Load the Whisper model
  import os
  import whisper

  # Load model from saved location
  print ("Load the Whisper model")
  model = whisper.load_model('medium', device='cuda', download_root='/content/podcast/')

  # Perform the transcription
  print ("Starting podcast transcription")
  result = model.transcribe(local_path + episode_name)

  # Return the transcribed text
  print ("Podcast transcription completed, returning results...")
  output = {}
  output['podcast_title'] = podcast_title
  output['episode_title'] = episode_title
  output['episode_image'] = episode_image
  output['episode_audio_url'] = episode_url
  output['episode_transcript'] = result['text']
  return output

@stub.function(image=uplimit_image, secret=modal.Secret.from_name("my-openai-secret"))
def get_podcast_summary(podcast_transcript):
  import openai
  ## RETURN THE SUMMARY OF THE PODCAST USING OPENAI
  # Prepare the conversation input
  instructPrompt = """
  Provide a short summary of the transcript. Make sure to identify podcast hosts and starring guests. 
  Include a few details, if mentioned in the transcript, about who the starring guests are.
  """
  request = instructPrompt + podcast_transcript
  conversation = [
    {"role": "system", "content": "You are assisting in extracting podcast information for a newsletter."},
    {"role": "user", "content": request}
    ]
  # Call the OpenAI API  
  chatOutput = openai.ChatCompletion.create(model="gpt-3.5-turbo-16k",
                                            messages=conversation
                                            )
  # Extract and return the response content
  podcastSummary = chatOutput.choices[0].message.content
  return podcastSummary

@stub.function(image=uplimit_image, secret=modal.Secret.from_name("my-openai-secret"))
def get_podcast_people(podcast_transcript):
    import openai

    # Prepare the conversation input
    instructPrompt = """
    You will be given the transcript of a podcast episode. Please identify the hosts and starring guests (if any). 
    For example, if the hosts are Micah Sargent and Dan Morin and the guests are Kathy Campbell and Matthew Castanelli output
    "* Hosts: Micah Sargent, Dan Morin
     * Guests: Kathy Campbell, Matthew Castanelli"
    If there are no guests, say "* Guests: None".
    """
    request = instructPrompt + podcast_transcript[:10000]
    conversation = [
        {"role": "system", "content": "You will be given the transcript of a podcast episode."},
        {"role": "user", "content": request}
    ]

    # Call the OpenAI API
    chatOutput = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-16k",
        messages=conversation
    )

    # Extract and return the response content
    podcastPeople = chatOutput.choices[0].message['content']
    return podcastPeople

@stub.function(image=uplimit_image, secret=modal.Secret.from_name("my-openai-secret"))
def get_podcast_highlights(podcast_transcript):
    import openai
    instructPrompt = """
    Extract and make a list of the key moments from the following podcast transcript. 
    """
    request = instructPrompt + podcast_transcript


    conversation = [
        {"role": "system", "content": "You are assisting in extracting podcast highlights."},
        {"role": "assistant", "content": request}
    ]

    chatOutput = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-16k",
        messages=conversation
    )

    podcastHighlights = chatOutput.choices[0].message['content']
    return podcastHighlights


@stub.function(image=uplimit_image, secret=modal.Secret.from_name("my-openai-secret"), timeout=1200)
def process_podcast(url, path):
  output = {}
  podcast_details = get_transcribe_podcast.call(url, path)
  podcast_summary = get_podcast_summary.call(podcast_details['episode_transcript'])
  podcast_people = get_podcast_people.call(podcast_details['episode_transcript'])
  podcast_highlights = get_podcast_highlights.call(podcast_details['episode_transcript'])
  output['podcast_details'] = podcast_details
  output['podcast_summary'] = podcast_summary
  output['podcast_people'] = podcast_people
  output['podcast_highlights'] = podcast_highlights
  return output

@stub.local_entrypoint()
def test_method(url, path):
  output = {}
  podcast_details = get_transcribe_podcast.call(url, path)
  print ("Podcast Summary: ", get_podcast_summary.call(podcast_details['episode_transcript']))
  print ("Podcast Information: ", get_podcast_people.call(podcast_details['episode_transcript']))
  print ("Podcast Highlights: ", get_podcast_highlights.call(podcast_details['episode_transcript']))
