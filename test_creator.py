import sqlite3
import torch
from moviepy.editor import *
import os
import sys
import random
import re

# --- Configuration ---
DB_NAME = 'master_db.sqlite'
VIDEO_OUTPUT_DIR = 'created_videos'
print(f"[Test Creator] Running in DRY-RUN mode.")

# Ensure output directory exists
os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)

# --- Database Functions ---
# (Copied directly from creator.py)

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

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

def create_test_job(conn):
    """Inserts a new PENDING job specifically for this test."""
    video_key = f"v_test_{int(random.time())}"
    genre = "test_genre"
    style = "test_style"
    voice = "test_voice"
    try:
        conn.execute(
            """
            INSERT INTO videos (video_key, status, genre, image_style, voice)
            VALUES (?, ?, ?, ?, ?)
            """,
            (video_key, 'PENDING', genre, style, voice)
        )
        conn.commit()
        print(f"[Test Creator] Created test job: {video_key}")
        return video_key
    except sqlite3.Error as e:
        print(f"Error inserting test job: {e}", file=sys.stderr)
        return None

# --- Mock AI Functions ---

def mock_generate_text_and_sentences():
    """Mocks the text generation pipeline."""
    print("[Test Creator] MOCK: Generating text.")
    story = "This is a test story. It has three sentences. This is the third and final sentence."
    sentences = ["This is a test story.", "It has three sentences.", "This is the third and final sentence."]
    return story, sentences

def mock_generate_speech(video_key, duration_seconds):
    """Mocks the speech generation, creating a silent MP3."""
    print("[Test Creator] MOCK: Generating silent audio.")
    audio_path = os.path.join(VIDEO_OUTPUT_DIR, f"{video_key}_narration.mp3")
    
    # Create a silent audio clip of the specified duration
    silent_clip = AudioClip(lambda t: 0, duration=duration_seconds, fps=44100)
    silent_clip.write_audiofile(audio_path, logger=None)
    
    return audio_path

def mock_generate_images(video_key, num_images):
    """Mocks the image generation, creating solid color placeholder images."""
    print(f"[Test Creator] MOCK: Generating {num_images} placeholder images.")
    image_paths = []
    hook_prompt = "mocked hook prompt (first sentence)"
    
    for i in range(num_images):
        img_path = os.path.join(VIDEO_OUTPUT_DIR, f"{video_key}_img_{i}.png")
        # Create a random solid color image
        color = (random.randint(50, 200), random.randint(50, 200), random.randint(50, 200))
        clip = ColorClip(size=(1080, 1920), color=color, duration=0.1)
        clip.save_frame(img_path)
        image_paths.append(img_path)
        
    return image_paths, hook_prompt

# --- Video Assembly Functions ---
# (Copied directly from creator.py)

def create_ken_burns_clip(image_path, duration, clip_size):
    """Creates a single ImageClip with a Ken Burns (pan and zoom) effect."""
    w, h = clip_size
    img_clip = (ImageClip(image_path)
                .set_duration(duration)
                .resize(height=h * 1.5))
    img_clip = img_clip.crop(x_center=img_clip.w / 2, y_center=img_clip.h / 2, width=w, height=h)
    zoomed_clip = img_clip.fx(vfx.resize, newsize=lambda t: 1.5 - 0.4 * (t / duration))
    pan_x = random.choice([-10, 10]) * (duration)
    final_clip = zoomed_clip.set_position(lambda t: ('center', 'center'))
    return final_clip

def create_video_file(video_key, sentences, image_paths, audio_path):
    """Assembles images, audio, and captions into the final MP4."""
    print(f"[Test Creator] Assembling video for {video_key}...")
    audio_clip = AudioFileClip(audio_path)
    video_duration = audio_clip.duration
    duration_per_image = video_duration / len(image_paths)
    clip_size = (1080, 1920)

    image_clips = []
    for i, img_path in enumerate(image_paths):
        clip = create_ken_burns_clip(img_path, duration_per_image, clip_size)
        clip = clip.set_start(i * duration_per_image)
        image_clips.append(clip)

    caption_clips = []
    duration_per_sentence = video_duration / len(sentences)
    for i, sentence in enumerate(sentences):
        caption = (TextClip(sentence,
                             fontsize=80,
                             color='white',
                             font='Inter-Bold',
                             stroke_color='black',
                             stroke_width=2,
                             method='caption',
                             size=(clip_size[0] * 0.8, None))
                   .set_duration(duration_per_sentence)
                   .set_start(i * duration_per_sentence)
                   .set_position(('center', 0.8), relative=True))
        caption_clips.append(caption)

    final_video = CompositeVideoClip(image_clips + caption_clips, size=clip_size)
    final_video = final_video.set_audio(audio_clip)
    final_video = final_video.set_duration(video_duration)
    
    output_path = os.path.join(VIDEO_OUTPUT_DIR, f"{video_key}_final.mp4")
    final_video.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac', logger=None)
    
    return output_path

def create_caption_file(video_key, story, genre, hook):
    """Creates the text file with YouTube Title, Description, and data-tag."""
    # (Copied directly from creator.py)
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
        
    video_key = create_test_job(conn)
    if not video_key:
        conn.close()
        return

    # Get the job details we just created
    job = conn.execute("SELECT * FROM videos WHERE video_key = ?", (video_key,)).fetchone()
    
    try:
        # 1. Set status to CREATING
        update_job_status(conn, video_key, 'CREATING')

        # 2. Mock Generate Text
        story, sentences = mock_generate_text_and_sentences()
        
        # 3. Mock Generate Speech
        # (3.5 seconds per sentence)
        video_duration = len(sentences) * 3.5 
        audio_path = mock_generate_speech(video_key, video_duration)

        # 4. Mock Generate Images (one per sentence)
        image_paths, hook_prompt = mock_generate_images(video_key, len(sentences))
        
        # 5. Assemble Video (REAL)
        video_path = create_video_file(video_key, sentences, image_paths, audio_path)

        # 6. Create Caption File (REAL)
        caption_path = create_caption_file(video_key, story, job['genre'], hook_prompt)

        # 7. Update Status to CREATED (REAL)
        update_job_status(conn, video_key, 'CREATED', script=story, hook=hook_prompt)
        
        print(f"[Test Creator] Success: Job {video_key} complete!")
        print(f"  -> Video: {video_path}")
        print(f"  -> Caption: {caption_path}")

    except Exception as e:
        print(f"Error processing test job {video_key}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        update_job_status(conn, video_key, 'FAILED')
    finally:
        conn.close()

if __name__ == "__main__":
    main()
