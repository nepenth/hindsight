# 🏋️ AI Fitness Coach

A personalized AI fitness coach that learns from your workouts and meals to provide customized advice and motivation.

## Features

- **🎯 Goal-Oriented Coaching**: Set goals and get personalized advice to achieve them
- **🏋️ Workout Tracking**: Log cardio, strength training, yoga, and custom workouts
- **🍽️ Meal Tracking**: Log meals with nutrition information
- **⏰ Temporal Queries**: Ask about progress over time ("How do I compare to last month?")
- **🤖 Personality-Driven**: Coach has personality traits (supportive, disciplined, motivating) that influence advice
- **📊 Smart Context**: Retrieves relevant history using semantic, keyword, graph, and temporal search

## Quick Start

### 1. Setup the Coach

First, create the fitness coach agent:

```bash
python setup_coach.py
```

This creates an AI coach with:
- High conscientiousness (disciplined, organized)
- High agreeableness (supportive, encouraging)
- Moderate-high extraversion (energetic, motivating)
- Low neuroticism (calm, stable)

### 2. Run the Demo

See everything in action:

```bash
python demo.py
```

**Choose your demo mode:**
- `already` - Use your previously imported Strava data
- `import` - Import Strava running data now (last 90 days)
- `no` - Use sample workout and meal data

The demo will:
1. Set a fitness goal
2. Use your real Strava data or log sample workouts
3. Log sample meals with nutrition info
4. Ask the coach personalized questions (running-focused if using Strava)
5. Show how the coach analyzes your training and provides insights

## Usage

### Set Goals

**Interactive mode:**
```bash
python log_goal.py
```

**Command-line:**
```bash
# Set a goal
python log_goal.py "Run a 5K in under 25 minutes"
python log_goal.py "Increase bench press to 225 lbs by June 2025"
python log_goal.py "Lose 15 pounds"
python log_goal.py "Complete a marathon"
```

### Log Workouts

**Interactive mode:**
```bash
python log_workout.py
```

**Command-line:**
```bash
# Cardio workout
python log_workout.py cardio 30 5  # 30 min, 5 km

# Strength training
python log_workout.py strength 45 squats deadlifts "bench press"

# Yoga
python log_workout.py yoga 30
```

### Log Meals

**Interactive mode:**
```bash
python log_meal.py
```

**Command-line:**
```bash
python log_meal.py breakfast oatmeal banana "protein shake"
python log_meal.py lunch "chicken breast" "brown rice" broccoli
python log_meal.py dinner salmon quinoa vegetables
```

### Chat with Your Coach

**Interactive mode:**
```bash
python coach_chat.py
```

**Single question:**
```bash
python coach_chat.py "Should I take a rest day tomorrow?"
python coach_chat.py "How is my nutrition?"
python coach_chat.py "What should I focus on this week?"
```

## 🏃 Strava Integration (NEW!)

Import your entire Strava workout history with one command!

```bash
# Get your Strava Client ID and Secret from: https://www.strava.com/settings/api
export STRAVA_CLIENT_ID=your_client_id
export STRAVA_CLIENT_SECRET=your_client_secret

# Import all activities
python import_strava.py

# Or import from specific date
python import_strava.py --after 2024-01-01

# Or import last 30 days
python import_strava.py --days 30
```

**What gets imported:**
- All runs, rides, swims, and other activities
- Distance, pace, heart rate, elevation
- Workout types (race, long run, intervals, etc.)
- Complete temporal history

**See [STRAVA_SETUP.md](STRAVA_SETUP.md) for detailed setup instructions.**

After import, your coach will know your entire training history and can answer questions like:
- "What did I run last spring?"
- "How has my 5k pace improved this year?"
- "What's my typical weekly mileage?"

## Example Questions to Ask

**General queries:**
- "What have I been doing for exercise?"
- "How is my nutrition looking?"
- "Should I take a rest day tomorrow?"
- "Am I getting enough protein?"

**Temporal comparisons:**
- "What workouts did I do last week?"
- "How has my performance been improving?"
- "How does this month compare to last month?"
- "How is my training intensity changing over time?"

**Goal-oriented:**
- "What should I focus on to achieve my goal?"
- "Am I on track to meet my 5K goal?"
- "What do I need to work on to get stronger?"

## How It Works

### Memory System

The coach uses a temporal-semantic memory system with three types of memories:

1. **World Facts**: Your actual workout and meal data
   - "User completed 30-minute cardio workout..."
   - "User ate chicken breast with brown rice..."

2. **Agent Facts**: Your goals and intentions
   - "User wants to build strength"
   - "User is training for a 5K"

3. **Opinions**: Coach's assessments and insights
   - "User is consistent with morning workouts [0.9]"
   - "User responds well to recovery guidance [0.7]"

### Personalization

The coach's advice is personalized based on:
- Your workout history (types, intensity, frequency)
- Your meal patterns (nutrition, timing)
- Temporal patterns (what you did last week/month)
- Formed opinions about your habits and progress
- The coach's personality traits

### Example Interaction

```
You: Should I take a rest day tomorrow?

🤔 Coach is thinking...

======================================================================
🏋️ COACH'S ADVICE
======================================================================

Based on your recent activity, I'd recommend taking a rest day tomorrow.
You've had 4 solid workout days this week including a high-intensity leg
day where you hit a new PR on squats - that's fantastic! Your body needs
time to recover and rebuild. Consider doing some light stretching or yoga
if you feel restless, but give those muscles a chance to adapt. Remember,
rest is when the real gains happen!

----------------------------------------------------------------------
📊 BASED ON:
----------------------------------------------------------------------

🌍 [WORLD]
   User completed 45-minute strength workout with high intensity.
   Exercises: squats, deadlifts, bench press. Notes: Leg day, hit new PR!
   📅 2025-01-20

🌍 [WORLD]
   User completed 30-minute cardio workout with moderate intensity.
   📅 2025-01-19

💭 [OPINION]
   User is very consistent with workout schedule [0.85]

======================================================================
```

## Architecture

Built on Memora's temporal-semantic memory system:
- Entity linking connects workouts to goals
- Temporal queries track progress over time
- Personality-driven opinion formation
- Multi-strategy retrieval (semantic + keyword + graph + temporal)

## Next Steps

1. **Set Goals**: Use `python log_goal.py "Your goal here"` to give your coach direction
2. **Track Progress**: Log measurements (weight, strength PRs, distances)
3. **Build History**: Consistent logging helps the coach learn your patterns
4. **Ask Questions**: The more you interact, the better the advice becomes
5. **Compare Over Time**: Ask temporal questions to track your improvement

## Tips

- **Set clear goals first** - Your coach tailors advice to your objectives
- Log workouts and meals consistently for best results
- Be specific with exercise names and food details
- **Ask temporal questions** - Compare time periods to track progress
- Use goal-oriented questions ("What should I focus on to achieve my goal?")
- Let the coach form opinions by using the chat regularly
