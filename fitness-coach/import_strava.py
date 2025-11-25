#!/usr/bin/env python3
"""
Import Strava activities into your AI Fitness Coach.

This script:
1. Authenticates with Strava
2. Fetches all your activities
3. Transforms them into workout format
4. Batch uploads to your fitness coach agent
"""
import requests
import os
import sys
import time
from datetime import datetime, timedelta
from strava_client import authenticate_strava
from strava_transformer import transform_activities, get_activity_summary

API_URL = "http://localhost:8080/api/v1"
AGENT_ID = "fitness-coach"

# Strava API credentials - set these as environment variables or edit here
STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")


def upload_workouts_batch(workouts, batch_size=50):
    """
    Upload workouts to fitness coach in batches.

    Args:
        workouts: List of workout dictionaries
        batch_size: Number of workouts per batch
    """
    total = len(workouts)
    uploaded = 0
    failed = 0

    print(f"\n📤 Uploading {total} workouts to fitness coach...")
    print("=" * 60)

    for i in range(0, total, batch_size):
        batch = workouts[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total + batch_size - 1) // batch_size

        print(f"\nBatch {batch_num}/{total_batches} ({len(batch)} workouts)...")

        # Prepare items for API
        items = [{
            "content": workout["content"],
            "context": f"workout-{workout['workout_type']}",
            "event_date": workout["event_date"]
        } for workout in batch]

        payload = {
            "agent_id": AGENT_ID,
            "items": items
        }

        try:
            response = requests.post(
                f"{API_URL}/agents/{AGENT_ID}/memories",
                json=payload,
                timeout=120  # Longer timeout for batch processing
            )

            if response.status_code == 200:
                uploaded += len(batch)
                print(f"  ✅ Uploaded {len(batch)} workouts")
            else:
                failed += len(batch)
                print(f"  ❌ Failed: {response.status_code}")
                print(f"     {response.text[:200]}")

        except Exception as e:
            failed += len(batch)
            print(f"  ❌ Error: {e}")

        # Rate limiting - be nice to your API
        if i + batch_size < total:
            time.sleep(1)

    print("\n" + "=" * 60)
    print(f"✅ Upload complete!")
    print(f"   Uploaded: {uploaded}")
    print(f"   Failed: {failed}")
    print(f"   Total: {total}")


def import_strava_activities(
    after_date=None,
    limit=None,
    dry_run=False
):
    """
    Import activities from Strava.

    Args:
        after_date: Only import activities after this date (datetime)
        limit: Maximum number of activities to import
        dry_run: If True, fetch and transform but don't upload
    """
    print("\n" + "=" * 60)
    print("🏃 STRAVA ACTIVITY IMPORTER")
    print("=" * 60)

    # Check credentials
    if not STRAVA_CLIENT_ID or not STRAVA_CLIENT_SECRET:
        print("\n❌ Error: Strava credentials not found!")
        print("\nPlease set environment variables:")
        print("  export STRAVA_CLIENT_ID=your_client_id")
        print("  export STRAVA_CLIENT_SECRET=your_client_secret")
        print("\nOr edit the script and set them directly.")
        print("\nGet credentials at: https://www.strava.com/settings/api")
        sys.exit(1)

    # Authenticate with Strava
    print("\n📡 Connecting to Strava...")
    try:
        client = authenticate_strava(STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET)
    except Exception as e:
        print(f"\n❌ Authentication failed: {e}")
        sys.exit(1)

    # Fetch activities
    print(f"\n📥 Fetching activities from Strava...")
    if after_date:
        print(f"   After: {after_date.strftime('%Y-%m-%d')}")

    def progress(msg):
        print(f"   {msg}")

    try:
        activities = client.get_all_activities(
            after=after_date,
            progress_callback=progress
        )
    except Exception as e:
        print(f"\n❌ Failed to fetch activities: {e}")
        sys.exit(1)

    if not activities:
        print("\n⚠️  No activities found!")
        return

    # Apply limit if specified
    if limit and len(activities) > limit:
        print(f"\n⚠️  Limiting to {limit} most recent activities")
        activities = activities[:limit]

    # Show summary
    print(f"\n✅ Fetched {len(activities)} activities")
    summary = get_activity_summary(activities)

    print("\n📊 Summary:")
    print("-" * 60)
    print(f"   Total Activities: {summary['total_activities']}")
    print(f"   Total Distance: {summary['total_distance_km']} km")
    print(f"   Total Time: {summary['total_time_hours']} hours")
    print(f"   Total Elevation: {summary['total_elevation_m']} m")
    print(f"   Date Range: {summary['date_range']['oldest']} to {summary['date_range']['newest']}")
    print("\n   Activity Types:")
    for activity_type, count in sorted(summary['activity_types'].items(), key=lambda x: -x[1]):
        print(f"     {activity_type}: {count}")

    # Transform activities
    print("\n🔄 Transforming activities to workout format...")
    workouts = transform_activities(activities)
    print(f"   ✅ Transformed {len(workouts)} activities")

    # Show sample
    if workouts:
        print("\n📝 Sample workout:")
        print("-" * 60)
        sample = workouts[0]
        print(f"   Type: {sample['workout_type']}")
        print(f"   Duration: {sample['duration_minutes']} min")
        print(f"   Intensity: {sample['intensity']}")
        print(f"   Description: {sample['content'][:100]}...")

    # Upload to fitness coach
    if dry_run:
        print("\n🔍 DRY RUN - Not uploading to fitness coach")
        print("   Remove --dry-run flag to actually import")
    else:
        confirm = input("\n❓ Upload these workouts to your fitness coach? (y/n): ").strip().lower()

        if confirm == 'y':
            upload_workouts_batch(workouts)

            print("\n" + "=" * 60)
            print("✨ Import complete!")
            print("\nYour fitness coach now has access to your Strava history!")
            print("\nTry asking:")
            print("  python coach_chat.py \"What have my runs looked like this year?\"")
            print("  python coach_chat.py \"How has my cycling improved?\"")
            print("  python coach_chat.py \"What did I do last month?\"")
        else:
            print("\n❌ Import cancelled")


def main():
    """Main entry point with CLI argument parsing."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Import Strava activities to AI Fitness Coach"
    )

    parser.add_argument(
        "--after",
        type=str,
        help="Import activities after this date (YYYY-MM-DD)",
        default=None
    )

    parser.add_argument(
        "--days",
        type=int,
        help="Import activities from last N days",
        default=None
    )

    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of activities to import",
        default=None
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and transform but don't upload"
    )

    args = parser.parse_args()

    # Parse date arguments
    after_date = None
    if args.after:
        after_date = datetime.strptime(args.after, "%Y-%m-%d")
    elif args.days:
        after_date = datetime.now() - timedelta(days=args.days)

    # Run import
    import_strava_activities(
        after_date=after_date,
        limit=args.limit,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()
