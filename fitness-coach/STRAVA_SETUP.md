# 🏃 Strava Integration Setup

Import all your Strava workout history into your AI Fitness Coach!

## Prerequisites

- Strava account with activity history
- Python 3.11+
- Fitness coach agent already created

## Quick Start (5 minutes)

### Step 1: Get Strava API Credentials

1. Go to https://www.strava.com/settings/api
2. Create a new application (if you don't have one):
   - **Application Name**: "My Fitness Coach" (or anything)
   - **Category**: Personal
   - **Website**: http://localhost (can be anything)
   - **Authorization Callback Domain**: localhost
3. Copy your **Client ID** and **Client Secret**

### Step 2: Set Environment Variables

**On Mac/Linux:**
```bash
export STRAVA_CLIENT_ID=your_client_id_here
export STRAVA_CLIENT_SECRET=your_client_secret_here
```

**On Windows (PowerShell):**
```powershell
$env:STRAVA_CLIENT_ID="your_client_id_here"
$env:STRAVA_CLIENT_SECRET="your_client_secret_here"
```

**Or edit the script directly:**
Open `import_strava.py` and set:
```python
STRAVA_CLIENT_ID = "your_client_id_here"
STRAVA_CLIENT_SECRET = "your_client_secret_here"
```

### Step 3: Run the Import

**Import ALL activities:**
```bash
python import_strava.py
```

**Import from specific date:**
```bash
python import_strava.py --after 2024-01-01
```

**Import last 30 days:**
```bash
python import_strava.py --days 30
```

**Import specific number of activities:**
```bash
python import_strava.py --limit 100
```

**Dry run (test without uploading):**
```bash
python import_strava.py --dry-run
```

### Step 4: Authenticate with Strava

The script will:
1. Open your browser for Strava authorization
2. Ask you to authorize "My Fitness Coach" to read your activities
3. Redirect to a URL with an authorization code
4. Paste the full redirect URL back into the terminal

**Example redirect URL:**
```
http://localhost:8000/?code=abc123xyz&scope=read,activity:read_all
```

Just copy-paste the entire URL!

### Step 5: Watch the Import

The script will:
1. ✅ Authenticate with Strava
2. 📥 Fetch all your activities (with progress updates)
3. 📊 Show a summary of what will be imported
4. 🔄 Transform activities to workout format
5. ❓ Ask for confirmation
6. 📤 Upload to your fitness coach in batches

**Sample output:**
```
📊 Summary:
   Total Activities: 245
   Total Distance: 1,523.4 km
   Total Time: 78.2 hours
   Total Elevation: 12,450 m
   Date Range: 2023-01-05 to 2024-11-24

   Activity Types:
     Run: 156
     Ride: 67
     Swim: 15
     Yoga: 7
```

## What Gets Imported

For each Strava activity, the coach will learn:

- **Activity type** (run, ride, swim, etc.)
- **Distance and duration**
- **Pace/speed** (calculated)
- **Elevation gain**
- **Heart rate** (if available)
- **Intensity** (calculated from HR or pace)
- **Date and time**
- **Workout type** (race, long run, intervals, etc.)

**Example memory created:**
> User completed run: 10.52km in 52m at 4:56/km pace with 150m elevation gain, avg HR 155bpm.

## After Import

Your fitness coach now has your complete training history!

**Try these queries:**
```bash
# Temporal queries
python coach_chat.py "What did I run last spring?"
python coach_chat.py "Show me my cycling from June to August"

# Pattern analysis
python coach_chat.py "How has my 5k pace improved this year?"
python coach_chat.py "What's my typical weekly mileage?"

# Training insights
python coach_chat.py "Based on my history, what should I focus on?"
python coach_chat.py "Am I running too much?"
python coach_chat.py "When was my last rest day?"
```

## Re-importing / Updates

**The import is idempotent** - you can run it multiple times safely. However, it will create duplicate memories.

**For continuous sync**, you have options:

### Option 1: Manual Periodic Import
Run with `--days 7` weekly to import new activities:
```bash
python import_strava.py --days 7
```

### Option 2: Scheduled Import (Advanced)
Create a cron job or scheduled task:
```bash
# Run daily at 6 AM
0 6 * * * cd /path/to/fitness-coach && python import_strava.py --days 1
```

### Option 3: Webhook (Future Enhancement)
Strava supports webhooks for real-time activity sync - this could be added as a future feature.

## Troubleshooting

### "No module named 'strava_client'"
Make sure you're running from the `fitness-coach` directory:
```bash
cd fitness-coach
python import_strava.py
```

### "Strava credentials not found"
Set the environment variables or edit the script directly (see Step 2).

### "Authentication failed"
- Check your Client ID and Client Secret are correct
- Make sure you authorized the app in your browser
- Try deleting `.strava_tokens.json` and re-authenticating

### "Token expired"
The script automatically refreshes tokens. If it fails:
```bash
rm .strava_tokens.json
python import_strava.py
```

### "Rate limit exceeded"
Strava allows 100 requests per 15 minutes. The script includes delays to respect this. If you hit the limit, wait 15 minutes and resume.

### API returns 500 error
Check the API logs:
```bash
docker logs memora-api --tail 50
```

Common issues:
- API not running (`docker ps`)
- OpenAI API key not set
- Database connection issue

## Privacy & Security

- **Tokens stored locally**: `.strava_tokens.json` (in `.gitignore`)
- **Read-only access**: Only reads activities, cannot modify or delete
- **Your data stays local**: Imported to your local fitness coach instance
- **Revoke access anytime**: https://www.strava.com/settings/apps

## Advanced Usage

### Custom Date Ranges

Import specific year:
```bash
python import_strava.py --after 2024-01-01 --dry-run
# Check the summary, then run without --dry-run
```

### Selective Import

Edit `strava_transformer.py` to filter activities:
```python
# Only import runs
if activity.get("type") != "Run":
    return None
```

### Custom Transformations

Modify `transform_activity()` in `strava_transformer.py` to:
- Change intensity calculation
- Add custom notes
- Extract different metrics
- Format descriptions differently

## Files Created

- `strava_client.py` - Strava API authentication and requests
- `strava_transformer.py` - Convert Strava → workout format
- `import_strava.py` - Main import script
- `.strava_tokens.json` - OAuth tokens (auto-generated, gitignored)
- `STRAVA_SETUP.md` - This file

## Next Steps

Once imported, explore your data:

1. **Visualize**: Open http://localhost:3000 to see the memory graph
2. **Chat**: Use `coach_chat.py` to ask questions about your training
3. **Log new workouts**: Continue logging manually or re-run import periodically
4. **Set goals**: Log your training goals as agent facts

Enjoy your AI fitness coach with years of training history! 🎉
