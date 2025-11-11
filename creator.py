import sqlite3
import torch
from transformers import pipeline, SpeechT5Processor, SpeechT5ForTextToSpeech, SpeechT5HifiGan
from diffusers import StableDiffusionXLPipeline, AutoencoderKL
from moviepy.editor import *
import os
import sys
from datasets import load_dataset
import re

# --- Configuration ---
DB_NAME = 'master_db.sqlite'
VIDEO_OUTPUT_DIR = 'created_videos'
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[Creator] Using device: {DEVICE}")

# Ensure output directory exists
os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)

# --- Database Functions ---

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def get_pending_job(conn):
    """Fetches the oldest PENDING job."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM videos WHERE status = 'PENDING' ORDER BY video_key LIMIT 1")
    return cursor.fetchone()

def update_job_status(conn, video_key, status, script=None, hook=None):
    """Updates the status and (optionally) the generated script/hook of a job."""
    sql = "UPDATE videos SET status = ?"
    params = [status]
    
    if script:
        sql += ", generated_script = ?"
        params.append(script)
    if hook:
        sql += ", hook_prompt = ?"
        params.append(hook)
        
    sql += " WHERE video_key = ?"
    params.append(video_key)
    
    conn.execute(sql, tuple(params))
    conn.commit()

# --- AI Model Functions ---

def initialize_models():
    """Loads all necessary AI models into memory."""
    print("[Creator] Loading all AI models...")
    try:
        # Text Generation (e.g., GPT-2)
        text_generator = pipeline('text-generation', model='gpt2', device=DEVICE)
        
        # Speech Generation (e.g., SpeechT5)
        speech_processor = SpeechT5Processor.from_pretrained("microsoft/speecht5_tts")
        speech_model = SpeechT5ForTextToSpeech.from_pretrained("microsoft/speecht5_tts").to(DEVICE)
        vocoder = SpeechT5HifiGan.from_pretrained("microsoft/speecht5_hifigan").to(DEVICE)
        
        # Load speaker embeddings (using a standard dataset)
        speaker_embeddings = load_dataset("Matthijs/cmu-arctic-xvectors", split="validation")
        # Pre-select a few speaker embeddings for variety
        speaker_embedding_map = {
            'en_US-kss-low': torch.tensor(speaker_embeddings[7306]['xvector']).unsqueeze(0).to(DEVICE),
            'en_US-ljspeech-medium': torch.tensor(speaker_embeddings[500]['xvector']).unsqueeze(0).to(DEVICE),
            'en_US-vctk-low': torch.tensor(speaker_embeddings[2100]['xvector']).unsqueeze(0).to(DEVICE),
        }

        # Image Generation (e.g., Stable Diffusion XL)
        # Load VAE for better performance/memory
        vae = AutoencoderKL.from_pretrained("madebyollin/sdxl-vae-fp16-fix", torch_dtype=torch.float16)
        image_generator = StableDiffusionXLPipeline.from_pretrained(
            "stabilityai/stable-diffusion-xl-base-1.0",
            vae=vae,
            torch_dtype=torch.float16,
            variant="fp16",
            use_safetensors=True
        ).to(DEVICE)
        
        print("[Creator] All models loaded successfully.")
        return text_generator, speech_processor, speech_model, vocoder, speaker_embedding_map, image_generator
    
    except Exception as e:
        print(f"Error loading models: {e}. Check VRAM and dependencies.", file=sys.stderr)
        return (None,) * 6

def generate_text_and_sentences(generator, genre):
    """Generates a short story and splits it into sentences."""
    prompt = f"Write a 150-word {genre} story that is shocking, viral, and has a twist ending. The story must be captivating for a short video. Story:"
    
    # max_length should be prompt_length + new_tokens
    response = generator(prompt, max_length=200, num_return_sequences=1, truncation=True)
    story_text = response[0]['generated_text'].replace(prompt, "").strip()
    
    # Clean up and split into sentences
    story_text = story_text.replace("\n", " ").replace("..", ".").strip()
    sentences = re.split(r'(?<=[.!?])\s+', story_text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    return story_text, sentences

def generate_speech(processor, model, vocoder, speaker_embedding, text, output_path):
    """Converts text to an MP3 file."""
    inputs = processor(text=text, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        speech = model.generate_speech(inputs["input_ids"], speaker_embedding, vocoder=vocoder)
    
    # Save as wav first (as that's the raw output)
    import soundfile as sf
    temp_wav = output_path.replace(".mp3", ".wav")
    sf.write(temp_wav, speech.cpu().numpy(), samplerate=16000)
    
    # Convert wav to mp3 using moviepy (or ffmpeg)
    AudioFileClip(temp_wav).write_audiofile(output_path, logger=None)
    os.remove(temp_wav)
    return output_path

def generate_images(generator, sentences, style, video_key):
    """Generates 3-5 images based on key sentences."""
    image_paths = []
    num_images = min(max(3, len(sentences) // 2), 5) # Aim for 3-5 images
    
    # 1. Generate Hook Image (from first sentence)
    hook_prompt = f"{sentences[0]}, {style}, cinematic, high detail, trending on artstation"
    print(f"[Creator] Generating hook image: {hook_prompt}")
    image = generator(prompt=hook_prompt, num_inference_steps=25).images[0]
    img_path = os.path.join(VIDEO_OUTPUT_DIR, f"{video_key}_img_0.png")
    image.save(img_path)
    image_paths.append(img_path)

    # 2. Generate Subsequent Images
    sentence_indices = [i * (len(sentences) // (num_images - 1)) for i in range(1, num_images)]
    
    for i, sent_idx in enumerate(sentence_indices):
        if sent_idx < len(sentences):
            prompt = f"{sentences[sent_idx]}, {style}, cinematic, atmospheric"
            print(f"[Creator] Generating image {i+1}: {prompt}")
            image = generator(prompt=prompt, num_inference_steps=20).images[0]
            img_path = os.path.join(VIDEO_OUTPUT_DIR, f"{video_key}_img_{i+1}.png")
            image.save(img_path)
            image_paths.append(img_path)
            
    return image_paths, hook_prompt

# --- Video Assembly Functions ---

def create_ken_burns_clip(image_path, duration, clip_size):
    """Creates a single ImageClip with a Ken Burns (pan and zoom) effect."""
    
    # Define clip size
    w, h = clip_size
    
    # Load image, crop to 9:16 aspect ratio
    img_clip = (ImageClip(image_path)
                .set_duration(duration)
                .resize(height=h * 1.5)) # Start zoomed in (1.5x)
    
    # Crop to 9:16
    img_clip = img_clip.crop(x_center=img_clip.w / 2, y_center=img_clip.h / 2, width=w, height=h)

    # Animate zoom (from 1.5x to 1.1x)
    zoomed_clip = img_clip.fx(vfx.resize, newsize=lambda t: 1.5 - 0.4 * (t / duration))
    
    # Animate pan (slight horizontal movement)
    pan_x = random.choice([-10, 10]) * (duration) # pixels to move
    final_clip = zoomed_clip.set_position(lambda t: ('center', 'center'))

    return final_clip

def create_video_file(video_key, sentences, image_paths, audio_path):
    """Assembles images, audio, and captions into the final MP4."""
    
    print(f"[Creator] Assembling video for {video_key}...")
    
    audio_clip = AudioFileClip(audio_path)
    video_duration = audio_clip.duration
    duration_per_image = video_duration / len(image_paths)
    
    clip_size = (1080, 1920) # YouTube Short format (9:16)
    
    # Create Ken Burns clips
    image_clips = []
    for i, img_path in enumerate(image_paths):
        clip = create_ken_burns_clip(img_path, duration_per_image, clip_size)
        clip = clip.set_start(i * duration_per_image)
        image_clips.append(clip)

    # Create Captions (simple one-by-one)
    # This is a simple implementation. A better one would time-base it.
    caption_clips = []
    duration_per_sentence = video_duration / len(sentences)
    for i, sentence in enumerate(sentences):
        caption = (TextClip(sentence,
                             fontsize=80,
                             color='white',
                             font='Inter-Bold', # Assumes 'Inter-Bold' is available
                             stroke_color='black',
                             stroke_width=2,
                             method='caption',
                             size=(clip_size[0] * 0.8, None)) # 80% width
                   .set_duration(duration_per_sentence)
                   .set_start(i * duration_per_sentence)
                   .set_position(('center', 0.8), relative=True)) # 80% down
        caption_clips.append(caption)

    # Combine all clips
    final_video = CompositeVideoClip(image_clips + caption_clips, size=clip_size)
    final_video = final_video.set_audio(audio_clip)
    final_video = final_video.set_duration(video_duration)
    
    output_path = os.path.join(VIDEO_OUTPUT_DIR, f"{video_key}_final.mp4")
    final_video.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac', logger=None)
    
    return output_path

def create_caption_file(video_key, story, genre, hook):
    """Creates the text file with YouTube Title, Description, and data-tag."""
    
    title = f"Shocking {genre.title()} Story! 😱 #shorts #{genre.replace(' ', '')}"
    description = f"""
A {genre} story generated by the Fame Flywheel.

What do you think of the ending? Let us know in the comments!

#shorts #ai #storytelling #{genre.replace(' ', '')}

---
[data-tag: {video_key}]
[hook-prompt: {hook}]
"""
    output_path = os.path.join(VIDEO_OUTPUT_DIR, f"{video_key}_caption.txt")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"TITLE:\n{title}\n\n")
        f.write(f"DESCRIPTION:\n{description}\n")
    return output_path

# --- Main Logic ---

def main():
    conn = get_db_connection()
    if not conn:
        return
        
    job = get_pending_job(conn)
    if not job:
        print("[Creator] No pending jobs found.")
        conn.close()
        return

    video_key = job['video_key']
    genre = job['genre']
    style = job['image_style']
    voice = job['voice']
    
    try:
        # 1. Set status to CREATING
        update_job_status(conn, video_key, 'CREATING')

        # 2. Load models
        models = initialize_models()
        if not models[0]: # Check if text_generator loaded
            raise Exception("Failed to initialize models.")
        
        text_gen, speech_proc, speech_model, vocoder, speaker_map, img_gen = models
        
        # 3. Generate Text
        print(f"[Creator] Generating text for {video_key}...")
        story, sentences = generate_text_and_sentences(text_gen, genre)
        
        # 4. Generate Speech
        print(f"[Creator] Generating speech for {video_key}...")
        audio_path = os.path.join(VIDEO_OUTPUT_DIR, f"{video_key}_narration.mp3")
        speaker_embedding = speaker_map.get(voice, speaker_map['en_US-ljspeech-medium']) # Default
        generate_speech(speech_proc, speech_model, vocoder, speaker_embedding, story, audio_path)

        # 5. Generate Images
        print(f"[Creator] Generating images for {video_key}...")
        image_paths, hook_prompt = generate_images(img_gen, sentences, style, video_key)
        
        # 6. Assemble Video
        print(f"[Creator] Assembling video for {video_key}...")
        video_path = create_video_file(video_key, sentences, image_paths, audio_path)

        # 7. Create Caption File
        caption_path = create_caption_file(video_key, story, genre, hook_prompt)

        # 8. Update Status to CREATED
        update_job_status(conn, video_key, 'CREATED', script=story, hook=hook_prompt)
        
        print(f"[Creator] Success: Job {video_key} complete!")
        print(f"  -> Video: {video_path}")
        print(f"  -> Caption: {caption_path}")

    except Exception as e:
        print(f"Error processing job {video_key}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        update_job_status(conn, video_key, 'FAILED')
    finally:
        conn.close()

if __name__ == "__main__":
    main()
