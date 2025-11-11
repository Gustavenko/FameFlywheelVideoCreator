# **Fame Flywheel MVP**

This project is a scalable MVP for creating and optimizing viral YouTube Shorts using 100% local, open-source AI models.

It consists of three Python scripts and a central SQLite database that work together in a continuous feedback loop.

* **brain.py**: Decides *what* to make (Exploit vs. Explore).  
* **creator.py**: *Builds* the video (Text, Voice, Images, Video).  
* **feedback.py**: *Learns* from YouTube analytics.

## **System Setup**

1. **Clone & Install:**  
   git clone \[your-repo-url\]  
   cd fame-flywheel-mvp  
   pip install \-r requirements.txt

2. Download Models:  
   The first time you run creator.py, it will download several gigabytes of models from Hugging Face (e.g., gpt2, SpeechT5, StableDiffusionXLPipeline). This is a one-time setup.  
3. **Get YouTube API Key:**  
   * Go to the [Google Cloud Console](https://console.cloud.google.com/).  
   * Create a new project.  
   * Enable the "YouTube Data API v3".  
   * Create an API Key under "Credentials".  
   * **Set the environment variable:**  
     \# On Linux/macOS  
     export YOUTUBE\_API\_KEY="your\_api\_key\_here"

     \# On Windows  
     set YOUTUBE\_API\_KEY="your\_api\_key\_here"

4. Initialize Database:  
   The scripts will create master\_db.sqlite automatically. You can inspect it using sqlite3 master\_db.sqlite and running the CREATE TABLE commands from schema.sql if needed.

## **The 5-Step Manual Workflow**

This is an MVP, so some steps are manual. Follow this loop.

### **Step 1: Run the "Brain"**

The Brain decides what video to make next.

python brain.py

This will run the 80/20 logic and insert a new row in the videos table with status \= 'PENDING'.

### **Step 2: Run the "Factory"**

The Creator finds the PENDING job and builds the video. This will take time and requires a good GPU.

python creator.py

On success, two files will appear in the created\_videos/ directory:

* v\_1678886400\_final.mp4  
* v\_1678886400\_caption.txt

The script will update the video's status to CREATED.

### **Step 3: Manual Upload to YouTube**

* Go to YouTube and upload the \_final.mp4 file as a Short.  
* Open the \_caption.txt file. Copy/paste the generated Title and Description.  
* **Publish the video.**

### **Step 4: Manual Database Update (CRITICAL)**

This is the most important manual step. You *must* tell the system what the new video's YouTube ID is.

1. Get the YouTube ID from the video's URL (e.g., https://youtube.com/shorts/**\_Hq1mF-gq0Y**).  
2. Get the video\_key from the filename (e.g., **v\_1678886400**).  
3. Run this SQL command in your terminal:

sqlite3 master\_db.sqlite "UPDATE videos SET status \= 'UPLOADED', youtube\_id \= '\_Hq1mF-gq0Y', upload\_time \= strftime('%s', 'now') WHERE video\_key \= 'v\_1678886400';"

*(Replace the youtube\_id and video\_key with your actual values)*.

The video is now UPLOADED and the feedback.py script will start tracking it.

### **Step 5: Schedule the "Collector"**

The Collector feeds the Brain. You must run it on a schedule (e.g., every hour) using cron or a similar task scheduler.

**Cronjob setup (Linux/macOS):**

1. Run crontab \-e  
2. Add this line to run the script every hour. Make sure to use the **full path** to your python executable and script.

\# Run the Fame Flywheel Collector every hour  
0 \* \* \* \* /usr/bin/python3 /path/to/your/project/feedback.py \>\> /path/to/your/project/feedback.log 2\>&1

**You have now completed the loop.** The Collector will add data, and the next time you run brain.py, its "Exploit" decision will be smarter.