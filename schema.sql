-- This schema defines the two core tables for the Fame Flywheel system.

-- The 'videos' table is the central command and control table.
-- It tracks a video's entire lifecycle, from PENDING to ANALYZED.
CREATE TABLE IF NOT EXISTS videos (
    video_key TEXT PRIMARY KEY,       -- A unique, system-generated ID (e.g., 'v_1678886400')
    youtube_id TEXT,                  -- The ID from YouTube (e.g., '_Hq1mF-gq0Y'), added manually by the user post-upload.
    status TEXT NOT NULL,             -- The current state: PENDING, CREATING, CREATED, UPLOADED, ANALYZED
    genre TEXT NOT NULL,              -- The story genre (e.g., 'creepy', 'lifehack', 'history')
    voice TEXT NOT NULL,              -- The voice model used (e.g., 'speecht5_voice_1')
    image_style TEXT NOT NULL,        -- The visual style (e.g., 'digital_painting', 'photorealistic', 'anime')
    upload_time INTEGER,              -- The UNIX timestamp when the user marked it as UPLOADED.
    
    -- Store the generated script and prompt for potential future analysis
    generated_script TEXT,
    hook_prompt TEXT
);

-- The 'performance_log' table stores time-series data for each video.
-- This is the raw data used by the 'brain' to calculate 'Fame Velocity'.
CREATE TABLE IF NOT EXISTS performance_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_key TEXT NOT NULL,          -- Foreign key linking to the videos table
    timestamp INTEGER NOT NULL,       -- The UNIX timestamp when this data point was recorded
    views INTEGER NOT NULL,
    likes INTEGER NOT NULL,
    comments INTEGER NOT NULL,
    
    FOREIGN KEY (video_key) REFERENCES videos (video_key)
);
