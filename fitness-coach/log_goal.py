#!/usr/bin/env python3
"""
Log fitness goals for the AI Fitness Coach.

Goals are stored as agent facts - things the user wants to achieve.
"""
import requests
import sys
from datetime import datetime

API_URL = "http://localhost:8080/api/v1"
AGENT_ID = "fitness-coach"


def log_goal(goal_description, target_date=None):
    """
    Log a fitness goal.

    Args:
        goal_description: Description of the goal
        target_date: Optional target date for achieving the goal
    """
    # Build the goal content
    content = f"User's fitness goal: {goal_description}"
    if target_date:
        content += f". Target date: {target_date}"

    # Prepare payload
    timestamp = datetime.now().isoformat()

    payload = {
        "agent_id": AGENT_ID,
        "items": [{
            "content": content,
            "context": "goal",
            "event_date": timestamp,
            "memory_type": "agent"  # Goals are agent facts (user's intentions)
        }]
    }

    # Post to API
    try:
        response = requests.post(
            f"{API_URL}/agents/{AGENT_ID}/memories",
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            print(f"✅ Goal logged: {goal_description}")
            if target_date:
                print(f"   Target: {target_date}")
            return True
        else:
            print(f"❌ Failed to log goal: {response.status_code}")
            print(response.text)
            return False

    except Exception as e:
        print(f"❌ Error logging goal: {e}")
        return False


def main():
    """Interactive goal logging."""
    print("\n🎯 FITNESS GOAL LOGGER")
    print("=" * 60)

    # Get goal description
    if len(sys.argv) > 1:
        # Command-line mode
        goal_description = " ".join(sys.argv[1:])
        target_date = None
    else:
        # Interactive mode
        print("\nWhat is your fitness goal?")
        print("Examples:")
        print("  • Run a 5K in under 25 minutes")
        print("  • Build muscle and gain 10 lbs")
        print("  • Lose 15 lbs")
        print("  • Complete a marathon")
        print("  • Do 20 pull-ups")

        goal_description = input("\nYour goal: ").strip()

        if not goal_description:
            print("❌ Goal description required")
            return

        # Optional target date
        print("\nTarget date? (YYYY-MM-DD or press Enter to skip)")
        target_date_input = input("Target date: ").strip()
        target_date = target_date_input if target_date_input else None

    # Log the goal
    log_goal(goal_description, target_date)

    print("\n💡 Your coach now knows your goal and will factor it into advice!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
