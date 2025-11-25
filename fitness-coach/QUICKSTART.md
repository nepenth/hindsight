# 🚀 AI Fitness Coach - Quick Start

Your AI fitness coach is ready! Here's how to start using it.

## ✅ What's Done

1. **Fitness coach agent created** with supportive personality traits
2. **Workout logging** script ready
3. **Meal logging** script ready
4. **Coach chat interface** ready
5. **Demo script** to see everything in action

## 🎯 Quick Test (5 minutes)

### Step 1: Log a Workout

```bash
cd fitness-coach

# Quick command-line log
python log_workout.py strength 45 squats deadlifts "bench press"

# Or interactive mode
python log_workout.py
```

### Step 2: Log a Meal

```bash
# Quick command-line log
python log_meal.py lunch "chicken breast" "brown rice" broccoli

# Or interactive mode
python log_meal.py
```

### Step 3: Chat with Your Coach

```bash
# Ask a question
python coach_chat.py "What have I been doing for exercise?"

# Or start interactive chat
python coach_chat.py
```

## 🎬 Full Demo

Run the complete demo to see all features:

```bash
python demo.py
```

**Demo Options:**

When you run the demo, you'll be asked to choose:
- **`already`** - You've already imported Strava data, skip import
- **`import`** - Import your real running data now (last 90 days)
- **`no`** - Use sample workout and meal data

The demo will:
1. Set a fitness goal (running-specific if using Strava data)
2. Optionally import your Strava running history (or skip if already done)
3. Log sample nutrition data
4. Ask the coach personalized questions including temporal comparisons
5. Show how the coach analyzes your training and provides insights

**Note:** If you choose `import`, you'll need credentials set:
```bash
export STRAVA_CLIENT_ID=your_id
export STRAVA_CLIENT_SECRET=your_secret
```

**Tip:** If you've already imported Strava data, choose `already` to save time!

## 📂 Files Created

All files are in `/fitness-coach/`:

- `setup_coach.py` - Creates the fitness coach agent ✅ (already run)
- `log_goal.py` - Set fitness goals
- `log_workout.py` - Log workouts
- `log_meal.py` - Log meals
- `coach_chat.py` - Chat with your coach
- `demo.py` - Complete demo with sample data
- `README.md` - Full documentation

## 🔥 Example Commands

**Set a goal:**
```bash
python log_goal.py "Run a 5K in under 25 minutes"
python log_goal.py "Increase bench press to 225 lbs by June"
python log_goal.py "Lose 15 pounds"
```

**Ask your coach:**
```bash
python coach_chat.py "What workouts did I do this week?"
python coach_chat.py "How is my nutrition?"
python coach_chat.py "Should I take a rest day?"
python coach_chat.py "What should I focus on to achieve my goal?"
python coach_chat.py "How has my training changed over time?"
python coach_chat.py "Am I getting enough protein?"
```

## 🎨 How It Works

1. **Log Data**: Workouts and meals are stored as "world facts" with timestamps
2. **Memory System**: Entity linking, temporal queries, semantic search
3. **Coach Thinks**: Uses the `/think` API to retrieve relevant history
4. **Personalized Advice**: Based on your actual data + coach personality
5. **Opinion Formation**: Coach forms beliefs about your habits (confidence scores)

## 💡 Tips

- Log consistently for best results
- Be specific with exercise names and foods
- Ask questions about trends and progress
- The coach learns from your interactions

## 🏗️ System Status

- ✅ API running at http://localhost:8080
- ✅ PostgreSQL running at localhost:5432
- ✅ Fitness coach agent created
- ✅ All scripts tested and ready

## 📖 Need More Help?

See `README.md` for full documentation including:
- Architecture details
- All command-line options
- More example interactions
- How the memory system works

---

**Ready to start? Run the demo:**

```bash
python demo.py
```

Or jump right in:

```bash
python log_workout.py  # Log your first workout!
```
