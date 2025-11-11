import sqlite3
import time
import os
import sys
from googleapiclient.discovery import build

# --- Configuration ---
DB_NAME = 'master_db.sqlite'

# !! IMPORTANT !! Set this environment variable before running.
# On Linux/macOS: export YOUTUBE_API_KEY="your_api_key_here"
# On Windows: set YOUTUBE_API_KEY="your_api_key_here"
API_KEY = os.environ.get('YOUTUBE_API_KEY')
YOUTUBE_API_SERVICE_NAME = 'youtube'
YOUTUBE_API_VERSION = 'v3'

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

def get_uploaded_videos(conn):
    """
    Fetches all videos marked as 'UPLOADED' or 'ANALYZED'
    that were uploaded in the last 7 days.
    """
    seven_days_ago = int(time.time()) - (7 * 24 * 60 * 60)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT video_key, youtube_id FROM videos
        WHERE status IN ('UPLOADED', 'ANALYZED') AND upload_time > ?
        """,
        (seven_days_ago,)
    )
    return cursor.fetchall()

def insert_performance_log(conn, video_key, views, likes, comments):
    """Inserts a new row into the performance_log table."""
    timestamp = int(time.time())
    try:
        conn.execute(
            """
            INSERT INTO performance_log (video_key, timestamp, views, likes, comments)
            VALUES (?, ?, ?, ?, ?)
            """,
            (video_key, timestamp, views, likes, comments)
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error inserting log for {video_key}: {e}", file=sys.stderr)

def update_video_status(conn, video_key, new_status):
    """Updates a video's status, e.g., from UPLOADED to ANALYZED."""
    try:
        conn.execute("UPDATE videos SET status = ? WHERE video_key = ?", (new_status, video_key))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error updating status for {video_key}: {e}", file=sys.stderr)


# --- YouTube API Functions ---

def get_youtube_service():
    """Initializes the YouTube Data API service."""
    if not API_KEY:
        print("Error: YOUTUBE_API_KEY environment variable not set.", file=sys.stderr)
        return None
    try:
        return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=API_KEY)
    except Exception as e:
        print(f"Error building YouTube service: {e}", file=sys.stderr)
        return None

def get_video_stats(service, youtube_id):
    """Fetches the latest view, like, and comment count for a video."""
    try:
        request = service.videos().list(
            part="statistics",
            id=youtube_id
        )
        response = request.execute()
        
        if not response.get('items'):
            print(f"Warning: No video found with ID {youtube_id}", file=sys.stderr)
            return None

        stats = response['items'][0]['statistics']
        return {
            'views': int(stats.get('viewCount', 0)),
            'likes': int(stats.get('likeCount', 0)),
            'comments': int(stats.get('commentCount', 0))
        }
    except Exception as e:
        print(f"Error fetching stats for {youtube_id}: {e}", file=sys.stderr)
        return None

# --- Main Logic ---

def main():
    """
    Main function for the 'Collector'.
    Runs hourly (via cron) to fetch new stats for active videos.
    """
    print("[Collector] Starting run...")
    
    service = get_youtube_service()
    if not service:
        return

    conn = get_db_connection()
    if not conn:
        return

    try:
        videos_to_check = get_uploaded_videos(conn)
        if not videos_to_check:
            print("[Collector] No active videos to check.")
            return

        print(f"[Collector] Checking stats for {len(videos_to_check)} videos...")
        
        for video in videos_to_check:
            video_key = video['video_key']
            youtube_id = video['youtube_id']
            
            if not youtube_id:
                print(f"Warning: Skipping {video_key}, no youtube_id.", file=sys.stderr)
                continue

            stats = get_video_stats(service, youtube_id)
            if stats:
                insert_performance_log(
                    conn,
                    video_key,
                    stats['views'],
                    stats['likes'],
                    stats['comments']
                )
                print(f"  -> Logged {video_key}: {stats['views']} views")

                # After 12 hours, mark as ANALYZED so the brain can use it
                upload_time = conn.execute("SELECT upload_time FROM videos WHERE video_key = ?", (video_key,)).fetchone()[0]
                if (time.time() - upload_time) > 43200: # 12 hours
                    update_video_status(conn, video_key, 'ANALYZED')

    finally:
        conn.close()
        print("[Collector] Run complete.")

if __name__ == "__main__":
    main()
