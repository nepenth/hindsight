#!/usr/bin/env python3
"""
Fitness Coach Demo
Demonstrates the complete AI Fitness Coach functionality with sample data.
"""
import time
import os
import sys
from log_workout import log_workout
from log_meal import log_meal
from log_goal import log_goal
from coach_chat import ask_coach, print_response
import requests

def import_strava_runs():
    """Import running activities from Strava."""
    print("\n🏃 STRAVA INTEGRATION")
    print("=" * 70)

    # Check for credentials
    client_id = os.getenv("STRAVA_CLIENT_ID")
    client_secret = os.getenv("STRAVA_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("\n⚠️  Strava credentials not found!")
        print("\nTo use Strava integration:")
        print("  1. Get credentials at: https://www.strava.com/settings/api")
        print("  2. Set environment variables:")
        print("     export STRAVA_CLIENT_ID=your_id")
        print("     export STRAVA_CLIENT_SECRET=your_secret")
        print("\nSkipping Strava import...")
        time.sleep(2)
        return False

    try:
        from strava_client import authenticate_strava
        from strava_transformer import transform_activities
        import requests

        print("\n📡 Connecting to Strava...")
        client = authenticate_strava(client_id, client_secret)

        print("\n📥 Fetching your running activities...")
        print("   (This may take a moment...)")

        # Fetch activities from last 90 days
        from datetime import datetime, timedelta
        after_date = datetime.now() - timedelta(days=90)
        activities = client.get_all_activities(after=after_date)

        # Filter to only runs
        runs = [a for a in activities if a.get("type") in ["Run", "VirtualRun"]]

        if not runs:
            print("\n⚠️  No running activities found in the last 90 days.")
            print("   Continuing with sample data...")
            return False

        print(f"\n✅ Found {len(runs)} running activities!")

        # Show summary
        total_distance = sum(r.get("distance", 0) for r in runs) / 1000
        print(f"   Total distance: {total_distance:.1f} km")

        # Transform and upload
        print("\n🔄 Importing runs to fitness coach...")
        workouts = transform_activities(runs)

        # Upload in batches
        API_URL = "http://localhost:8080/api/v1"
        AGENT_ID = "fitness-coach"

        for i in range(0, len(workouts), 20):
            batch = workouts[i:i+20]
            items = [{
                "content": w["content"],
                "context": f"workout-{w['workout_type']}",
                "event_date": w["event_date"]
            } for w in batch]

            response = requests.post(
                f"{API_URL}/agents/{AGENT_ID}/memories",
                json={"agent_id": AGENT_ID, "items": items},
                timeout=60
            )

            if response.status_code == 200:
                print(f"   ✅ Uploaded batch {i//20 + 1} ({len(batch)} runs)")
            time.sleep(0.5)

        print(f"\n✅ Successfully imported {len(runs)} runs from Strava!")
        return True

    except Exception as e:
        print(f"\n❌ Strava import failed: {e}")
        print("   Continuing with sample data...")
        return False


def demo():
    """Run a complete demo of the fitness coach."""

    print("\n" + "=" * 70)
    print("🏋️ AI FITNESS COACH DEMO")
    print("=" * 70)

    # Ask about Strava integration
    print("\n📊 SETUP OPTIONS")
    print("-" * 70)
    print("\nDo you have Strava running data?")
    print("  • Yes, already imported - Skip import, use existing Strava data")
    print("  • Yes, import now - Import your running history (last 90 days)")
    print("  • No - Use sample workout/meal data instead")

    strava_choice = input("\nChoice (already/import/no): ").strip().lower()

    strava_imported = False
    has_strava_data = False

    if strava_choice == 'already':
        print("\n✅ Using your existing Strava data")
        has_strava_data = True
        time.sleep(1)
    elif strava_choice == 'import':
        strava_imported = import_strava_runs()
        if strava_imported:
            has_strava_data = True
            time.sleep(2)
    else:
        print("\n📝 Using sample data for demo")
        time.sleep(1)

    # Continue with regular demo
    print("\n" + "=" * 70)
    print("🏋️ DEMO FLOW")
    print("=" * 70)

    if has_strava_data:
        print("\nThis demo will:")
        print("  1. Set a running goal")
        print("  2. Use your Strava running data")
        print("  3. Add sample nutrition data")
        print("  4. Ask the coach running-focused questions")
        print("  5. Show how the coach analyzes your training")
    else:
        print("\nThis demo will:")
        print("  1. Set a fitness goal")
        print("  2. Log sample workouts and meals")
        print("  3. Ask the coach personalized questions")
        print("  4. Show how the coach learns and forms opinions")

    print("\n" + "=" * 70 + "\n")
    input("Press Enter to start the demo...")

    # Step 0: Set a goal
    print("\n🎯 Step 0: Setting Fitness Goal...")
    print("-" * 70)

    if has_strava_data:
        # Running-specific goal
        goal = "Run a 5K in under 25 minutes by March 2025"
    else:
        # General fitness goal
        goal = "Build strength and improve overall fitness"

    log_goal(goal, "2025-03-31" if has_strava_data else None)

    print("\n✅ Goal set!")
    print(f"   🎯 {goal}\n")
    input("Press Enter to continue...")

    # Step 1: Log workouts (skip if using Strava data)
    if not has_strava_data:
        print("\n📝 Step 1: Logging Sample Workouts...")
        print("-" * 70)

        workouts = [
            ("cardio", 30, ["running"], "moderate", "Morning 5K run, felt good"),
            ("strength", 45, ["squats", "deadlifts", "bench press"], "high", "Leg day, hit new PR on squats!"),
            ("yoga", 30, ["sun salutations", "warrior poses"], "low", "Recovery day stretching"),
            ("cardio", 25, ["cycling"], "high", "HIIT cycling session"),
        ]

        for workout in workouts:
            workout_type, duration, exercises, intensity, notes = workout
            log_workout(workout_type, duration, exercises, intensity, notes)
            time.sleep(0.5)

        print("\n✅ Sample workouts logged!\n")
        input("Press Enter to continue...")
    else:
        print("\n✅ Step 1: Skipping sample workouts (using your Strava data)")
        print("-" * 70)
        time.sleep(1)

    # Step 2: Log meals (always do this - Strava doesn't have meal data)
    if not has_strava_data:
        print("\n📝 Step 2: Logging Sample Meals...")
    else:
        print("\n📝 Step 2: Adding Sample Nutrition Data...")

    print("-" * 70)

    meals = [
        ("breakfast", ["oatmeal", "banana", "protein shake"], 450, 35, 55, 12, "Post-workout breakfast"),
        ("lunch", ["chicken breast", "brown rice", "broccoli"], 550, 45, 60, 15, "Balanced lunch"),
        ("snack", ["apple", "almonds"], 200, 5, 25, 15, "Afternoon snack"),
        ("dinner", ["salmon", "quinoa", "mixed vegetables"], 600, 40, 50, 25, "Light dinner"),
    ]

    for meal in meals:
        meal_type, foods, calories, protein, carbs, fats, notes = meal
        log_meal(meal_type, foods, calories, protein, carbs, fats, notes)
        time.sleep(0.5)

    print("\n✅ Nutrition data logged!\n")
    input("Press Enter to continue...")

    # Step 3: Ask the coach questions
    print("\n💬 Step 3: Asking the Coach Questions...")
    print("-" * 70 + "\n")

    # Use different questions depending on whether we have Strava data
    if has_strava_data:
        questions = [
            "What does my running training look like recently?",
            "How do my runs this month compare to last month?",  # Temporal comparison
            "Based on my runs, should I take a rest day?",
            "What do you recommend I focus on to achieve my 5K goal?",
        ]
    else:
        questions = [
            "What have I been doing for exercise?",
            "How is my training intensity changing over time?",  # Temporal comparison
            "Should I take a rest day tomorrow?",
            "What should I focus on to achieve my fitness goal?",
        ]

    for i, question in enumerate(questions, 1):
        print(f"\n{'=' * 70}")
        print(f"QUESTION {i}/{len(questions)}")
        print(f"{'=' * 70}")
        print(f"\nYou: {question}")
        print("\n🤔 Coach is thinking...")

        result = ask_coach(question)
        if result:
            print_response(result)

        if i < len(questions):
            input("\nPress Enter for next question...")

    # Final message
    print("\n" + "=" * 70)
    print("✨ DEMO COMPLETE!")
    print("=" * 70)

    if has_strava_data:
        print("\nThe fitness coach now knows about:")
        print("  ✅ Your 5K running goal (sub-25 minutes by March 2025)")
        print("  ✅ Your actual running history from Strava")
        print("  ✅ Distances, paces, heart rates, elevation")
        print("  ✅ Temporal patterns in your training")
        print("  ✅ Sample nutrition data")
        print("  ✅ Personalized coaching insights")
        print("\nYou can now:")
        print("  • python coach_chat.py   - Ask about your real training data")
        print("  • python log_goal.py     - Set additional goals")
        print("  • python log_meal.py     - Log your actual meals")
        print("  • python import_strava.py --days 7  - Import new runs weekly")
    else:
        print("\nThe fitness coach now knows about your:")
        print("  ✅ Fitness goal (build strength and improve overall fitness)")
        print("  ✅ Workout history (types, duration, intensity)")
        print("  ✅ Meal history (foods, nutrition, timing)")
        print("  ✅ Progress patterns and habits")
        print("  ✅ Personalized coaching insights")
        print("\nYou can now use:")
        print("  • python log_goal.py     - Set new goals")
        print("  • python log_workout.py  - Log new workouts")
        print("  • python log_meal.py     - Log new meals")
        print("  • python coach_chat.py   - Chat with your coach")
        print("\n💡 Want to use real data? Run: python import_strava.py")

    print("\n" + "=" * 70 + "\n")

if __name__ == "__main__":
    try:
        demo()
    except KeyboardInterrupt:
        print("\n\n👋 Demo interrupted. Thanks for watching!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
