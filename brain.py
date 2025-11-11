import sqlite3
import random
import time
import sys

# --- Configuration ---
DB_NAME = 'master_db.sqlite'
EXPLOIT_THRESHOLD = 0.8  # 80% chance to exploit, 20% to explore

# Define the parameter space for exploration
EXPLORE_GENRES = ['creepy pasta', 'weird history fact', 'shocking science fact', 'uplifting personal story', 'mind-bending puzzle']
EXPLORE_STYLES = ['photorealistic', 'digital painting', 'dark fantasy', 'anime', 'pixel art', 'cinematic']
EXPLORE_VOICES = ['en_US-kss-low', 'en_US-ljspeech-medium', 'en_US-vctk-low'] # Example voice IDs (adjust based on your chosen model)

# --- Database Functions ---

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}", file=sys.stderr)
        return None

def find_best_parameters(conn):
    """
    Finds the best-performing parameters (genre, image_style, voice)
    based on 'Fame Velocity'.
    
    Fame Velocity = Avg. view gain between 2 and 10 hours post-upload.
    This query is the core of the 'exploit' logic.
    """
    query = """
    WITH VideoGains AS (
        -- 1. Calculate the view gain for each video in the 2-10 hour window
        SELECT
            v.video_key,
            v.genre,
            v.image_style,
            v.voice,
            -- Find the difference between the max and min views in the window
            MAX(p.views) - MIN(p.views) AS view_gain
        FROM
            videos v
        JOIN
            performance_log p ON v.video_key = p.video_key
        WHERE
            -- Only look at videos that have been uploaded and analyzed
            v.status = 'ANALYZED' AND
            -- Define the 2-10 hour window (7200 to 36000 seconds)
            p.timestamp BETWEEN (v.upload_time + 7200) AND (v.upload_time + 36000)
        GROUP BY
            v.video_key, v.genre, v.image_style, v.voice
        HAVING
            -- Ensure we have at least two data points to measure a gain
            COUNT(p.log_id) > 1
    )
    -- 2. Average the view_gain for each unique combination of parameters
    SELECT
        genre,
        image_style,
        voice,
        AVG(view_gain) AS fame_velocity
    FROM
        VideoGains
    GROUP BY
        genre,
        image_style,
        voice
    ORDER BY
        fame_velocity DESC
    LIMIT 1;
    """
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        result = cursor.fetchone()
        if result:
            print(f"[Brain] Exploit: Found best parameters with {result['fame_velocity']:.0f} avg velocity.")
            return (result['genre'], result['image_style'], result['voice'])
    except sqlite3.Error as e:
        print(f"Error in 'exploit' query: {e}", file=sys.stderr)
        
    return None

def explore_parameters():
    """
S    elects a random set of parameters.
    This is the 'explore' logic.
    """
    print("[Brain] Explore: Trying a new combination.")
    genre = random.choice(EXPLORE_GENRES)
    style = random.choice(EXPLORE_STYLES)
    voice = random.choice(EXPLORE_VOICES)
    return (genre, style, voice)

def insert_new_job(conn, genre, style, voice):
    """
    Inserts a new PENDING job into the videos table.
    """
    video_key = f"v_{int(time.time())}"
    try:
        conn.execute(
            """
            INSERT INTO videos (video_key, status, genre, image_style, voice)
            VALUES (?, ?, ?, ?, ?)
            """,
            (video_key, 'PENDING', genre, style, voice)
        )
        conn.commit()
        print(f"[Brain] Success: Created new job '{video_key}' with genre '{genre}'.")
    except sqlite3.Error as e:
        print(f"Error inserting new job: {e}", file=sys.stderr)

# --- Main Logic ---

def main():
    """
    Main function for the 'Brain'.
    Implements the 80/20 Multi-Armed Bandit logic.
    """
    conn = get_db_connection()
    if not conn:
        return

    try:
        # Check if we have enough data to exploit
        best_params = find_best_parameters(conn)
        
        # Multi-Armed Bandit: 80% Exploit, 20% Explore
        if best_params and random.random() < EXPLOIT_THRESHOLD:
            # Exploit
            genre, style, voice = best_params
        else:
            # Explore (or exploit failed)
            genre, style, voice = explore_parameters()
            
        # Create the new job
        insert_new_job(conn, genre, style, voice)
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()
